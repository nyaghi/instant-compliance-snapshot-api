"""Deleting an advisory probe must preserve actual lookup and failure behavior."""
import ast
from contextlib import ExitStack
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch
import registry_snapshot_server as c


class FloridaPreflightTests(unittest.TestCase):
    def test_master_change_is_only_the_redundant_probe_deletion(self):
        from testing.capacity_lab.fl_alias_scope import restore_fl_redundant_preflight
        root=Path(__file__).resolve().parents[2]
        old=ast.parse(subprocess.check_output(['git','show','8967853:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        self.assertNotEqual(ast.dump(old),ast.dump(new))
        restore_fl_redundant_preflight(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_real_search_and_cleanup_preserved_without_advisory_request(self):
        for status in ('Current','Not Registered','Site Not Reachable'):
            with self.subTest(status=status), ExitStack() as stack:
                result=c.checker.StateResult('Example Relief','12-3456789','FL',status,'')
                result.raw_status_text=status
                result.success=status!='Site Not Reachable'
                playwright=stack.enter_context(patch.object(c.checker,'sync_playwright'))
                browser=playwright.return_value.__enter__.return_value.chromium.launch.return_value
                context=browser.new_context.return_value
                search=stack.enter_context(patch.object(c,'search_fl',return_value=result))
                probe=stack.enter_context(patch.object(c,'quick_registry_preflight',side_effect=AssertionError('Redundant network call')))
                stack.enter_context(patch.object(c,'response_data_for_lookup',side_effect=lambda r,*a:r))
                stack.enter_context(patch.object(c,'CAPTURE_EVIDENCE_SCREENSHOTS',False))
                stack.enter_context(patch.object(c,'CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT',False))
                general=stack.enter_context(patch.object(c,'BROWSER_LOOKUP_SEMAPHORE',MagicMock()))
                florida=stack.enter_context(patch.object(c,'FL_LOOKUP_SEMAPHORE',MagicMock()))
                actual=c.run_state_lookup('Example Relief','123456789','FL',confirm_single_no_match=False)
                self.assertIs(actual,result)
                search.assert_called_once()
                self.assertIs(search.call_args.args[0],context.new_page.return_value)
                probe.assert_not_called()
                context.close.assert_called_once();browser.close.assert_called_once()
                general.release.assert_called_once();florida.release.assert_called_once()


if __name__=='__main__':unittest.main()
