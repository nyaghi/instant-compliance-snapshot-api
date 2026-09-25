import copy
import unittest
from deployment.capacity_trial import API_ID, WORKER_ID, VERSION, COMMIT, scale_plan, summarize_series


class CapacityTrialTests(unittest.TestCase):
    def setUp(self):
        self.services = {sid: {'id': sid, 'branch': 'performance-lab-20260924',
            'autoDeployTrigger': 'off', 'suspended': 'not_suspended',
            'type': 'web_service' if sid == API_ID else 'background_worker',
            'name': 'api' if sid == API_ID else 'charityclarity-performance-lab-worker-1',
            'serviceDetails': {'plan': 'pro', 'region': 'oregon', 'numInstances': 1}}
            for sid in (API_ID, WORKER_ID)}
        self.deployments = {sid: {'status': 'live', 'commit': {'id': COMMIT}} for sid in self.services}
        self.metrics = {'settings': {'source_version': VERSION, 'workflow_limit': 15, 'registry_limits': {'NY': 2}},
            'jobs': [{'phase': 'done', 'count': 96}], 'workflows': [{'phase': 'completed', 'count': 3}],
            'workers': [{'id': sid+'-instance-a', 'heartbeat': 99, 'retired': False, 'slots': 12}
                        for sid in self.services]}

    def plan(self, **kw):
        return scale_plan(self.services, self.deployments, self.metrics, now=100, **kw)

    def test_plan_is_bounded_and_does_not_mutate_inputs(self):
        before = copy.deepcopy((self.services, self.deployments, self.metrics))
        p = self.plan()
        self.assertEqual((p['monthly_compute_usd'], p['monthly_compute_delta_usd']), (255, 85))
        self.assertEqual((p['total_cpu'], p['expected_workers']), (6, 3))
        self.assertEqual(p['body'], {'numInstances': 2})
        self.assertEqual(before, (self.services, self.deployments, self.metrics))

    def test_protected_or_unknown_service_is_rejected(self):
        self.services['srv-d8a38lnavr4c73d4ib30'] = self.services.pop(API_ID)
        with self.assertRaises(ValueError): self.plan()

    def test_changed_code_blocks_hardware_comparison(self):
        self.deployments[WORKER_ID]['commit']['id'] = 'new-code'
        with self.assertRaises(ValueError): self.plan()

    def test_inflight_or_quarantined_jobs_block_scale(self):
        for phase in ('queued', 'running', 'quarantined', 'stopping'):
            with self.subTest(phase=phase):
                self.metrics['jobs'] = [{'phase': phase, 'count': 1}]
                with self.assertRaises(ValueError): self.plan()

    def test_active_workflow_blocks_scale(self):
        self.metrics['workflows'] = [{'phase': 'active', 'count': 1}]
        with self.assertRaises(ValueError): self.plan()

    def test_missing_or_duplicate_supervisor_blocks_scale(self):
        self.metrics['workers'][1]['id'] = self.metrics['workers'][0]['id']
        with self.assertRaises(ValueError): self.plan()
        self.metrics['workers'][1]['heartbeat'] = 10
        with self.assertRaises(ValueError): self.plan()

    def test_autoscaling_or_disk_or_changed_plan_blocks_scale(self):
        for key, value in [('autoscaling', {'enabled': True}), ('disk', {'id': 'disk'}), ('plan', 'standard')]:
            with self.subTest(key=key):
                old = self.services[WORKER_ID]['serviceDetails'].copy()
                self.services[WORKER_ID]['serviceDetails'][key] = value
                with self.assertRaises(ValueError): self.plan()
                self.services[WORKER_ID]['serviceDetails'] = old

    def test_repeated_or_larger_scale_is_rejected(self):
        with self.assertRaises(ValueError): self.plan(target_instances=3)
        self.services[WORKER_ID]['serviceDetails']['numInstances'] = 2
        with self.assertRaises(ValueError): self.plan()

    def test_rollback_requires_three_idle_workers(self):
        self.services[WORKER_ID]['serviceDetails']['numInstances'] = 2
        with self.assertRaises(ValueError): self.plan(target_instances=1)
        self.metrics['workers'].append({**self.metrics['workers'][1], 'id': WORKER_ID+'-instance-b'})
        p = self.plan(target_instances=1)
        self.assertEqual((p['expected_workers'], p['monthly_compute_delta_usd']), (2, -85))

    def test_replica_metrics_do_not_confuse_per_instance_with_total(self):
        data = [{'labels': [{'field': 'instance', 'value': name}],
                 'values': [{'timestamp': t, 'value': v} for t, v in points]}
                for name, points in [('a', [('t1', 1), ('t2', 2)]), ('b', [('t2', 2), ('t3', 1)])]]
        p = summarize_series(data)
        self.assertEqual(p['per_instance']['a']['peak'], 2)
        self.assertEqual(p['aligned_total'], {'peak': 4, 'sampled_mean': 4, 'samples': 1})
        self.assertEqual(p['unaligned_samples'], 2)

    def test_missing_or_duplicate_instance_metrics_are_rejected(self):
        with self.assertRaises(ValueError): summarize_series([{'labels': [], 'values': []}])
        s = {'labels': [{'field': 'instance', 'value': 'a'}], 'values': []}
        with self.assertRaises(ValueError): summarize_series([s, s])


if __name__ == '__main__': unittest.main()
