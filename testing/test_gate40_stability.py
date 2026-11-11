from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import registry_snapshot_server as m


class Gate40Stability(TestCase):
    def test_joined_wv_name_replays_without_expanding_the_query_cap(self):
        name = 'Navy-Marine Corps Relief Society'
        joined = 'NavyMarine Corps Relief Society'
        org = m.checker.Organization(name, '530204618')
        detail = ('CHARITIES INFORMATION\nID:\n4404\nInitial Registration Date:\n10/14/2003\n'
                  'Organization Name:\nNavyMarine Corps Relief Society\nExpiration Date:\n10/14/2026\n'
                  'Status:\nActive\nStreet Address:\n875 N Randolph Street, Arlington, VA 22203\nCounty:\n')
        class Source:
            def __init__(self, name, detail):
                self.searched = []
                self.name = name
                self.body = detail
            def search(self, query):
                self.searched.append(query)
                if query != joined:
                    return 'No records found', []
                return 'Records found', [{'target':4404,'count':5,'values':['4404',self.name,'Active']}]
            def detail(self, row, credential):
                assert (row, credential) == (4404, '4404')
                return self.body
        with patch.object(m,'known_names_for_ein',return_value=[]), patch.object(
                m,'reconciled_registry_address',return_value={'decision':'corroborated'}):
            plan=m.wv_preferred_query_variants(name, org.ein, limit=6)
            self.assertEqual(plan[:2], [name, joined])
            self.assertLessEqual(len(plan),6)
            self.assertFalse(m.wv_core_search_completed([name,'Navy Marine Corps Relief Society'],plan,joined_query=joined))
            source=Source(joined,detail)
            good=m.search_wv_precise(None,org,public_lookup=source)
            self.assertTrue(good.success,good.raw_status_text)
            self.assertEqual(good.matched_registry_identifier,'4404')
            self.assertIn('Status: Active | Expiration Date: 10/14/2026',good.raw_status_text)
            with patch.object(m,'reconciled_registry_address',return_value={'decision':'conflict'}):
                review=m.search_wv_precise(None,org,public_lookup=Source(joined,detail))
                self.assertEqual(review.reason_code,'WV_JOINED_NAME_IDENTITY_UNCONFIRMED')
            wrong=m.search_wv_precise(None,org,public_lookup=Source(joined,detail.replace('4404','9999')))
            self.assertFalse(wrong.success)
            self.assertNotEqual(wrong.matched_registry_identifier,'4404')
            affiliate=m.search_wv_precise(None,org,public_lookup=Source(joined+' Local Chapter',detail))
            self.assertNotEqual(affiliate.matched_registry_identifier,'4404')
        self.assertFalse(m.wv_joined_hyphen_variant('National Relief Society - Local Chapter'))

    def test_ca_reporting_status_does_not_determine_compliance(self):
        entity = {'entityStatus': 'Listed'}
        registration = {'registrationNumber': '4404', 'registrationType': 'Charitable Organization',
                        'registrationStatus': 'Registered'}
        for reporting in ('Current', 'Due', 'In Review', 'Pending', 'Past Due'):
            for expiry, expected in (('2025-01-01', 'Delinquent'), ('2099-01-01', 'Current')):
                with self.subTest(reporting=reporting, expiry=expiry):
                    source = {**registration, 'reportingStatus': reporting, 'currentExpirationDate': expiry}
                    status, raw, *_ = m.checker.ca_evoke_status_from_record(entity, [source])
                    result = m.checker.StateResult('Example Charity', '123456789', 'CA', status, '')
                    result.raw_status_text = raw
                    self.assertIn(f'Reporting Status: {reporting}', raw)
                    self.assertEqual(m.true_status_from_body(result, ''), expected)
        source = {**registration, 'registrationStatus': 'Pending', 'reportingStatus': 'In Review'}
        status, raw, *_ = m.checker.ca_evoke_status_from_record(entity, [source])
        result = m.checker.StateResult('Example Charity', '123456789', 'CA', status, '')
        result.raw_status_text = raw
        self.assertEqual(m.ca_explicit_primary_registry_status(result), 'Pending')

    def test_mn_active_charity_granted_uses_published_extension_only(self):
        detail='Organization Type\tCHARITY\nStatus\tActive\nExtension\tGranted\nFinancial Information'
        with patch.object(m,'status_from_calendar_date',return_value='Upcoming Filing') as calendar:
            r=SimpleNamespace(state='MN',raw_status_text='Fiscal Year Ending 12/31/2024')
            self.assertTrue(m.apply_mn_confirmed_charity_extension(r,detail,date(2024,12,31)))
            calendar.assert_called_once_with(date(2026,11,15))
            self.assertEqual(m.true_status_from_body(r,''),'Upcoming Filing')
        for text in (detail.replace('Active','Inactive'),detail.replace('Granted','Requested'),
                     detail.replace('CHARITY','TRUST'),detail.replace('Extension','Historical Extension')):
            self.assertFalse(m.apply_mn_confirmed_charity_extension(SimpleNamespace(),text,date(2024,12,31)))
