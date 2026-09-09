import sys, unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class WashingtonModeTests(unittest.TestCase):
    def test_ready_mode_needs_no_click(self):
        page=Mock();page.evaluate.return_value=True
        c.wa_select_ready_fein_mode(page)
        page.locator.assert_not_called()

    def test_silent_radio_selection_retries_label(self):
        page=Mock();page.evaluate.return_value=False
        page.wait_for_function.side_effect=[TimeoutError('panel missing'),None]
        c.wa_select_ready_fein_mode(page)
        page.get_by_text.assert_called_once_with('FEIN Number',exact=True)
        self.assertEqual(page.wait_for_function.call_count,2)

    def test_checked_but_missing_panel_is_reclicked(self):
        page=Mock();page.evaluate.return_value=False
        page.wait_for_function.side_effect=[TimeoutError(),TimeoutError(),None]
        c.wa_select_ready_fein_mode(page)
        page.locator.return_value.first.click.assert_called_once()
        self.assertTrue(page.locator.return_value.first.click.call_args.kwargs['force'])

    def test_failure_does_not_proceed_to_search(self):
        module=c.load_wa_nm_module();page=Mock()
        with patch.object(module,'switch_to_fein_mode',side_effect=TimeoutError('not ready')):
            with self.assertRaises(TimeoutError):module.fill_fein_and_search(page,'123456789')
        page.get_by_role.assert_not_called()

    def test_mode_timeout_is_explicit(self):
        page=Mock();page.evaluate.return_value=False
        page.wait_for_function.side_effect=TimeoutError('missing field')
        with self.assertRaisesRegex(TimeoutError,'no EIN search was submitted'):
            c.wa_select_ready_fein_mode(page)
        self.assertEqual(page.wait_for_function.call_count,3)

    def test_master_owns_mode_selection(self):
        self.assertIs(c.load_wa_nm_module().switch_to_fein_mode,c.wa_select_ready_fein_mode)

    def test_wrong_input_value_is_not_submitted(self):
        module=c.load_wa_nm_module();page=Mock()
        page.locator.return_value.first.input_value.return_value='987654321'
        with patch.object(module,'switch_to_fein_mode'),patch.object(module.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'did not retain'):
                module.fill_fein_and_search(page,'123456789')
        page.get_by_role.assert_not_called()

if __name__=='__main__':unittest.main()
