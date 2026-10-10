import unittest

from deployment.lab_identity import staging_mirror_identity


class StagingMirrorIdentityTests(unittest.TestCase):
    def setUp(self):
        self.resources = {
            'version': '2026.09.29.2-performance-lab',
            'origin': 'https://charityclarity-staging-ef-api.onrender.com',
            'api': {'id': 'srv-teststageapi', 'name': 'charityclarity-staging-ef-api'},
            'worker': {'id': 'srv-teststageworker', 'name': 'charityclarity-staging-ef-worker'},
            'database': {'host': 'dpg-teststagedb-a', 'name': 'cc_staging_ef'},
        }
        self.env = {
            'CE_STAGING_MIRROR': '1',
            'CE_APP_VERSION': self.resources['version'],
            'PUBLIC_BASE_URL': self.resources['origin'],
            'RENDER_SERVICE_ID': self.resources['api']['id'],
            'RENDER_SERVICE_NAME': self.resources['api']['name'],
            'CE_LAB_DURABLE_QUEUE': '1',
            'CE_LAB_DATABASE_URL': 'postgresql://u:p@dpg-teststagedb-a/cc_staging_ef',
        }

    def test_api_and_worker_use_only_their_own_queue(self):
        self.assertTrue(staging_mirror_identity(self.env, self.resources))
        worker = {**self.env, 'CE_LAB_ROLE': 'worker',
                  'RENDER_SERVICE_ID': self.resources['worker']['id'],
                  'RENDER_SERVICE_NAME': self.resources['worker']['name']}
        self.assertTrue(staging_mirror_identity(worker, self.resources))
        child = {**worker, 'CE_FINAL_FOUR_CHILD': '1', 'CE_LAB_DURABLE_QUEUE': '0'}
        child.pop('CE_LAB_DATABASE_URL')
        self.assertTrue(staging_mirror_identity(child, self.resources))

    def test_protected_services_trial_database_and_wrong_origin_fail_closed(self):
        for changed in (
            {'RENDER_SERVICE_ID': 'srv-dau1rv0u01pc73auc4jg'},
            {'RENDER_SERVICE_ID': 'srv-d8a38lnavr4c73d4ib30'},
            {'PUBLIC_BASE_URL': 'https://staging.compliance-express.com'},
            {'CE_LAB_DATABASE_URL': 'postgresql://u:p@dpg-dau1ru5g1s2s73b4tgn0-a/cc_final_four_29_2'},
            {'CE_FINAL_FOUR_TRIAL': '1'},
        ):
            with self.subTest(changed=changed):
                self.assertIsNone(staging_mirror_identity({**self.env, **changed}, self.resources))


if __name__ == '__main__':
    unittest.main()
