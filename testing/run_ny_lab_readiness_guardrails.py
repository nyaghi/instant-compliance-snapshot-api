"""Lab headless navigation readiness; master EIN/status protocol stays intact."""
import ast
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.org=c.checker.Organization('Fixture Foundation','123456789')
        self.p=Mock();self.browser=self.p.chromium.launch.return_value
        self.page=self.browser.new_context.return_value.new_page.return_value
        self.page.goto.return_value=Mock(status=200)
        self.playwright=Mock()
        self.playwright.__enter__=Mock(return_value=self.p)
        self.playwright.__exit__=Mock(return_value=False)
        self.semaphore=Mock();self.semaphore.acquire.return_value=True
        self.result=c.checker.StateResult(self.org.organization_name,self.org.ein,'NY','Current','')
        self.result.source_attempts=['NY RegistrySearch: complete','NY RegistryDetail: complete']
        self.clock=0

    def run_lookup(self):
        with patch.object(c.checker,'sync_playwright',return_value=self.playwright), \
             patch.object(c,'BROWSER_LOOKUP_SEMAPHORE',self.semaphore), \
             patch.object(c,'search_ny_direct',return_value=self.result) as self.direct, \
             patch.object(c.time,'perf_counter',side_effect=lambda:self.clock):
            return c.search_ny_verified(self.org)

    def test_normal_flow_keeps_real_verify_search_and_detail_protocol(self):
        result=self.run_lookup()
        self.assertIs(result,self.result)
        self.page.goto.assert_called_once_with('https://charities-search.ag.ny.gov/RegistrySearch',wait_until='commit',timeout=15000)
        self.page.get_by_role.assert_called_once_with('button',name='Verify',exact=True)
        self.page.get_by_role.return_value.wait_for.assert_called_once_with(timeout=27000)
        self.direct.assert_called_once_with(self.org,browser_page=self.page)
        self.assertIn('NY RegistryDetail: complete',result.source_attempts)
        self.browser.close.assert_called_once();self.semaphore.release.assert_called_once()

    def test_navigation_time_is_subtracted_from_original_combined_allowance(self):
        def navigation(*args,**kwargs):
            self.clock=14
            return Mock(status=200)
        self.page.goto.side_effect=navigation
        self.run_lookup()
        self.page.get_by_role.return_value.wait_for.assert_called_once_with(timeout=13000)

    def test_exhausted_allowance_does_not_start_lookup(self):
        def navigation(*args,**kwargs):
            self.clock=28
            return Mock(status=200)
        self.page.goto.side_effect=navigation
        result=self.run_lookup()
        self.direct.assert_not_called()
        self.assertFalse(result.success)
        self.assertEqual(result.status,'Unable to Confirm')

    def test_navigation_timeout_is_not_mislabeled_verification_rejection(self):
        self.page.goto.side_effect=TimeoutError('secret address token')
        result=self.run_lookup()
        self.assertIn('page navigation',result.source_note)
        self.assertIn('TimeoutError',result.source_attempts[-1])
        self.assertNotIn('secret',' '.join(result.source_attempts))
        self.assertEqual(result.status_reason,'NY_BROWSER_READINESS_INCOMPLETE')
        self.direct.assert_not_called()
        self.browser.close.assert_called_once();self.semaphore.release.assert_called_once()

    def test_http_error_cannot_be_a_negative_or_enter_registry_lookup(self):
        self.page.goto.return_value=Mock(status=503)
        result=self.run_lookup()
        self.assertEqual(result.status,'Unable to Confirm');self.assertFalse(result.success)
        self.direct.assert_not_called()

    def test_missing_verify_control_has_own_failure_step(self):
        self.page.get_by_role.return_value.wait_for.side_effect=TimeoutError('secret')
        result=self.run_lookup()
        self.assertIn('verification control readiness',result.source_note)
        self.direct.assert_not_called()

    def test_explicit_registry_verification_failure_is_not_retried(self):
        self.result.status='Unable to Confirm';self.result.success=False
        self.result.status_reason='NY_VERIFICATION_REQUIRED'
        result=self.run_lookup()
        self.assertEqual(result.status_reason,'NY_VERIFICATION_REQUIRED')
        self.direct.assert_called_once();self.page.goto.assert_called_once()

    def test_browser_launch_failure_releases_capacity(self):
        self.p.chromium.launch.side_effect=RuntimeError('secret')
        result=self.run_lookup()
        self.assertIn('browser startup',result.source_note)
        self.semaphore.release.assert_called_once();self.direct.assert_not_called()

    def test_browser_transport_and_status_functions_are_unchanged(self):
        root=Path(__file__).resolve().parents[1]
        old=ast.parse(subprocess.check_output(['git','show','73a262f:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        for name in ('ny_browser_registry_response','search_ny_direct','ny_select_confirmed_duplicate',
                     'ny_safe_identity_from_evidence','apply_ny_latest_fye_next_cycle_status'):
            a=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name==name)
            b=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.dump(a),ast.dump(b))

    def test_only_authorized_readiness_function_differs_from_previous_lab_release(self):
        root=Path(__file__).resolve().parents[1]
        old=ast.parse(subprocess.check_output(['git','show','73a262f:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        for tree in (old,new):
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='search_ny_verified')
            tree.body.remove(node)
        self.assertEqual(ast.dump(old),ast.dump(new))


if __name__=='__main__':unittest.main(verbosity=2)
