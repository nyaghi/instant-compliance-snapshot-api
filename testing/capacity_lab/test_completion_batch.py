"""Reaped-task persistence and passive Florida diagnostics preserve behavior."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from psycopg import DataError

from deployment.queue_engine import FloridaTrace, execute
from deployment.queue_worker import Supervisor


class CompletionBatchTests(unittest.TestCase):
    def supervisor(self):
        s = object.__new__(Supervisor)
        s.id, s.queue = 'worker', Mock()
        s.active = {str(i): {'terminated': i != 2, 'job': {'token': str(i)},
            'result': {'status': 'Current'}, 'error': None, 'temp': Mock()} for i in range(3)}
        return s

    def test_only_reaped_tasks_persist_and_live_capacity_stays_held(self):
        s = self.supervisor(); original = dict(s.active)
        s.persist_terminated()
        self.assertEqual(set(s.active), {'2'})
        self.assertEqual([r[0] for r in s.queue.complete_many.call_args.args[1]], ['0', '1'])
        original['0']['temp'].cleanup.assert_called_once()
        original['1']['temp'].cleanup.assert_called_once()
        original['2']['temp'].cleanup.assert_not_called()

    def test_db_failure_preserves_all_reservations_for_retry(self):
        s = self.supervisor(); s.queue.complete_many.side_effect = [OSError('offline'), [True, True]]
        s.persist_terminated()
        self.assertEqual(len(s.active), 3)
        for r in s.active.values(): r['temp'].cleanup.assert_not_called()
        s.persist_terminated(); self.assertEqual(set(s.active), {'2'})

    def test_bad_output_isolated_without_discarding_good_task(self):
        for error in (ValueError('identity'), DataError('invalid JSON data')):
            with self.subTest(error=type(error).__name__):
                s = self.supervisor(); s.queue.complete_many.side_effect = error
                s.queue.complete.side_effect = [error, True, True]
                s.persist_terminated()
                self.assertEqual(set(s.active), {'2'})
                self.assertEqual(s.queue.complete.call_args_list[1].kwargs, {'error': 'WORKER_RESULT_REJECTED'})

    def test_individual_persistence_failure_still_keeps_its_capacity(self):
        s = self.supervisor(); s.queue.complete_many.side_effect = ValueError('bad batch')
        s.queue.complete.side_effect = [OSError('retry'), True]
        s.persist_terminated(); self.assertEqual(set(s.active), {'0', '2'})


class FloridaTraceTests(unittest.TestCase):
    def test_preserves_return_and_exception_and_removes_hooks(self):
        for error in (None, ValueError('original failure')):
            page = Mock(); trace = FloridaTrace(); sentinel = object()
            original = Mock(return_value=sentinel, side_effect=error)
            if error:
                with self.assertRaisesRegex(ValueError, 'original failure'): trace.wrap(original)(page, 'org')
            else: self.assertIs(trace.wrap(original)(page, 'org'), sentinel)
            self.assertEqual(page.on.call_args_list, page.remove_listener.call_args_list)
            original.assert_called_once_with(page, 'org')

    def test_redacts_query_fragment_and_never_reads_headers(self):
        trace = FloridaTrace()
        request = SimpleNamespace(url='https://registry.example/search?token=secret#secret',
                                  method='POST', resource_type='document')
        trace.request('request', request)
        self.assertEqual(trace.events[0]['path'], '/search')
        self.assertNotIn('secret', str(trace.events))
        trace.request('request', object())  # Malformed observation cannot raise.

    def test_restores_master_wrapper_on_success_and_failure(self):
        original = Mock(return_value='result')
        master = SimpleNamespace(APP_VERSION='test', SUPPORTED_STATES=['FL'], search_fl=original,
                                 normalize_organization_requests=lambda *a, **k: ['org'])
        job = {'version':'test','state':'FL','payload':{}}
        def run(*args):
            self.assertEqual(master.search_fl(Mock(), 'org'), 'result')
            return [{'status':'Current'}]
        master.run_state_lookups_parallel = run
        result = execute(master, job)
        self.assertEqual(result['status'], 'Current'); self.assertTrue(result['lab_fl_trace'])
        self.assertIs(master.search_fl, original)
        master.run_state_lookups_parallel = Mock(side_effect=RuntimeError('source error'))
        with self.assertRaisesRegex(RuntimeError, 'source error'): execute(master, job)
        self.assertIs(master.search_fl, original)


if __name__ == '__main__': unittest.main(verbosity=2)
