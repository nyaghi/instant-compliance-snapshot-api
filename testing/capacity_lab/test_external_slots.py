"""Real isolated-schema tests for the connector reservation added to staging."""
from deployment.durable_queue import NotFound
from testing.capacity_lab.test_durable_queue import DurableTests, payload

class ExternalSlots(DurableTests):
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
