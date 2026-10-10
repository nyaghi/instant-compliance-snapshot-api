"""The former trial pool can remain isolated after its trial clock expires."""
import unittest
from unittest.mock import patch

from deployment import lab_identity
from deployment.queue_worker import task_environment


class PermanentStagingIdentityTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            'version': lab_identity.TRIAL_VERSION,
            'origin': 'https://fixture-final-four.onrender.com',
            'api': {'id': 'srv-fixtureapi', 'name': 'charityclarity-final-four-29-2'},
            'worker': {'id': 'srv-fixtureworker', 'name': 'charityclarity-final-four-29-2-worker'},
            'database': {'host': 'dpg-fixture-a', 'name': lab_identity.TRIAL_DATABASE_NAME},
        }
        self.expired_trial = {**self.manifest, 'activated_epoch': 1000,
                              'expires_epoch': 1000 + 120 * 3600, 'spending_cap_usd': 80}
        self.env = {
            'CE_PERMANENT_STAGING': '1', 'CE_FINAL_FOUR_TRIAL': '0',
            'CE_APP_VERSION': lab_identity.TRIAL_VERSION,
            'PUBLIC_BASE_URL': self.manifest['origin'],
            'RENDER_SERVICE_ID': self.manifest['api']['id'],
            'RENDER_SERVICE_NAME': self.manifest['api']['name'],
            'CE_LAB_DURABLE_QUEUE': '1',
            'CE_LAB_DATABASE_URL': 'postgresql://u:p@dpg-fixture-a/cc_final_four_29_2',
        }

    def test_same_resources_remain_valid_after_trial_expiry(self):
        with patch.object(lab_identity, '_manifest', return_value=self.expired_trial):
            self.assertEqual(lab_identity.permanent_staging_identity(self.env, self.manifest),
                             {**self.manifest, 'permanent_staging': True})
            self.assertFalse(lab_identity.trial_access_expired(self.env, self.expired_trial, 9999999))
            with patch.object(lab_identity, 'STAGING_MANIFEST') as path:
                path.read_text.return_value = __import__('json').dumps(self.manifest)
                self.assertTrue(lab_identity.performance_origin_enabled(self.env))

    def test_worker_child_has_no_database_or_control_plane_key(self):
        worker = {**self.env, 'CE_LAB_ROLE': 'worker',
                  'RENDER_SERVICE_ID': self.manifest['worker']['id'],
                  'RENDER_SERVICE_NAME': self.manifest['worker']['name'],
                  'RENDER_API_KEY': 'fixture'}
        with patch.object(lab_identity, '_manifest', return_value=self.expired_trial), \
             patch.object(lab_identity, 'STAGING_MANIFEST') as path:
            path.read_text.return_value = __import__('json').dumps(self.manifest)
            child = task_environment(worker)
            self.assertTrue(lab_identity.trial_identity(child))
            for key in ('CE_LAB_DATABASE_URL', 'CE_TEST_DATABASE_URL', 'RENDER_API_KEY'):
                self.assertNotIn(key, child)
            self.assertIsNone(lab_identity.trial_identity({**child, 'CE_LAB_DATABASE_URL': 'leaked'}))

    def test_other_pool_or_origin_cannot_claim_staging(self):
        with patch.object(lab_identity, '_manifest', return_value=self.expired_trial):
            for changed in (
                {'RENDER_SERVICE_ID': 'srv-d8a38lnavr4c73d4ib30'},
                {'PUBLIC_BASE_URL': 'https://staging.compliance-express.com'},
                {'CE_LAB_DATABASE_URL': 'postgresql://u:p@dpg-dar6utvavr4c7380ou60-a/cc_performance_lab'},
                {'CE_FINAL_FOUR_TRIAL': '1'},
            ):
                with self.subTest(changed=changed):
                    self.assertIsNone(lab_identity.permanent_staging_identity({**self.env, **changed}, self.manifest))
            different = {**self.manifest, 'origin': 'https://different.onrender.com'}
            self.assertIsNone(lab_identity.permanent_staging_identity(self.env, different))

    def test_staging_retains_sales_sixty_second_contract(self):
        identity = {**self.manifest, 'permanent_staging': True}
        self.assertEqual(lab_identity.trial_sales_cutoff({}, identity), 60)
        self.assertEqual(lab_identity.trial_sales_cutoff({'sales_cutoff_seconds': 60, 'mode': 'sales'}, identity), 60)
        with self.assertRaises(ValueError):
            lab_identity.trial_sales_cutoff({'sales_cutoff_seconds': 90, 'mode': 'sales'}, identity)


if __name__ == '__main__':
    unittest.main()
