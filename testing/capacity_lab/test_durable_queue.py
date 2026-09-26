"""Real PostgreSQL integration, concurrent connections and independent workers.

Requires CE_TEST_DATABASE_URL pointing to the isolated lab database. Every test
uses a random schema and drops only that schema; it cannot erase the live queue.
No registry network calls and no customer browser are involved.
"""
import concurrent.futures
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from deployment.durable_queue import Queue, Conflict, QueueFull, NotFound, normalize_submission
from deployment.queue_worker import ProcessTree, Supervisor, process_running

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'fixture-performance-lab'
STATES = ['CO','ME','AR','NY','CA','LA']


def payload(ein='123456789', states=None, **changes):
    return normalize_submission({'ein': ein, 'organization_name': 'Fixture Foundation',
        'alternate_names': ['Official Former Name'], 'states': states or ['CO'], **changes}, STATES)


@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'), 'Real lab Postgres required')
class DurableTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ['CE_TEST_DATABASE_URL']
        self.schema = 'cc_test_'+uuid.uuid4().hex
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.q = Queue(self.dsn, test_schema=self.schema)
        self.q.initialize(VERSION, {'CO':30,'ME':1,'AR':1,'CA':4,'IRS':4})
        self.extra = []

    def tearDown(self):
        for q in self.extra: q.close()
        self.q.close()
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def second(self):
        q = Queue(self.dsn, test_schema=self.schema); self.extra.append(q); return q

    def submit(self, p=None, scope='a', key=None):
        return self.q.submit(scope, key or uuid.uuid4().hex, p or payload(), VERSION, ['CO','ME','IRS'])[0]

    def worker(self, q=None, slots=8):
        ident = uuid.uuid4().hex
        (q or self.q).register_worker(ident, VERSION, slots)
        return ident

    def finish(self, job, q=None):
        return (q or self.q).complete(job['owner'], job['id'], job['token'],
            {'ein':job['payload']['ein'],'state':job['state'],'app_version':VERSION,'status':'Current'})

    def test_idempotency_and_active_ein_dedupe_across_connections(self):
        q2 = self.second()
        with concurrent.futures.ThreadPoolExecutor(6) as pool:
            rows = list(pool.map(lambda i: (self.q if i%2 else q2).submit('a','same',payload(),VERSION), range(12)))
        self.assertEqual(len({r[0] for r in rows}), 1)
        self.assertEqual(sum(r[1] for r in rows), 1)
        self.assertEqual(self.submit(key='another'), rows[0][0])
        with self.assertRaises(Conflict): self.submit(payload(alternate_names=[]), key='same')
        with self.assertRaises(Conflict): self.submit(payload(mode='sales'))

    def test_admission_observation_does_not_change_job_or_capacity(self):
        ident=self.submit();worker=self.worker();job=self.q.claim(worker)
        observation={'window_seconds':3,'seconds_by_reason':{'cpu_pressure':2,'claim_transaction':1},
                     'counts_by_reason':{'cpu_pressure':4,'claim_transaction':1}}
        allowed=self.q.heartbeat(worker,[(job['id'],job['token'])],observation=observation)
        self.assertIn(job['id'],allowed)
        with self.q.transaction() as (conn,now):
            row=conn.execute("SELECT detail FROM cc_lab_events WHERE event='worker_admission'").fetchone()
            held=conn.execute("SELECT count(*) AS n FROM cc_lab_jobs WHERE phase='running'").fetchone()['n']
        self.assertEqual(row['detail'],{'worker':worker,**observation})
        self.assertEqual(held,1)
        self.finish(job)
        self.assertEqual(self.q.status('a',ident)['phase'],'completed')

    def test_ny_explicit_activation_claims_real_work_and_preserves_limits(self):
        disabled=self.submit(payload(states=['NY']))
        self.assertEqual(self.q.status('a',disabled)['jobs'][0]['error'],'NY_COLLECTOR_NOT_CONFIGURED')
        self.q.ny_enabled=True
        enabled=self.submit(payload('987654321',states=['NY']))
        job=self.q.claim(self.worker())
        self.assertEqual(job['workflow_id'],enabled)
        self.assertEqual(job['state'],'NY')
        self.assertEqual(job['resources'],['NY'])
        self.finish(job)

    def test_recent_measured_duration_priority_keeps_organization_fairness(self):
        old=self.submit(payload(states=['CO','LA']))
        worker=self.worker()
        for _ in range(2):
            job=self.q.claim(worker);self.finish(job)
        with self.q.transaction() as (c,now):
            c.execute('UPDATE cc_lab_jobs SET claimed=%s,finished=%s WHERE workflow_id=%s AND state=%s',(now-70,now-10,old,'LA'))
            c.execute('UPDATE cc_lab_jobs SET claimed=%s,finished=%s WHERE workflow_id=%s AND state=%s',(now-12,now-10,old,'CO'))
        a=self.submit(payload(states=['CO','LA']))
        b=self.submit(payload('987654321',states=['CO','LA']))
        first,second=self.q.claim(worker),self.q.claim(worker)
        self.assertEqual({first['workflow_id'],second['workflow_id']},{a,b})
        self.assertEqual([first['state'],second['state']],['LA','LA'])
        self.finish(first);self.finish(second)
        self.assertEqual(self.q.claim(worker)['state'],'CO')

    def test_idle_claim_skips_history_but_refreshes_worker(self):
        worker = self.worker()
        with self.q.transaction() as (c, now):
            c.execute('UPDATE cc_lab_workers SET heartbeat=%s WHERE id=%s', (now-100, worker))
        queries = []
        original = self.q.transaction

        class ObservedConnection:
            def __init__(self, conn): self.conn = conn
            def pipeline(self): return self.conn.pipeline()
            def execute(self, query, *args, **kwargs):
                queries.append(query)
                return self.conn.execute(query, *args, **kwargs)

        @contextmanager
        def observed():
            with original() as (c, now):
                yield ObservedConnection(c), now

        with patch.object(self.q, 'transaction', observed):
            self.assertIsNone(self.q.claim(worker))
        self.assertFalse(any('percentile_cont' in query for query in queries))
        with original() as (c, now):
            heartbeat = c.execute('SELECT heartbeat FROM cc_lab_workers WHERE id=%s', (worker,)).fetchone()['heartbeat']
            self.assertLess(now-heartbeat, 5)

    def test_pipelined_claim_failure_rolls_back_job_and_dispatch(self):
        ident = self.submit()
        worker = self.worker()
        with patch.object(self.q, 'event', side_effect=RuntimeError('Fixture claim event failure')):
            with self.assertRaisesRegex(RuntimeError, 'Fixture claim event failure'):
                self.q.claim(worker)
        state = self.q.status('a', ident)
        self.assertEqual(state['phase'], 'queued')
        self.assertIsNone(state['started'])
        self.assertEqual(state['jobs'][0]['phase'], 'queued')
        self.assertEqual(state['jobs'][0]['attempt'], 0)
        self.assertIsNotNone(self.q.claim(worker))

    def test_worker_headroom_ceiling_cannot_bypass_physical_or_workflow_limit(self):
        worker=self.worker(slots=12)
        for i in range(20):self.submit(payload(f'{i+1:09}'))
        self.assertIsNone(self.q.claim(worker,slot_limit=0))
        jobs=[self.q.claim(worker,slot_limit=2,admission_evidence={'reason':'fixture'}) for _ in range(3)]
        self.assertEqual(sum(j is not None for j in jobs),2)
        more=[self.q.claim(worker,slot_limit=100) for _ in range(12)]
        self.assertEqual(sum(j is not None for j in more),10)
        self.assertIsNone(self.q.claim(worker,slot_limit=100))
        second=self.worker(slots=12)
        self.assertEqual(sum(self.q.claim(second) is not None for _ in range(12)),3)
        with self.q.transaction() as (c,_):
            evidence=c.execute("SELECT detail FROM cc_lab_events WHERE event='claimed' AND detail->'admission'->>'reason'='fixture'").fetchall()
        self.assertEqual(len(evidence),2)

    def test_scope_isolation_and_completed_result_replay(self):
        a, b = self.submit(scope='a'), self.submit(scope='b')
        self.assertNotEqual(a,b)
        with self.assertRaises(NotFound): self.q.status('b',a)
        with self.assertRaises(NotFound): self.q.cancel('b',a)
        w=self.worker(); j=self.q.claim(w); self.finish(j)
        self.assertIsNotNone(self.q.status('a',a)['finished'])

    def test_15_workflow_ceiling_across_independent_workers(self):
        q2 = self.second()
        for i in range(20): self.submit(payload(f'{i+1:09}'))
        workers = [self.worker(q2 if i%2 else self.q) for i in range(4)]
        def claims(pair):
            i,w=pair; q=q2 if i%2 else self.q
            return [j for _ in range(8) if (j:=q.claim(w))]
        with concurrent.futures.ThreadPoolExecutor(4) as pool: groups=list(pool.map(claims, enumerate(workers)))
        jobs=[j for g in groups for j in g]
        self.assertEqual(len(jobs),15)
        m=self.q.metrics(); self.assertEqual(sum(r['count'] for r in m['workflows'] if r['phase'] in ('active','attention','stopping')),15)
        self.finish(jobs[0])
        self.assertIsNotNone(self.q.claim(workers[0]))

    def test_explicit_twenty_workflow_trial_preserves_global_ceiling(self):
        with self.q.transaction() as (c, now):
            c.execute('UPDATE cc_lab_settings SET workflow_limit=20 WHERE id=1')
        self.q.initialize(VERSION, {'CO':30,'ME':1,'AR':1,'CA':4,'IRS':4}, workflow_limit=20)
        with self.assertRaises(ValueError):
            self.q.initialize(VERSION, {}, workflow_limit=21)
        with self.assertRaises(Conflict):
            self.q.initialize(VERSION, {'CO':30,'ME':1,'AR':1,'CA':4,'IRS':4})
        for i in range(21): self.submit(payload(f'{i+1:09}'))
        workers = [self.worker() for _ in range(4)]
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            groups = list(pool.map(lambda w: [j for _ in range(8) if (j := self.q.claim(w))], workers))
        jobs = [j for group in groups for j in group]
        self.assertEqual(len(jobs), 20)
        self.assertEqual(len({j['workflow_id'] for j in jobs}), 20)
        self.finish(jobs[0])
        self.assertIsNotNone(self.q.claim(workers[0]))

    def test_registry_limit_discovery_reservation_and_fairness(self):
        q2=self.second(); w1=self.worker(); w2=self.worker(q2)
        a=self.submit(payload(states=['ME','CO','AR']))
        b=self.submit(payload('987654321',states=['ME','CO']))
        jobs=[self.q.claim(w1),q2.claim(w2),self.q.claim(w1),q2.claim(w2)]
        self.assertEqual(len({j['workflow_id'] for j in jobs[:2]}),2)
        self.assertEqual(sum(j['state']=='ME' for j in jobs if j),1)
        self.assertEqual(q2.claim(w2),None)
        discovery=self.submit(normalize_submission({'ein':'123123123','organization_name':'Discovery', 'kind':'discovery'},STATES))
        self.assertIsNone(q2.claim(w2))  # ME lane is already held.
        for j in jobs: self.finish(j)
        j=q2.claim(w2)
        self.assertIsNotNone(j)
        if j['state']!='@discovery': self.finish(j); j=q2.claim(w2)
        self.assertEqual(j['weight'],4)

    def test_three_twelve_slot_replicas_keep_global_workflow_and_ny_caps(self):
        queues = [self.q, self.second(), self.second()]
        for q in queues:
            q.ny_enabled = True
        # Production NY cap is two; use the same shared cap in this isolated schema.
        with self.q.transaction() as (c, _):
            c.execute("UPDATE cc_lab_settings SET registry_limits=jsonb_set(registry_limits,'{NY}','2'::jsonb)")
        for i in range(20):
            self.submit(payload(f'{i+1:09}', states=['CO', 'NY']))
        workers = [self.worker(q, slots=12) for q in queues]
        def claim(pair):
            q, w = pair
            return [j for _ in range(12) if (j := q.claim(w))]
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            groups = list(pool.map(claim, zip(queues, workers)))
        jobs = [j for group in groups for j in group]
        self.assertEqual(len({j['id'] for j in jobs}), len(jobs))
        self.assertEqual(len({j['workflow_id'] for j in jobs}), 15)
        self.assertEqual(sum(j['state'] == 'NY' for j in jobs), 2)
        self.assertTrue(all(len(group) <= 12 for group in groups))
        self.assertEqual(sum(r['count'] for r in self.q.metrics()['workflows'] if r['phase'] == 'queued'), 5)

    def test_earlier_discovery_finishes_before_younger_overlapping_work(self):
        with self.q.transaction() as (c,_):
            c.execute("UPDATE cc_lab_settings SET registry_limits=jsonb_set(registry_limits,'{CO}','2'::jsonb)")
        worker=self.worker(slots=12)
        self.submit(payload(states=['ME']));held=self.q.claim(worker)
        discovery=self.submit(normalize_submission({'ein':'222222222','organization_name':'Discovery','kind':'discovery'},STATES))
        self.submit(payload('333333333',states=['CO','LA']))
        self.submit(payload('444444444',states=['CO']))
        unrelated=self.q.claim(worker);self.assertEqual(unrelated['state'],'LA')
        self.assertIsNone(self.q.claim(worker))  # Younger CO work waits; LA did not.
        self.finish(held)
        ready=self.q.claim(worker)
        self.assertEqual(ready['workflow_id'],discovery)
        self.assertEqual(ready['state'],'@discovery')
        self.assertIsNone(self.q.claim(worker))  # Discovery keeps priority while running.
        self.finish(ready)
        self.assertEqual(self.q.claim(worker)['state'],'CO')
        self.assertEqual(self.q.claim(worker)['state'],'CO')
        self.assertIsNone(self.q.claim(worker))  # Actual CO cap is still enforced.

    def test_new_discovery_cannot_preempt_older_registration_work(self):
        worker=self.worker(slots=12)
        self.submit(payload(states=['ME']));held=self.q.claim(worker)
        older=self.submit(payload('333333333',states=['CO']))
        self.submit(normalize_submission({'ein':'222222222','organization_name':'Discovery','kind':'discovery'},STATES))
        job=self.q.claim(worker)
        self.assertEqual(job['workflow_id'],older)
        self.assertEqual(job['state'],'CO')

    def test_all_earlier_discoveries_finish_before_younger_overlapping_work(self):
        with self.q.transaction() as (c,_):
            c.execute("UPDATE cc_lab_settings SET registry_limits=jsonb_set(registry_limits,'{ME}','2'::jsonb)")
        worker=self.worker(slots=12)
        for ein in ('222222222','333333333'):
            self.submit(normalize_submission({'ein':ein,'organization_name':'Discovery','kind':'discovery'},STATES))
        first=self.q.claim(worker);second=self.q.claim(worker)
        younger=self.submit(payload('444444444',states=['CO']))
        self.assertIsNone(self.q.claim(worker))
        self.finish(first)
        self.assertIsNone(self.q.claim(worker))
        self.finish(second)
        self.assertEqual(self.q.claim(worker)['workflow_id'],younger)

    def test_waiting_discovery_outside_workflow_ceiling_cannot_block_active_work(self):
        with self.q.transaction() as (c,_):
            c.execute('UPDATE cc_lab_settings SET workflow_limit=1')
        worker=self.worker(slots=12)
        active=self.submit(payload(states=['CO','ME']))
        self.assertEqual(self.q.claim(worker)['state'],'CO')
        self.submit(normalize_submission({'ein':'222222222','organization_name':'Discovery','kind':'discovery'},STATES))
        next_job=self.q.claim(worker)
        self.assertEqual(next_job['workflow_id'],active);self.assertEqual(next_job['state'],'ME')

    def test_unfit_multi_source_job_does_not_reserve_small_worker_capacity(self):
        with self.q.transaction() as (c,_):
            c.execute("UPDATE cc_lab_settings SET registry_limits=jsonb_set(registry_limits,'{CO}','1'::jsonb)")
        worker=self.worker(slots=2)
        self.submit(payload(states=['ME']));self.q.claim(worker)
        self.submit(normalize_submission({'ein':'222222222','organization_name':'Discovery','kind':'discovery'},STATES))
        self.submit(payload('333333333',states=['CO']))
        self.assertEqual(self.q.claim(worker)['state'],'CO')

    def test_canceling_waiting_discovery_removes_its_priority_reservation(self):
        with self.q.transaction() as (c,_):
            c.execute("UPDATE cc_lab_settings SET registry_limits=jsonb_set(registry_limits,'{CO}','1'::jsonb)")
        worker=self.worker(slots=12)
        self.submit(payload(states=['ME']));self.q.claim(worker)
        discovery=self.submit(normalize_submission({'ein':'222222222','organization_name':'Discovery','kind':'discovery'},STATES))
        self.submit(payload('333333333',states=['CO']))
        self.assertIsNone(self.q.claim(worker))
        self.q.cancel('a',discovery)
        self.assertEqual(self.q.claim(worker)['state'],'CO')

    def test_cancel_retains_capacity_until_termination_ack(self):
        ident=self.submit(payload(states=['CO','ME'])); w=self.worker(); j=self.q.claim(w)
        self.q.cancel('a',ident)
        st=self.q.status('a',ident); self.assertEqual(st['phase'],'stopping'); self.assertIsNone(st['finished'])
        self.assertEqual(self.q.heartbeat(w,[(j['id'],j['token'])]),[])
        self.assertTrue(self.q.complete(w,j['id'],j['token'],error='TASK_STOPPED'))
        st=self.q.status('a',ident); self.assertEqual(st['phase'],'canceled')
        self.assertTrue(all(r['phase']=='done' for r in st['jobs']))

    def test_expired_lease_quarantines_without_duplicate_dispatch(self):
        ident=self.submit(payload(states=['ME'])); w=self.worker(); j=self.q.claim(w)
        with self.q.transaction() as (c,now): c.execute('UPDATE cc_lab_jobs SET lease_until=%s WHERE id=%s',(now-1,j['id']))
        self.assertEqual(self.q.status('a',ident)['phase'],'attention')
        replacement=self.worker()
        self.assertIsNone(self.q.claim(replacement))
        self.assertEqual(self.q.heartbeat(w,[(j['id'],j['token'])]),[])
        self.q.confirm_worker_stopped(w,'Fixture supervisor verified all descendant process IDs have exited')
        newer=self.q.claim(replacement)
        self.assertNotEqual(newer['token'],j['token'])
        self.assertFalse(self.finish(j))
        self.assertTrue(self.finish(newer))
        self.assertEqual(self.q.status('a',ident)['phase'],'completed')

    def test_deadline_counts_queue_time_and_does_not_create_negative(self):
        ident=self.submit(payload(mode='sales')); w=self.worker()
        with self.q.transaction() as (c,now):
            row=c.execute('SELECT * FROM cc_lab_workflows WHERE id=%s',(ident,)).fetchone()
            self.assertEqual(row['deadline']-row['submitted'],60)
            c.execute('UPDATE cc_lab_workflows SET deadline=%s WHERE id=%s',(now-1,ident))
        self.assertIsNone(self.q.claim(w))
        st=self.q.status('a',ident); self.assertEqual(st['phase'],'expired')
        self.assertIsNone(st['jobs'][0]['result']); self.assertEqual(st['jobs'][0]['error'],'WORKFLOW_DEADLINE')

    def test_expired_running_work_cannot_publish_late_success(self):
        ident=self.submit(); w=self.worker(); j=self.q.claim(w)
        with self.q.transaction() as (c,now): c.execute('UPDATE cc_lab_workflows SET deadline=%s WHERE id=%s',(now-1,ident))
        self.finish(j)
        st=self.q.status('a',ident); self.assertEqual(st['phase'],'expired'); self.assertIsNone(st['jobs'][0]['result'])

    def test_api_restart_preserves_jobs_names_and_results(self):
        ident=self.submit(); w=self.worker(); j=self.q.claim(w); self.finish(j)
        self.q.close(); self.q=Queue(self.dsn,test_schema=self.schema)
        st=self.q.status('a',ident); self.assertEqual(st['jobs'][0]['result']['status'],'Current')
        with self.q.transaction() as (c,_):
            saved=c.execute('SELECT payload FROM cc_lab_workflows WHERE id=%s',(ident,)).fetchone()['payload']
        self.assertEqual(saved,payload())

    def test_version_identity_and_queue_bounds(self):
        with self.assertRaises(Conflict): self.q.register_worker('wrong','wrong-performance-lab',8)
        ident=self.submit(); w=self.worker(); j=self.q.claim(w)
        with self.assertRaises(ValueError): self.q.complete(w,j['id'],j['token'],{'ein':'111111111','state':'CO','app_version':VERSION})
        with self.q.transaction() as (c,_): c.execute('UPDATE cc_lab_settings SET backlog_limit=1 WHERE id=1')
        with self.assertRaises(QueueFull): self.submit(payload('987654321'))
        self.finish(j)
        self.assertFalse(self.finish(j))

    def test_two_supervisors_preserve_output_and_kill_descendants(self):
        command=[sys.executable,str(ROOT/'testing/capacity_lab/queue_fixture_task.py')]
        q2=self.second()
        with tempfile.TemporaryDirectory() as temp:
            marker=Path(temp)/'child.pid'
            env={**os.environ,'CC_FIXTURE_DESCENDANT':str(marker),'CC_FIXTURE_DELAY':'.3'}
            a=Supervisor(self.q,VERSION,2,command,env)
            b=Supervisor(q2,VERSION,2,command,{**os.environ,'CC_FIXTURE_DELAY':'.3'})
            ids=[self.submit(payload(f'{i+1:09}',states=['CO','CA'])) for i in range(4)]
            threads=[threading.Thread(target=s.run) for s in (a,b)]
            for t in threads:t.start()
            try:
                end=time.monotonic()+45
                while time.monotonic()<end:
                    states=[self.q.status('a',i) for i in ids]
                    if all(s['finished'] for s in states):break
                    time.sleep(.3)
                self.assertTrue(all(s['finished'] for s in states),states)
                for st in states:
                    for job in st['jobs']:
                        self.assertIsNone(job['error'])
                        self.assertEqual(job['result']['reviewed_names'],['Official Former Name'])
                        self.assertEqual(job['result']['registration_date'],'2000-01-01')
                        self.assertEqual(len(job['result']['identity_anchor']['locations']),2)
                with self.q.transaction() as (c,_):
                    owners={r['owner'] for r in c.execute('SELECT owner FROM cc_lab_jobs')}
                self.assertEqual(owners,{a.id,b.id})
                self.assertTrue(marker.is_file())
                self.assertFalse(process_running(int(marker.read_text())))
            finally:
                a.stop(); b.stop()
                for t in threads:t.join(20)
                self.assertFalse(any(t.is_alive() for t in threads))

    def test_os_worker_loss_requires_confirmed_death_then_recovers(self):
        ident=self.submit(payload(states=['CO']))
        with tempfile.TemporaryDirectory() as temp:
            marker=Path(temp)/'worker.id'
            env={**os.environ,'CC_TEST_SCHEMA':self.schema,'CC_FIXTURE_DELAY':'120'}
            tree=ProcessTree([sys.executable,str(ROOT/'testing/capacity_lab/queue_fixture_worker.py'),str(marker)],{},temp,env)
            try:
                end=time.monotonic()+30; job=None
                while time.monotonic()<end:
                    with self.q.transaction() as (c,_):
                        job=c.execute("SELECT * FROM cc_lab_jobs WHERE workflow_id=%s AND phase='running'",(ident,)).fetchone()
                    if job and marker.is_file():break
                    time.sleep(.2)
                self.assertIsNotNone(job)
                worker=marker.read_text()
                tree.stop()
                self.assertFalse(process_running(tree.pid))
                with self.q.transaction() as (c,now):c.execute('UPDATE cc_lab_jobs SET lease_until=%s WHERE id=%s',(now-1,job['id']))
                self.assertEqual(self.q.status('a',ident)['phase'],'attention')
                replacement=self.worker()
                self.assertIsNone(self.q.claim(replacement))
                self.q.confirm_worker_stopped(worker,'OS test verified supervisor and descendants terminated via Job Object/process group')
                newer=self.q.claim(replacement)
                self.assertEqual(newer['attempt'],2)
                self.assertFalse(self.q.complete(worker,job['id'],job['token'],error='late stale completion'))
                self.finish(newer)
                self.assertEqual(self.q.status('a',ident)['phase'],'completed')
            finally:tree.stop()


class InputTests(unittest.TestCase):
    def test_rejects_credentials_scope_injection_and_invalid_inputs(self):
        for change in ({'scope':'another-company'}, {'admin_passcode':'secret'}, {'ein':'000000000'},
                       {'states':['XX']}, {'alternate_names':['x']*33}, {'kind':'shell'}):
            with self.subTest(change=change),self.assertRaises(ValueError): payload(**change)


if __name__=='__main__': unittest.main(verbosity=2)
