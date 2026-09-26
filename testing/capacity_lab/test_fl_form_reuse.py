"""Reuse completed public forms without skipping names or accepting stale results."""
import ast
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs
from unittest.mock import MagicMock, patch

import registry_snapshot_server as m


class FloridaFormReuseTests(unittest.TestCase):
    def run_mock(self, texts, reusable=True, failed_submission=None):
        page = MagicMock()
        page.url = m.FL_CHECK_A_CHARITY_URL
        page.evaluate.return_value = reusable
        page.expect_navigation.return_value.__enter__.return_value.value = SimpleNamespace(status=200)
        calls = []
        def read(_):
            value = texts[len(calls)]
            calls.append(value)
            return value
        submissions = [0]
        def click(**kw):
            submissions[0] += 1
            if failed_submission == submissions[0]:
                raise TimeoutError('Submitted document incomplete')
        page.get_by_role.return_value.click.side_effect = click
        variants = ['Example Relief', 'Example Relief Inc', 'The Example Relief Inc']
        with patch.object(m, 'reviewed_queries_first', return_value=variants.copy()), \
             patch.object(m.checker, 'find_visible_input', return_value=page), \
             patch.object(m, 'readable_page_text', side_effect=read), patch.object(m.time, 'sleep'):
            result = m.search_fl(page, SimpleNamespace(organization_name='Example Relief', ein='123456789'))
        return result, page, variants

    def test_all_variants_complete_with_one_initial_get(self):
        result, page, variants = self.run_mock(['No records found'] * 3)
        self.assertTrue(result.success)
        self.assertEqual(result.status, m.checker.STATUS_NOT_REGISTERED)
        self.assertEqual(page.goto.call_count, 1)
        self.assertEqual([c.args[0] for c in page.fill.call_args_list if c.args[0]], variants)

    def test_missing_form_reloads_for_each_variant(self):
        result, page, _ = self.run_mock(['No records found'] * 3, reusable=False)
        self.assertTrue(result.success)
        self.assertEqual(page.goto.call_count, 3)

    def test_failed_post_invalidates_form_and_never_becomes_negative(self):
        result, page, _ = self.run_mock(['No records found'] * 4, failed_submission=2)
        self.assertFalse(result.success)
        self.assertEqual(result.reason_code, 'FL_INCOMPLETE_SEARCH')
        self.assertEqual(page.goto.call_count, 2)

    def test_redirect_never_reuses_form(self):
        page = MagicMock()
        page.url = 'https://unrelated.example/search'
        self.assertFalse(m.fl_completed_search_form_available(page))
        page.evaluate.assert_not_called()

    def test_detached_context_does_not_abort_recovery(self):
        page = MagicMock()
        page.url = m.FL_CHECK_A_CHARITY_URL
        page.evaluate.side_effect = RuntimeError('Document context was destroyed')
        self.assertFalse(m.fl_completed_search_form_available(page))

    def test_real_browser_reuses_updated_viewstate_and_finds_later_name(self):
        requests = []
        def document(viewstate, body=''):
            return f'''<html><body><form method="post" action="./CheckACharity.aspx">
            <input type="hidden" name="__VIEWSTATE" value="{viewstate}">
            <input name="ctl00$cpMainContent$BusinessNameTb">
            <input type="submit" name="ctl00$cpMainContent$SingleSearchBt" value="Search">
            </form>{body}</body></html>'''
        def respond(route):
            req = route.request
            data = parse_qs(req.post_data or '')
            requests.append((req.method, data))
            if req.method == 'GET':
                html = document('initial')
            elif len(requests) == 2:
                html = document('updated', 'No records found')
            else:
                html = document('final', '<table><tr><td>Example Relief Inc</td>'
                    '<td>License/Registration Number CH12345 Expiration Date 12/31/2027 Status Current</td></tr></table>')
            route.fulfill(status=200, content_type='text/html', body=html)
        with m.checker.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.route('**/*', respond)
                with patch.object(m, 'reviewed_queries_first', return_value=['Old Example Relief', 'Example Relief Inc']), \
                     patch.object(m.time, 'sleep'):
                    result = m.search_fl(page, SimpleNamespace(organization_name='Example Relief Inc', ein='123456789'))
                self.assertEqual(result.status, 'Current')
                self.assertEqual(result.matched_registry_identifier, 'CH12345')
                self.assertEqual([r[0] for r in requests], ['GET', 'POST', 'POST'])
                self.assertEqual(requests[2][1]['__VIEWSTATE'], ['updated'])
                self.assertEqual(requests[2][1]['ctl00$cpMainContent$BusinessNameTb'], ['Example Relief Inc'])
                self.assertTrue(m.fl_completed_search_form_available(page))
                for script in [
                    "document.querySelector('[name=__VIEWSTATE]').value=''",
                    "document.querySelector('form').action='https://unrelated.example/'",
                    "document.querySelector('form').style.display='none'",
                ]:
                    page.set_content(document('valid'))
                    page.evaluate(script)
                    self.assertFalse(m.fl_completed_search_form_available(page))
            finally:
                browser.close()

    def test_matching_classification_and_variant_generation_unchanged(self):
        root = Path(__file__).resolve().parents[2]
        old = subprocess.check_output(['git', 'show', 'dbc5105:registry_snapshot_server.py'], cwd=root).decode('utf-8')
        current = (root / 'registry_snapshot_server.py').read_text(encoding='utf-8')
        def normalize(source):
            tree = ast.parse(source)
            tree.body = [n for n in tree.body if getattr(n, 'name', '') != 'fl_completed_search_form_available']
            class Restore(ast.NodeTransformer):
                def visit_Assign(self, node):
                    if any(isinstance(t, ast.Name) and t.id == 'completed_search_form' for t in node.targets):
                        return None
                    return self.generic_visit(node)
                def visit_If(self, node):
                    if 'fl_completed_search_form_available' in ast.unparse(node.test):
                        return ast.Expr(value=ast.Call(func=ast.Name(id='load_fl_search_page', ctx=ast.Load()), args=[], keywords=[]))
                    return self.generic_visit(node)
            return ast.dump(Restore().visit(tree), include_attributes=False)
        self.assertEqual(normalize(current), normalize(old))


if __name__ == '__main__': unittest.main()
