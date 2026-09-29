"""Source-wide queue work must not multiply one exceptional lookup by a cohort."""
import ast,collections,os,subprocess,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from deployment.durable_queue import DurationEstimates,sales_tail_scores,cohort_timing_estimates,claim_candidates
from testing.capacity_lab.workload_timing_scope import strip_workload_timing
from testing.capacity_lab import test_durable_queue as dbtests

FLAGS={'CE_LAB_SALES_COHORT_TIMING':'1','CE_LAB_SALES_TAIL_CENSORING':'1','CE_LAB_SALES_WORKLOAD_TIMING':'1','CE_LAB_SALES_GLOBAL_PRIORITY':'1'}

def ws():
    return [dict(id=str(i),mode='sales',kind='registration',submitted=100000,deadline=100060,dispatched=0) for i in range(20)]

class WorkloadTiming(unittest.TestCase):
    def test_exceptional_source_does_not_starve_consistently_slower_source(self):
        estimates=DurationEstimates([dict(state='SC',seconds=1,mean_seconds=4,tail_seconds=31),dict(state='WA',seconds=20,mean_seconds=20,tail_seconds=24)])
        estimates.as_of=100000
        pending={w['id']:[dict(id=w['id']+s,state=s) for s in ['SC','WA']] for w in ws()}
        old=sales_tail_scores(ws(),pending,[],estimates,{'SC':4,'WA':8})
        self.assertGreater(old['SC'],old['WA'])
        estimates.workload_timing=True
        scores=sales_tail_scores(ws(),pending,[],estimates,{'SC':4,'WA':8})
        self.assertEqual(scores,{'SC':47,'WA':54})
        with patch.dict(os.environ,FLAGS):
            candidates=claim_candidates(ws(),pending,collections.Counter(),estimates,scores,100001,'test-performance-lab',None)
        self.assertEqual(candidates[0][1]['state'],'WA')
        self.assertEqual(len(candidates),40)

    def test_last_wave_keeps_tail_and_source_capacity_counts_running(self):
        estimates=DurationEstimates([dict(state='WA',seconds=10,mean_seconds=12,tail_seconds=30)])
        estimates.as_of=100000;estimates.workload_timing=True
        pending={'0':[{'state':'WA'}]}
        self.assertEqual(sales_tail_scores(ws(),pending,[],estimates,{'WA':8}),{'WA':30})
        held=[dict(state='WA',workflow_id='1') for _ in range(8)]
        self.assertEqual(sales_tail_scores(ws(),pending,held,estimates,{'WA':8}),{'WA':31.5})
        self.assertEqual(sales_tail_scores(ws()[:1],pending,held,estimates,{'WA':8}),{})

    def test_busy_organization_does_not_lose_equal_source_turn_to_later_deadline(self):
        workflows=ws()[:2];workflows[1].update(submitted=100001,deadline=100061)
        estimates=DurationEstimates([dict(state='WA',seconds=10,tail_seconds=20,mean_seconds=12)])
        estimates.as_of=100000
        pending={w['id']:[dict(id=w['id']+'WA',state='WA')] for w in workflows}
        running=collections.Counter({'0':9,'1':0})
        with patch.dict(os.environ,FLAGS):
            old=claim_candidates(workflows,pending,running,estimates,{'WA':20},100003,'test-performance-lab',None)
            self.assertEqual(old[0][0]['id'],'1')
            estimates.workload_timing=True
            new=claim_candidates(workflows,pending,running,estimates,{'WA':20},100003,'test-performance-lab',None)
            self.assertEqual([w['id'] for w,j in new],['0','1'])
            self.assertEqual(len(new),len(old))

    def test_frozen_metadata_includes_censored_duration_but_never_result_or_identity(self):
        q=Mock();q.sales_policy='tail-aware';q._cohort_timing_cache=None
        c=Mock();c.execute.side_effect=[[dict(state='WA',seconds=8,tail_seconds=20,mean_seconds=10)],[dict(state='WA',tail_seconds=26,mean_seconds=13)]]
        with patch.dict(os.environ,FLAGS):
            values=cohort_timing_estimates(q,c,100003,{'WA'},'test-performance-lab',ws())
            self.assertIs(values,cohort_timing_estimates(q,c,100030,{'WA'},'test-performance-lab',ws()))
        self.assertEqual(values.means,{'WA':13});self.assertEqual(values.tails,{'WA':26})
        self.assertEqual(values['WA'],8);self.assertTrue(values.workload_timing)
        self.assertEqual(c.execute.call_count,2)
        for call in c.execute.call_args_list:
            sql,params=call.args
            self.assertIn('avg(recent.seconds)',sql);self.assertIn('LIMIT 20',sql)
            self.assertNotIn('result',sql);self.assertNotIn('ein',sql);self.assertNotIn('payload',sql)
            self.assertEqual(params,(['WA'],13600,100000))

    def test_flag_change_does_not_reuse_other_policy_cache(self):
        q=Mock();q.sales_policy='tail-aware';q._cohort_timing_cache=None;c=Mock();c.execute.return_value=[]
        with patch.dict(os.environ,FLAGS):
            first=cohort_timing_estimates(q,c,100001,{'WA'},'test-performance-lab',ws())
            with patch.dict(os.environ,{'CE_LAB_SALES_WORKLOAD_TIMING':'0'}):
                second=cohort_timing_estimates(q,c,100002,{'WA'},'test-performance-lab',ws())
        self.assertIsNot(first,second);self.assertFalse(second.workload_timing)
        self.assertEqual(c.execute.call_count,4)

    def test_unknown_source_preserves_full_default_tail(self):
        estimates=DurationEstimates([]);estimates.as_of=100000;estimates.workload_timing=True
        self.assertEqual(sales_tail_scores(ws(),{'0':[dict(state='WA')]},[],estimates,{'WA':4}),{'WA':10})

    def test_only_elapsed_time_estimating_changed(self):
        root=Path(__file__).resolve().parents[2]
        old=ast.parse(subprocess.check_output(['git','show','1f0cc4f:deployment/durable_queue.py'],cwd=root).decode())
        new=ast.parse((root/'deployment/durable_queue.py').read_text());strip_workload_timing(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Real lab Postgres required')
class WorkloadRealDB(unittest.TestCase):
    setUp=dbtests.DurableTests.setUp
    tearDown=dbtests.DurableTests.tearDown
    submit=dbtests.DurableTests.submit
    worker=dbtests.DurableTests.worker
    finish=dbtests.DurableTests.finish

    def test_changed_priority_keeps_caps_identity_and_hard_deadline(self):
        self.q.sales_policy='tail-aware';worker=self.worker(slots=12)
        with self.q.transaction() as (c,now):
            c.execute("UPDATE cc_lab_settings SET registry_limits=jsonb_set(registry_limits,'{CO}','1') WHERE id=1")
        a=self.submit(dbtests.payload(states=['CO','ME'],mode='sales'))
        b=self.submit(dbtests.payload(ein='987654321',states=['CO','ME'],mode='sales'))
        estimates=DurationEstimates([dict(state='CO',seconds=1,tail_seconds=30,mean_seconds=1),dict(state='ME',seconds=20,tail_seconds=25,mean_seconds=20)])
        estimates.as_of=1;estimates.workload_timing=True
        with patch('deployment.durable_queue.cohort_timing_estimates',return_value=estimates),patch.dict(os.environ,FLAGS):
            jobs=[self.q.claim(worker),self.q.claim(worker)]
            self.assertEqual({j['state'] for j in jobs},{'CO','ME'})
            self.assertIsNone(self.q.claim(worker),'Each source still has its existing one-job cap')
            for j in jobs:self.finish(j)
            remaining=[self.q.claim(worker),self.q.claim(worker)]
            self.assertEqual({j['state'] for j in remaining},{'CO','ME'})
            for j in remaining:self.finish(j)
        for ident in [a,b]:
            result=self.q.status('a',ident)
            self.assertEqual(result['deadline']-result['submitted'],60)
            self.assertIsNotNone(result['finished'])

if __name__=='__main__':unittest.main()
