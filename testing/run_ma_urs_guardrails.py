"""Every Woman Treaty real document, identity failures and unchanged MA controls."""
import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

F = Path(__file__).parent / 'fixtures'


class Today(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 15)


class URSTests(unittest.TestCase):
    def setUp(self):
        self.today = patch.object(c, 'date', Today)
        self.today.start()
        self.addCleanup(self.today.stop)
        self.text = (F/'ma-everywoman-2016.txt').read_text(encoding='utf-8')
        self.completed = json.loads((F/'ma-everywoman-2016.json').read_text())
        self.completed['filings']['061133']['document_years'] = ['2016'] * 3

    def parse(self, text=None, year=2016, account='061133', ein='473272024'):
        return c.ma_scanned_urs_overdue_evidence(self.text if text is None else text, year, account, ein)

    def page(self):
        page = Mock()
        page.context.request.get.return_value.ok = True
        page.context.request.get.return_value.body.return_value = (F/'ma-everywoman-2016.png').read_bytes()
        return page

    def result(self):
        return c.checker.StateResult('Every Woman Treaty Inc.', '473272024', 'MA', 'Current', '')

    def test_reported_case_date_and_comment(self):
        evidence = self.parse()
        self.assertEqual(evidence['reporting_period_end'], '12/31/2016')
        self.assertNotIn('filing_status', evidence)
        r = self.result()
        c.annotate_ma_visible_form_pc_due(r, evidence)
        self.assertEqual(c.true_status_from_body(r, ''), 'Delinquent')
        self.assertEqual(r.computed_due_date, '')
        self.assertEqual(r.next_required_period, '')
        comment = c.comments_for_result(r, '', 'Delinquent')
        for text in ('Unified Registration Statement', '12/31/2016', 'infers Delinquent', 'not an explicit state determination'):
            self.assertIn(text, comment)
        self.assertNotIn('latest submitted Form PC', comment)

    def test_actual_scan_through_existing_reader(self):
        evidence = c.ma_read_legacy_form_pc(self.page(), self.completed, '061133')
        self.assertTrue(evidence.get('legacy_urs_overdue'))
        self.assertEqual(evidence['reporting_period_end'], '12/31/2016')
        self.assertIn('/document/download/0695e000007jZD2AAM', evidence['source_url'])

    def test_wrong_missing_or_conflicting_ein_rejected(self):
        for text in (self.text.replace('47-3272024', '99-9999999'),
                     self.text.replace('47-3272024', ''), self.text+'\n99-9999999'):
            self.assertFalse(self.parse(text))
        self.assertFalse(self.parse(ein=''))
        self.assertFalse(self.parse(account=''))

    def test_wrong_form_and_unlabeled_date_rejected(self):
        for text in (self.text.replace('Unified Registration Statement', 'IRS tax return'),
                     self.text.replace('This URS covers the reporting year which ended', 'Received date')):
            self.assertFalse(self.parse(text))

    def test_invalid_ambiguous_or_wrong_year_rejected(self):
        label = 'This URS covers the reporting year which ended (day/month/year) '
        for text in (self.text.replace('12/31/2016', '2/31/2016'),
                     self.text.replace('12/31/2016', '12/31/201'),
                     self.text+'\n'+label+'12/31/2016'):
            self.assertFalse(self.parse(text))
        self.assertFalse(self.parse(year=2017))

    def test_recent_or_future_urs_never_establishes_delinquent_or_current(self):
        for year in (2024, 2025, 2026, 2027):
            self.assertFalse(self.parse(self.text.replace('12/31/2016', f'12/31/{year}'), year=year))
        self.assertTrue(self.parse(self.text.replace('12/31/2016', '12/31/2023'), year=2023))

    def test_incomplete_history_and_newer_documents_block_fallback(self):
        lines = [[[[0, 0]] * 4, t, .99] for t in self.text.splitlines()]
        with patch.object(c, '_MA_LEGACY_OCR', Mock(return_value=(lines, None))):
            for years in ([], ['2016', ''], ['2016', '2025']):
                completed = copy.deepcopy(self.completed)
                completed['filings']['061133']['document_years'] = years
                self.assertFalse(c.ma_read_legacy_form_pc(self.page(), completed, '061133'))

    def test_wrong_account_unavailable_document_or_duplicate_latest_rejected(self):
        page = self.page()
        self.assertFalse(c.ma_read_legacy_form_pc(page, self.completed, '999999'))
        page.context.request.get.assert_not_called()
        page.context.request.get.return_value.ok = False
        self.assertFalse(c.ma_read_legacy_form_pc(page, self.completed, '061133'))
        completed = copy.deepcopy(self.completed)
        row = dict(completed['filings']['061133']['annual_scans'][0])
        row['url'] += 'other'
        completed['filings']['061133']['annual_scans'].append(row)
        page = self.page()
        self.assertFalse(c.ma_read_legacy_form_pc(page, completed, '061133'))
        page.context.request.get.assert_not_called()

    def test_visible_pending_and_adverse_status_still_control(self):
        for extra, expected in (({'registration_pending': True, 'registry_status': 'Pending'}, 'Pending'),
                                ({'adverse_status': 'Revoked'}, 'Revoked')):
            r = self.result()
            c.annotate_ma_visible_form_pc_due(r, {**self.parse(), **extra})
            self.assertEqual(r.status, expected)

    def test_invisible_pending_does_not_override_document(self):
        page = self.page()
        page.locator.return_value.inner_text.return_value = 'AG Account Number 061133'
        page.get_by_role.return_value.all_inner_texts.return_value = ['2016 FY2016 PC - Form PC/Annual RPT.tiff']
        with patch.object(c, 'ma_read_legacy_form_pc', return_value=self.parse()):
            evidence = c.ma_read_latest_form_pc(page, self.result(), 'AG Account Number 061133', self.completed)
        self.assertEqual(evidence['noncontrolling_network_status'], 'In-Progress')
        r = self.result()
        c.annotate_ma_visible_form_pc_due(r, evidence)
        self.assertEqual(r.status, 'Delinquent')


if __name__ == '__main__':
    unittest.main(verbosity=2)
