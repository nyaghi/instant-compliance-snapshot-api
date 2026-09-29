"""Offline controls for shared routing; no registry or browser access."""
import copy
import threading
import time
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from router import CapacityRouter, Request, Worker


def request(i=0, state='CA', resource='browser', registry='', org=0):
    return Request(str(i), {'ein': f'{org + 1:09}', 'state': state, 'organization_name': f'Org {org}',
                           'alternate_names': [f'Alias {org}', f'Former {org}'],
                           'address_evidence': [{'source': 'fixture', 'city': f'City {org}'}]}, resource, registry)


def answer(payload, control):
    control.checkpoint()
    return {**payload, 'status': 'Current', 'success': True, 'registration_date': '2001-02-03',
            'last_filed_period': '2025-06-30', 'matched_registry_identifier': payload['ein'],
            'comments': 'Recorded state evidence, unchanged'}


class RouterControls(unittest.TestCase):
    def test_fifteen_workflows_use_both_pools_and_preserve_465_responses(self):
        def execute(p, c):
            c.wait(.002)
            return answer(p, c)
        workers = [Worker(f'{pool}{i}', pool, {'browser': 2}, execute) for pool in ('a', 'b') for i in range(6)]
        with CapacityRouter(workers) as router:
            futures = []
            for org in range(15):
                jobs = [request(org * 31 + i, org=org) for i in range(31)]
                futures.extend(zip(jobs, router.submit('workspace', f'org-{org}', jobs, time.monotonic() + 10).values()))
            for job, future in futures:
                self.assertEqual(future.result(10), answer(job.payload, type('C', (), {'checkpoint': lambda _: None})()))
            router.drain()
            dispatches = [e for e in router.trace if e['event'] == 'dispatch']
            self.assertEqual(len(dispatches), 465)
            self.assertEqual({e['pool'] for e in dispatches}, {'a', 'b'})
            self.assertTrue(all(e['worker_active']['browser'] <= 2 for e in dispatches))
            self.assertTrue(all(e['workflow_active'] <= 15 and e['active_workflows'] <= 15 for e in dispatches))

    def test_shared_limit_queues_sixteenth_workflow_until_running_work_drains(self):
        release = threading.Event()
        def execute(p, c):
            release.wait(2)
            return answer(p, c)
        with CapacityRouter([Worker('a', 'a', {'browser': 16}, execute)]) as router:
            groups = [router.submit('w', str(i), [request(i, org=i)], time.monotonic() + 3) for i in range(16)]
            end = time.monotonic() + 1
            while len([e for e in router.trace if e['event'] == 'dispatch']) < 15 and time.monotonic() < end:
                time.sleep(.005)
            self.assertEqual(len([e for e in router.trace if e['event'] == 'dispatch']), 15)
            self.assertFalse(next(iter(groups[15].values())).done())
            release.set()
            router.drain()
            self.assertTrue(all(e['active_workflows'] <= 15 for e in router.trace))

    def test_canceled_work_does_not_consume_next_run_and_cannot_write_late_result(self):
        entered = threading.Event()
        def execute(p, c):
            entered.set()
            c.wait(5)
            return answer(p, c)
        with CapacityRouter([Worker('a', 'a', {'browser': 1}, execute)]) as router:
            futures = router.submit('w', 'old', [request(i) for i in range(5)], time.monotonic() + 10)
            self.assertTrue(entered.wait(1))
            router.cancel('w', 'old')
            router.drain(1)
            self.assertTrue(all(f.result()['status_reason'] == 'WORKFLOW_CANCELED' for f in futures.values()))
            self.assertEqual(len([e for e in router.trace if e['event'] == 'dispatch']), 1)
            router.workers[0].execute = answer
            row = router.submit('w', 'new', [request(10)], time.monotonic() + 1)['10'].result(1)
            self.assertEqual(row['status'], 'Current')

    def test_deadline_includes_queue_and_does_not_turn_expiry_into_not_registered(self):
        def execute(p, c):
            c.wait(.2)
            return answer(p, c)
        with CapacityRouter([Worker('a', 'a', {'browser': 1}, execute)]) as router:
            futures = router.submit('w', 'sales', [request(i) for i in range(4)], time.monotonic() + .025)
            rows = [f.result(1) for f in futures.values()]
            router.drain(1)
            self.assertTrue(all(not r['success'] and r['status'] == 'Unable to Confirm' for r in rows))
            self.assertEqual(len([e for e in router.trace if e['event'] == 'dispatch']), 1)

    def test_uncooperative_worker_holds_capacity_until_it_actually_returns(self):
        release, entered = threading.Event(), threading.Event()
        def execute(p, c):
            entered.set()
            release.wait(1)
            return answer(p, c)
        with CapacityRouter([Worker('a', 'a', {'browser': 1}, execute)], max_workflows=1) as router:
            old = router.submit('w', 'old', [request()], time.monotonic() + 2)['0']
            self.assertTrue(entered.wait(1))
            router.cancel('w', 'old')
            self.assertTrue(old.done())
            new = router.submit('w', 'new', [request(1)], time.monotonic() + 2)['1']
            self.assertFalse(new.done())
            self.assertEqual(router.workers[0].active['browser'], 1)
            release.set()
            self.assertEqual(new.result(1)['status'], 'Current')
            self.assertEqual(old.result()['status_reason'], 'WORKFLOW_CANCELED')

    def test_cancellation_cannot_cross_workspace_boundary(self):
        def execute(p, c):
            c.wait(.01)
            return answer(p, c)
        with CapacityRouter([Worker('a', 'a', {'browser': 2}, execute)]) as router:
            first = router.submit('one', 'same-id', [request()], time.monotonic() + 1)['0']
            second = router.submit('two', 'same-id', [request(1)], time.monotonic() + 1)['1']
            self.assertFalse(router.cancel('unrelated', 'same-id'))
            router.cancel('one', 'same-id')
            self.assertEqual(first.result(1)['status_reason'], 'WORKFLOW_CANCELED')
            self.assertEqual(second.result(1)['status'], 'Current')

    def test_mismatched_ein_and_state_are_rejected_and_slots_released(self):
        for replacement in ({'ein': '999999999'}, {'state': 'XX'}):
            def bad(p, c):
                return {**answer(p, c), **replacement}
            with CapacityRouter([Worker('a', 'a', {'browser': 1}, bad)]) as router:
                row = router.submit('w', 'bad', [request()], time.monotonic() + 1)['0'].result(1)
                self.assertEqual(row['status'], 'Unable to Confirm')
                router.drain()
                self.assertEqual(router.workers[0].active['browser'], 0)

    def test_worker_exception_is_conservative_and_does_not_leak_secrets(self):
        def bad(p, c):
            raise RuntimeError('SECRET_TOKEN_SHOULD_NOT_ESCAPE')
        with CapacityRouter([Worker('a', 'a', {'browser': 1}, bad)]) as router:
            row = router.submit('w', 'bad', [request()], time.monotonic() + 1)['0'].result(1)
            self.assertEqual(row['status'], 'Unable to Confirm')
            self.assertNotIn('SECRET', str(row))
            router.drain()

    def test_unhealthy_worker_is_excluded_before_dispatch(self):
        with CapacityRouter([Worker('a', 'a', {'browser': 2}, answer, healthy=False),
                             Worker('b', 'b', {'browser': 1}, answer)]) as router:
            self.assertEqual(router.submit('w', 'one', [request()], time.monotonic() + 1)['0'].result(1)['status'], 'Current')
            self.assertEqual([e['worker'] for e in router.trace if e['event'] == 'dispatch'], ['b'])

    def test_download_work_is_not_blocked_by_full_browser_lane(self):
        release, entered = threading.Event(), threading.Event()
        def execute(p, c):
            if p['state'] == 'CA':
                entered.set()
                release.wait(1)
            return answer(p, c)
        with CapacityRouter([Worker('a', 'a', {'browser': 1, 'data': 1}, execute)]) as router:
            rows = router.submit('w', 'one', [request(), request(1, 'DC', 'data')], time.monotonic() + 2)
            self.assertTrue(entered.wait(1))
            self.assertEqual(rows['1'].result(.5)['state'], 'DC')
            self.assertFalse(rows['0'].done())
            release.set()

    def test_same_profile_registry_queue_serializes_and_preserves_pacing(self):
        def execute(p, c):
            c.wait(.005)
            return answer(p, c)
        with CapacityRouter([Worker('a', 'a', {'browser': 4}, execute)],
                            registry_limits={'ny-profile': 1}, registry_intervals={'ny-profile': .015}) as router:
            rows = router.submit('w', 'one', [request(i, 'NY', registry='ny-profile') for i in range(3)], time.monotonic() + 2)
            [f.result(2) for f in rows.values()]
            router.drain()
            events = [e for e in router.trace if e['event'] in ('dispatch', 'finished')]
            self.assertEqual([e['event'] for e in events], ['dispatch', 'finished'] * 3)
            self.assertGreaterEqual(events[2]['at'] - events[1]['at'], .014)

    def test_caller_mutation_cannot_change_submitted_identity_or_aliases(self):
        gate = threading.Event()
        def execute(p, c):
            gate.wait(1)
            return answer(p, c)
        job = request()
        original = copy.deepcopy(job.payload)
        with CapacityRouter([Worker('a', 'a', {'browser': 1}, execute)]) as router:
            f = router.submit('w', 'one', [job], time.monotonic() + 2)['0']
            job.payload['ein'] = '999999999'
            job.payload['alternate_names'].clear()
            gate.set()
            row = f.result(1)
            self.assertEqual(row['ein'], original['ein'])
            self.assertEqual(row['alternate_names'], original['alternate_names'])

    def test_fairness_does_not_drain_one_waiting_workflow_before_the_rest(self):
        with CapacityRouter([Worker('a', 'a', {'browser': 1}, answer, healthy=False)]) as router:
            for i in range(15):
                router.submit('w', str(i), [request(i * 3 + j) for j in range(3)], time.monotonic() + 3)
            router.set_health('a', True)
            router.drain(3)
            first = [e['workflow'] for e in router.trace if e['event'] == 'dispatch'][:15]
            self.assertEqual(len(set(first)), 15)

    def test_expired_requests_never_enter_workers(self):
        def forbidden(p, c):
            self.fail('Expired work reached worker')
        with CapacityRouter([Worker('a', 'a', {'browser': 1}, forbidden)]) as router:
            row = router.submit('w', 'old', [request()], time.monotonic() - 1)['0'].result(1)
            self.assertEqual(row['status_reason'], 'DEADLINE_EXCEEDED')
            self.assertFalse(any(e['event'] == 'dispatch' for e in router.trace))

    def test_multiple_organizations_cannot_bypass_limit_inside_one_workflow(self):
        with CapacityRouter([Worker('a', 'a', {'browser': 1}, answer)]) as router:
            with self.assertRaises(ValueError):
                router.submit('w', 'combined', [request(0, org=0), request(1, org=1)], time.monotonic() + 1)
            self.assertFalse(router.flows)


if __name__ == '__main__':
    unittest.main(verbosity=2)
