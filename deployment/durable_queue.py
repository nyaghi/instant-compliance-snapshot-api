"""Private lab durable scheduler; never interprets registry evidence.

Postgres is the single scheduling authority. Transactions are short and globally
serialized with an advisory lock; no network/registry work runs in a transaction.
An expired worker lease is quarantined, NOT blindly reassigned. A supervisor must
prove termination before returning its reservations. This favors correctness
over availability during uncertain worker loss.
"""
from contextlib import contextmanager
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

LOCK = 4823915721
HELD = ('running', 'stopping', 'quarantined')
TERMINAL = ('completed', 'canceled', 'expired')


class Conflict(ValueError): pass
class QueueFull(ValueError): pass
class NotFound(ValueError): pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def normalize_submission(payload, supported):
    """Validate immutable scheduling input. Master retains alias normalization."""
    allowed = {'organization_name', 'ein', 'alternate_names', 'states', 'mode', 'kind'}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise ValueError('Unexpected workflow fields')
    name, ein = payload.get('organization_name'), payload.get('ein')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 300:
        raise ValueError('Organization name required')
    if not isinstance(ein, str) or not re.fullmatch(r'\d{2}-?\d{7}', ein) or ein.replace('-', '') == '000000000':
        raise ValueError('Valid EIN required')
    aliases = payload.get('alternate_names', [])
    if not isinstance(aliases, list) or len(aliases) > 32 or any(not isinstance(x, str) or not 1 <= len(x.strip()) <= 300 for x in aliases):
        raise ValueError('Invalid reviewed alternate names')
    kind, mode = payload.get('kind', 'registration'), payload.get('mode', 'standard')
    if kind not in ('registration', 'discovery') or mode not in ('standard', 'sales'):
        raise ValueError('Invalid workflow kind or mode')
    states = payload.get('states', [])
    if not isinstance(states, list) or any(not isinstance(s, str) or s not in supported for s in states):
        raise ValueError('Unsupported state')
    if kind == 'registration' and not states or kind == 'discovery' and states:
        raise ValueError('Select states for registration only')
    if kind == 'discovery' and (mode != 'standard' or aliases):
        raise ValueError('Discovery takes only the entered name and EIN')
    return {'organization_name': name.strip(), 'ein': ein.replace('-', ''),
            'alternate_names': aliases, 'states': sorted(set(states)), 'mode': mode, 'kind': kind}


class Queue:
    def __init__(self, dsn, max_connections=6, test_schema=None, ny_enabled=False):
        options = {'options': '-c statement_timeout=10000'}
        self.lock = LOCK
        self.ny_enabled = ny_enabled
        if test_schema is not None:
            if not re.fullmatch(r'cc_test_[a-f0-9]{32}', test_schema): raise ValueError('Invalid test schema')
            options['options'] += ' -c search_path='+test_schema
            self.lock = int(test_schema[-8:], 16)
        self.pool = ConnectionPool(dsn, min_size=1, max_size=max_connections, timeout=10,
                                   kwargs={'row_factory': dict_row, 'connect_timeout': 8, **options}, open=True)
        self.pool.wait(15)

    def close(self): self.pool.close()

    @contextmanager
    def transaction(self):
        with self.pool.connection() as conn, conn.transaction():
            with conn.pipeline():
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (self.lock,))
                clock = conn.execute('SELECT extract(epoch FROM clock_timestamp()) AS t')
            now = float(clock.fetchone()['t'])
            yield conn, now

    def initialize(self, version, registry_limits, workflow_limit=15, backlog_limit=1000):
        if not 1 <= workflow_limit <= 20 or backlog_limit < 1:
            raise ValueError('Invalid queue limits')
        with self.transaction() as (c, now):
            c.execute(Path(__file__).with_name('queue_schema.sql').read_text())
            c.execute('INSERT INTO cc_lab_settings VALUES (1,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                      (workflow_limit, backlog_limit, version, Jsonb(registry_limits)))
            actual = c.execute('SELECT * FROM cc_lab_settings WHERE id=1').fetchone()
            if actual != dict(id=1, workflow_limit=workflow_limit, backlog_limit=backlog_limit,
                              source_version=version, registry_limits=registry_limits):
                raise Conflict('Stored queue configuration differs; explicit idle migration required')

    @staticmethod
    def event(c, now, event, workflow=None, job=None, **detail):
        c.execute('INSERT INTO cc_lab_events(workflow_id,job_id,event,at,detail) VALUES (%s,%s,%s,%s,%s)',
                  (workflow, job, event, now, Jsonb(detail)))

    def submit(self, scope, key, payload, version, discovery_sources=()):
        if not scope or not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ValueError('Idempotency-Key required (1–128 characters)')
        fingerprint = digest({'payload': payload, 'version': version})
        with self.transaction() as (c, now):
            config = c.execute('SELECT * FROM cc_lab_settings WHERE id=1').fetchone()
            if config['source_version'] != version: raise Conflict('Queue release mismatch')
            prior = c.execute('SELECT * FROM cc_lab_submissions WHERE scope=%s AND key=%s', (scope, key)).fetchone()
            if prior:
                if prior['fingerprint'] != fingerprint: raise Conflict('Idempotency key was used for different inputs')
                return prior['workflow_id'], False
            prior = c.execute('SELECT * FROM cc_lab_workflows WHERE scope=%s AND ein=%s AND finished IS NULL',
                              (scope, payload['ein'])).fetchone()
            if prior:
                if prior['fingerprint'] != fingerprint: raise Conflict('This organization already has different work in progress')
                ident, created = prior['id'], False
            else:
                count = c.execute('SELECT count(*) AS n FROM cc_lab_workflows WHERE finished IS NULL').fetchone()['n']
                if count >= config['backlog_limit']: raise QueueFull('Lab backlog is full; no work was accepted')
                ident, created = str(uuid.uuid4()), True
                seconds = 90 if payload['kind'] == 'discovery' else 60 if payload['mode'] == 'sales' else 900
                c.execute('INSERT INTO cc_lab_workflows(id,scope,ein,fingerprint,payload,kind,mode,source_version,phase,submitted,deadline) '
                          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s)",
                          (ident, scope, payload['ein'], fingerprint, Jsonb(payload), payload['kind'], payload['mode'], version, now, now+seconds))
                for state in (['@discovery'] if payload['kind'] == 'discovery' else payload['states']):
                    resources = sorted(set(discovery_sources)) if state == '@discovery' else [state]
                    error = 'NY_COLLECTOR_NOT_CONFIGURED' if state == 'NY' and not self.ny_enabled else None
                    c.execute('INSERT INTO cc_lab_jobs(id,workflow_id,state,resources,weight,phase,finished,error) '
                              'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                              (str(uuid.uuid4()), ident, state, Jsonb(resources), 4 if state == '@discovery' else 1,
                               'done' if error else 'queued', now if error else None, error))
                self.event(c, now, 'accepted', ident)
            c.execute('INSERT INTO cc_lab_submissions VALUES (%s,%s,%s,%s)', (scope, key, fingerprint, ident))
            self._settle(c, now)
            return ident, created

    def register_worker(self, ident, version, slots):
        if not 1 <= slots <= 12: raise ValueError('Worker reservations must be 1–12')
        with self.transaction() as (c, now):
            cfg = c.execute('SELECT * FROM cc_lab_settings WHERE id=1').fetchone()
            if version != cfg['source_version']: raise Conflict('Worker release differs from queue')
            # Each supervisor boot has a new UUID. IDs cannot be reused to steal jobs.
            c.execute('INSERT INTO cc_lab_workers VALUES (%s,%s,%s,%s,false)', (ident, version, slots, now))

    def _settle(self, c, now):
        with c.pipeline():
            self._settle_batch(c, now)

    def _settle_batch(self, c, now):
        # Set operations keep transaction cost independent of queued org count.
        c.execute("UPDATE cc_lab_workflows SET stop_reason='deadline',phase='stopping' "
                  'WHERE finished IS NULL AND stop_reason IS NULL AND deadline<=%s', (now,))
        c.execute("UPDATE cc_lab_jobs j SET phase='done',finished=%s,error='WORKFLOW_'||upper(w.stop_reason) "
                  "FROM cc_lab_workflows w WHERE j.workflow_id=w.id AND w.stop_reason IS NOT NULL AND j.phase='queued'", (now,))
        c.execute("UPDATE cc_lab_jobs j SET phase='stopping' FROM cc_lab_workflows w "
                  "WHERE j.workflow_id=w.id AND w.stop_reason IS NOT NULL AND j.phase='running'")
        c.execute("WITH stale AS (UPDATE cc_lab_jobs SET phase='quarantined',error='WORKER_LEASE_LOST' "
                  "WHERE phase IN ('running','stopping') AND lease_until<=%s RETURNING id,workflow_id) "
                  "INSERT INTO cc_lab_events(workflow_id,job_id,event,at,detail) "
                  "SELECT workflow_id,id,'quarantined',%s,'{}'::jsonb FROM stale", (now, now))
        c.execute("WITH done AS (UPDATE cc_lab_workflows w SET finished=%s,phase=CASE "
                  "WHEN stop_reason='deadline' THEN 'expired' WHEN stop_reason IS NOT NULL THEN 'canceled' ELSE 'completed' END "
                  "WHERE finished IS NULL AND NOT EXISTS (SELECT 1 FROM cc_lab_jobs j WHERE j.workflow_id=w.id AND j.phase<>'done') "
                  'RETURNING id,phase) INSERT INTO cc_lab_events(workflow_id,event,at,detail) '
                  "SELECT id,phase,%s,'{}'::jsonb FROM done", (now, now))
        c.execute("UPDATE cc_lab_workflows w SET phase=CASE WHEN EXISTS "
                  "(SELECT 1 FROM cc_lab_jobs j WHERE j.workflow_id=w.id AND j.phase='quarantined') THEN 'attention' "
                  "WHEN stop_reason IS NOT NULL THEN 'stopping' WHEN started IS NOT NULL THEN 'active' ELSE 'queued' END "
                  'WHERE finished IS NULL')

    def claim(self, worker, slot_limit=None, admission_evidence=None):
        with self.transaction() as (c, now):
            self._settle(c, now)
            # All reads remain under the same advisory transaction lock. Pipeline
            # independent reads rather than paying a network round trip for each.
            # Capacity and priority are still decided from fresh database rows.
            with c.pipeline():
                worker_row = c.execute('SELECT * FROM cc_lab_workers WHERE id=%s', (worker,))
                settings_row = c.execute('SELECT * FROM cc_lab_settings WHERE id=1')
                held_rows = c.execute("SELECT * FROM cc_lab_jobs WHERE phase IN ('running','stopping','quarantined')")
                active_rows = c.execute('SELECT * FROM cc_lab_workflows WHERE started IS NOT NULL AND finished IS NULL')
                workflow_rows = c.execute("SELECT * FROM cc_lab_workflows WHERE phase IN ('queued','active') AND stop_reason IS NULL")
                pending_rows = c.execute("SELECT * FROM cc_lab_jobs WHERE phase='queued' ORDER BY state,id")
            wk = worker_row.fetchone()
            if not wk or wk['retired']: raise Conflict('Worker is not registered or is retired')
            ceiling = wk['slots'] if slot_limit is None else min(wk['slots'],max(0,int(slot_limit)))
            cfg = settings_row.fetchone()
            held = held_rows.fetchall()
            used = sum(j['weight'] for j in held if j['owner'] == worker)
            c.execute('UPDATE cc_lab_workers SET heartbeat=%s WHERE id=%s', (now, worker))
            if used >= ceiling: return None
            active = active_rows.fetchall()
            running = Counter(j['workflow_id'] for j in held)
            busy = Counter(r for j in held for r in j['resources'])
            workflows = workflow_rows.fetchall()
            pending = {}
            for job in pending_rows:
                pending.setdefault(job['workflow_id'], []).append(job)
            # No priority decision is needed when there is no pending work.
            # Settlement and the worker heartbeat above still run while idle.
            if not pending or not workflows: return None
            # Earlier multi-source workflows finish before younger single-source
            # jobs use overlapping sources. Merely reserving one spare permit
            # prevented total starvation but let later work crowd discovery's
            # remaining execution allowance. Older registration work and work on
            # unrelated sources remain eligible, so new discovery arrivals cannot
            # indefinitely preempt existing registrations. No running job is
            # interrupted; actual reservations still use the capacity checks below.
            protected = None
            earlier_multi = []
            for w in sorted(workflows,key=lambda w:(w['submitted'],w['id'])):
                if w['source_version'] != wk['source_version'] or running[w['id']] >= 15: continue
                if w['started'] is None and len(active) >= cfg['workflow_limit']: continue
                candidates=[j for j in pending.get(w['id'],[]) if len(j['resources'])>1 and j['weight']<=wk['slots']]
                ongoing=[j for j in held if j['workflow_id']==w['id'] and j['phase']=='running' and len(j['resources'])>1]
                earlier_multi.extend((w['submitted'],set(j['resources'])) for j in candidates+ongoing)
                if candidates and protected is None:
                    protected=min(candidates,key=lambda j:j['id'])
            # Start slow state work earlier within each organization's fair turn.
            # Recent measured durations only: no organization or state overrides.
            estimates = {r['state']: r['seconds'] for r in c.execute(
                "SELECT state, percentile_cont(0.5) WITHIN GROUP (ORDER BY seconds) AS seconds FROM "
                "(SELECT state,finished-claimed AS seconds,row_number() OVER "
                "(PARTITION BY state ORDER BY finished DESC) AS n FROM cc_lab_jobs "
                "WHERE phase='done' AND error IS NULL AND attempt=1 AND finished>=%s "
                "AND claimed IS NOT NULL AND finished>claimed AND finished-claimed<=300) recent "
                "WHERE n<=20 GROUP BY state", (now-86400,))}
            for jobs in pending.values():
                jobs.sort(key=lambda j: (-estimates.get(j['state'], 10.0), j['state'], j['id']))
            workflows.sort(key=lambda w: (running[w['id']], w['dispatched'], w['submitted'], w['id']))
            if (protected and used+protected['weight']<=ceiling
                    and all(busy[r]<cfg['registry_limits'].get(r,4) for r in protected['resources'])):
                workflows.sort(key=lambda w:w['id']!=protected['workflow_id'])
            for w in workflows:
                if w['source_version'] != wk['source_version'] or running[w['id']] >= 15: continue
                if w['started'] is None and len(active) >= cfg['workflow_limit']: continue
                for j in pending.get(w['id'], []):
                    if used+j['weight'] > ceiling: continue
                    if len(j['resources'])==1 and any(
                            submitted<w['submitted'] and j['resources'][0] in resources
                            for submitted,resources in earlier_multi): continue
                    if any(busy[r] >= cfg['registry_limits'].get(r, 4) for r in j['resources']): continue
                    token = str(uuid.uuid4())
                    run_until = min(w['deadline'], now + (90 if j['state'] == '@discovery' else 300))
                    with c.pipeline():
                        c.execute("UPDATE cc_lab_jobs SET phase='running',owner=%s,token=%s,attempt=attempt+1,claimed=%s,lease_until=%s,run_until=%s WHERE id=%s",
                                  (worker, token, now, now+20, run_until, j['id']))
                        c.execute("UPDATE cc_lab_workflows SET phase='active',started=COALESCE(started,%s),dispatched=%s WHERE id=%s", (now, now, w['id']))
                        self.event(c, now, 'claimed', w['id'], j['id'], worker=worker, token=token,
                                   slot_limit=ceiling, admission=admission_evidence)
                    return {**j, 'owner': worker, 'token': token, 'attempt': j['attempt']+1,
                            'payload': w['payload'], 'version': w['source_version'], 'run_seconds': max(0, run_until-now),
                            'submitted': w['submitted'], 'claimed': now}
            return None

    def heartbeat(self, worker, jobs, observation=None):
        allowed = []
        with self.transaction() as (c, now):
            self._settle(c, now)
            wk = c.execute('SELECT * FROM cc_lab_workers WHERE id=%s', (worker,)).fetchone()
            if not wk or wk['retired']: return []
            c.execute('UPDATE cc_lab_workers SET heartbeat=%s WHERE id=%s', (now, worker))
            if observation is not None:
                self.event(c, now, 'worker_admission', worker=worker, **observation)
            for job, token in jobs:
                row = c.execute("UPDATE cc_lab_jobs SET lease_until=%s WHERE id=%s AND token=%s AND owner=%s AND phase='running' AND run_until>%s RETURNING id",
                                (now+20, job, token, worker, now)).fetchone()
                if row: allowed.append(job)
        return allowed

    def complete(self, worker, job, token, result=None, error=None):
        """Call only after the supervisor has reaped the entire task process tree."""
        with self.transaction() as (c, now):
            self._settle(c, now)
            j = c.execute('SELECT * FROM cc_lab_jobs WHERE id=%s AND owner=%s AND token=%s', (job, worker, token)).fetchone()
            if not j or j['phase'] not in HELD: return False
            w = c.execute('SELECT * FROM cc_lab_workflows WHERE id=%s', (j['workflow_id'],)).fetchone()
            if j['phase'] != 'running' or now >= j['run_until'] or w['stop_reason']:
                result, error = None, j['error'] or 'WORKFLOW_'+(w['stop_reason'] or 'deadline').upper()
            if result is not None:
                if not isinstance(result, dict) or re.sub(r'\D', '', str(result.get('ein', ''))) != w['ein']:
                    raise ValueError('Worker result identity mismatch')
                if j['state'] != '@discovery' and result.get('state') != j['state']:
                    raise ValueError('Worker result state mismatch')
                if result.get('app_version') != w['source_version']: raise ValueError('Worker result release mismatch')
            if result is None and not error: raise ValueError('Missing result or error')
            c.execute("UPDATE cc_lab_jobs SET phase='done',finished=%s,result=%s,error=%s WHERE id=%s",
                      (now, Jsonb(result) if result is not None else None, error, job))
            self.event(c, now, 'finished', w['id'], job, error=error)
            self._settle(c, now)
            return True

    def cancel(self, scope, ident):
        with self.transaction() as (c, now):
            w = c.execute('SELECT * FROM cc_lab_workflows WHERE scope=%s AND id=%s', (scope, ident)).fetchone()
            if not w: raise NotFound('Workflow not found')
            if w['finished'] is None:
                c.execute("UPDATE cc_lab_workflows SET phase='stopping',stop_reason=COALESCE(stop_reason,'canceled') WHERE id=%s", (ident,))
                self.event(c, now, 'cancel_requested', ident)
                self._settle(c, now)

    def confirm_worker_stopped(self, worker, proof):
        """Operator-only recovery, never an HTTP user action or elapsed-time guess.

Caller must verify the hosting instance or all local descendant processes are
dead. Persist that evidence reference, fence all tokens, then requeue boundedly.
"""
        if not isinstance(proof, str) or len(proof.strip()) < 16: raise ValueError('Termination evidence reference required')
        with self.transaction() as (c, now):
            self._settle(c, now)
            c.execute('UPDATE cc_lab_workers SET retired=true WHERE id=%s', (worker,))
            for j in c.execute("SELECT * FROM cc_lab_jobs WHERE owner=%s AND phase IN ('running','stopping','quarantined')", (worker,)).fetchall():
                w = c.execute('SELECT * FROM cc_lab_workflows WHERE id=%s', (j['workflow_id'],)).fetchone()
                retry = not w['stop_reason'] and j['attempt'] < 2
                c.execute('UPDATE cc_lab_jobs SET phase=%s,token=NULL,owner=NULL,result=NULL,error=%s,finished=%s WHERE id=%s',
                          ('queued' if retry else 'done', None if retry else 'WORKER_STOPPED', None if retry else now, j['id']))
                self.event(c, now, 'termination_confirmed', w['id'], j['id'], proof=proof, requeued=retry)
            self._settle(c, now)

    def status(self, scope, ident):
        with self.transaction() as (c, now):
            self._settle(c, now)
            w = c.execute('SELECT * FROM cc_lab_workflows WHERE scope=%s AND id=%s', (scope, ident)).fetchone()
            if not w: raise NotFound('Workflow not found')
            jobs = c.execute('SELECT state,phase,attempt,claimed,finished,result,error FROM cc_lab_jobs WHERE workflow_id=%s ORDER BY state', (ident,)).fetchall()
            position = c.execute("SELECT count(*) AS n FROM cc_lab_workflows WHERE phase='queued' AND submitted<=%s", (w['submitted'],)).fetchone()['n'] if w['phase'] == 'queued' else 0
            return {k: w[k] for k in ('id','ein','kind','mode','phase','source_version','submitted','deadline','started','finished','stop_reason')} | {
                'jobs': jobs, 'completed': sum(j['phase'] == 'done' for j in jobs), 'total': len(jobs),
                'queue_position': position, 'queue_seconds': (w['started'] or w['finished'] or now)-w['submitted'],
                'execution_seconds': max(0, (w['finished'] or now)-w['started']) if w['started'] else 0}

    def metrics(self):
        with self.transaction() as (c, now):
            self._settle(c, now)
            return {'scope': 'shared_postgres', 'settings': c.execute('SELECT * FROM cc_lab_settings').fetchone(),
                    'workflows': c.execute('SELECT phase,count(*) AS count FROM cc_lab_workflows GROUP BY phase').fetchall(),
                    'jobs': c.execute('SELECT phase,count(*) AS count FROM cc_lab_jobs GROUP BY phase').fetchall(),
                    'workers': c.execute('SELECT id,slots,heartbeat,retired FROM cc_lab_workers').fetchall()}
