"""Global source start spacing, unchanged identity and hard deadline safeguards."""
import ast,json,os,subprocess,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from deployment.durable_queue import sales_source_start_intervals,sales_source_start_after
from testing.capacity_lab.start_pacing_scope import strip_start_pacing,strip_start_index
from testing.capacity_lab import test_durable_queue as dbtests

class StartPacing(unittest.TestCase):
    workflows=[{'mode':'sales','kind':'registration'}]*2
    def test_configuration_is_bounded_and_lab_concurrent_sales_only(self):
        with patch.dict(os.environ,{'CE_LAB_SALES_START_INTERVALS':'{"NY":1}'}):
            self.assertEqual(sales_source_start_intervals(self.workflows,'v-performance-lab'),{'NY':1})
            for ws,version in [(self.workflows,'production'),(self.workflows[:1],'v-performance-lab'),
                    ([self.workflows[0],{'mode':'standard','kind':'registration'}],'v-performance-lab'),
                    ([self.workflows[0],{'mode':'sales','kind':'discovery'}],'v-performance-lab')]:
                self.assertEqual(sales_source_start_intervals(ws,version),{})
        for value in ['null','[]','bad','{"NY":true}','{"NY":-1}','{"NY":6}','{"NY":NaN}','{"NY":Infinity}','{"NY":0}','{"ny":1}']:
            with self.subTest(value=value),patch.dict(os.environ,{'CE_LAB_SALES_START_INTERVALS':value}):
                self.assertEqual(sales_source_start_intervals(self.workflows,'v-performance-lab'),{})

    def test_completed_fast_jobs_keep_start_reservation_and_other_sources_are_free(self):
        c=Mock();c.execute.return_value=[{'state':'NY','claimed':10}]
        with patch.dict(os.environ,{'CE_LAB_SALES_START_INTERVALS':'{"NY":1}'}):
            self.assertEqual(sales_source_start_after(c,self.workflows,'v-performance-lab',10.2),{'NY':11})
            self.assertEqual(sales_source_start_after(c,self.workflows,'v-performance-lab',11),{})
        query=c.execute.call_args.args[0]
        self.assertIn('LIMIT 1',query)
        for forbidden in ['result','payload',"phase='running'"]:
            self.assertNotIn(forbidden,query)

    def test_no_configuration_performs_no_database_read(self):
        c=Mock()
        with patch.dict(os.environ,{'CE_LAB_SALES_START_INTERVALS':'{}'}):
            self.assertEqual(sales_source_start_after(c,self.workflows,'v-performance-lab',10),{})
        c.execute.assert_not_called()

    def test_whole_queue_preserved_except_timestamp_guard(self):
        root=Path(__file__).resolve().parents[2]
        before=ast.parse(subprocess.check_output(['git','show','543752c:deployment/durable_queue.py'],cwd=root).decode())
        after=ast.parse((root/'deployment/durable_queue.py').read_text())
        strip_start_pacing(after);self.assertEqual(ast.dump(before),ast.dump(after))

    def test_schema_adds_only_latest_start_index(self):
        root=Path(__file__).resolve().parents[2]
        before=subprocess.check_output(['git','show','543752c:deployment/queue_schema.sql'],cwd=root).decode()
        self.assertEqual(strip_start_index((root/'deployment/queue_schema.sql').read_text()),before)

@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Real lab Postgres required')
class PacingRealDB(unittest.TestCase):
    setUp=dbtests.DurableTests.setUp
    tearDown=dbtests.DurableTests.tearDown
    submit=dbtests.DurableTests.submit
    worker=dbtests.DurableTests.worker
    finish=dbtests.DurableTests.finish
    second=dbtests.DurableTests.second

    def test_independent_workers_share_start_reservation_after_fast_completion(self):
        q2=self.second();a=self.worker();b=self.worker(q2)
        first=self.submit(dbtests.payload(states=['CO','LA'],mode='sales'))
        second=self.submit(dbtests.payload(ein='987654321',states=['CO','LA'],mode='sales'))
        with patch.dict(os.environ,{'CE_LAB_SALES_START_INTERVALS':'{"CO":5}'}):
            one=self.q.claim(a);self.assertEqual(one['state'],'CO');self.finish(one)
            # Both workflows retain LA so the concurrent cohort is still active.
            next_job=q2.claim(b);self.assertEqual(next_job['state'],'LA')
            self.finish(next_job,q2)
            another=q2.claim(b);self.assertEqual(another['state'],'LA')
            # Leave LA held; completion cannot hide the earlier CO timestamp.
            self.assertIsNone(q2.claim(b))
            remaining=one['claimed']+5-time.time()
            if remaining>0:time.sleep(remaining+.02)
            last=q2.claim(b);self.assertEqual(last['state'],'CO')
            self.assertGreaterEqual(last['claimed']-one['claimed'],5)
            self.finish(last,q2);self.finish(another,q2)
        for ident in [first,second]:
            state=self.q.status('a',ident)
            self.assertEqual(state['deadline']-state['submitted'],60)
            self.assertIsNotNone(state['finished'])

if __name__=='__main__':unittest.main()
