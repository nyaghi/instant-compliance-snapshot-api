"""Kentucky source-column matching without relaxed cross-state name rules."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

LEGAL = 'Morgan Stanley Global Impact Funding Trust, Inc.'
DBA = 'CMI Employee Appreciation Fund'
NAME = LEGAL + ' | DBA: ' + DBA
ROW = ('14131', NAME, '2024', '14131 ' + NAME + ' Yr Last Filed 2024')


class KentuckyDbaTests(unittest.TestCase):
    def lookup(self, name, rows=None):
        with patch.object(c, 'load_ky_snapshot_records', return_value=rows or [ROW]), \
             patch.object(c, 'known_names_for_ein', return_value=[]), \
             patch.object(c, 'fiscal_year_end_for_ein', return_value=(12, 31)), \
             patch.object(c.urllib.request, 'urlopen', side_effect=AssertionError('No network')):
            return c.search_ky_strict_snapshot(c.checker.Organization(name, '474444592'))

    def test_exact_legal_and_dba_match_same_record_and_year(self):
        for name in (LEGAL, DBA, 'CMI Employee Appreciation'):
            with self.subTest(name=name):
                r = self.lookup(name)
                self.assertEqual(r.matched_registry_identifier, '14131')
                self.assertEqual(r.matched_registry_name, NAME)
                self.assertIn('Yr Last Filed: 2024', r.raw_status_text)

    def test_final_master_identity_check_accepts_explicit_dba(self):
        self.assertTrue(c.ky_snapshot_registry_name_is_safe(NAME, [DBA], DBA, '474444592'))

    def test_different_dba_does_not_match_shared_words(self):
        for name in ('CMI Employee Retirement Fund', 'CMI Research Foundation', 'Community Appreciation Foundation'):
            with self.subTest(name=name):
                self.assertEqual(c.public_status(self.lookup(name)), 'Not Registered')

    def test_unmarked_long_name_is_not_arbitrarily_split(self):
        joined = LEGAL + ' ' + DBA
        self.assertEqual(c.ky_registry_name_variants(joined), [joined])
        self.assertEqual(c.public_status(self.lookup(DBA, [('14131', joined, '2024', '')])), 'Not Registered')

    def test_duplicate_alias_across_different_ids_is_not_first_row_match(self):
        other = ('99999', 'Unrelated Trust | DBA: ' + DBA, '2025', '')
        for rows in ([ROW, other], [other, ROW]):
            result = self.lookup(DBA, rows)
            self.assertEqual(c.public_status(result), 'Needs Review')
            self.assertEqual(result.status_reason, 'KY_AMBIGUOUS_DBA_MATCH')

    def test_neighbor_and_same_id_other_alias_cannot_supply_filing_year(self):
        rows = [('3324', 'Morgan Stanley Global Impact Funding Trust', '2025', ''),
                ROW, ('14131', LEGAL + ' | DBA: MS Gift Cures, Inc.', '2024', '')]
        r = self.lookup(DBA, rows)
        self.assertEqual(r.matched_registry_identifier, '14131')
        self.assertIn('Yr Last Filed: 2024', r.raw_status_text)

    def test_single_word_explicit_alias_is_not_discarded(self):
        r = self.lookup('FoodChain', [('54321', 'Legal Relief | DBA: FoodChain', '2025', '')])
        self.assertEqual(r.matched_registry_identifier, '54321')

    def test_distinctive_hospital_name_cannot_be_lost_in_legal_column(self):
        row = ('11312', 'Beth Israel Medical Center | DBA: Mount Sinai Beth Israel', '2024', '')
        original = 'Beth Israel Deaconess Medical Center, Inc.'
        self.assertEqual(c.public_status(self.lookup(original, [row])), 'Not Registered')
        self.assertFalse(c.ky_snapshot_registry_name_is_safe(row[1], [original], original, '042103881'))
        org = c.checker.Organization(original, '042103881')
        variant = c.org_with_name(org, 'Beth Israel Medical Center')
        with patch.object(c, 'load_ky_snapshot_records', return_value=[row]):
            self.assertEqual(c.public_status(c.search_ky_strict_snapshot(variant)), 'Not Registered')

    def test_actual_verified_source_page_keeps_columns_and_neighbors(self):
        import pdfplumber
        from pypdf import PdfReader
        path = Path(__file__).resolve().parents[1] / 'downloadable-data/KY.pdf'
        page_index = next(i for i, page in enumerate(PdfReader(path).pages)
                          if 'CMI Employee' in page.extract_text())
        original = pdfplumber.open
        with original(path) as pdf:
            # Retain a real source table, exercising the parser rather than only strings.
            page = pdf.pages[page_index]
            from types import SimpleNamespace
            fake = SimpleNamespace(pages=[page])
            with patch.object(pdfplumber, 'open') as opener:
                opener.return_value.__enter__.return_value = fake
                rows = c.ky_parse_pdf_table_records(b'opened verified PDF above')
        hit = [r for r in rows if r[0] == '14131' and DBA in r[1]]
        self.assertEqual(hit, [ROW])
        self.assertEqual(len([r for r in rows if r[0] == '14131']), 2)
        self.assertTrue(any(r[0] == '3324' and ' | DBA: ' not in r[1] for r in rows))


if __name__ == '__main__':
    unittest.main(verbosity=2)
