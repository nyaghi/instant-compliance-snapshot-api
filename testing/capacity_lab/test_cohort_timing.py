"""Unfinished long searches must not disappear from Sales timing estimates."""
import ast, os, subprocess, unittest, uuid
from pathlib import Path
from unittest.mock import Mock, patch
from deployment.durable_queue import cohort_timing_estimates, DurationEstimates, sales_tail_scores
from testing.capacity_lab.cohort_scope import strip_cohort_timing
from testing.capacity_lab import test_durable_queue as dbtests

FLAGS={'CE_LAB_SALES_COHORT_TIMING':'1','CE_LAB_SALES_TAIL_CENSORING':'1'}
def workflows(mode='sales',kind='registration',before=100000):
    return [{'id':s,'mode':mode,'kind':kind,'submitted':before} for s in ['a','b']]

class CohortTiming(unittest.TestCase):
    def queue(self):
        q=Mock();q.sales_policy='tail-aware';q._cohort_timing_cache=None
        return q

    def test_same_cohort_keeps_prearrival_sample_and_only_metadata_is_read(self):
        q=self.queue();c=Mock()
        c.execute.side_effect=[[{'state':'SC','seconds':1,'tail_seconds':33}], [{'state':'SC','tail_seconds':20}]]
        with patch.dict(os.environ,FLAGS):
            first=cohort_timing_estimates(q,c,100001,{'SC'},'v-performance-lab',workflows())
            second=cohort_timing_estimates(q,c,100045,{'SC'},'v-performance-lab',workflows())
        self.assertIs(first,second);self.assertEqual(first['SC'],1);self.assertEqual(first.tails['SC'],33)
        self.assertEqual(first.as_of,100000);self.assertEqual(c.execute.call_count,2)
        for call in c.execute.call_args_list:
            sql,params=call.args
            self.assertIn('finished<=%s',sql);self.assertIn('LIMIT 20',sql)
            self.assertEqual(params,(['SC'],13600,100000))
            self.assertNotIn('result',sql);self.assertNotIn('payload',sql)
        q.cached_duration_estimates.assert_not_called()

    def test_cache_invalidates_for_new_cohort_version_or_unseen_state(self):
        q=self.queue();c=Mock();c.execute.return_value=[]
        with patch.dict(os.environ,FLAGS):
            for version,before,states in [('v-performance-lab',100000,{'SC'}),
                    ('v-performance-lab',100010,{'SC'}),('next-performance-lab',100010,{'SC'}),
                    ('next-performance-lab',100010,{'SC','MI'})]:
                cohort_timing_estimates(q,c,100020,states,version,workflows(before=before))
        self.assertEqual(c.execute.call_count,8)

    def test_single_standard_mixed_discovery_optout_foreign_version_and_bad_clock_keep_original(self):
        cases=[(workflows()[:1],{},'v-performance-lab',100001),
            (workflows(mode='standard'),{},'v-performance-lab',100001),
            ([workflows()[0],workflows(mode='standard')[1]],{},'v-performance-lab',100001),
            (workflows(kind='discovery'),{},'v-performance-lab',100001),
            (workflows(),{'CE_LAB_SALES_COHORT_TIMING':'0'},'v-performance-lab',100001),
            (workflows(),{},'production',100001),(workflows(),{},'v-performance-lab',99999),
            (workflows(),{},'v-performance-lab',100061)]
        for ws,flags,version,now in cases:
            with self.subTest(ws=ws,flags=flags,version=version,now=now):
                q=self.queue();c=Mock()
                with patch.dict(os.environ,{**FLAGS,**flags}):
                    self.assertIs(cohort_timing_estimates(q,c,now,{'SC'},version,ws),q.cached_duration_estimates.return_value)
                q.cached_duration_estimates.assert_called_once_with(c,now,{'SC'},version)
                c.execute.assert_not_called()

    def test_spare_lanes_cannot_shorten_one_remaining_search(self):
        estimates=DurationEstimates([{'state':'SC','seconds':1,'tail_seconds':33}])
        ws=workflows();jobs={'a':[{'state':'SC'}]}
        old=sales_tail_scores(ws,jobs,[],estimates,{'SC':4})
        self.assertEqual(old['SC'],8.25)
        estimates.as_of=100000
        self.assertEqual(sales_tail_scores(ws,jobs,[],estimates,{'SC':4})['SC'],33)
        jobs['a']*=8
        self.assertEqual(sales_tail_scores(ws,jobs,[],estimates,{'SC':4})['SC'],66)

    def test_whole_queue_outside_timing_is_identical_to_prior_working_order(self):
        root=Path(__file__).resolve().parents[2]
        old=ast.parse(subprocess.check_output(['git','show','4c9b3af:deployment/durable_queue.py'],cwd=root).decode())
        new=ast.parse((root/'deployment/durable_queue.py').read_text());strip_cohort_timing(new)
        self.assertEqual(ast.dump(old),ast.dump(new))


@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Real lab Postgres required')
class CohortRealDB(unittest.TestCase):
    setUp=dbtests.DurableTests.setUp
    tearDown=dbtests.DurableTests.tearDown
    submit=dbtests.DurableTests.submit
    worker=dbtests.DurableTests.worker
    finish=dbtests.DurableTests.finish

    def test_new_quick_completions_do_not_evict_precohort_slow_history(self):
        ident=self.submit();worker=self.worker();self.finish(self.q.claim(worker))
        self.q.sales_policy='tail-aware'
        with self.q.transaction() as (c,now):
            before=now-100
            samples=[(1,before-1-i,None) for i in range(18)]
            samples += [(33,before-.5,None),(33,before-.1,None)]
            samples += [(1,before+5+i*.01,None) for i in range(20)]
            samples += [(299,before-.05,'HTTP_500')]
            for duration,finished,error in samples:
                history=uuid.uuid4().hex
                c.execute("INSERT INTO cc_lab_workflows SELECT %s,scope,ein,fingerprint,payload,kind,mode,source_version,"
                    "phase,stop_reason,submitted,deadline,started,finished,dispatched FROM cc_lab_workflows WHERE id=%s",(history,ident))
                c.execute("INSERT INTO cc_lab_jobs(id,workflow_id,state,resources,weight,phase,attempt,claimed,finished,error) "
                    "VALUES (%s,%s,'SC','[]',1,'done',1,%s,%s,%s)",(uuid.uuid4().hex,history,finished-duration,finished,error))
            current=self.q.duration_estimates(c,before+10,{'SC'})
            self.assertEqual(current['SC'],1);self.assertEqual(current.tails['SC'],1)
            with patch.dict(os.environ,FLAGS):
                snapshot=cohort_timing_estimates(self.q,c,before+10,{'SC'},'fixture-performance-lab',workflows(before=before))
                self.assertEqual(snapshot['SC'],1);self.assertEqual(snapshot.tails['SC'],33)
                self.assertEqual(snapshot.as_of,before)
                self.assertIs(cohort_timing_estimates(self.q,c,before+50,{'SC'},'fixture-performance-lab',workflows(before=before)),snapshot)

if __name__=='__main__':unittest.main()
