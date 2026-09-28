"""Load-sensitive elapsed histories must survive later individual checks."""
import os,subprocess,time,unittest,uuid
from pathlib import Path
from unittest.mock import Mock,patch
from deployment.durable_queue import apply_loaded_timing_floor,cohort_timing_estimates,DurationEstimates
from testing.capacity_lab.test_cohort_timing import workflows
from testing.capacity_lab.test_observed_tail import FLAGS as OLD_FLAGS
from testing.capacity_lab import test_durable_queue as f
FLAGS={**OLD_FLAGS,'CE_LAB_SALES_LOADED_TIMING':'1'}

class LoadedTiming(unittest.TestCase):
    def queue(self):
        q=Mock();q.sales_policy='tail-aware';q._cohort_timing_cache=None;return q
    def test_concurrent_floor_keeps_individual_median_and_raises_only_tail_and_mean(self):
        q=self.queue();c=Mock();c.execute.side_effect=[
            [dict(state='MI',seconds=10,tail_seconds=20,mean_seconds=12)],
            [dict(state='MI',tail_seconds=20,mean_seconds=12)],
            [dict(state='MI',tail_seconds=40,mean_seconds=24)]]
        with patch.dict(os.environ,FLAGS):
            v=cohort_timing_estimates(q,c,100001,{'MI'},'fixture-performance-lab',workflows())
        self.assertEqual(v['MI'],10);self.assertEqual(v.tails['MI'],40);self.assertEqual(v.means['MI'],24)
        self.assertTrue(v.loaded_timing)
        sql,params=c.execute.call_args.args
        for part in ['source_pressure>=2','attempt=1','finished<=%s','LIMIT 20','finished-claimed<=300']:
            self.assertIn(part,sql)
        for forbidden in ['payload','result','ein','organization_name']:self.assertNotIn(forbidden,sql)
        self.assertEqual(params,(['MI'],13600,100000))
    def test_unknown_source_and_faster_loaded_sample_do_not_lower_existing_estimate(self):
        v=DurationEstimates([dict(state='OR',seconds=8,tail_seconds=20,mean_seconds=12)])
        c=Mock();c.execute.return_value=[dict(state='OR',tail_seconds=10,mean_seconds=6)]
        apply_loaded_timing_floor(c,100000,{'OR','LA'},v)
        self.assertEqual(dict(v),{'OR':8});self.assertEqual(v.tails['OR'],20);self.assertEqual(v.means['OR'],12)
        self.assertNotIn('LA',v)
    def test_flag_invalidates_cache_but_same_cohort_freezes_before_first_response(self):
        q=self.queue();c=Mock();c.execute.return_value=[]
        with patch.dict(os.environ,FLAGS):
            a=cohort_timing_estimates(q,c,100001,{'MI'},'x-performance-lab',workflows())
            self.assertIs(a,cohort_timing_estimates(q,c,100015,{'MI'},'x-performance-lab',workflows()))
            self.assertEqual(c.execute.call_count,3)
            with patch.dict(os.environ,{'CE_LAB_SALES_LOADED_TIMING':'0'}):
                b=cohort_timing_estimates(q,c,100016,{'MI'},'x-performance-lab',workflows())
            self.assertIsNot(a,b);self.assertEqual(c.execute.call_count,5)
    def test_individual_standard_mixed_discovery_and_nonlab_use_unchanged_path(self):
        for ws,version in [(workflows()[:1],'x-performance-lab'),(workflows(mode='standard'),'x-performance-lab'),
                ([workflows()[0],workflows(mode='standard')[1]],'x-performance-lab'),
                (workflows(kind='discovery'),'x-performance-lab'),(workflows(),'production')]:
            q=self.queue();c=Mock()
            with patch.dict(os.environ,FLAGS):
                self.assertIs(cohort_timing_estimates(q,c,100001,{'MI'},version,ws),q.cached_duration_estimates.return_value)
            c.execute.assert_not_called()
    def test_all_admission_fencing_deadlines_matching_and_registry_code_unchanged(self):
        from testing.capacity_lab.loaded_timing_scope import assert_loaded_scope
        root=Path(__file__).resolve().parents[2]
        for path in ['deployment/durable_queue.py','deployment/queue_schema.sql']:
            assert_loaded_scope(root,'470f337',path)
        subprocess.run(['git','diff','--exit-code','470f337','--','registry_snapshot_server.py',
            'deployment/queue_engine.py','deployment/queue_worker.py','deployment/lab_capacity.py',
            'deployment/performance_lab.py','web-staging','browser-connector'],cwd=root,check=True,capture_output=True)

@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Real isolated PostgreSQL required')
class LoadedTimingDB(unittest.TestCase):
    setUp=f.DurableTests.setUp
    tearDown=f.DurableTests.tearDown
    submit=f.DurableTests.submit
    worker=f.DurableTests.worker
    second=f.DurableTests.second
    finish=f.DurableTests.finish
    def test_additive_upgrade_preserves_completed_records_and_unknown_history(self):
        ident=self.submit();self.finish(self.q.claim(self.worker()))
        with self.q.transaction() as (c,now):
            before=c.execute('SELECT id,phase,result,error,claimed,finished FROM cc_lab_jobs WHERE workflow_id=%s',(ident,)).fetchall()
            c.execute('DROP INDEX cc_lab_jobs_loaded_duration')
            c.execute('ALTER TABLE cc_lab_jobs DROP COLUMN source_pressure')
        self.q.initialize(f.VERSION,{'CO':30,'ME':1,'AR':1,'CA':4,'IRS':4})
        with self.q.transaction() as (c,now):
            after=c.execute('SELECT id,phase,result,error,claimed,finished FROM cc_lab_jobs WHERE workflow_id=%s',(ident,)).fetchall()
            self.assertEqual(before,after)
            self.assertEqual(c.execute('SELECT source_pressure FROM cc_lab_jobs WHERE workflow_id=%s',(ident,)).fetchone()['source_pressure'],0)
            values=DurationEstimates([])
            apply_loaded_timing_floor(c,now,{'CO'},values)
            self.assertEqual(dict(values),{});self.assertEqual(values.tails,{})
    def test_actual_source_reservations_are_recorded_across_workers(self):
        a=self.worker();b=self.worker(self.second())
        for ein in ['123456789','987654321','234567890']:
            self.submit(f.payload(ein=ein,states=['CO','LA']))
        first=self.q.claim(a);second=self.extra[0].claim(b)
        self.assertEqual(first['state'],'CO');self.assertEqual(second['state'],'CO')
        with self.q.pool.connection() as c:
            rows=c.execute('SELECT id,source_pressure FROM cc_lab_jobs WHERE id=ANY(%s)',([first['id'],second['id']],)).fetchall()
        self.assertEqual({x['id']:x['source_pressure'] for x in rows},{first['id']:1,second['id']:2})
        self.finish(first);self.finish(second,self.extra[0])
    def test_many_new_individual_checks_cannot_erase_older_loaded_timings(self):
        ident=self.submit();self.finish(self.q.claim(self.worker()));self.q.sales_policy='tail-aware'
        with self.q.transaction() as (c,now):
            before=now-10
            samples=[(2,before-1-i*.01,1,None,1) for i in range(100)]
            samples.extend([(40,before-20,5,None,1),(20,before-21,2,None,1)])
            # These must never contribute to the loaded floor.
            samples.extend([(299,before-2,0,None,1),(299,before+1,10,None,1),
                (299,before-90000,10,None,1),(299,before-3,10,'CANCELED',1),
                (299,before-4,10,None,2)])
            for duration,finished,pressure,error,attempt in samples:
                hist=uuid.uuid4().hex
                c.execute('INSERT INTO cc_lab_workflows SELECT %s,scope,ein,fingerprint,payload,kind,mode,source_version,phase,stop_reason,submitted,deadline,started,finished,dispatched FROM cc_lab_workflows WHERE id=%s',(hist,ident))
                c.execute("INSERT INTO cc_lab_jobs(id,workflow_id,state,resources,weight,phase,attempt,claimed,finished,error,source_pressure) VALUES (%s,%s,'MI','[]',1,'done',%s,%s,%s,%s,%s)",(uuid.uuid4().hex,hist,attempt,finished-duration,finished,error,pressure))
            v=DurationEstimates([dict(state='MI',seconds=2,tail_seconds=2,mean_seconds=2)])
            apply_loaded_timing_floor(c,before,{'MI'},v)
            self.assertEqual(v['MI'],2);self.assertEqual(v.tails['MI'],40);self.assertEqual(v.means['MI'],30)
    def test_censored_workflow_timeout_is_only_a_lower_bound_and_sample_is_bounded(self):
        ident=self.submit();self.finish(self.q.claim(self.worker()))
        with self.q.transaction() as (c,now):
            before=now-10
            for i in range(25):
                hist=uuid.uuid4().hex;finished=before-1-i
                c.execute('INSERT INTO cc_lab_workflows SELECT %s,scope,ein,fingerprint,payload,kind,mode,source_version,phase,stop_reason,submitted,deadline,started,finished,dispatched FROM cc_lab_workflows WHERE id=%s',(hist,ident))
                duration=30 if i<20 else 250
                c.execute("INSERT INTO cc_lab_jobs(id,workflow_id,state,resources,weight,phase,attempt,claimed,finished,error,source_pressure) VALUES (%s,%s,'MI','[]',1,'done',1,%s,%s,'WORKFLOW_DEADLINE',3)",(uuid.uuid4().hex,hist,finished-duration,finished))
            v=DurationEstimates([dict(state='MI',seconds=10,tail_seconds=20,mean_seconds=10)])
            apply_loaded_timing_floor(c,before,{'MI'},v)
            self.assertEqual(v.tails['MI'],30);self.assertEqual(v.means['MI'],30);self.assertEqual(v['MI'],10)
if __name__=='__main__':unittest.main()
