"""Browser snapshot must retain every field used by the existing selectors."""
import unittest
from unittest.mock import Mock
import registry_snapshot_server as m


class TableSnapshotTests(unittest.TestCase):
    def test_real_browser_fields_equal_individual_inner_text_reads(self):
        with m.checker.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content('''<table><tr><th>Search results</th></tr>
                <tr><td>1001</td><td>Example &amp; Relief<br>Inc.
                  <span style="display:none">Hidden</span></td>
                  <td>Address</td><td>Charity</td><td>Closed</td></tr>
                <tr><td>1002</td><td>Example &amp; Relief Inc.</td>
                  <td>Address</td><td>Charity</td><td>Active</td></tr>
                <tr><td>Partial</td><td>Unfinished</td></tr></table>''')
                rows = page.locator('tr')
                expected = []
                for index in range(min(rows.count(), 100)):
                    cells = rows.nth(index).locator('td')
                    count = cells.count()
                    expected.append({'index': index, 'count': count,
                        'values': [cells.nth(i).inner_text() if i < count else None for i in (0, 1, 4)]})
                self.assertEqual(m.registry_table_text_snapshot(rows, 100, (0, 1, 4)), expected)
                self.assertEqual(m.registry_table_text_snapshot(rows, 2, (0, 1, 4)), expected[:2])
                page.set_content('<table></table>')
                self.assertEqual(m.registry_table_text_snapshot(page.locator('tr'), 100, (0, 1, 4)), [])
            finally:
                browser.close()

    def test_malformed_response_is_incomplete_not_no_record(self):
        bad = [None, {}, [None], [{'index': 1, 'count': 5, 'values': ['1', 'Relief', 'Active']}],
            [{'index': 0, 'count': 5, 'values': ['1', None, 'Active']}],
            [{'index': 0, 'count': 2, 'values': ['1', 'Relief', 'Active']}],
            [{'index': 0, 'count': 5, 'values': ['1']}]]
        for value in bad:
            with self.subTest(value=value):
                rows = Mock(); rows.evaluate_all.return_value = value
                with self.assertRaises(ValueError):
                    m.registry_table_text_snapshot(rows, 100, (0, 1, 4))


if __name__ == '__main__': unittest.main()
