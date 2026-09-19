"""Approved September 13 corrections, tested through final master responses."""
import copy
import sys
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class Today(date):
    @classmethod
    def today(cls): return cls(2026, 9, 13)


class Revisions(unittest.TestCase):
    name = 'American Farrier’s Association Foundation Inc.'
    ein = '87-2999231'
    href = 'CredSummaryDetails.aspx?chid=945248&h=764579286'

    def setUp(self):
        for p in (patch.object(c, 'date', Today),
                  patch.object(c, 'public_profile_for_ein', return_value={}),
                  patch.object(c.urllib.request, 'urlopen', side_effect=AssertionError('Unexpected network'))):
            p.start(); self.addCleanup(p.stop)

    def final(self, result, org):
        return c.response_data_for_lookup(result, '', org, org.organization_name, org.ein, result.state, time.perf_counter())

    def ma(self, period='12/31/2024', status='Not Doing Business in Mass', empty=False, visible=''):
        org = c.checker.Organization(self.name, self.ein)
        result = c.checker.StateResult(self.name, self.ein, 'MA', 'Current', 'https://masscharities.my.site.com/FilingSearch/s/')
        result.matched_registry_name = self.name; result.success = True
        page = Mock(); page.get_by_role.return_value.all_inner_texts.return_value = []
        completed = {'record': {'ago_account':'069404', 'registry_status':status},
                     'filings': {'069404': {'empty':empty}}}
        filing = {'period_end':period,'filing_status':'Submitted','ago_account':'069404'} if period else {}
        with patch.object(c, 'ma_read_legacy_form_pc', return_value=filing):
            evidence = c.ma_read_latest_form_pc(page, result, 'AG Account Number 069404 ' + visible, completed)
        c.annotate_ma_visible_form_pc_due(result, evidence)
        return self.final(result, org)

    def test_ma_non_operating_phrase_uses_confirmed_submitted_period(self):
        data = self.ma()
        self.assertEqual(data['status'], 'Upcoming Filing')
        self.assertEqual(data['computed_due_date'], '11/15/2026')
        self.assertIn('Not Doing Business in Mass', data['comments'])
        self.assertIn('inferred', data['comments'])
        self.assertNotIn('groups this inactive status', data['comments'])

    def test_ma_calendar_is_calculated_and_never_a_fixed_status(self):
        for period, expected in [('12/31/2023','Delinquent'), ('12/31/2025','Current')]:
            with self.subTest(period=period): self.assertEqual(self.ma(period)['status'], expected)

    def test_ma_non_operating_phrase_uses_confirmed_empty_annuals(self):
        self.assertEqual(self.ma('', empty=True)['status'], 'Delinquent')
        data = self.ma('')
        self.assertEqual(data['status'], 'Unable to Confirm')
        self.assertIn('Not Doing Business in Mass', data['comments'])

    def test_ma_empty_history_and_explicit_adverse_controls(self):
        self.assertEqual(self.ma('', status='', empty=True)['status'], 'Delinquent')
        for value, expected in [('Suspended','Suspended'), ('Revoked','Revoked'), ('Closed','Closed / Withdrawn / Canceled'), ('Withdrawn','Closed / Withdrawn / Canceled')]:
            with self.subTest(value=value): self.assertEqual(self.ma(visible='Registration Status: '+value)['status'], expected)

    def va(self, ein='471614315', registrations=None, fallback=False, error=False):
        org = c.checker.Organization('Al-Ayn Social Care Foundation', '47-1614315')
        entity = {'id':'74671','name':org.organization_name,'ein':ein,'status':'Not Authorized to Solicit'}
        with patch.object(c, 'va_evoke_entity_search_by_ein', return_value=[] if fallback else [entity]), \
             patch.object(c, 'va_evoke_entity_search_by_name', return_value=[entity]), \
             patch.object(c, 'va_evoke_registrations_for_entity_with_retry', return_value=(None,['timeout']) if error else (registrations or [],[])):
            return self.final(c.search_va_evoke_api(org), org)

    def test_va_explicit_restriction_with_exact_ein_and_completed_empty_history(self):
        data = self.va()
        self.assertEqual(data['status'], 'Suspended'); self.assertTrue(data['success'])
        self.assertEqual(data['va_entity_evidence']['entity_id'], '74671')
        self.assertIn('Not Authorized to Solicit', data['comments'])
        self.assertIn('no registration entries', data['comments'])
        self.assertIn('does not establish', data['comments'])

    def test_va_no_new_override_on_wrong_missing_or_name_only_identity(self):
        for ein, fallback in [('987654321',False), ('',False), ('471614315',True)]:
            with self.subTest(ein=ein, fallback=fallback): self.assertEqual(self.va(ein, fallback=fallback)['status'], 'Unable to Confirm')

    def test_va_incomplete_history_is_not_completed_empty_history(self):
        data = self.va(error=True)
        self.assertEqual(data['status'], 'Site Not Reachable')
        self.assertEqual(data['reason_code'], 'VA_REGISTRATION_DETAIL_FETCH_FAILED')

    def test_va_expired_registration_control_remains_delinquent(self):
        data = self.va(registrations=[{'id':'1','status':{'name':'Expired'},'expirationDate':'2025-05-15','registrationType':{'name':'Charitable'}}])
        self.assertEqual(data['status'], 'Delinquent')

    def wi(self, *, ein=None, name=None, license='23067-800', href=None, primary='AMERICAN FARRIERS ASSOCIATION INC', detail_number='23067-800', detail_status='License is not current (Voluntary surrender)', detail_missing=False, expiration='7/31/2025'):
        org = c.checker.Organization(name or self.name, self.ein if ein is None else ein)
        candidate = c.wi_foundation_identity_review('AMERICAN FARRIERS ASSOCIATION INC', org.organization_name, license, href or self.href, expiration)
        self.assertIsNotNone(candidate)
        text = '' if detail_missing else f'Name: {primary}\nCredential Type: Charitable Organization\nCredential Number: {detail_number}\nStatus {detail_status}\n'
        evidence = {'requested_ein':'872999231', 'credential':'23067-800',
                    'registry_name':'AMERICAN FARRIERS ASSOCIATION INC',
                    'detail_url':c.urljoin(c.WI_SEARCH_URL,self.href), 'fiscal_year':'2022', 'tax_period':'202212',
                    'matched_amounts':{'totcntrbs':131315,'totrevenue':130869,'totfuncexpns':9816,
                                      'totnetassetsend':122273,'othrchgsnetassetfnd':1220}}
        with patch.object(c, 'wi_http_search_best_match', return_value=(copy.deepcopy(candidate), True)), \
             patch.object(c, 'wi_confirm_cross_state_credential', side_effect=c.wi_confirm_reviewed_credential), \
             patch.object(c, 'wi_foundation_filing_identity', return_value=evidence), \
             patch.object(c, 'wi_identity_page', return_value=text):
            # Inject the previously retrieved proof for these legacy response/
            # status controls. New live lookups use cross-state identity; their
            # no-financial-read contract is covered in wi_cross_state tests.
            return self.final(c.search_wi(None, org), org)

    def test_wi_reviewed_credential_uses_current_public_status(self):
        for raw, expected in [('License is not current (Voluntary surrender)','Closed / Withdrawn / Canceled'), ('License is not current (Suspended)','Suspended'), ('License is not current (Revoked)','Revoked')]:
            with self.subTest(raw=raw):
                data = self.wi(detail_status=raw)
                self.assertEqual(data['status'], expected)
                self.assertTrue(data['success'])
                self.assertEqual(data['matched_registry_identifier'], '23067-800')
                self.assertIn('corroborated', data['comments'].lower())
                self.assertIn('2022', data['comments'])
                self.assertIn('does not display an EIN', data['comments'])

    def test_wi_review_cannot_cross_ein_credential_url_or_primary_name(self):
        controls = [{'ein':'61-1424719'}, {'ein':''}, {'license':'99999-800'}, {'href':'CredSummaryDetails.aspx?chid=1'},
                    {'href':'https://example.org/CredSummaryDetails.aspx?chid=945248'},
                    {'primary':'AMERICAN FARRIERS ASSOCIATION FOUNDATION INC'}, {'detail_number':'99999-800'}, {'detail_missing':True}]
        for kwargs in controls:
            with self.subTest(kwargs=kwargs): self.assertEqual(self.wi(**kwargs)['status'], 'Needs Review')

    def test_wi_reviewed_identity_does_not_freeze_surrender_status(self):
        self.assertEqual(self.wi(detail_status='License is current (Active)', expiration='7/31/2028')['status'], 'Current')

    def test_foundation_is_not_globally_discarded(self):
        for requested, candidate in [(self.name,'AMERICAN FARRIERS ASSOCIATION INC'),
                                      ('Air Force Academy Foundation','AIR FORCE ACADEMY ATHLETIC CORPORATION'),
                                      ('National Marrow Donor Program','National Marrow Donor Program Foundation')]:
            self.assertNotEqual(c.score_candidate(requested, '', {'name':candidate})['decision'], 'accepted')


if __name__ == '__main__': unittest.main(verbosity=2)
