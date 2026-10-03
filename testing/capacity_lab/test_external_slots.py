"""Real isolated-schema tests for the connector reservation added to staging."""
from deployment.durable_queue import NotFound, normalize_submission
from testing.capacity_lab.test_durable_queue import DurableTests, payload

class ExternalSlots(DurableTests):
    def test_progressive_release_is_monotonic_bounded_and_keeps_request_identity(self):
        p=payload(states=['CO','ME','AR','CA','LA'],state_concurrency=5,external_state_slots=2)
        ident=self.submit(p,key='progressive-control'); worker=self.worker(slots=12)
        self.assertTrue(all(self.q.claim(worker) for _ in range(3)))
        self.assertIsNone(self.q.claim(worker))
        self.q.release_external_slots('a',ident,1)
        self.q.release_external_slots('a',ident,1)
        self.q.release_external_slots('a',ident,0)
        self.assertIsNotNone(self.q.claim(worker))
        self.assertIsNone(self.q.claim(worker))
        for invalid in (-1,3,True,1.0,'1'):
            with self.assertRaises(ValueError):self.q.release_external_slots('a',ident,invalid)
        self.assertIsNone(self.q.claim(worker))
        self.q.release_external_slots('a',ident,2)
        self.assertIsNotNone(self.q.claim(worker))
        self.q.release_external_slots('a',ident,2)
        self.q.release_external_slots('a',ident)
        self.assertIsNone(self.q.claim(worker))
        self.assertEqual(self.submit(p,key='progressive-control'),ident)

    def test_release_after_cancel_does_not_start_pending_work(self):
        ident=self.submit(payload(states=['CO','ME','AR','CA','LA'],state_concurrency=5,external_state_slots=2))
        worker=self.worker(slots=12)
        self.assertIsNotNone(self.q.claim(worker))
        self.q.cancel('a',ident)
        self.q.release_external_slots('a',ident,1)
        self.assertIsNone(self.q.claim(worker))

    def test_connector_only_sales_preparation_settles_without_state_jobs(self):
        p=normalize_submission({'ein':'123456789','organization_name':'Control',
            'states':[],'mode':'sales','alternate_names':[],
            'external_state_slots':1,'state_concurrency':20},['GA'])
        ident=self.submit(p); worker=self.worker(slots=12)
        job=self.q.claim(worker)
        self.assertEqual(job['state'],'@sales_identity')
        self.finish(job)
        status=self.q.status('a',ident)
        self.assertIsNotNone(status['finished'])
        self.assertEqual(status['jobs'],[])
        self.assertEqual(status['preparation'][0]['phase'],'done')

    def test_external_release_uses_same_ceiling_without_changing_request_identity(self):
        p=payload(states=['CO','ME','AR','CA','LA'],state_concurrency=5,external_state_slots=2)
        ident=self.submit(p,key='external-control'); worker=self.worker(slots=12)
        jobs=[self.q.claim(worker) for _ in range(3)]
        self.assertTrue(all(jobs));self.assertIsNone(self.q.claim(worker))
        self.q.release_external_slots('a',ident)
        self.q.release_external_slots('a',ident)
        self.assertEqual(self.submit(p,key='external-control'),ident)
        self.assertIsNotNone(self.q.claim(worker));self.assertIsNotNone(self.q.claim(worker))
        self.assertIsNone(self.q.claim(worker))

    def test_other_scope_cannot_release_connector_reservation(self):
        ident=self.submit(payload(external_state_slots=2))
        with self.assertRaises(NotFound):self.q.release_external_slots('different-owner',ident)
