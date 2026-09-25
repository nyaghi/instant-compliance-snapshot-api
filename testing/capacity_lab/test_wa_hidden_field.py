"""Washington completed-negative timing fix; no matching or status edits."""
import ast
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch
import registry_snapshot_server as master


class WashingtonHiddenFieldTests(unittest.TestCase):
    def page(self, visible=False):
        page=Mock();ein=Mock();name=Mock()
        ein.is_visible.return_value=visible
        def locator(selector):
            return Mock(first=ein if selector=='#FEINNoSearchField' else name) if selector in ('#FEINNoSearchField','#txtKeywordSearch') else Mock()
        page.locator.side_effect=locator
        return page,ein,name

    def test_hidden_ein_is_not_filled_and_name_is_submitted(self):
        page,ein,name=self.page()
        with patch.object(master.time,'sleep'):
            self.assertTrue(master.wa_fill_ready_name_and_search(page,'Complete Legal Name'))
        ein.fill.assert_not_called()
        name.wait_for.assert_called_once_with(state='visible',timeout=10000)
        name.type.assert_called_once_with('Complete Legal Name',delay=35)
        self.assertIn("new Event('change'",page.evaluate.call_args.args[0])
        page.get_by_role.return_value.click.assert_called_once_with(timeout=5000,force=True)

    def test_visible_ein_is_still_cleared(self):
        page,ein,name=self.page(True)
        with patch.object(master.time,'sleep'):
            self.assertTrue(master.wa_fill_ready_name_and_search(page,'Name'))
        ein.fill.assert_called_once_with('')

    def test_optional_ein_failure_preserves_existing_name_fallback(self):
        page,ein,name=self.page(True);ein.fill.side_effect=RuntimeError('field changed')
        with patch.object(master.time,'sleep'):
            self.assertTrue(master.wa_fill_ready_name_and_search(page,'Name'))
        name.type.assert_called_once_with('Name',delay=35)

    def test_incomplete_name_panel_does_not_submit(self):
        page,ein,name=self.page();name.wait_for.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):master.wa_fill_ready_name_and_search(page,'Name')
        page.get_by_role.assert_not_called()

    def test_module_uses_master_hook(self):
        self.assertIs(master.load_wa_nm_module().fill_name_and_search,master.wa_fill_ready_name_and_search)

    def test_only_new_helper_and_one_hook_changed_since_perf14(self):
        root=Path(__file__).resolve().parents[2]
        old=ast.parse(subprocess.check_output(['git','show','355b736:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        new.body.remove(next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='wa_fill_ready_name_and_search'))
        loader=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name=='load_wa_nm_module')
        removed=0
        for branch in [n for n in ast.walk(loader) if isinstance(n,ast.If)]:
            for node in list(branch.body):
                if isinstance(node,ast.Assign) and ast.unparse(node)=='module.fill_name_and_search = wa_fill_ready_name_and_search':
                    branch.body.remove(node);removed+=1
        self.assertEqual(removed,1)
        self.assertEqual(ast.dump(old),ast.dump(new))


if __name__=='__main__':unittest.main(verbosity=2)
