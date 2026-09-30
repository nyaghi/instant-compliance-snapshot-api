"""No network: 29.2 cannot reuse staging services, queue, or expired capacity."""
import ast
import copy
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from deployment import lab_identity as identity
from testing.performance_origin_audit import RestoreApprovedOrigin

ROOT = Path(__file__).resolve().parents[1]


class IsolationControls(unittest.TestCase):
    def fixture(self):
        manifest = {
            'version': identity.TRIAL_VERSION,
            'origin': 'https://fixture-final-four.onrender.com',
            'api': {'id': 'srv-fixtureapi', 'name': 'charityclarity-final-four-29-2'},
            'worker': {'id': 'srv-fixtureworker', 'name': 'charityclarity-final-four-29-2-worker'},
            'database': {'host': 'dpg-fixture-a', 'name': identity.TRIAL_DATABASE_NAME},
            'activated_epoch': 1000, 'expires_epoch': 1000 + 120*3600,
            'spending_cap_usd': 80,
        }
        env = {
            'CE_FINAL_FOUR_TRIAL': '1', 'CE_APP_VERSION': identity.TRIAL_VERSION,
            'PUBLIC_BASE_URL': manifest['origin'], 'RENDER_SERVICE_ID': manifest['api']['id'],
            'RENDER_SERVICE_NAME': manifest['api']['name'], 'CE_LAB_DURABLE_QUEUE': '1',
            'CE_LAB_DATABASE_URL': 'postgresql://fixture:fixture@dpg-fixture-a/cc_final_four_29_2',
        }
        return env, manifest

    def test_approved_origin_behavior_is_unchanged(self):
        for value in (identity.APPROVED_ORIGIN, '', None, 'https://staging.compliance-express.com'):
            env = {'PUBLIC_BASE_URL': value}
            self.assertEqual(identity.performance_origin_enabled(env), value == identity.APPROVED_ORIGIN)

    def test_new_origin_alone_never_enables_optimizations(self):
        env, _ = self.fixture()
        env.pop('CE_FINAL_FOUR_TRIAL')
        self.assertFalse(identity.performance_origin_enabled(env))

    def test_trial_api_and_worker_have_separate_allowlisted_identities(self):
        env, manifest = self.fixture()
        self.assertEqual(identity.trial_identity(env, manifest, 2000), manifest)
        worker = {**env, 'CE_LAB_ROLE': 'worker', 'RENDER_SERVICE_ID': manifest['worker']['id'],
                  'RENDER_SERVICE_NAME': manifest['worker']['name']}
        self.assertEqual(identity.trial_identity(worker, manifest, 2000), manifest)
        self.assertIsNone(identity.trial_identity({**worker, 'RENDER_SERVICE_ID': manifest['api']['id']}, manifest, 2000))

    def test_all_existing_services_and_origins_are_protected(self):
        env, manifest = self.fixture()
        for sid in identity.PROTECTED_SERVICES:
            changed = copy.deepcopy(manifest); changed['api']['id'] = sid
            self.assertIsNone(identity.trial_identity({**env, 'RENDER_SERVICE_ID': sid}, changed, 2000))
        for origin in identity.PROTECTED_ORIGINS:
            changed = {**manifest, 'origin': origin}
            self.assertIsNone(identity.trial_identity({**env, 'PUBLIC_BASE_URL': origin}, changed, 2000))

    def test_trial_cannot_connect_to_approved_queue(self):
        env, manifest = self.fixture()
        for host in (identity.APPROVED_DATABASE, identity.APPROVED_DATABASE + '.oregon-postgres.render.com'):
            changed = copy.deepcopy(manifest); changed['database']['host'] = host
            dsn = 'postgresql://fixture:fixture@' + host + '/cc_final_four_29_2'
            self.assertIsNone(identity.trial_identity({**env, 'CE_LAB_DATABASE_URL': dsn}, changed, 2000))
        self.assertIsNone(identity.trial_identity({**env, 'CE_LAB_DATABASE_URL': env['CE_LAB_DATABASE_URL'].replace('cc_final_four_29_2', 'cc_performance_lab')}, manifest, 2000))

    def test_time_and_cost_limits_fail_closed(self):
        env, manifest = self.fixture()
        for now in (999, manifest['expires_epoch'], manifest['expires_epoch']+1):
            self.assertIsNone(identity.trial_identity(env, manifest, now))
        for changed in ({**manifest, 'expires_epoch': manifest['expires_epoch']+1},
                        {**manifest, 'spending_cap_usd': 81}, {**manifest, 'spending_cap_usd': 0}):
            self.assertIsNone(identity.trial_identity(env, changed, 2000))

    def test_manifest_and_exact_version_are_required(self):
        env, manifest = self.fixture()
        for changed in (None, {}, {'origin': manifest['origin']}):
            with patch.object(identity, '_manifest', return_value=changed):
                self.assertFalse(identity.performance_origin_enabled(env))
        self.assertIsNone(identity.trial_identity({**env, 'CE_APP_VERSION': '2026.09.29.1-performance-lab'}, manifest, 2000))

    def test_child_keeps_approved_performance_identity_without_database_or_render_credentials(self):
        from deployment.queue_worker import task_environment
        env, manifest = self.fixture()
        env.update(RENDER_API_KEY='fixture-do-not-forward',CE_TEST_DATABASE_URL='fixture-do-not-forward')
        with patch.object(identity,'_manifest',return_value=manifest),patch.object(identity.time,'time',return_value=2000):
            child=task_environment(env)
            self.assertTrue(identity.performance_origin_enabled(child))
            self.assertEqual(child['CE_LAB_DURABLE_QUEUE'],'0')
            for key in ('CE_LAB_DATABASE_URL','CE_TEST_DATABASE_URL','RENDER_API_KEY'):
                self.assertNotIn(key,child)
                self.assertIsNone(identity.trial_identity({**child,key:'unexpected-secret'}))
            self.assertIsNone(identity.trial_identity({**child,'RENDER_SERVICE_ID':next(iter(identity.PROTECTED_SERVICES))}))
            with self.assertRaises(RuntimeError):task_environment({**env,'PUBLIC_BASE_URL':identity.APPROVED_ORIGIN})
        self.assertIsNone(identity.trial_identity(child,manifest,manifest['expires_epoch']))

    def test_baseline_child_environment_stays_exact(self):
        from deployment.queue_worker import task_environment
        env={'PUBLIC_BASE_URL':identity.APPROVED_ORIGIN,'CE_LAB_DATABASE_URL':'fixture','RENDER_API_KEY':'fixture','CE_LAB_DURABLE_QUEUE':'1'}
        self.assertEqual(task_environment(env),{'PUBLIC_BASE_URL':identity.APPROVED_ORIGIN,'CE_LAB_DURABLE_QUEUE':'0'})

    def test_forkserver_preload_preserves_validated_identity_before_main_is_reimported(self):
        import sys
        from deployment import performance_lab
        env,manifest=self.fixture()
        prefix=(ROOT/'deployment/engine_preload.py').read_text().split('started, cpu_started =',1)[0]
        def validated_parent(actual):
            self.assertIsNotNone(identity.trial_identity(actual,manifest,2000))
            self.assertIn('CE_LAB_DATABASE_URL',actual)
        with patch.dict(os.environ,env,clear=True),patch.object(sys,'platform','linux'), \
                patch.object(performance_lab,'validate_environment',side_effect=validated_parent), \
                patch.object(performance_lab,'install_http_egress_guard'):
            exec(compile(prefix,'preload-identity-control','exec'),{})
            self.assertEqual(os.environ['CE_FINAL_FOUR_CHILD'],'1')
            self.assertNotIn('CE_LAB_DATABASE_URL',os.environ)
            self.assertIsNotNone(identity.trial_identity(os.environ,manifest,2000))

    def test_environment_gate_does_not_change_registry_or_queue_code(self):
        """Compare all mature code outside audited origin and NJ acquisition additions."""
        class Restore(RestoreApprovedOrigin):
            def visit_FunctionDef(self, node):
                # These new, not-yet-routed source parsers are checked by the
                # final-four controls. The exact NJ exemption acquisition
                # additions are audited separately; all other functions stay exact.
                if node.name in {'final_four_source_date', 'al_charity_search_evidence',
                                 'nc_charity_record_evidence', 'nv_charity_detail_evidence',
                                 'final_four_license_result', 'tn_charity_detail_evidence',
                                 'nc_charity_profile_evidence', 'final_four_search_evidence',
                                 'final_four_browser_lookup', 'licensed_primary_positive_complete', 'final_four_date_metadata',
                                 'final_four_filing_metadata', 'nv_charity_filings_evidence',
                                 'final_four_clean_evidence', 'final_four_compact_search_evidence', 'final_four_connector_failure', 'final_four_connector_advance',
                                 'final_four_connector_request', '_send_final_four_connector'}:
                    return None
                if node.name == 'do_POST':
                    route = ast.parse('if self.path == "/api/final-four-connector":\n self._send_final_four_connector()\n return').body[0]
                    if ast.dump(node.body[0]) == ast.dump(route):
                        node.body.pop(0)
                return super().visit_FunctionDef(node)
            def visit_ImportFrom(self, node):
                return None if node.module == 'deployment.lab_identity' else node
            def visit_UnaryOp(self, node):
                if (isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Call)
                        and isinstance(node.operand.func, ast.Name)
                        and node.operand.func.id == 'performance_origin_enabled'):
                    return ast.parse("os.environ.get('PUBLIC_BASE_URL') != " + repr(identity.APPROVED_ORIGIN), mode='eval').body
                return self.generic_visit(node)
            def visit_Call(self, node):
                if isinstance(node.func, ast.Name) and node.func.id == 'performance_origin_enabled':
                    return ast.parse("os.environ.get('PUBLIC_BASE_URL') == " + repr(identity.APPROVED_ORIGIN), mode='eval').body
                return self.generic_visit(node)
        for name in ('registry_snapshot_server.py', 'deployment/durable_queue.py'):
            previous = subprocess.check_output(['git', 'show', 'approved-2026.09.29.1:'+name], cwd=ROOT).decode('utf-8')
            current = (ROOT/name).read_text(encoding='utf-8')
            self.assertEqual(ast.dump(ast.parse(previous)), ast.dump(Restore().visit(ast.parse(current))), name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
