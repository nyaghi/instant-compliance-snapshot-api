import tempfile
import threading
import unittest
from pathlib import Path

from charityclarity_funnel import FunnelStore, clean_attribution, normalize_email


class FunnelStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = FunnelStore(Path(self.tempdir.name) / "funnel.sqlite3")

    def tearDown(self):
        self.tempdir.cleanup()

    def reserve(self, email=" Person@Example.org "):
        return self.store.reserve_free_search(
            email,
            email,
            "Example Foundation",
            "12-3456789",
            "PA",
            {"utm_source": "google", "email": "must-not-be-kept"},
        )

    def test_normalizes_email_and_consumes_only_after_success(self):
        first = self.reserve()
        self.assertTrue(first.eligible)
        self.assertTrue(self.store.complete_free_search(first.request_id, "Current"))
        repeat = self.reserve("person@example.org")
        self.assertFalse(repeat.eligible)
        self.assertEqual(repeat.reason, "already_used")

    def test_failure_does_not_consume_allowance(self):
        first = self.reserve()
        self.assertTrue(self.store.fail_free_search(first.request_id, "registry_unavailable"))
        retry = self.reserve("person@example.org")
        self.assertTrue(retry.eligible)

    def test_concurrent_requests_cannot_bypass_reservation(self):
        barrier = threading.Barrier(3)
        decisions = []

        def attempt():
            barrier.wait()
            decisions.append(self.reserve("simultaneous@example.org"))

        workers = [threading.Thread(target=attempt) for _ in range(2)]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join()
        self.assertEqual(sum(decision.eligible for decision in decisions), 1)
        self.assertEqual({decision.reason for decision in decisions}, {"eligible", "in_progress"})

    def test_events_are_idempotent_and_exclude_sensitive_attribution(self):
        self.assertTrue(
            self.store.record_event(
                "landing_page_viewed",
                "event-1",
                session_id="session-1",
                attribution={"utm_source": "google", "email": "hidden@example.org", "ein": "123456789"},
            )
        )
        self.assertFalse(self.store.record_event("landing_page_viewed", "event-1"))
        report = self.store.report(0, 4_000_000_000)
        self.assertEqual(report["events"]["landing_page_viewed"], 1)
        self.assertEqual(clean_attribution({"utm_source": "google", "email": "hidden"}), {"utm_source": "google"})

    def test_normalize_email(self):
        self.assertEqual(normalize_email("  Mixed.Case@Example.Org  "), "mixed.case@example.org")


if __name__ == "__main__":
    unittest.main()
