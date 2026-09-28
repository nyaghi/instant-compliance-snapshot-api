"""A rare live path must survive a small sample dominated by fast file hits."""
import ast, os, subprocess, unittest, uuid
from pathlib import Path
from unittest.mock import Mock, patch
from deployment.durable_queue import cohort_timing_estimates, sales_tail_scores
from testing.capacity_lab.test_cohort_timing import workflows
from testing.capacity_lab import test_durable_queue as fixtures

FLAGS = {'CE_LAB_SALES_COHORT_TIMING':'1', 'CE_LAB_SALES_TAIL_CENSORING':'1',
         'CE_LAB_SALES_WORKLOAD_TIMING':'1', 'CE_LAB_SALES_OBSERVED_TAIL':'1'}

class ObservedTail(unittest.TestCase):
    def queue(self):
        q=Mock(); q.sales_policy='tail-aware'; q._cohort_timing_cache=None
        return q

    def test_small_sample_preserves_one_slow_path_without_multiplying_it(self):
        q=self.queue(); c=Mock()
        c.execute.side_effect=[[dict(state='OR',seconds=1,tail_seconds=30,mean_seconds=2.45)],
                              [dict(state='OR',tail_seconds=30,mean_seconds=2.45)]]
        with patch.dict(os.environ,FLAGS):
            values=cohort_timing_estimates(q,c,100001,{'OR'},'test-performance-lab',workflows())
        self.assertEqual(values['OR'],1); self.assertEqual(values.tails['OR'],30)
        self.assertEqual(values.means['OR'],2.45)
        pending={'a':[dict(state='OR') for _ in range(20)]}
        self.assertAlmostEqual(sales_tail_scores(workflows(),pending,[],values,{'OR':4})['OR'],39.8)
        for call in c.execute.call_args_list:
            sql,params=call.args
            self.assertIn('max(recent.seconds) AS tail_seconds',sql)
            self.assertIn('ORDER BY finished DESC LIMIT 20',sql)
            self.assertIn('finished<=%s',sql)
            self.assertEqual(params,(['OR'],13600,100000))
            for private in ['result','payload','ein']: self.assertNotIn(private,sql)

    def test_disabled_flag_preserves_percentile_and_invalidates_cached_policy(self):
        q=self.queue(); c=Mock(); c.execute.return_value=[]
        with patch.dict(os.environ,FLAGS):
            first=cohort_timing_estimates(q,c,100001,{'OR'},'test-performance-lab',workflows())
            self.assertIs(first,cohort_timing_estimates(q,c,100010,{'OR'},'test-performance-lab',workflows()))
            with patch.dict(os.environ,{'CE_LAB_SALES_OBSERVED_TAIL':'0'}):
                second=cohort_timing_estimates(q,c,100011,{'OR'},'test-performance-lab',workflows())
        self.assertIsNot(first,second); self.assertFalse(second.observed_tail)
        self.assertEqual(c.execute.call_count,4)
        self.assertIn('percentile_cont(0.95)',c.execute.call_args.args[0])

    def test_single_standard_mixed_discovery_and_nonlab_retain_original_estimator(self):
        for ws,version in [(workflows()[:1],'v-performance-lab'),
                (workflows(mode='standard'),'v-performance-lab'),
                ([workflows()[0],workflows(mode='standard')[1]],'v-performance-lab'),
                (workflows(kind='discovery'),'v-performance-lab'),(workflows(),'production')]:
            q=self.queue(); c=Mock()
            with patch.dict(os.environ,FLAGS):
                result=cohort_timing_estimates(q,c,100001,{'OR'},version,ws)
            self.assertIs(result,q.cached_duration_estimates.return_value)
            c.execute.assert_not_called()

    def test_registry_deadlines_admission_matching_and_all_other_queue_functions_unchanged(self):
        root=Path(__file__).resolve().parents[2]
        old=ast.parse(subprocess.check_output(['git','show','3383085:deployment/durable_queue.py'],cwd=root).decode())
        new=ast.parse((root/'deployment/durable_queue.py').read_text())
        old_fn=next(n for n in old.body if getattr(n,'name','')=='cohort_timing_estimates')
        new_fn=next(n for n in new.body if getattr(n,'name','')=='cohort_timing_estimates')
        self.assertNotEqual(ast.dump(old_fn),ast.dump(new_fn))
        from testing.capacity_lab.observed_tail_scope import strip_observed_tail
        strip_observed_tail(new)
        self.assertEqual(ast.dump(old),ast.dump(new))
        subprocess.run(['git','diff','--exit-code','3383085','--',
            'CharityClarity_WA_NM_checker.py',
            'deployment/queue_schema.sql','deployment/lab_capacity.py','web-staging','browser-connector'],
            cwd=root,check=True,capture_output=True)
        from testing.capacity_lab.failure_label_scope import assert_diagnostics_only
        for path in ['deployment/queue_engine.py','deployment/queue_worker.py']:
            assert_diagnostics_only(root,'3383085',path)
        from testing.capacity_lab.ok_detail_scope import assert_ok_detail_only
        assert_ok_detail_only(root,'3383085')

@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Real isolated Postgres schema required')
class ObservedTailDB(unittest.TestCase):
    setUp=fixtures.DurableTests.setUp
    tearDown=fixtures.DurableTests.tearDown
    submit=fixtures.DurableTests.submit
    worker=fixtures.DurableTests.worker
    finish=fixtures.DurableTests.finish

    def test_one_slow_completed_query_in_twenty_keeps_full_tail_and_original_median(self):
        ident=self.submit(); worker=self.worker(); self.finish(self.q.claim(worker))
        self.q.sales_policy='tail-aware'
        with self.q.transaction() as (c,now):
            before=now-100
            samples=[(1,before-1-i,None) for i in range(19)]+[(30,before-.5,None)]
            samples += [(299,before-.1,'HTTP_500'),(1,before+1,None)]
            for duration,finished,error in samples:
                hist=uuid.uuid4().hex
                c.execute('INSERT INTO cc_lab_workflows SELECT %s,scope,ein,fingerprint,payload,kind,mode,source_version,'
                    'phase,stop_reason,submitted,deadline,started,finished,dispatched FROM cc_lab_workflows WHERE id=%s',(hist,ident))
                c.execute("INSERT INTO cc_lab_jobs(id,workflow_id,state,resources,weight,phase,attempt,claimed,finished,error) "
                    "VALUES (%s,%s,'OR','[]',1,'done',1,%s,%s,%s)",(uuid.uuid4().hex,hist,finished-duration,finished,error))
            with patch.dict(os.environ,FLAGS):
                values=cohort_timing_estimates(self.q,c,before+10,{'OR'},'test-performance-lab',workflows(before=before))
            self.assertEqual(values['OR'],1); self.assertEqual(values.tails['OR'],30)
            self.assertAlmostEqual(values.means['OR'],2.45)
            with patch.dict(os.environ,{**FLAGS,'CE_LAB_SALES_OBSERVED_TAIL':'0'}):
                prior=cohort_timing_estimates(self.q,c,before+11,{'OR'},'test-performance-lab',workflows(before=before))
            self.assertAlmostEqual(prior.tails['OR'],2.45)

if __name__=='__main__': unittest.main()
