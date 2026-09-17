"""OK first-page name ranking must agree with master identity acceptance."""
import html
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class OklahomaNameRankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = c.checker.sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def choose(self, requested, candidates):
        page = self.browser.new_page()
        try:
            page.set_content('<table>' + ''.join(
                f'<tr><td><a href="charityDetail.aspx?id={identifier}">{identifier}</a></td><td>{html.escape(name)}</td>'
                '<td>Charitable Organization</td><td>Legal In use</td></tr>'
                for identifier, name in candidates) + '</table>')
            org = c.checker.Organization(requested, '541637257')
            with patch.object(c, 'known_names_for_ein', return_value=[]):
                selected = c.ok_choose_safe_result_row_on_page(page, org, None)
            return selected[2:] if selected else None
        finally:
            page.close()

    def test_real_reported_name_variants_use_the_first_page_record(self):
        for requested in ('Coptic Orphans Support Association', 'Coptic Orphan Support Association'):
            self.assertEqual(self.choose(requested, [('4312648321', 'COPTIC ORPHANS SUPPORT ORGANIZATION')]),
                             ('COPTIC ORPHANS SUPPORT ORGANIZATION', '4312648321'))

    def test_pagination_numbers_are_not_filing_links(self):
        page=self.browser.new_page()
        try:
            page.set_content('<table><tr><td><a href="javascript:page(2)">2</a></td></tr>'
                '<tr><td><a href="https://example.com/charityDetail.aspx?id=123">123</a></td></tr>'
                '<tr><td><a href="charityDetail.aspx?id=4312648321">4312648321</a></td><td>Example Relief</td></tr></table>')
            org=c.checker.Organization('Example Relief','123456789')
            with patch.object(c,'known_names_for_ein',return_value=[]):
                chosen=c.ok_choose_safe_result_row_on_page(page,org,None)
            self.assertEqual(chosen[3],'4312648321')
            page.set_content('<table><tr><td><a href="charityDetail.aspx?id=4312648321">4312648321</a></td></tr></table>')
            with self.assertRaisesRegex(ValueError,'no readable organization name'):
                c.ok_choose_safe_result_row_on_page(page,org,None)
        finally:page.close()

    def test_generic_terminal_words_do_not_veto_complete_distinctive_core(self):
        for tail in ('Association', 'Organization', 'Foundation'):
            self.assertEqual(self.choose('Distinctive Community Relief Association', [('123456', 'Distinctive Community Relief '+tail)])[1], '123456')

    def test_exact_name_keeps_priority_over_descriptor_variant(self):
        original = 'Coptic Orphans Support Association'
        rows = [('4312648321', 'COPTIC ORPHANS SUPPORT ORGANIZATION'), ('123456789', original)]
        for candidates in (rows, list(reversed(rows))):
            self.assertEqual(self.choose(original, candidates)[1], '123456789')

    def test_missing_distinctive_words_are_not_supplied(self):
        for candidate in ('Coptic Support Organization', 'Orphans Support Organization', 'Coptic Orphans Medical Support Organization'):
            self.assertIsNone(self.choose('Coptic Orphans Support Association', [('123456', candidate)]))

    def test_previous_false_positives_stay_rejected(self):
        for original, candidate in (
            ('Autism Research Institute', 'Organization for Autism Research'),
            ('Beth Israel Deaconess Hospital - Milton, Inc.', 'Beth Israel Deaconess Hospital - Needham, Inc.'),
            ('Children’s Health Care Foundation', 'Children’s Healthcare of Atlanta')):
            with self.subTest(original=original):
                self.assertIsNone(self.choose(original, [('123456', candidate)]))

    def test_air_force_existing_exact_record_outranks_related_athletic_entity(self):
        original = 'Air Force Academy Foundation'
        other = 'Air Force Academy Athletic Corporation'
        self.assertFalse(c.shared_distinctive_core_match(original, other))
        # The approved OK source has the exact Foundation record. Its existing
        # priority must remain; the reported single-row false positive was FL.
        rows = [('123456', other), ('987654', original)]
        for candidates in (rows, list(reversed(rows))):
            self.assertEqual(self.choose(original, candidates)[1], '987654')


if __name__ == '__main__':
    unittest.main(verbosity=2)
