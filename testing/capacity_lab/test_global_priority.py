"""Cross-organization urgency must not bypass any capacity or identity guard."""
import ast,collections,os,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
from deployment.durable_queue import claim_candidates,DurationEstimates
from testing.capacity_lab.global_priority_scope import strip_global_priority
from testing.capacity_lab import test_durable_queue as dbtests

class GlobalPriority(unittest.TestCase):
    def fixture(self):
        ws=[dict(id=x,mode='sales',kind='registration',deadline=60,submitted=0,dispatched=0) for x in ['easy','slow']]
        pending={x:[dict(id=x+s,state=s,workflow_id=x) for s in (['CO'] if x=='easy' else ['ME'])] for x in ['easy','slow']}
        estimates=DurationEstimates([dict(state='CO',seconds=1,tail_seconds=1),dict(state='ME',seconds=30,tail_seconds=30)])
        estimates.as_of=0
        return ws,pending,collections.Counter({'slow':4}),estimates,{'CO':1,'ME':30}

    def call(self,parts,now=0,version='fixture-performance-lab',protected=None):
        return claim_candidates(*parts,now,version,protected)

    def test_long_eligible_source_precedes_easy_org_without_erasing_candidates(self):
        parts=self.fixture()
        with patch.dict(os.environ,{'CE_LAB_SALES_GLOBAL_PRIORITY':'1'}):
            choices=self.call(parts)
        self.assertEqual([w['id'] for w,j in choices],['slow','easy'])
        self.assertEqual([w['id'] for w in parts[0]],['easy','slow'])
        self.assertEqual(sum(len(x) for x in parts[1].values()),len(choices))

    def test_fairness_breaks_equal_priority_and_infeasible_search_keeps_last(self):
        parts=self.fixture();parts[4]['CO']=30
        with patch.dict(os.environ,{'CE_LAB_SALES_GLOBAL_PRIORITY':'1'}):
            self.assertEqual(self.call(parts)[0][0]['id'],'easy')
            parts[4]['CO']=1
            self.assertEqual(self.call(parts,now=40)[0][0]['id'],'easy')
            parts[1]['slow'].insert(0,dict(id='seed',state='@sales_identity',workflow_id='slow'))
            self.assertEqual(self.call(parts,now=40)[0][1]['state'],'@sales_identity')

    def test_optout_individual_mixed_discovery_protected_and_scarce_keep_original(self):
        for case in ['flag','single','mixed','discovery','protected','scarce','unfrozen','foreign']:
            parts=self.fixture();ws,pending,running,estimates,scores=parts
            if case=='single':ws[:]=ws[:1]
            if case=='mixed':ws[1]['mode']='standard'
            if case=='discovery':ws[1]['kind']='discovery'
            if case=='scarce':scores.clear()
            if case=='unfrozen':del estimates.as_of
            with self.subTest(case=case),patch.dict(os.environ,{'CE_LAB_SALES_GLOBAL_PRIORITY':'0' if case=='flag' else '1'}):
                actual=self.call(parts,version='production' if case=='foreign' else 'fixture-performance-lab',
                                 protected={'id':'p'} if case=='protected' else None)
                self.assertEqual(actual,[(w,j) for w in ws for j in pending[w['id']]])

    def test_all_admission_deadline_identity_and_result_code_is_unchanged(self):
        root=Path(__file__).resolve().parents[2]
        before=ast.parse(subprocess.check_output(['git','show','0339eeb:deployment/durable_queue.py'],cwd=root).decode())
        after=ast.parse((root/'deployment/durable_queue.py').read_text())
        strip_global_priority(after);self.assertEqual(ast.dump(before),ast.dump(after))

@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Real lab Postgres required')
class GlobalRealDB(unittest.TestCase):
    setUp=dbtests.DurableTests.setUp
    tearDown=dbtests.DurableTests.tearDown
    submit=dbtests.DurableTests.submit
    worker=dbtests.DurableTests.worker
    finish=dbtests.DurableTests.finish

    def test_global_urgency_uses_free_lane_and_preserves_source_reservation(self):
        self.q.sales_policy='tail-aware';worker=self.worker(slots=12)
        estimates=DurationEstimates([dict(state='CO',seconds=1,tail_seconds=1),dict(state='ME',seconds=30,tail_seconds=30)])
        estimates.as_of=0
        slow=self.submit(dbtests.payload(states=['CO','ME'],mode='sales'))
        with patch('deployment.durable_queue.cohort_timing_estimates',return_value=estimates),patch.dict(os.environ,{'CE_LAB_SALES_GLOBAL_PRIORITY':'1'}):
            first=self.q.claim(worker);self.assertEqual(first['state'],'CO')
            easy=self.submit(dbtests.payload(ein='987654321',states=['CO'],mode='sales'))
            chosen=self.q.claim(worker)
            self.assertEqual((chosen['workflow_id'],chosen['state']),(slow,'ME'))
            next_job=self.q.claim(worker)
            self.assertEqual((next_job['workflow_id'],next_job['state']),(easy,'CO'))
            waiting=self.submit(dbtests.payload(ein='112233445',states=['ME'],mode='sales'))
            self.assertIsNone(self.q.claim(worker),'The second ME query must retain its source cap')
            self.finish(chosen)
            last=self.q.claim(worker);self.assertEqual((last['workflow_id'],last['state']),(waiting,'ME'))
            for job in [first,next_job,last]:self.finish(job)
        for ident in [slow,easy,waiting]:
            status=self.q.status('a',ident)
            self.assertEqual(status['deadline']-status['submitted'],60)
            self.assertIsNotNone(status['finished'])

if __name__=='__main__':unittest.main()
