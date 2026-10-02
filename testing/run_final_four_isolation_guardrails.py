"""No network: 29.2 cannot reuse staging services, queue, or expired capacity."""
import ast
import copy
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from deployment import lab_identity as identity
from testing.performance_origin_audit import RestoreApprovedOrigin, restore_al_0622

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

    def test_october_two_delta_preserves_every_unaudited_master_and_queue_function(self):
        audited={'registry_snapshot_server.py':{'nm_browser_courtesy_names','nm_browser_lookup',
            'pa_name_search_plan','final_four_connector_failure','final_four_browser_lookup',
            'structured_registry_name','ar_result_rows','search_ar_precise','ok_choose_safe_result_row_on_page',
            'ok_open_latest_equivalent_detail','search_ok_precise','licensed_compound_retrieval_names',
            'irs_index_object_ids','identity_irs_historical_names','irs_period_for_label','ms_name_search_plan','ny_connector_failure'},
            'deployment/durable_queue.py':{'order_pending'}}
        for name,allowed in audited.items():
            previous=subprocess.check_output(['git','show','c8e6a0af19177f31951aacad60e783a369343aa5:'+name],cwd=ROOT).decode('utf-8')
            trees=[ast.parse(previous),ast.parse((ROOT/name).read_text(encoding='utf-8'))]
            for tree in trees:
                # The sole NY/IL/GA handler change is accepting this exact
                # packaged trial version. Restore it before whole-file parity.
                handlers=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'ny_connector_request','ny_connector_advance','il_verification_recovery'}]
                for handler in handlers:
                    for n in ast.walk(handler):
                        if isinstance(n,ast.Set):n.elts=[v for v in n.elts if not(isinstance(v,ast.Constant) and v.value in {'0.6.46','0.6.47','0.6.48','0.6.49','0.6.50'})]
                tree.body=[n for n in tree.body if not(isinstance(n,ast.FunctionDef) and n.name in allowed)]
            self.assertEqual(ast.dump(trees[0]),ast.dump(trees[1]),name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
