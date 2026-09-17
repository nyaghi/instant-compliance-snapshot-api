"""Complete MA document histories; reported real upload and policy boundaries."""
import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

F = Path(__file__).parent / 'fixtures/ma-arboretum'


class Today(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 15)


class MixedHistory(unittest.TestCase):
    def setUp(self):
        p = patch.object(c, 'date', Today)
        p.start()
        self.addCleanup(p.stop)
        self.raw = json.loads((F/'public-responses.json').read_text())
        self.completed = {'record': {'ago_account': '067048', 'ein': '521257712',
                                     'registry_status': 'In-Progress'}}
        for item in self.raw:
            if item['method'] not in {'get_ALL_FILINGS_ATTACHMENTS_FOR_PUBLICUSERS', 'get_CHARITY_ATTACHMENTS_FOR_PUBLICUSERS'}:
                continue
            response = Mock(url='https://masscharities.my.site.com/aura')
            response.request.post_data = urlencode({'message': json.dumps({'actions': [{'id': '1', 'params': {
                'classname': 'AeS_Apex_Controller_Class', 'method': item['method'], 'params': item['params']}}]})})
            response.json.return_value = {'actions': [{'id': '1', 'state': item['state'], 'returnValue': {'returnValue': item['rows']}}]}
            c.ma_capture_completed_response(response, c.checker.Organization('Friends of the National Arboretum', '521257712'), self.completed)

    def result(self):
        return c.checker.StateResult('Friends of the National Arboretum', '52-1257712', 'MA', 'Current', '')

    def page(self):
        p = Mock()
        p.locator.return_value.inner_text.return_value = 'AG Account Number 067048'
        p.get_by_role.return_value.all_inner_texts.return_value = ['2021 Schedule-A2 Data', '2020 FY2020 PC - Articles ORG/Bylaws.tiff', 'FY2021 PC - Form PC/Annual RPT.tiff']
        p.context.request.get.return_value.ok = True
        p.context.request.get.return_value.body.return_value = (F/'registration-documents.tiff').read_bytes()
        return p

    def infer(self, completed=None):
        return c.ma_completed_history_inference(self.completed if completed is None else completed, '067048')

    def test_both_sections_and_title_only_year_collected(self):
        reg = self.completed['registration_documents']['067048']
        self.assertTrue(reg['complete'])
        self.assertEqual(reg['document_years'], ['2021'])
        self.assertEqual(len(reg['annual_scans']), 1)
        self.assertFalse(self.completed['filings']['067048']['only_schedule_a2'])

    def test_actual_reported_upload_through_master_reader_and_comment(self):
        evidence = c.ma_read_latest_form_pc(self.page(), self.result(), 'AG Account Number 067048', self.completed)
        self.assertTrue(evidence['completed_history_inferred_delinquent'])
        self.assertEqual(evidence['latest_public_document_year'], 2021)
        self.assertEqual(evidence['noncontrolling_network_status'], 'In-Progress')
        r = c.annotate_ma_visible_form_pc_due(self.result(), evidence)
        self.assertEqual(c.true_status_from_body(r, '2021 Schedule-A2 Data'), 'Delinquent')
        self.assertEqual(r.computed_due_date, '')
        self.assertEqual(r.fiscal_year_end, '')
        self.assertIsNone(c.filing_context(r, '')['due_date'])
        comment = c.comments_for_result(r, '', 'Delinquent')
        for text in ('2021', 'infers Delinquent', 'not an explicit state determination'):
            self.assertIn(text, comment)
        self.assertNotIn('In-Progress', comment)
        self.assertNotIn('missing public filing details do not establish delinquency', comment)

    def test_no_annual_mixed_known_nonannual_documents(self):
        self.completed['registration_documents']['067048'] = c.ma_public_document_collection([])
        self.completed['filings']['067048'] = c.ma_public_document_collection([
            {'filingYear': '2026', 'nameforURL': 'Schedule-A2 Data'},
            {'filingYear': '2026', 'nameforURL': 'FY2026 PC - Articles ORG/Bylaws.tiff'}])
        self.assertTrue(self.infer()['no_annual_report_confirmed'])

    def test_missing_incomplete_and_wrong_account_do_not_infer(self):
        for key in ('filings', 'registration_documents'):
            value = copy.deepcopy(self.completed)
            del value[key]
            self.assertFalse(self.infer(value))
            value = copy.deepcopy(self.completed)
            value[key]['067048']['complete'] = False
            self.assertFalse(self.infer(value))
        self.completed['record']['ago_account'] = '999999'
        self.assertFalse(self.infer())

    def test_newer_unknown_or_future_year_blocks_stale_fallback(self):
        for year in ('2023', '2024', '2025', '2026', '2027', '', 'unknown'):
            value = copy.deepcopy(self.completed)
            value['filings']['067048']['documents'].append({'year': year, 'title': 'Other/Misc', 'url': ''})
            self.assertFalse(self.infer(value), year)

    def test_title_year_conflict_and_unknown_document_not_no_annual(self):
        for row in ({'filingYear': '2021', 'nameforURL': 'FY2025 PC - Form PC/Annual RPT.tiff'},
                    {'nameforURL': 'Unknown attachment'}):
            self.completed['registration_documents']['067048'] = c.ma_public_document_collection([row])
            self.assertFalse(self.infer())

    def test_download_failure_does_not_turn_into_delinquent(self):
        for fail in ('http', 'exception', 'nonimage'):
            p = self.page()
            if fail == 'http': p.context.request.get.return_value.ok = False
            elif fail == 'exception': p.context.request.get.side_effect = TimeoutError()
            else: p.context.request.get.return_value.body.return_value = b'not an image'
            e = c.ma_read_latest_form_pc(p, self.result(), 'AG Account Number 067048', self.completed)
            self.assertEqual(c.annotate_ma_visible_form_pc_due(self.result(), e).status, 'Unable to Confirm')

    def test_wrong_or_missing_document_ein_blocks_fallback(self):
        for text in ('Schedule A-2 99-9999999', 'Schedule A-2', '52-1257712 99-9999999'):
            lines = [[[[0, 0]]*4, text, .99]]
            with patch.object(c, '_MA_LEGACY_OCR', Mock(return_value=(lines, None))):
                e = c.ma_read_latest_form_pc(self.page(), self.result(), 'AG Account Number 067048', self.completed)
            self.assertEqual(c.annotate_ma_visible_form_pc_due(self.result(), e).status, 'Unable to Confirm')

    def test_multiple_old_uploads_use_completed_stale_history(self):
        reg = self.completed['registration_documents']['067048']
        reg['annual_scans'].append({**reg['annual_scans'][0], 'url': reg['annual_scans'][0]['url']+'other'})
        p = self.page()
        e = c.ma_read_latest_form_pc(p, self.result(), 'AG Account Number 067048', self.completed)
        self.assertEqual(c.annotate_ma_visible_form_pc_due(self.result(), e).status, 'Delinquent')
        self.assertTrue(e['completed_history_inferred_delinquent'])
        p.context.request.get.assert_not_called()

    def test_multiple_recent_or_incomplete_uploads_remain_inconclusive(self):
        for mode in ('recent', 'incomplete', 'unknown', 'wrong-account'):
            value = copy.deepcopy(self.completed)
            reg = value['registration_documents']['067048']
            reg['annual_scans'].append({**reg['annual_scans'][0], 'url': reg['annual_scans'][0]['url']+'other'})
            if mode == 'recent': reg['documents'].append({'year': '2025', 'title': 'Other/Misc'})
            elif mode == 'incomplete': reg['complete'] = False
            elif mode == 'unknown': reg['documents'].append({'year': '', 'title': 'Other/Misc'})
            else: value['record']['ago_account'] = '999999'
            e = c.ma_read_latest_form_pc(self.page(), self.result(), 'AG Account Number 067048', value)
            self.assertEqual(c.annotate_ma_visible_form_pc_due(self.result(), e).status, 'Unable to Confirm', mode)

    def test_visible_pending_and_adverse_overrides(self):
        for visible, expected in [('Pending', 'Pending'), ('Suspended', 'Suspended'), ('Revoked', 'Revoked'), ('Closed', 'Closed / Withdrawn / Canceled')]:
            p = self.page()
            body = 'AG Account Number 067048 Registration Status: '+visible
            p.locator.return_value.inner_text.return_value = body
            e = c.ma_read_latest_form_pc(p, self.result(), body, self.completed)
            self.assertEqual(c.annotate_ma_visible_form_pc_due(self.result(), e).status, expected)
            p.context.request.get.assert_not_called()

    def test_new_registration_annual_not_hidden_by_empty_main_history(self):
        self.completed['filings']['067048'] = c.ma_public_document_collection([])
        self.completed['registration_documents']['067048'] = c.ma_public_document_collection([
            {'nameforURL': 'FY2025 PC - Form PC/Annual RPT.tiff', 'url': 'https://masscharities.my.site.com/FilingSearch/sfc/servlet.shepherd/document/download/fixture'}])
        e = {'period_start': '1/1/2025', 'period_end': '12/31/2025', 'filing_year': 2025, 'filing_status': 'Submitted', 'ago_account': '067048'}
        with patch.object(c, 'ma_read_legacy_form_pc', return_value=e):
            evidence = c.ma_read_latest_form_pc(self.page(), self.result(), 'AG Account Number 067048', self.completed)
        self.assertEqual(c.annotate_ma_visible_form_pc_due(self.result(), evidence).status, 'Current')

    def test_existing_electronic_period_still_wins_over_older_supplements(self):
        from run_ma_form_pc_guardrails import MassachusettsTests
        test = MassachusettsTests()
        test.setUp()
        try: test.test_latest_row_selection_is_by_year_not_first_row()
        finally: test.doCleanups()

    def test_previously_approved_no_annual_controls_keep_status_and_reason(self):
        for ein, account in [('81-1823628', '084432'), ('81-4770680', '084259')]:
            completed = json.loads((F/(ein+'-control.json')).read_text())
            p = self.page()
            p.locator.return_value.inner_text.return_value = 'AG Account Number '+account
            p.get_by_role.return_value.all_inner_texts.return_value = []
            evidence = c.ma_read_latest_form_pc(p, self.result(), 'AG Account Number '+account, completed)
            r = c.annotate_ma_visible_form_pc_due(self.result(), evidence)
            self.assertEqual(r.status, 'Delinquent')
            self.assertEqual(r.status_reason, 'MA_CONFIRMED_EMPTY_HISTORY_INFERRED_DELINQUENT')
            p.context.request.get.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
