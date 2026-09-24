"""Deterministic scheduling/cleanup controls; no registry calls or remote I/O."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path
import sys
import threading
import time
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from deployment.lab_capacity import FairCapacity, AdmissionSemaphore, REQUEST_GROUP, REQUEST_TIMING, install


class FairCapacityTests(unittest.TestCase):
    def until(self, predicate):
        end = time.monotonic() + 3
        while not predicate():
            if time.monotonic() > end: self.fail('Fixture did not reach expected condition')
            time.sleep(.002)

    def test_waiting_organization_precedes_busy_organizations_backlog(self):
        pool = FairCapacity(2)
        first = pool.acquire('A', 'registration', 1)
        second = pool.acquire('A', 'registration', 1)
        order, release = [], threading.Event()
        def job(group):
            ticket = pool.acquire(group, 'registration', 2)
            self.assertIsNotNone(ticket)
            order.append(group)
            release.wait(2)
            pool.release(ticket)
        with ThreadPoolExecutor(4) as executor:
            futures = [executor.submit(job, 'A') for _ in range(3)]
            self.until(lambda: pool.snapshot()['queued'] == 3)
            futures.append(executor.submit(job, 'B'))
            self.until(lambda: pool.snapshot()['queued'] == 4)
            pool.release(first)
            self.until(lambda: len(order) == 1)
            self.assertEqual(order, ['B'])
            release.set()
            pool.release(second)
            for future in futures: future.result()
        self.assertEqual(pool.snapshot()['active'], 0)

    def test_discovery_and_registration_share_physical_reservations(self):
        pool = FairCapacity(4, category_limits={'discovery_browser': 2})
        d = [pool.acquire(str(i), 'discovery_browser', 0) for i in range(2)]
        self.assertIsNone(pool.acquire('next', 'discovery_browser', 0))
        r = [pool.acquire(str(i), 'registration', 0) for i in range(2)]
        self.assertIsNone(pool.acquire('next', 'registration', 0))
        self.assertEqual(pool.snapshot()['active'], 4)
        for ticket in d+r: pool.release(ticket)

    def test_blocked_discovery_category_does_not_block_registration(self):
        pool = FairCapacity(2, category_limits={'discovery_browser': 1})
        d = pool.acquire('A', 'discovery_browser', 0)
        with ThreadPoolExecutor(1) as executor:
            waiting = executor.submit(pool.acquire, 'B', 'discovery_browser', .2)
            self.until(lambda: pool.snapshot()['queued'] == 1)
            r = pool.acquire('C', 'registration', 0)
            self.assertIsNotNone(r)
            self.assertIsNone(waiting.result())
        pool.release(r); pool.release(d)

    def test_expired_queue_work_never_starts_after_capacity_frees(self):
        pool = FairCapacity(1)
        busy = pool.acquire('A', 'registration', 0)
        with ThreadPoolExecutor(1) as executor:
            waiting = executor.submit(pool.acquire, 'B', 'registration', .02)
            self.assertIsNone(waiting.result())
        pool.release(busy)
        s = pool.snapshot()
        self.assertEqual(s['counts']['admitted'], 1)
        self.assertEqual(s['counts']['queue_expired'], 1)
        self.assertEqual(s['queued'], 0)

    def test_canceled_queued_work_never_uses_a_slot(self):
        pool = FairCapacity(1)
        t = pool.acquire('A', 'registration', 0)
        canceled = threading.Event()
        with ThreadPoolExecutor(1) as executor:
            f = executor.submit(pool.acquire, 'B', 'registration', 5, canceled.is_set)
            self.until(lambda: pool.snapshot()['queued'] == 1)
            canceled.set()
            self.assertIsNone(f.result(1))
        pool.release(t)
        self.assertEqual(pool.snapshot()['counts']['admitted'], 1)

    def test_queue_is_bounded_and_full_does_not_leak_tickets(self):
        pool = FairCapacity(1, max_waiters=1)
        busy = pool.acquire('A', 'registration', 0)
        with ThreadPoolExecutor(1) as executor:
            f = executor.submit(pool.acquire, 'B', 'registration', .05)
            self.until(lambda: pool.snapshot()['queued'] == 1)
            self.assertIsNone(pool.acquire('C', 'registration', 0))
            self.assertIsNone(f.result())
        pool.release(busy)
        self.assertEqual(pool.snapshot()['counts']['queue_full'], 1)
        self.assertEqual(pool.snapshot()['queued'], 0)

    def test_100_distinct_organizations_3200_fixture_jobs_are_bounded(self):
        pool = FairCapacity(8)
        def flow(i):
            for state in range(32):
                t = pool.acquire(str(i), 'registration', 5)
                self.assertIsNotNone(t)
                try: time.sleep(.0005)
                finally: pool.release(t)
        with ThreadPoolExecutor(100) as executor:
            list(executor.map(flow, range(100)))
        s = pool.snapshot()
        self.assertEqual(s['counts']['admitted'], 3200)
        self.assertEqual(s['counts']['completed'], 3200)
        self.assertLessEqual(s['counts']['peak_active'], 8)
        self.assertGreater(s['counts']['peak_waiters'], 8)
        self.assertEqual(s['active'], 0)
        self.assertEqual(s['queued'], 0)
        self.assertLessEqual(len(s['recent']), 512)
        self.assertFalse(pool.by_group)

    def test_context_identity_and_queue_timing_do_not_leak(self):
        pool = FairCapacity(1)
        sem = AdmissionSemaphore(pool, 'registration')
        group = REQUEST_GROUP.set('fixture-group')
        timing = {'started': time.monotonic()}
        token = REQUEST_TIMING.set(timing)
        try:
            self.assertTrue(sem.acquire(timeout=1))
            self.assertEqual(next(iter(pool.active)).group, 'fixture-group')
            self.assertIn('queue_seconds', timing)
            with self.assertRaises(RuntimeError): sem.acquire(timeout=0)
            sem.release()
            with self.assertRaises(ValueError): sem.release()
        finally:
            REQUEST_GROUP.reset(group); REQUEST_TIMING.reset(token)
        self.assertEqual(REQUEST_GROUP.get(), 'unattributed')
        self.assertIsNone(REQUEST_TIMING.get())

    def test_exception_cleanup_and_no_early_release(self):
        pool = FairCapacity(1)
        sem = AdmissionSemaphore(pool, 'registration')
        with self.assertRaises(RuntimeError):
            self.assertTrue(sem.acquire(timeout=0))
            try:
                self.assertIsNone(pool.acquire('other', 'registration', 0))
                raise RuntimeError('Registry fixture failed')
            finally: sem.release()
        self.assertEqual(pool.snapshot()['active'], 0)

    def test_install_shares_pool_preserves_discovery_contract(self):
        seen = []
        master = types.SimpleNamespace(MAX_BROWSER_LOOKUPS=8,
                   canonical_ein_digits=lambda e:e.replace('-', ''))
        def original(source, ein, deadline):
            seen.append((source, ein, deadline, REQUEST_GROUP.get()))
            self.assertTrue(master.IDENTITY_BROWSER_SLOTS.acquire(timeout=0))
            try: return {'names': ['Former Name'], 'complete': True}
            finally: master.IDENTITY_BROWSER_SLOTS.release()
        master.identity_browser_names = original
        pool = install(master, 8)
        expected = {'names': ['Former Name'], 'complete': True}
        self.assertEqual(master.identity_browser_names('MA', '12-3456789', 123), expected)
        self.assertEqual(seen, [('MA', '12-3456789', 123, 'lab:123456789')])
        self.assertIs(master.IDENTITY_BROWSER_SLOTS.pool, master.SINGLE_STATE_REQUEST_SEMAPHORE.pool)
        self.assertEqual(pool.snapshot()['counts']['completed'], 1)
        self.assertEqual(REQUEST_GROUP.get(), 'unattributed')
        with self.assertRaises(RuntimeError): install(master, 9)


if __name__ == '__main__': unittest.main(verbosity=2)
