"""Completed response, rendered rows, and actual click reception are distinct."""
import ast
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch
import registry_snapshot_server as m


def strip_actionable(tree):
    helper = next((n for n in tree.body if getattr(n, 'name', '') == 'wa_completed_search_rendered'), None)
    if helper is None:
        return
    tree.body.remove(helper)
    wait = next(n for n in tree.body if getattr(n, 'name', '') == 'wait_for_result_link_or_no_value')
    assert [a.arg for a in wait.args.kwonlyargs] == ['require_complete_before_link']
    wait.args.kwonlyargs = []; wait.args.kw_defaults = []
    loop = next(n for n in wait.body if isinstance(n, ast.While))
    assert ast.unparse(loop.body[0].test) == 'require_complete_before_link and (not wa_completed_search_rendered(page))'
    loop.body.pop(0)
    fn = next(n for n in tree.body if getattr(n, 'name', '') == 'search_wa')
    class Restore(ast.NodeTransformer):
        count = 0
        def visit_If(self, node):
            self.generic_visit(node)
            if ast.unparse(node.test) == 'readiness_waits_only':
                assert len(node.orelse) == 1
                self.count += 1
                return node.orelse
            return node
    restore = Restore(); restore.visit(fn); assert restore.count == 2


class Actionable(unittest.TestCase):
    def test_partial_failed_pending_or_not_yet_rendered_is_not_ready(self):
        module = m.load_wa_nm_module()
        ready = dict(completed=1, pending=0, failed=0, lastStatus=200,
                     lastText=json.dumps([{'EntityName': 'Example Relief'}]))
        for override, rendered, want in [({}, ['Example Relief (Also Name)'], True),
                ({'pending': 1}, ['Example Relief'], False), ({'completed': 0}, ['Example Relief'], False),
                ({'lastText': '['}, ['Example Relief'], False), ({}, [], False),
                ({'lastText': '[{}]'}, ['Example Relief'], False),
                ({'lastText': '[{"EntityName":"Different Entity"}]'}, ['Example Relief'], False),
                ({'lastText': '[]'}, [], True)]:
            page = Mock(); page.locator.return_value.all_inner_texts.return_value = rendered
            with self.subTest(override=override, rendered=rendered), patch.object(module, 'wa_search_tracker_state', return_value={**ready, **override}):
                self.assertEqual(module.wa_completed_search_rendered(page), want)
        for override in [{'lastStatus': 503}, {'failed': 1}]:
            with patch.object(module, 'wa_search_tracker_state', return_value={**ready, **override}):
                with self.assertRaisesRegex(RuntimeError, 'response failed'):
                    module.wa_completed_search_rendered(Mock())

    def test_candidate_selection_waits_for_complete_rendered_response(self):
        module = m.load_wa_nm_module(); page = Mock(); link = Mock()
        with patch.object(module, 'wa_completed_search_rendered', side_effect=[False, True]) as ready, patch.object(module, 'scroll_to_results'), patch.object(module, 'find_result_link', return_value=link) as find, patch.object(module.time, 'sleep'):
            result = module.wait_for_result_link_or_no_value(page, 'Example Relief', require_search_response=True, require_complete_before_link=True)
        self.assertIs(result, link); self.assertEqual(ready.call_count, 2); find.assert_called_once()

    def test_empty_response_alone_cannot_become_definitive_negative(self):
        module = m.load_wa_nm_module(); page = Mock()
        page.locator.return_value.inner_text.return_value = 'Loading'
        with patch.object(module, 'wa_completed_search_rendered', return_value=True), patch.object(module, 'scroll_to_results'), patch.object(module, 'find_result_link', return_value=None), patch.object(module.time, 'time', side_effect=[0, 0, 2]), patch.object(module.time, 'sleep'):
            result = module.wait_for_result_link_or_no_value(page, 'Example Relief', timeout_seconds=1, require_search_response=True, require_complete_before_link=True)
        self.assertIsNone(result)

    def test_real_browser_click_waits_for_loading_overlay(self):
        with m.checker.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content('''<table><tr><td><a href="#" onclick="window.selected=true;return false">Example Relief</a></td></tr></table>
                    <div id="overlay" style="position:fixed;inset:0;z-index:100;background:white"></div>''')
                link = page.get_by_role('link', name='Example Relief')
                link.click(force=True)
                self.assertIsNone(page.evaluate('window.selected'))
                page.evaluate('setTimeout(()=>document.querySelector("#overlay").remove(),300)')
                link.click(timeout=3000)
                self.assertTrue(page.evaluate('window.selected'))
            finally:
                browser.close()

    def test_exact_module_scope_since_76(self):
        root = Path(m.__file__).parent
        old = ast.parse(subprocess.check_output(['git', 'show', 'd4e9cdd:CharityClarity_WA_NM_checker.py'], cwd=root).decode('utf-8'))
        new = ast.parse((root/'CharityClarity_WA_NM_checker.py').read_text(encoding='utf-8'))
        strip_actionable(new)
        self.assertEqual(ast.dump(old), ast.dump(new))


if __name__ == '__main__':
    unittest.main()
