"""Start spacing affects urgency without relaxing a single admission check."""
import ast,copy,os,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
from deployment.durable_queue import DurationEstimates,apply_paced_tail_floor
from testing.capacity_lab.paced_timing_scope import strip_paced_timing
from testing.capacity_lab import test_durable_queue as f

class PacedTiming(unittest.TestCase):
    def setUp(self):
        self.ws=[dict(id=str(i),mode='sales',kind='registration') for i in range(20)]
        self.pending={w['id']:[dict(state='FL'),dict(state='MD')] for w in self.ws}
        self.est=DurationEstimates([dict(state='FL',seconds=3,tail_seconds=25,mean_seconds=4)])
        self.est.workload_timing=True
        self.env=patch.dict(os.environ,{'CE_LAB_SALES_START_INTERVALS':'{"FL":1.5}'})
        self.env.start();self.addCleanup(self.env.stop)
    def test_full_backlog_includes_nineteen_start_intervals_and_one_tail(self):
        scores={'FL':35.,'MD':46.};before=copy.deepcopy(self.pending)
        apply_paced_tail_floor(scores,self.ws,self.pending,self.est,'x-performance-lab')
        self.assertEqual(scores,{'FL':53.5,'MD':46.});self.assertEqual(self.pending,before)
        self.assertEqual(self.est['FL'],3);self.assertEqual(self.est.tails['FL'],25)
    def test_fewer_waiting_jobs_do_not_charge_completed_or_running_starts(self):
        for count,want in [(1,25),(4,29.5),(0,5)]:
            scores={'FL':5};pending={w['id']:self.pending[w['id']] for w in self.ws[:count]}
            apply_paced_tail_floor(scores,self.ws,pending,self.est,'x-performance-lab')
            self.assertEqual(scores['FL'],want)
    def test_never_lowers_existing_duration_or_enables_disabled_policy(self):
        for scores in [{'FL':80},{}]:
            before=dict(scores);apply_paced_tail_floor(scores,self.ws,self.pending,self.est,'x-performance-lab')
            self.assertEqual(scores,before)
        self.est.workload_timing=False;scores={'FL':3}
        apply_paced_tail_floor(scores,self.ws,self.pending,self.est,'x-performance-lab')
        self.assertEqual(scores,{'FL':3})
    def test_individual_standard_mixed_discovery_and_nonlab_unchanged(self):
        for ws,version in [(self.ws[:1],'x-performance-lab'),
                ([dict(w,mode='standard') for w in self.ws],'x-performance-lab'),
                ([dict(self.ws[0],mode='standard'),*self.ws[1:]],'x-performance-lab'),
                ([dict(w,kind='discovery') for w in self.ws],'x-performance-lab'),(self.ws,'production')]:
            scores={'FL':3};apply_paced_tail_floor(scores,ws,self.pending,self.est,version)
            self.assertEqual(scores,{'FL':3})
    def test_invalid_configuration_preserves_ordering(self):
        for config in ['{}','{"FL":0}','{"FL":true}','{"FL":NaN}','broken']:
            with patch.dict(os.environ,{'CE_LAB_SALES_START_INTERVALS':config}):
                scores={'FL':3};apply_paced_tail_floor(scores,self.ws,self.pending,self.est,'x-performance-lab')
                self.assertEqual(scores,{'FL':3})
    def test_queue_and_all_fencing_identity_result_deadline_logic_unchanged(self):
        root=Path(__file__).resolve().parents[2]
        before=ast.parse(subprocess.check_output(['git','show','0029ee5:deployment/durable_queue.py'],cwd=root).decode())
        after=ast.parse((root/'deployment/durable_queue.py').read_text())
        strip_paced_timing(after);self.assertEqual(ast.dump(before),ast.dump(after))

@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Isolated lab PostgreSQL required')
class PacedTimingDB(unittest.TestCase):
    setUp=f.DurableTests.setUp
    tearDown=f.DurableTests.tearDown
    submit=f.DurableTests.submit
    worker=f.DurableTests.worker
    finish=f.DurableTests.finish
    def test_paced_priority_and_start_guard_both_hold_in_real_queue(self):
        self.q.sales_policy='tail-aware';worker=self.worker(slots=12)
        ids=[self.submit(f.payload(ein=str(100000001+i),states=['CO','LA'],mode='sales')) for i in range(20)]
        estimates=DurationEstimates([dict(state='CO',seconds=1,tail_seconds=2,mean_seconds=1),
                                    dict(state='LA',seconds=3,tail_seconds=6,mean_seconds=3)])
        estimates.as_of=1;estimates.workload_timing=True
        with patch('deployment.durable_queue.cohort_timing_estimates',return_value=estimates),patch.dict(os.environ,{
                'CE_LAB_SALES_START_INTERVALS':'{"CO":2}', 'CE_LAB_SALES_GLOBAL_PRIORITY':'1'}):
            first=self.q.claim(worker);self.assertEqual(first['state'],'CO')
            self.finish(first)
            # Even after a quick completion, urgency cannot bypass spacing.
            second=self.q.claim(worker);self.assertEqual(second['state'],'LA');self.finish(second)
        for ident in ids:
            state=self.q.status('a',ident);self.assertEqual(state['deadline']-state['submitted'],60)

if __name__=='__main__':unittest.main()
