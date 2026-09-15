"""Real MA scan and negative controls; no registry/network requests."""
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

FIXTURE = Path(__file__).parent / 'fixtures/ma-conservation-2021'


class Today(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 15)


class ScannedPeriodTests(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(c, 'date', Today),
                  patch.object(c.urllib.request, 'urlopen', side_effect=AssertionError('No network'))):
            p.start()
            self.addCleanup(p.stop)

    def text(self, period='01 01 2021 to 12 31 2021'):
        return ('Form PC\nReport for the Fiscal Period:\n' + period +
                '\nAttorney General Account: 065449\nFederal ID: 26-1154515')

    def parse(self, text, year=2021, account='065449', ein='261154515'):
        return c.ma_scanned_form_pc_evidence(text, year, account, ein)

    def test_space_compact_and_slash_dates(self):
        for period in ('01 01 2021 to 12 31 2021', '01012021 to 12312021',
                       '01 01 2021 to 12312021', '01/01/2021 to 12/31/2021'):
            with self.subTest(period=period):
                self.assertEqual(self.parse(self.text(period)).get('period_end'), '12/31/2021')

    def test_never_invents_missing_digits_or_accepts_bad_period(self):
        for period in ('01012021 to 312021', '01 01 2021 to 31 2021',
                       '01012021 to 02312021', '01012021 to 12312022',
                       '01012019 to 12312021', '12312021 to 01012021',
                       '01012021 12312021', '01012021 to 12312021 to 12312021'):
            with self.subTest(period=period):
                self.assertFalse(self.parse(self.text(period)))

    def test_identity_form_label_and_year_still_required(self):
        t = self.text()
        for text, year, account, ein in (
            (t, 2022, '065449', '261154515'), (t, 2021, '999999', '261154515'),
            (t, 2021, '065449', '999999999'), (t.replace('Form PC', 'IRS 990'), 2021, '065449', '261154515'),
            (t.replace('Report for the Fiscal Period', 'Received date'), 2021, '065449', '261154515')):
            self.assertFalse(self.parse(text, year, account, ein))

    def test_prior_noncalendar_slash_scan_unchanged(self):
        t = 'Form PC\n09/01/2020 to 08/31/2021\nReport for the Fiscal Period:\n027670\n86-0481941'
        self.assertEqual(self.parse(t, account='027670', ein='860481941')['period_end'], '8/31/2021')

    def test_reread_cannot_replace_identity_or_invent_period(self):
        for original in (self.text().replace('26-1154515', '99-9999999'),
                         self.text().replace('065449', '999999'),
                         self.text().replace('Form PC', 'IRS 990'),
                         self.text().replace('Report for the Fiscal Period', 'Received')):
            self.assertFalse(c.ma_scanned_form_pc_evidence(original, 2021, '065449', '261154515', self.text()))
        for row in ('Report for the Fiscal Period: 01012021 to 312021',
                    'Received: 01012021 to 12312021'):
            self.assertFalse(c.ma_scanned_form_pc_evidence(self.text(), 2021, '065449', '261154515', row))

    def test_reread_requires_unique_high_confidence_label(self):
        from PIL import Image
        with Image.open(FIXTURE / 'form-pc-first-page.png') as scanned:
            good = [[[90, 575], [456, 575], [456, 612], [90, 612]], 'Report for the Fiscal Period:', .99]
            ocr = Mock(return_value=([[[[0, 0]] * 4, 'uncertain date', .84]], None))
            for labels in ([], [good, good], [[good[0], good[1], .84]]):
                self.assertEqual(c.ma_scanned_period_row_text(scanned, labels, ocr), '')
            ocr.assert_not_called()
            self.assertEqual(c.ma_scanned_period_row_text(scanned, [good], ocr), '')
            ocr.assert_called_once()

    def test_successful_original_read_does_not_reread(self):
        completed = json.loads((FIXTURE / 'completed-evidence.json').read_text())
        lines = [[[[0, 0]] * 4, t, .99] for t in self.text('1/1/2021 to 12/31/2021').splitlines()]
        with patch.object(c, '_MA_LEGACY_OCR', Mock(return_value=(lines, None))), \
             patch.object(c, 'ma_scanned_period_row_text', side_effect=AssertionError('Original read succeeded')):
            self.assertEqual(c.ma_read_legacy_form_pc(self.page(), completed, '065449')['period_end'], '12/31/2021')

    def page(self):
        page = Mock()
        page.context.request.get.return_value.ok = True
        page.context.request.get.return_value.body.return_value = (FIXTURE / 'form-pc-first-page.png').read_bytes()
        return page

    def test_actual_scan_through_reader_status_and_comment(self):
        completed = json.loads((FIXTURE / 'completed-evidence.json').read_text())
        page = self.page()
        evidence = c.ma_read_legacy_form_pc(page, completed, '065449')
        self.assertEqual(evidence.get('period_end'), '12/31/2021')
        self.assertTrue(evidence.get('legacy_period_row_reread'))
        evidence['registry_status'] = completed['record']['registry_status']
        r = c.checker.StateResult(completed['record']['name'], '261154515', 'MA', 'Current', '')
        c.annotate_ma_visible_form_pc_due(r, evidence)
        self.assertEqual(c.true_status_from_body(r, ''), 'Delinquent')
        self.assertEqual(r.next_required_period, '12/31/2022')
        self.assertEqual(r.computed_due_date, '11/15/2023')
        comment = c.comments_for_result(r, '', 'Delinquent')
        for item in ('12/31/2021', '11/15/2023', 'Delinquent'):
            self.assertIn(item, comment)
        page.context.request.get.assert_called_once()

    def test_unavailable_document_and_ambiguous_latest_remain_inconclusive(self):
        completed = json.loads((FIXTURE / 'completed-evidence.json').read_text())
        page = self.page()
        page.context.request.get.return_value.ok = False
        self.assertFalse(c.ma_read_legacy_form_pc(page, completed, '065449'))
        page = self.page()
        completed['filings']['065449']['annual_scans'].append(
            {'year': '2021', 'url': 'https://masscharities.my.site.com/FilingSearch/sfc/servlet.shepherd/document/download/other'})
        self.assertFalse(c.ma_read_legacy_form_pc(page, completed, '065449'))
        page.context.request.get.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
