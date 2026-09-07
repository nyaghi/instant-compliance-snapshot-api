"""State-specific NMDP regressions; offline test tooling, never runtime routing."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc


class AsOfDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 7)


class StateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(cc, 'date', AsOfDate)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_alaska_cycle_rolls_in_july_not_january_or_september(self):
        for day, expected in ((date(2026, 6, 30), 2026), (date(2026, 7, 1), 2027),
                              (date(2026, 9, 1), 2027), (date(2027, 1, 1), 2027)):
            self.assertEqual(cc.ak_latest_registration_cycle(day), expected)

    def test_alaska_confirmed_cycle_is_not_financial_year_plus_one(self):
        for cycle, status in ((2027, 'Current'), (2026, 'Delinquent')):
            r = cc.checker.StateResult('Fixture', '123456789', 'AK', '', '')
            cc.apply_ak_registration_status_from_best_evidence(r, None, None, {}, 'Fixture', cycle,
                                                              last_year_on_record=cycle)
            self.assertEqual(r.status, status)
            self.assertIn(f'Next Filing Due: 9/1/{cycle}', r.raw_status_text)
            self.assertNotIn('following year', cc.comments_for_result(r, '', r.status))

    def test_alaska_pdf_header_outweighs_old_financial_period(self):
        r = cc.checker.StateResult('Fixture', '123456789', 'AK', '', '')
        with patch.object(cc, 'fetch_ak_registration_pdf', return_value=(
                '2027 Charitable Organization Registration and Renewal Accounting end date 12/31/2024', '')):
            cc.apply_ak_registration_status_from_best_evidence(r, None, None, {}, 'Fixture', 2027)
        self.assertEqual(r.status, 'Current')
        self.assertIn('9/1/2027', r.raw_status_text)

    def test_nm_granted_noncalendar_cycle_uses_actual_period(self):
        module = cc.load_wa_nm_module()
        rows = [(2024, 'Extension Granted', '2/18/2026'), (2024, 'Extension Requested', '2/18/2026'),
                (2024, 'Tax Year Registration Open', '10/1/2025'),
                (2023, 'Registration Submitted 20234222534939375', '12/15/2025')]
        r = module.SearchResult('Fixture', '123456789', 'NM', module.STATUS_UNKNOWN, '', '', '')
        r = cc.nm_apply_status_history_master(module, r, rows, '09/30/2024')
        self.assertEqual(r.status, 'Upcoming Filing')
        self.assertIn('FYE: 09/30/2025', r.raw_status_text)
        self.assertIn('Due: 09/30/2026', r.raw_status_text)
        self.assertEqual(cc.classify_nm_status_history(r.raw_status_text), 'Upcoming Filing')

    def test_nm_official_month_end_examples_and_extension(self):
        for fye, regular, extended in ((date(2024, 6, 30), date(2024, 12, 31), date(2025, 6, 30)),
                                      (date(2024, 12, 31), date(2025, 6, 30), date(2025, 12, 31)),
                                      (date(2025, 9, 30), date(2026, 3, 31), date(2026, 9, 30))):
            self.assertEqual(cc.nm_due_date_from_fye_master(fye, False), regular)
            self.assertEqual(cc.nm_due_date_from_fye_master(fye, True), extended)

    def test_va_expired_restriction_is_not_formal_suspension(self):
        reg = {'status': {'name': 'Expired/Lapsed'}, 'expirationDate': '2/15/2024',
               'extensionDate': '8/15/2024', 'registrationNumber': '660607'}
        status, raw, _, _ = cc.va_evoke_status_from_entity_and_registrations(
            {'status': 'Not Authorized to Solicit'}, [reg])
        self.assertEqual(status, 'Delinquent')
        r = cc.checker.StateResult('Fixture', '123456789', 'VA', status, '')
        r.raw_status_text = raw
        self.assertEqual(cc.true_status_from_body(r, raw), 'Delinquent')
        self.assertIn('Not Authorized to Solicit', cc.comments_for_result(r, '', status))
        for explicit in ('Suspended', 'Not Authorized to Solicit; Suspended'):
            self.assertEqual(cc.va_evoke_status_from_entity_and_registrations({'status': explicit}, [reg])[0], 'Suspended')

    def test_va_other_restrictions_cannot_become_current(self):
        reg = {'status': {'name': 'Registered'}, 'expirationDate': '2/15/2028'}
        self.assertEqual(cc.va_evoke_status_from_entity_and_registrations({'status': 'Not Authorized to Solicit'}, [reg])[0], 'Unable to Confirm')
        self.assertEqual(cc.va_evoke_status_from_entity_and_registrations({'status': 'Registered'}, [reg])[0], 'Current')

    def wi_html(self, primary='National Marrow Donor Program', alias='National Marrow Donor Program Foundation'):
        row = lambda name: f'<tr><td>4708-800</td><td>Charitable Organization</td><td><a href="CredSummaryDetails.aspx?chid=695959">{name}</a></td><td>Minneapolis MN</td><td>01/14/1994</td><td>07/31/2025</td></tr>'
        return '<table id="ctl00_cphMainContent_OrgCredentialSearch_gvCredentialSearchResults">'+row(primary)+row(alias)+'</table>'

    def test_wi_same_credential_alias_requires_primary_detail_confirmation(self):
        name = 'National Marrow Donor Program'
        for detail, conflict in (('Name: NATIONAL MARROW DONOR PROGRAM Credential Type: CHARITABLE ORGANIZATION (800) Credential Number: 4708-800 Status License is not current (Revoked) Other Names: National Marrow Donor Program Foundation', False),
                                 ('Name: National Marrow Donor Program Foundation Credential Type: CHARITABLE ORGANIZATION Credential Number: 4708-800 Status License is current (Active)', True),
                                 ('', True)):
            with patch.object(cc, 'wi_http_detail_text', return_value=detail):
                result = cc.wi_best_match_from_html(self.wi_html(), [name], original_name=name, ein='840865803')
            self.assertIsNotNone(result)
            self.assertEqual(result['identity_conflict'], conflict)
            if not conflict:
                self.assertEqual(cc.wi_status_from_detail_status(result['detail_status']), 'Revoked')

    def test_wi_separate_foundation_is_still_rejected(self):
        name = 'National Marrow Donor Program'
        with patch.object(cc, 'wi_http_detail_status', return_value='License is current (Active)'):
            self.assertIsNone(cc.wi_best_match_from_html(self.wi_html(name+' Foundation', name+' Foundation'),
                                                       [name], original_name=name, ein='840865803'))

    def test_ok_http_200_document_error_qualifies_but_generic_html_does_not(self):
        page = Mock()
        page.url = 'https://www.sos.ok.gov/corp/charityDetail.aspx?id=fixture'
        page.get_by_role.return_value.get_attribute.return_value = "javascript:__doPostBack('ctl00$DefaultContent$grdFilingList$ctl02$lnkAction','')"
        page.locator.return_value.first.evaluate.return_value = {}
        response = page.request.post.return_value
        response.ok = True; response.status = 200; response.headers = {'content-type': 'text/html'}
        response.body.return_value = b'<html>Document unavailable</html>'
        for content, eligible in (('<html>Document unavailable</html>', True), ('Login required', False),
                                  ('Registration rejected. Document unavailable', False), ('Unknown HTML', False)):
            cc._ok_certificate_cache.clear()
            page.evaluate.return_value = {'ok': True, 'status': 200, 'content_type': 'text/html',
                                          'pdf_base64': '', 'error_text': content}
            result = cc.ok_fetch_registration_certificate(page, '74201040002 Renewal Registration December 22, 2025 4', 'Fixture')
            self.assertEqual(cc.ok_certificate_service_unavailable(result), eligible)
            due = cc.ok_calculated_registration_expiration('74201040002 Renewal Registration December 22, 2025 4',
                   result, 'Active', ['74201040002 Renewal Registration December 22, 2025 4'], cc.state_batch_modules(['OK'])['msok'])
            self.assertEqual(due, date(2026, 12, 22) if eligible else None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
