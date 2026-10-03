"""Lab Sales waits: retain completed-response and exact-EIN interpretation."""
import ast
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch
import registry_snapshot_server as m


def strip_ready_steps(tree):
    from testing.capacity_lab.test_nj_same_lookup import strip_same_lookup
    strip_same_lookup(tree)
    helper = next((n for n in tree.body if getattr(n, 'name', '') == 'lab_wa_readiness_waits_only'), None)
    if helper is None:
        return
    tree.body.remove(helper)
    fn = next(n for n in tree.body if getattr(n, 'name', '') == 'search_wa_nm_state')
    wa = next(n for n in fn.body if isinstance(n, ast.If))
    added = wa.body[0]
    assert isinstance(added, ast.If) and ast.unparse(added.test) == 'lab_wa_readiness_waits_only()'
    assert len(added.orelse) == 1 and len(added.body) == 1
    wa.body[0:1] = added.orelse


class ReadySteps(unittest.TestCase):
    def test_gate_preserves_standard_and_other_environments(self):
        base = {'PUBLIC_BASE_URL': 'https://instant-compliance-snapshot-api-hn4v.onrender.com', 'CE_LAB_WA_READY_STEPS': '1'}
        for mode, version, env, want in [
            ('sales', 'x-performance-lab', {}, True),
            ('standard', 'x-performance-lab', {}, False),
            ('sales', 'staging', {}, False),
            ('sales', 'x-performance-lab', {'PUBLIC_BASE_URL': 'https://staging.compliance-express.com'}, False),
            ('sales', 'x-performance-lab', {'CE_LAB_WA_READY_STEPS': ''}, False)]:
            with self.subTest(mode=mode, version=version, env=env), patch.object(m, 'APP_VERSION', version), patch.dict(os.environ, {**base, **env}):
                token = m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
                try:
                    self.assertEqual(m.lab_wa_readiness_waits_only(), want)
                finally:
                    m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_search_retains_submission_detail_and_identity_guards(self):
        module = m.load_wa_nm_module()
        for fast in [False, True]:
            for case in ['current', 'wrong_ein', 'incomplete', 'no_record', 'name_fallback', 'pending', 'mode_failed']:
                with self.subTest(fast=fast, case=case):
                    browser, context, page, link = Mock(), Mock(), Mock(), Mock()
                    context.new_page.return_value = page
                    link.inner_text.return_value = 'Example Relief'
                    response = 'NO_VALUE' if case in ['no_record', 'name_fallback'] else None if case == 'pending' else link
                    detail = 'FEIN Number:\n' + ('987654321' if case == 'wrong_ein' else '123456789')
                    if case != 'incomplete':
                        detail += '\nStatus:\nActive\nRenewal Date:\n12/31/2030'
                    manager = Mock(); manager.__enter__ = Mock(return_value=Mock()); manager.__exit__ = Mock(return_value=False)
                    with patch.object(module, 'sync_playwright', return_value=manager), patch.object(module, 'launch_context', return_value=(browser, context)), patch.object(module, 'safe_wait_for_network_idle') as idle, patch.object(module.time, 'sleep') as pause, patch.object(module, 'install_wa_search_tracker') as tracker, patch.object(module, 'switch_to_fein_mode', side_effect=TimeoutError('not ready') if case == 'mode_failed' else None), patch.object(module, 'fill_fein_and_search', return_value=True) as submit, patch.object(module, 'wait_for_result_link_or_no_value', return_value=response) as completed, patch.object(module, 'wa_name_fallback_result_link', return_value=link if case == 'name_fallback' else None) as fallback, patch.object(module, 'wa_search_tracker_state', return_value={'pending': 1}), patch.object(module, 'read_wa_detail', return_value=detail) as read:
                        result = module.search_wa(module.Organization('Example Relief', '123456789'), readiness_waits_only=fast)
                    tracker.assert_called_once_with(page)
                    if fast:
                        idle.assert_not_called(); pause.assert_not_called()
                    else:
                        self.assertGreaterEqual(idle.call_count, 1)
                    if case == 'mode_failed':
                        submit.assert_not_called(); read.assert_not_called(); self.assertFalse(result.success)
                        continue
                    submit.assert_called_once_with(page, '123456789', readiness_waits_only=fast)
                    options = {'timeout_seconds':22, 'require_search_response':True}
                    if fast:
                        options['require_complete_before_link'] = True
                    completed.assert_called_once_with(page, 'Example Relief', **options)
                    if case in ['current', 'name_fallback']:
                        link.click.assert_called_once_with(timeout=5000, **({} if fast else {'force':True}))
                        self.assertEqual(result.status, 'Current')
                        self.assertEqual(result.verified_registry_ein, '123456789')
                    elif case == 'no_record':
                        fallback.assert_called_once(); read.assert_not_called()
                        self.assertEqual(result.status, module.STATUS_NOT_REGISTERED)
                    elif case == 'pending':
                        fallback.assert_not_called(); read.assert_not_called(); self.assertFalse(result.success)
                        self.assertIn('did not complete', result.error)
                    else:
                        self.assertEqual(result.status, 'Unable to Confirm')
                        if case == 'wrong_ein':
                            self.assertFalse(result.success); self.assertEqual(result.verified_registry_ein, '')
                    context.close.assert_called_once(); browser.close.assert_called_once()

    def test_exact_scope_preserves_all_other_master_and_module_behavior(self):
        # The historical snapshot predates unrelated approved repairs. Use
        # the current pre-fix release and explicit Washington change scope.
        from testing.run_wa_submission_guardrails import Submission
        Submission().test_other_master_and_module_functions_unchanged_from_bh()

if __name__ == '__main__':
    unittest.main()
