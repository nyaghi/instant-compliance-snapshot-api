"""Bounded passive NJ progress, with exact-baseline behavior comparisons."""
import ast
import copy
import subprocess
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import registry_snapshot_server as m
from testing.test_nj_scrolling_grid import ScrollingGrid, source_pages

BASE = '01d8d01add09bf0a7140d00728e5ecfb7624c21e'
ROOT = Path(__file__).resolve().parents[1]


def baseline(name):
    source = subprocess.check_output(['git', 'show', BASE+':registry_snapshot_server.py'], cwd=ROOT).decode()
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = dict(vars(m))
    exec(compile(ast.get_source_segment(source, node), '<ML-baseline>', 'exec'), scope)
    f = scope[name]
    return types.FunctionType(f.__code__, vars(m), name, f.__defaults__)


class PageProgress(unittest.TestCase):
    def test_30_browser_contexts_preserve_rows_requests_and_decisions(self):
        case = ScrollingGrid(); case.setUp()
        old = baseline('nj_search_body')
        pages = source_pages()
        with m.checker.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                for i in range(30):
                    org = case.org if i == 0 else m.checker.Organization('Control '+str(i),str(100000000+i))
                    with patch.object(m, 'nj_search_body', old):
                        before = case.browser_case(browser, pages, org, document_scroll=i%2==0)
                    after = case.browser_case(browser, pages, org, document_scroll=i%2==0)
                    self.assertEqual(before[:3], after[:3])
                    self.assertEqual(before[3]['phase'], after[3]['phase'])
                    self.assertEqual(after[3]['accepted_pages'], 5)
                    self.assertEqual(after[3]['accepted_rows'], 42)
                    self.assertEqual(after[3]['expected_rows'], 42)
                    self.assertTrue(after[3]['last_page_rendered'])
                    self.assertGreater(after[3]['scroll_attempts'], 0)
                body, data, calls, diag = case.browser_case(browser, pages, case.org, stale=True)
                self.assertIsNone(body); self.assertIsNone(data)
                self.assertEqual(diag['accepted_pages'], 1)
                self.assertEqual(diag['accepted_rows'], 10)
                self.assertTrue(diag['last_page_rendered'])
            finally:
                browser.close()

    def test_30_name_plan_contexts_retain_only_bounded_numeric_facts(self):
        old = baseline('search_nj_with_name_fallback')
        for i in range(30):
            org = m.checker.Organization('Control '+str(i),str(100000000+i))
            original = dict(phase='awaiting_remaining_grid_pages', accepted_pages=2,
                accepted_rows=20, expected_rows=42, rendered_rows=20, last_page_rendered=True,
                scroll_attempts=4, matching_responses=2, response_seconds=3.4, reused_form=True,
                query='PRIVATE SENTINEL', body='PRIVATE SENTINEL', elapsed_seconds=float('inf'),
                form_ready_seconds=float('nan'))
            def run(fn):
                page = SimpleNamespace(_cc_nj_query_diagnostic=copy.deepcopy(original))
                def direct(page, value, identity_org=None):
                    result = m.checker.StateResult(org.organization_name,org.ein,'NJ','Not Registered','')
                    result.success = identity_org is None
                    if identity_org is not None:
                        result.status='Unable to Verify'; result.reason_code='NJ_INCOMPLETE_QUERY_RESPONSE'
                    return result
                with patch.object(m,'nj_same_lookup_zero_queries',return_value=set()), \
                     patch.object(m,'nj_name_fallback_queries',return_value=[org.organization_name]), \
                     patch.object(m,'search_nj_direct',side_effect=direct):
                    return fn(page,org)
            before, after = run(old),run(m.search_nj_with_name_fallback)
            a,b=vars(before).copy(),vars(after).copy()
            a.pop('lab_diagnostic');b.pop('lab_diagnostic')
            self.assertEqual(a,b)
            row=after.lab_diagnostic['queries'][0]
            observation=row.pop('query_observation')
            self.assertEqual(row,before.lab_diagnostic['queries'][0])
            self.assertEqual(observation['accepted_pages'],2)
            self.assertTrue(observation['last_page_rendered'])
            self.assertNotIn('body',observation);self.assertNotIn('query',observation)
            self.assertNotIn('elapsed_seconds',observation);self.assertNotIn('form_ready_seconds',observation)


if __name__ == '__main__':
    unittest.main()
