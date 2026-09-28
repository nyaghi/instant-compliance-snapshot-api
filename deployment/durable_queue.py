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
import math
import os
from pathlib import Path
import re
import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

LOCK = 4823915721
HELD = ('running', 'stopping', 'quarantined')
TERMINAL = ('completed', 'canceled', 'expired')
DISCOVERY_QUEUE_SECONDS = 270
DISCOVERY_EXECUTION_SECONDS = 90


class Conflict(ValueError): pass
class QueueFull(ValueError): pass
class NotFound(ValueError): pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def normalize_submission(payload, supported):
    """Validate immutable scheduling input. Master retains alias normalization."""
    allowed = {'organization_name', 'ein', 'alternate_names', 'states', 'mode', 'kind', 'state_concurrency'}
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
    concurrency = payload.get('state_concurrency', 15)
    allowed_concurrency = (5, 10, 15, 20, 32) if mode == 'sales' else (5, 10, 15, 20)
    if type(concurrency) is not int or concurrency not in allowed_concurrency:
        raise ValueError('Lab state concurrency must be 5, 10, 15 or 20; Sales also allows 32')
    if kind == 'discovery' and 'state_concurrency' in payload:
        raise ValueError('State concurrency applies only to registration')
    normalized = {'organization_name': name.strip(), 'ein': ein.replace('-', ''),
                  'alternate_names': aliases, 'states': sorted(set(states)), 'mode': mode, 'kind': kind}
    # Keep default submissions and their idempotency fingerprints unchanged.
    if concurrency != 15:
        normalized['state_concurrency'] = concurrency
    return normalized


class DurationEstimates(dict):
    """Median service times plus source-wide tail latency for Sales ordering.

    Only elapsed times are retained. No organization identity, registry result,
    or classification is reused, and unknown states keep the existing default.
    """
    def __init__(self, rows):
        rows = list(rows)
        super().__init__((r['state'], r['seconds']) for r in rows)
        self.tails = {r['state']: r['tail_seconds'] for r in rows}
        self.means = {r['state']: r.get('mean_seconds', r['seconds']) for r in rows}


def sales_tail_scores(workflows, pending, held, estimates, limits):
    """Estimated source drain time, never a result or an admission decision.

    Shortest-first across every organization leaves the same slow registries
    idle until late in Sales. Under concurrent Sales demand, start the sources
    with the largest shared backlog earlier. Limits and process reservations
    remain authoritative; no work is omitted or permit released early.
    """
    sales = {w['id'] for w in workflows if w['mode'] == 'sales'}
    if len(sales) < 2:
        return {}
    demand = Counter(j['state'] for ident in sales for j in pending.get(ident, [])
                     if not j['state'].startswith('@'))
    demand.update(j['state'] for j in held if j['workflow_id'] in sales
                  and not j['state'].startswith('@'))
    if getattr(estimates, 'as_of', None) is not None:
        if getattr(estimates, 'workload_timing', False):
            # One slow query does not make every queued query equally slow.
            # Retain a full tail allowance, then estimate the remaining waves
            # from the source-wide mean. This changes ordering, not admission.
            return {state: getattr(estimates, 'tails', estimates).get(state, 10.0)
                    + max(0.0, count-max(1, limits.get(state, 4)))
                    * estimates.means.get(state, 10.0) / max(1, limits.get(state, 4))
                    for state, count in demand.items()}
        # Spare lanes cannot make a single remaining query take less than one
        # query's service time. Avoid demoting the last long searches.
        return {state: max(1.0, count / max(1, limits.get(state, 4)))
                * getattr(estimates, 'tails', estimates).get(state, 10.0)
                for state, count in demand.items()}
    return {state: count * getattr(estimates, 'tails', estimates).get(state, 10.0) / max(1, limits.get(state, 4))
            for state, count in demand.items()}


def sales_tail_capacity(workflows, pending, held, estimates, workers, version, now):
    """Use slow-source ordering only when measured work fits physical capacity.

    This is a priority heuristic, never permission to overbook. The ordinary
    live source/CPU/memory/slot checks still decide whether a job can start.
    Scarce pools retain shortest-first, as does any unknown/stale capacity.
    """
    sales = [w for w in workflows if w['mode'] == 'sales']
    if len(sales) < 2:
        return False
    window = min(w['deadline'] for w in sales) - now
    slots = sum(w['slots'] for w in workers if not w['retired']
                and w['source_version'] == version and 0 <= now-w['heartbeat'] < 20)
    if window <= 0 or slots <= 0:
        return False
    demand = sum(j['weight'] * estimates.get(j['state'], 10.0)
                 for w in sales for j in pending.get(w['id'], []))
    # Existing work of either mode continues to own its physical reservation.
    demand += sum(j['weight'] * max(1.0, estimates.get(j['state'], 10.0)
                  - max(0.0, now-(j.get('claimed') or now))) for j in held)
    return demand <= slots * window


def order_pending(workflow, jobs, estimates, tail_scores, now):
    def key(job):
        state = job['state']
        seconds = estimates.get(state, 10.0)
        if workflow['mode'] == 'sales' and tail_scores:
            # Work unlikely to fit must not displace feasible completions.
            return (state != '@sales_identity', seconds > workflow['deadline']-now,
                    -tail_scores.get(state, 0), seconds, state, job['id'])
        direction = 1 if workflow['mode'] == 'sales' else -1
        return (state != '@sales_identity', direction*seconds, state, job['id'])
    jobs.sort(key=key)


def apply_censored_tail_floor(c, now, states, estimates):
    """A deadline-truncated search is a lower bound on source service time.

    Preserve completed medians and all admission rules. Only concurrent Sales
    urgency uses this floor; failed results themselves are never reused.
    """
    rows = c.execute(
        "SELECT wanted.state, percentile_cont(0.95) WITHIN GROUP (ORDER BY recent.seconds) AS tail_seconds "
        "FROM unnest(%s::text[]) AS wanted(state) CROSS JOIN LATERAL "
        "(SELECT finished-claimed AS seconds FROM cc_lab_jobs WHERE state=wanted.state "
        "AND phase='done' AND (error IS NULL OR error IN ('WORKFLOW_DEADLINE','TASK_TIME_LIMIT')) "
        "AND attempt=1 AND finished>=%s AND claimed IS NOT NULL "
        "AND finished>claimed AND finished-claimed<=300 "
        "ORDER BY finished DESC LIMIT 20) recent GROUP BY wanted.state", (sorted(states), now-86400))
    for row in rows:
        state = row['state']
        estimates.tails[state] = max(estimates.tails.get(state, estimates.get(state, 10.0)), row['tail_seconds'])


def cohort_timing_estimates(queue, c, now, states, version, workflows):
    """Freeze elapsed-time metadata before a concurrent Sales cohort begins.

    In-burst quick completions must not evict the slow searches from the last20
    sample while those searches are still waiting. Read the existing bounded
    timing histories as of the oldest active Sales submission, with the same
    completed median and censored tail rules. No identities/results are reused.
    Standard, mixed-mode, discovery and individual Sales retain their path.
    """
    enabled = (getattr(queue, 'sales_policy', '') == 'tail-aware'
               and version.endswith('-performance-lab')
               and os.environ.get('CE_LAB_SALES_COHORT_TIMING') == '1'
               and len(workflows) > 1
               and all(w['mode'] == 'sales' and w['kind'] == 'registration'
                       for w in workflows))
    if not enabled:
        return queue.cached_duration_estimates(c, now, states, version)
    before = min(w['submitted'] for w in workflows)
    if not 0 <= now-before <= 60:
        return queue.cached_duration_estimates(c, now, states, version)
    cache = getattr(queue, '_cohort_timing_cache', None)
    workload_timing = os.environ.get('CE_LAB_SALES_WORKLOAD_TIMING') == '1'
    if (cache and cache[0] == version and cache[1] == before and states <= cache[2]
            and getattr(cache[3], 'workload_timing', False) == workload_timing):
        return cache[3]
    def rows(include_censored):
        eligible = ("(error IS NULL OR error IN ('WORKFLOW_DEADLINE','TASK_TIME_LIMIT'))"
                    if include_censored else 'error IS NULL')
        projection = ("percentile_cont(0.95) WITHIN GROUP (ORDER BY recent.seconds) AS tail_seconds"
                      if include_censored else
                      "percentile_cont(0.5) WITHIN GROUP (ORDER BY recent.seconds) AS seconds, "
                      "percentile_cont(0.95) WITHIN GROUP (ORDER BY recent.seconds) AS tail_seconds")
        if workload_timing:
            projection += ", avg(recent.seconds) AS mean_seconds"
        return c.execute(
            f"SELECT wanted.state, {projection} FROM unnest(%s::text[]) AS wanted(state) "
            "CROSS JOIN LATERAL (SELECT finished-claimed AS seconds FROM cc_lab_jobs "
            f"WHERE state=wanted.state AND phase='done' AND {eligible} AND attempt=1 "
            "AND finished>=%s AND finished<=%s AND claimed IS NOT NULL "
            "AND finished>claimed AND finished-claimed<=300 "
            "ORDER BY finished DESC LIMIT 20) recent GROUP BY wanted.state",
            (sorted(states), before-86400, before))
    values = DurationEstimates(rows(False))
    if os.environ.get('CE_LAB_SALES_TAIL_CENSORING') == '1':
        for row in rows(True):
            state = row['state']
            values.tails[state] = max(values.tails.get(state, values.get(state, 10.0)), row['tail_seconds'])
            if workload_timing and row.get('mean_seconds') is not None:
                values.means[state] = row['mean_seconds']
    values.as_of = before
    values.workload_timing = workload_timing
    queue._cohort_timing_cache = (version, before, frozenset(states), values)
    return values


def claim_candidates(workflows, pending, running, estimates, tail_scores, now, version, protected):
    """Order candidates; the claim loop still owns every admission check.

    A source's urgency must be compared across the whole concurrent Sales
    cohort. Comparing organizations first can strand a slow search even when
    its source lane is free. Organization fairness breaks ties between equal
    source priorities. This never grants capacity or bypasses identity work.
    """
    candidates = [(w, j) for w in workflows for j in pending.get(w['id'], [])]
    enabled = (version.endswith('-performance-lab')
               and os.environ.get('CE_LAB_SALES_GLOBAL_PRIORITY') == '1'
               and getattr(estimates, 'as_of', None) is not None
               and bool(tail_scores) and protected is None and len(workflows) > 1
               and all(w['mode'] == 'sales' and w['kind'] == 'registration' for w in workflows))
    if enabled:
        def key(pair):
            w, j = pair
            seconds = estimates.get(j['state'], 10.0)
            if getattr(estimates, 'workload_timing', False):
                # Equal source urgency follows the earliest hard deadline.
                # A workflow with several long-running states must not keep
                # losing its remaining source turns merely because it is busy.
                return (j['state'] != '@sales_identity', seconds > w['deadline']-now,
                        -tail_scores.get(j['state'], 0), w['deadline'],
                        w['submitted'], w['id'], seconds, j['state'], j['id'])
            return (j['state'] != '@sales_identity', seconds > w['deadline']-now,
                    -tail_scores.get(j['state'], 0), running[w['id']],
                    w['dispatched'], w['submitted'], w['id'], seconds, j['state'], j['id'])
        candidates.sort(key=key)
    return candidates


def sales_source_start_intervals(workflows, version):
    """Optional lab start-rate limits, separate from simultaneous source slots."""
    if (not version.endswith('-performance-lab') or len(workflows) < 2
            or not all(w['mode'] == 'sales' and w['kind'] == 'registration' for w in workflows)):
        return {}
    try:
        values = json.loads(os.environ.get('CE_LAB_SALES_START_INTERVALS', '{}'))
        if (not isinstance(values, dict) or len(values) > 32
                or any(not re.fullmatch(r'[A-Z]{2}', key) or type(value) not in (int, float)
                       or not math.isfinite(value) or not 0 < value <= 5
                       for key, value in values.items())):
            return {}
        return values
    except (ValueError, TypeError):
        return {}


def sales_source_start_after(c, workflows, version, now):
    """Read latest starts under the claim lock, including already finished jobs.

    A fast failure must not erase its start-rate reservation. This changes only
    admission timing; no registry response, identity or result is read or reused.
    The indexed lookup is bounded to one timestamp per configured source.
    """
    intervals = sales_source_start_intervals(workflows, version)
    if not intervals:
        return {}
    rows = c.execute(
        'SELECT wanted.state, recent.claimed FROM unnest(%s::text[]) AS wanted(state) '
        'CROSS JOIN LATERAL (SELECT claimed FROM cc_lab_jobs WHERE state=wanted.state '
        'AND claimed IS NOT NULL ORDER BY claimed DESC LIMIT 1) recent', (sorted(intervals),))
    return {row['state']: row['claimed'] + intervals[row['state']] for row in rows
            if row['claimed'] + intervals[row['state']] > now}


class Queue:
    def __init__(self, dsn, max_connections=6, test_schema=None, ny_enabled=False, sales_policy=None):
        self.sales_policy = sales_policy or os.environ.get('CE_LAB_SALES_QUEUE_POLICY', 'shortest')
        if self.sales_policy not in ('shortest', 'tail-aware'):
            raise ValueError('Unsupported lab Sales queue policy')
        self._duration_cache = None
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
    def transaction(self, *, blocking=True):
        with self.pool.connection() as conn, conn.transaction():
            with conn.pipeline():
                lock = conn.execute("SELECT pg_advisory_xact_lock(%s)" if blocking else
                                    "SELECT pg_try_advisory_xact_lock(%s) AS acquired", (self.lock,))
                clock = conn.execute('SELECT extract(epoch FROM clock_timestamp()) AS t')
            if not blocking and not lock.fetchone()['acquired']:
                yield None
                return
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
                seconds = DISCOVERY_QUEUE_SECONDS if payload['kind'] == 'discovery' else (60 if payload['mode'] == 'sales' else 900)
                c.execute('INSERT INTO cc_lab_workflows(id,scope,ein,fingerprint,payload,kind,mode,source_version,phase,submitted,deadline) '
                          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'queued',%s,%s)",
                          (ident, scope, payload['ein'], fingerprint, Jsonb(payload), payload['kind'], payload['mode'], version, now, now+seconds))
                states = ['@discovery'] if payload['kind'] == 'discovery' else payload['states']
                if payload['kind'] == 'registration' and payload['mode'] == 'sales' and not payload['alternate_names']:
                    states = ['@sales_identity', *states]
                for state in states:
                    resources = (sorted(set(discovery_sources)) if state == '@discovery' else
                                 ['CO','IRS'] if state == '@sales_identity' else [state])
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
        c.execute("WITH desired AS (SELECT w.id,CASE WHEN EXISTS "
                  "(SELECT 1 FROM cc_lab_jobs j WHERE j.workflow_id=w.id AND j.phase='quarantined') THEN 'attention' "
                  "WHEN stop_reason IS NOT NULL THEN 'stopping' WHEN started IS NOT NULL THEN 'active' ELSE 'queued' END "
                  "AS phase FROM cc_lab_workflows w WHERE finished IS NULL) "
                  "UPDATE cc_lab_workflows w SET phase=d.phase FROM desired d "
                  "WHERE w.id=d.id AND w.phase IS DISTINCT FROM d.phase")

    def claim(self, worker, slot_limit=None, admission_evidence=None):
        # Claiming new work must not queue behind other workers and prevent this
        # supervisor from collecting completions or enforcing active deadlines.
        # A busy lock is an empty attempt; the existing bounded backoff retries.
        # Every actual read/admission still holds the same transaction lock.
        with self.transaction(blocking=False) as acquired:
            if acquired is None:
                return None
            c, now = acquired
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
                identity_rows = c.execute("SELECT j.workflow_id,j.phase,j.error FROM cc_lab_jobs j "
                    "JOIN cc_lab_workflows w ON w.id=j.workflow_id WHERE j.state='@sales_identity' AND w.finished IS NULL")
                capacity_rows = (c.execute('SELECT source_version,slots,heartbeat,retired FROM cc_lab_workers '
                    'WHERE retired=false AND heartbeat>%s', (now-20,)) if self.sales_policy == 'tail-aware' else None)
            identity = {row['workflow_id']: row for row in identity_rows.fetchall()}
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
            start_after = sales_source_start_after(c, workflows, cfg['source_version'], now)
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
                if w['source_version'] != wk['source_version'] or running[w['id']] >= w['payload'].get('state_concurrency', 15): continue
                if w['started'] is None and len(active) >= cfg['workflow_limit']: continue
                candidates=[j for j in pending.get(w['id'],[]) if len(j['resources'])>1 and j['weight']<=wk['slots']]
                ongoing=[j for j in held if j['workflow_id']==w['id'] and j['phase']=='running'
                         and (len(j['resources'])>1 or j['state']=='@discovery')]
                earlier_multi.extend((w['submitted'],set(j['resources'])) for j in candidates+ongoing)
                if candidates and protected is None:
                    protected=min(candidates,key=lambda j:j['id'])
            # Optional lab-only concurrent Sales policy. Organization fairness,
            # actual source/CPU limits, identity dependency and cutoff are below.
            estimates = cohort_timing_estimates(self, c, now,
                {j['state'] for jobs in pending.values() for j in jobs}, cfg['source_version'], workflows)
            tail_scores = (sales_tail_scores(workflows, pending, held, estimates, cfg['registry_limits'])
                           if capacity_rows is not None and sales_tail_capacity(workflows, pending, held,
                               estimates, capacity_rows.fetchall(), cfg['source_version'], now) else {})
            for workflow in workflows:
                order_pending(workflow, pending.get(workflow['id'], []), estimates, tail_scores, now)
            workflows.sort(key=lambda w: (running[w['id']], w['dispatched'], w['submitted'], w['id']))
            if (protected and used+protected['weight']<=ceiling
                    and all(busy[r]<cfg['registry_limits'].get(r,4) for r in protected['resources'])):
                workflows.sort(key=lambda w:w['id']!=protected['workflow_id'])
            for w, j in claim_candidates(workflows, pending, running, estimates, tail_scores,
                                         now, cfg['source_version'], protected):
                if w['source_version'] != wk['source_version'] or running[w['id']] >= w['payload'].get('state_concurrency', 15): continue
                if w['started'] is None and len(active) >= cfg['workflow_limit']: continue
                seed = identity.get(w['id'])
                if seed and j['state'] != '@sales_identity' and seed['phase'] != 'done': continue
                if used+j['weight'] > ceiling: continue
                if len(j['resources'])==1 and any(
                        submitted<w['submitted'] and j['resources'][0] in resources
                        for submitted,resources in earlier_multi): continue
                if any(busy[r] >= cfg['registry_limits'].get(r, 4) for r in j['resources']): continue
                if start_after.get(j['state'], now) > now: continue
                token = str(uuid.uuid4())
                if j['state'] == '@discovery' and w['started'] is None:
                    # The bounded waiting allowance must not consume the
                    # collector's unchanged execution allowance. Activate it
                    # once, atomically with the first claim. Recovery never
                    # resets this deadline or extends an already running job.
                    w['deadline'] = now + DISCOVERY_EXECUTION_SECONDS
                    c.execute('UPDATE cc_lab_workflows SET deadline=%s WHERE id=%s', (w['deadline'], w['id']))
                    self.event(c, now, 'discovery_execution_started', w['id'], j['id'],
                               queue_seconds=now-w['submitted'], execution_seconds=DISCOVERY_EXECUTION_SECONDS)
                run_until = min(w['deadline'], now + (DISCOVERY_EXECUTION_SECONDS if j['state'] == '@discovery' else 8 if j['state'] == '@sales_identity' else 300))
                seed_cursor = None
                with c.pipeline():
                    if seed and seed['phase']=='done' and j['state']!='@sales_identity':
                        seed_cursor = c.execute("SELECT result FROM cc_lab_jobs WHERE workflow_id=%s AND state='@sales_identity'", (w['id'],))
                    c.execute("UPDATE cc_lab_jobs SET phase='running',owner=%s,token=%s,attempt=attempt+1,claimed=%s,lease_until=%s,run_until=%s WHERE id=%s",
                              (worker, token, now, now+20, run_until, j['id']))
                    c.execute("UPDATE cc_lab_workflows SET phase='active',started=COALESCE(started,%s),dispatched=%s WHERE id=%s", (now, now, w['id']))
                    self.event(c, now, 'claimed', w['id'], j['id'], worker=worker, token=token,
                               slot_limit=ceiling, admission=admission_evidence,
                               state_concurrency=w['payload'].get('state_concurrency', 15),
                               sales_policy=('tail-aware' if tail_scores else 'shortest') if w['mode']=='sales' else None,
                               sales_policy_configured=self.sales_policy if w['mode']=='sales' else None,
                               source_timing_as_of=getattr(estimates, 'as_of', None),
                               source_drain_estimate=tail_scores.get(j['state']))
                if seed_cursor: seed['result'] = seed_cursor.fetchone()['result']
                return {**j, 'owner': worker, 'token': token, 'attempt': j['attempt']+1,
                        'payload': w['payload'], 'version': w['source_version'], 'run_seconds': max(0, run_until-now),
                        'submitted': w['submitted'], 'claimed': now,
                        **({'sales_identity': seed['result'] if seed['result'] is not None and not seed['error'] else
                            {'state':'@sales_identity','ein':w['ein'],'app_version':w['source_version'],
                             'sources':{},'errors':{'identity':seed['error'] or 'INCOMPLETE'}}}
                           if seed and seed['phase']=='done' and j['state']!='@sales_identity' else {})}
            return None

    def cached_duration_estimates(self, c, now, states, version):
        # Only scheduling durations are reused, for five seconds. Registry
        # results, identity evidence and current reservations are never cached.
        # Querying the same recent medians on every claim overwhelmed the small
        # lab queue database at 24 workers. Missing states/version/clock expiry
        # refresh the complete requested set; an unknown duration remains 10s.
        cache = self._duration_cache
        if cache and cache[0] == version and 0 <= now-cache[1] < 5 and states <= cache[2]:
            return cache[3]
        values = self.duration_estimates(c, now, states)
        if (getattr(self, 'sales_policy', '') == 'tail-aware'
                and os.environ.get('CE_LAB_SALES_TAIL_CENSORING') == '1'):
            apply_censored_tail_floor(c, now, states, values)
        self._duration_cache = (version, now, frozenset(states), values)
        return values

    @staticmethod
    def duration_estimates(c, now, states):
        # Same last-20 median and bounds; indexed top-N retrieval avoids sorting
        # all of the day's completed jobs on every scheduler turn.
        return DurationEstimates(c.execute(
            "SELECT wanted.state, percentile_cont(0.5) WITHIN GROUP (ORDER BY recent.seconds) AS seconds, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY recent.seconds) AS tail_seconds "
            "FROM unnest(%s::text[]) AS wanted(state) CROSS JOIN LATERAL "
            "(SELECT finished-claimed AS seconds FROM cc_lab_jobs WHERE state=wanted.state "
            "AND phase='done' AND error IS NULL AND attempt=1 AND finished>=%s "
            "AND claimed IS NOT NULL AND finished>claimed AND finished-claimed<=300 "
            "ORDER BY finished DESC LIMIT 20) recent GROUP BY wanted.state", (sorted(states), now-86400)))

    def release_discovery_sources(self, worker, job, token, completed):
        """Supervisor-only evidence from returned collectors, fenced like leases.

        The task remains running with its full physical weight and deadline.
        Never release IRS here: other discovery collectors may still use it.
        """
        if not isinstance(completed, list) or any(not isinstance(s, str) for s in completed):
            return False
        with self.transaction() as (c, now):
            self._settle(c, now)
            j = c.execute("SELECT * FROM cc_lab_jobs WHERE id=%s AND owner=%s AND token=%s "
                          "AND phase='running' AND state='@discovery' AND lease_until>%s AND run_until>%s",
                          (job, worker, token, now, now)).fetchone()
            if not j: return False
            requested = set(completed)
            if 'IRS' in requested or not requested.issubset(set(j['resources']) | set(j['released_resources'])):
                return False
            newly = sorted(requested.intersection(j['resources']))
            if newly:
                remaining = [s for s in j['resources'] if s not in requested]
                released = sorted(set(j['released_resources']) | set(newly))
                c.execute('UPDATE cc_lab_jobs SET resources=%s,released_resources=%s WHERE id=%s',
                          (Jsonb(remaining), Jsonb(released), job))
                self.event(c, now, 'discovery_sources_finished', j['workflow_id'], job, sources=newly)
            return True

    def heartbeat(self, worker, jobs, observation=None):
        allowed = []
        with self.transaction() as (c, now):
            self._settle(c, now)
            wk = c.execute('SELECT * FROM cc_lab_workers WHERE id=%s', (worker,)).fetchone()
            if not wk or wk['retired']: return []
            c.execute('UPDATE cc_lab_workers SET heartbeat=%s WHERE id=%s', (now, worker))
            if observation is not None:
                self.event(c, now, 'worker_admission', worker=worker, **observation)
            # Lease updates are independent inside the same advisory-locked
            # transaction. Pipeline their round trips; retain every ownership,
            # token, phase and deadline predicate and the original input order.
            with c.pipeline():
                renewals = [(job, c.execute("UPDATE cc_lab_jobs SET lease_until=%s WHERE id=%s AND token=%s AND owner=%s AND phase='running' AND run_until>%s RETURNING id",
                                           (now+20, job, token, worker, now)))
                            for job, token in jobs]
            for job, cursor in renewals:
                if cursor.fetchone(): allowed.append(job)
        return allowed

    def complete(self, worker, job, token, result=None, error=None):
        """Call only after the supervisor has reaped the entire task process tree."""
        return self.complete_many(worker, [(job, token, result, error)])[0]

    def complete_many(self, worker, completions):
        """Persist already-reaped tasks together, preserving every job's fence.

        No capacity is released for a live process. Invalid results roll back
        the whole transaction; the supervisor can isolate them individually.
        """
        if not 1 <= len(completions) <= 12 or len({item[0] for item in completions}) != len(completions):
            raise ValueError('Completion batch must contain 1–12 distinct jobs')
        with self.transaction() as (c, now):
            self._settle(c, now)
            jobs = {j['id']: j for j in c.execute(
                'SELECT j.*,w.ein,w.source_version,w.stop_reason FROM cc_lab_jobs j '
                'JOIN cc_lab_workflows w ON w.id=j.workflow_id WHERE j.id=ANY(%s) AND j.owner=%s',
                ([item[0] for item in completions], worker))}
            updates=[]; accepted=[]
            for job,token,result,error in completions:
                j=jobs.get(job)
                if not j or j['token'] != token or j['phase'] not in HELD:
                    accepted.append(False);continue
                if j['phase'] != 'running' or now >= j['run_until'] or j['stop_reason']:
                    result,error=None,j['error'] or 'WORKFLOW_'+(j['stop_reason'] or 'deadline').upper()
                if result is not None:
                    if not isinstance(result,dict) or re.sub(r'\D','',str(result.get('ein',''))) != j['ein']:
                        raise ValueError('Worker result identity mismatch')
                    if j['state'] != '@discovery' and result.get('state') != j['state']:
                        raise ValueError('Worker result state mismatch')
                    if result.get('app_version') != j['source_version']:raise ValueError('Worker result release mismatch')
                if result is None and not error:raise ValueError('Missing result or error')
                updates.append((j,result,error));accepted.append(True)
            with c.pipeline():
                for j,result,error in updates:
                    c.execute("UPDATE cc_lab_jobs SET phase='done',finished=%s,result=%s,error=%s WHERE id=%s",
                              (now,Jsonb(result) if result is not None else None,error,j['id']))
                    self.event(c,now,'finished',j['workflow_id'],j['id'],error=error)
            self._settle(c, now)
            return accepted

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
                c.execute('UPDATE cc_lab_jobs SET phase=%s,token=NULL,owner=NULL,result=NULL,error=%s,finished=%s,'
                          'resources=%s,released_resources=%s WHERE id=%s',
                          ('queued' if retry else 'done', None if retry else 'WORKER_STOPPED', None if retry else now,
                           Jsonb(sorted(set(j['resources']) | set(j['released_resources']))), Jsonb([]), j['id']))
                self.event(c, now, 'termination_confirmed', w['id'], j['id'], proof=proof, requeued=retry)
            self._settle(c, now)

    def status(self, scope, ident):
        snapshot, due = self._status_snapshot(scope, ident)
        if due:
            # Expiry/worker-loss transitions still use the scheduling authority.
            # Ordinary UI polling must not serialize behind (or ahead of) claims.
            with self.transaction() as (c, now):
                self._settle(c, now)
            snapshot, _ = self._status_snapshot(scope, ident)
        return snapshot

    def _status_snapshot(self, scope, ident):
        with self.pool.connection() as c, c.transaction():
            c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            now = float(c.execute('SELECT extract(epoch FROM clock_timestamp()) AS t').fetchone()['t'])
            w = c.execute('SELECT * FROM cc_lab_workflows WHERE scope=%s AND id=%s', (scope, ident)).fetchone()
            if not w: raise NotFound('Workflow not found')
            jobs = c.execute('SELECT state,phase,attempt,claimed,finished,result,error,lease_until FROM cc_lab_jobs WHERE workflow_id=%s ORDER BY state', (ident,)).fetchall()
            due = (w['finished'] is None and (w['stop_reason'] is None and w['deadline'] <= now or any(
                j['phase'] in ('running', 'stopping') and j['lease_until'] is not None and j['lease_until'] <= now for j in jobs)))
            for j in jobs: j.pop('lease_until')
            preparation = [j for j in jobs if j['state']=='@sales_identity']
            jobs = [j for j in jobs if j['state']!='@sales_identity']
            position = c.execute("SELECT count(*) AS n FROM cc_lab_workflows WHERE phase='queued' AND submitted<=%s", (w['submitted'],)).fetchone()['n'] if w['phase'] == 'queued' else 0
            return ({k: w[k] for k in ('id','ein','kind','mode','phase','source_version','submitted','deadline','started','finished','stop_reason')} | {
                'preparation': preparation, 'jobs': jobs, 'completed': sum(j['phase'] == 'done' for j in jobs), 'total': len(jobs),
                'queue_position': position, 'queue_seconds': (w['started'] or w['finished'] or now)-w['submitted'],
                'execution_seconds': max(0, (w['finished'] or now)-w['started']) if w['started'] else 0}, due)

    def metrics(self):
        with self.transaction() as (c, now):
            self._settle(c, now)
            return {'scope': 'shared_postgres', 'settings': c.execute('SELECT * FROM cc_lab_settings').fetchone(),
                    'workflows': c.execute('SELECT phase,count(*) AS count FROM cc_lab_workflows GROUP BY phase').fetchall(),
                    'jobs': c.execute('SELECT phase,count(*) AS count FROM cc_lab_jobs GROUP BY phase').fetchall(),
                    'workers': c.execute('SELECT id,slots,heartbeat,retired FROM cc_lab_workers').fetchall()}
