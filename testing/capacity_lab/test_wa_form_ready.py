"""Sales form timing keeps exact input, completed search and detail guards."""
import ast,subprocess,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import registry_snapshot_server as m
from testing.capacity_lab.wa_form_scope import strip_wa_form_waits

class FormReady(unittest.TestCase):
    def test_exact_change_scope(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','371e88e:CharityClarity_WA_NM_checker.py'],cwd=root).decode('utf-8'))
        new=ast.parse((root/'CharityClarity_WA_NM_checker.py').read_text(encoding='utf-8'));strip_wa_form_waits(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_reactive_form_receives_same_ein_without_fixed_delays(self):
        module=m.load_wa_nm_module()
        with m.checker.sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                for fast in (False,True):
                    page=browser.new_page()
                    page.set_content('''<input type="radio" value="FEINNo" checked>
                    <input id="FEINNoSearchField" oninput="window.current=this.value">
                    <button onclick="window.submitted=window.current">Search</button>''')
                    with patch.object(module.time,'sleep') as sleep:
                        self.assertTrue(module.fill_fein_and_search(page,'12-3456789',readiness_waits_only=fast))
                    self.assertEqual(page.evaluate('window.submitted'),'123456789')
                    self.assertEqual(sleep.call_count,0 if fast else 2)
                    page.close()
            finally:browser.close()

    def test_failed_identity_or_unready_mode_never_submits(self):
        module=m.load_wa_nm_module()
        for fast in (False,True):
            page=Mock();page.locator.return_value.first.input_value.return_value='987654321'
            with patch.object(module,'switch_to_fein_mode'),patch.object(module.time,'sleep'):
                with self.assertRaisesRegex(RuntimeError,'did not retain'):module.fill_fein_and_search(page,'123456789',readiness_waits_only=fast)
            page.get_by_role.assert_not_called()
            with patch.object(module,'switch_to_fein_mode',side_effect=TimeoutError('not ready')):
                with self.assertRaises(TimeoutError):module.fill_fein_and_search(page,'123456789',readiness_waits_only=fast)
            page.get_by_role.assert_not_called()

    def test_complete_rendered_rows_need_no_scrolling_pause(self):
        module=m.load_wa_nm_module();page=Mock();link=Mock()
        with patch.object(module,'wa_completed_search_rendered',side_effect=[False,True]),patch.object(module,'scroll_to_results') as scroll,patch.object(module,'find_result_link',return_value=link),patch.object(module.time,'sleep'):
            self.assertIs(module.wait_for_result_link_or_no_value(page,'Example Relief',require_search_response=True,require_complete_before_link=True),link)
        scroll.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
