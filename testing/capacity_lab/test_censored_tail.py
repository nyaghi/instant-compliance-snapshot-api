"""Deadline-truncated timing informs priority, never status or deadlines."""
import ast, os, subprocess, unittest, uuid
from pathlib import Path
from unittest.mock import Mock, patch
from deployment.durable_queue import Queue, DurationEstimates, apply_censored_tail_floor, order_pending, sales_tail_scores
from testing.capacity_lab.test_sales_tail import job, workflow
from testing.capacity_lab import test_durable_queue as dbtests


def strip_censored_tail(tree):
    from testing.capacity_lab.dispatch_scope import strip_dispatch_fairness
    strip_dispatch_fairness(tree)
    helper = next((n for n in tree.body if getattr(n, 'name', '') == 'apply_censored_tail_floor'), None)
    if helper is None: return
    tree.body.remove(helper)
    q = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Queue')
    fn = next(n for n in q.body if getattr(n, 'name', '') == 'cached_duration_estimates')
    additions = [n for n in fn.body if isinstance(n, ast.If) and 'CE_LAB_SALES_TAIL_CENSORING' in ast.unparse(n.test)]
    assert len(additions) == 1
    assert ast.unparse(additions[0].body[0]) == 'apply_censored_tail_floor(c, now, states, values)'
    fn.body.remove(additions[0])


def assert_queue_file_matches_ref(root, ref, path):
    original = subprocess.check_output(['git', 'show', ref+':'+path], cwd=root).decode()
    current = (root/path).read_text()
    if path == 'deployment/durable_queue.py':
        tree = ast.parse(current); strip_censored_tail(tree)
        assert ast.dump(tree) == ast.dump(ast.parse(original))
    elif path == 'deployment/queue_schema.sql':
        index = ("CREATE INDEX IF NOT EXISTS cc_lab_jobs_recent_tail ON cc_lab_jobs(state,finished DESC)\n"
                 " WHERE phase='done' AND (error IS NULL OR error IN ('WORKFLOW_DEADLINE','TASK_TIME_LIMIT'))\n"
                 " AND attempt=1 AND claimed IS NOT NULL;\n")
        assert current.count(index) == 1
        assert current.replace(index, '') == original
    else:
        raise AssertionError('Unexpected scope path')


class CensoredTail(unittest.TestCase):
    def estimates(self):
        return DurationEstimates([{'state': 'SC', 'seconds': 1, 'tail_seconds': 2},
                                  {'state': 'MI', 'seconds': 12, 'tail_seconds': 30}])

    def test_deadline_lower_bound_can_raise_tail_without_changing_completed_median(self):
        c = Mock(); c.execute.return_value = [{'state': 'SC', 'tail_seconds': 20}, {'state': 'MI', 'tail_seconds': 10}]
        values = self.estimates(); before = dict(values)
        apply_censored_tail_floor(c, 100000, {'SC', 'MI'}, values)
        self.assertEqual(values, before)
        self.assertEqual(values.tails, {'SC': 20, 'MI': 30})
        sql = c.execute.call_args.args[0]
        self.assertIn('LIMIT 20', sql)
        self.assertIn('WORKFLOW_DEADLINE', sql)
        self.assertNotIn('payload', sql); self.assertNotIn('result', sql)

    def test_single_sales_and_standard_keep_identical_order(self):
        values = self.estimates(); values.tails['SC'] = 60
        for mode, expected in [('sales', ['SC', 'MI']), ('standard', ['MI', 'SC'])]:
            w = workflow(mode=mode); jobs = [job('MI'), job('SC')]
            scores = sales_tail_scores([w], {'a': jobs}, [], values, {'SC': 4, 'MI': 4})
            self.assertEqual(scores, {})
            order_pending(w, jobs, values, scores, 0)
            self.assertEqual([j['state'] for j in jobs], expected)

    def test_explicit_opt_in_and_tail_policy_required_and_metadata_cache_retained(self):
        for policy, flag, expected in [('tail-aware', '1', 1), ('tail-aware', '', 0), ('shortest', '1', 0)]:
            q = Queue.__new__(Queue); q.sales_policy = policy; q._duration_cache = None
            q.duration_estimates = Mock(return_value=self.estimates())
            with patch.dict(os.environ, {'CE_LAB_SALES_TAIL_CENSORING': flag}), \
                 patch('deployment.durable_queue.apply_censored_tail_floor') as floor:
                q.cached_duration_estimates(None, 10, {'MI', 'SC'}, 'fixture-performance-lab')
                q.cached_duration_estimates(None, 12, {'MI', 'SC'}, 'fixture-performance-lab')
                self.assertEqual(floor.call_count, expected)
                q.duration_estimates.assert_called_once()

    def test_all_admission_fairness_cutoff_and_result_fences_are_identical(self):
        root = Path(__file__).resolve().parents[2]
        old = ast.parse(subprocess.check_output(['git', 'show', '93f0f95:deployment/durable_queue.py'], cwd=root).decode())
        new = ast.parse((root/'deployment/durable_queue.py').read_text())
        strip_censored_tail(new)
        self.assertEqual(ast.dump(old), ast.dump(new))

    def test_schema_only_adds_the_timing_index(self):
        assert_queue_file_matches_ref(Path(__file__).resolve().parents[2], '93f0f95', 'deployment/queue_schema.sql')


@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'), 'Real lab Postgres required')
class CensoredRealDB(unittest.TestCase):
    setUp = dbtests.DurableTests.setUp
    tearDown = dbtests.DurableTests.tearDown
    submit = dbtests.DurableTests.submit
    worker = dbtests.DurableTests.worker
    finish = dbtests.DurableTests.finish

    def test_indexed_tail_includes_recent_deadlines_excludes_other_failure_retry_and_stale_history(self):
        ident = self.submit(); worker = self.worker(); first = self.q.claim(worker); self.finish(first)
        with self.q.transaction() as (c, now):
            # 18 completed 1s calls and two 25s deadline truncations are the
            # newest eligible SC records. Unrelated failures cannot inflate it.
            samples = [(1, None, 1, i) for i in range(2, 20)]
            samples += [(25, 'WORKFLOW_DEADLINE', 1, 0), (25, 'TASK_TIME_LIMIT', 1, 1),
                        (299, 'CANCELED', 1, 0), (299, 'HTTP_500', 1, 0),
                        (299, 'WORKFLOW_DEADLINE', 2, 0), (299, 'WORKFLOW_DEADLINE', 1, 90000),
                        (299, 'WORKFLOW_DEADLINE', 1, 25)]
            for duration, error, attempt, age in samples:
                history = uuid.uuid4().hex; finished = now-age
                c.execute("INSERT INTO cc_lab_workflows SELECT %s,scope,ein,fingerprint,payload,kind,mode,source_version,"
                          "phase,stop_reason,submitted,deadline,started,finished,dispatched FROM cc_lab_workflows WHERE id=%s",
                          (history, ident))
                c.execute("INSERT INTO cc_lab_jobs(id,workflow_id,state,resources,weight,phase,attempt,claimed,finished,error) "
                          "VALUES (%s,%s,'SC','[]',1,'done',%s,%s,%s,%s)",
                          (uuid.uuid4().hex, history, attempt, finished-duration, finished, error))
            values = self.q.duration_estimates(c, now, {'SC'}); self.assertEqual(values['SC'], 1)
            self.assertEqual(values.tails['SC'], 1)
            apply_censored_tail_floor(c, now, {'SC'}, values)
            self.assertEqual(values['SC'], 1); self.assertEqual(values.tails['SC'], 25)
            index = c.execute("SELECT indexdef FROM pg_indexes WHERE schemaname=%s AND indexname='cc_lab_jobs_recent_tail'", (self.schema,)).fetchone()
            self.assertIsNotNone(index)


if __name__ == '__main__': unittest.main()
