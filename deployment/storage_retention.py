"""Staging artifact retention. Short idle-only batches; never registry work.

Aurora archives expire after 24 hours. Alerts artifacts use their own existing
retention/protection rules. Filing applications and receipts are separate tables
and are never touched here. Queue timing metadata is retained; old bulky results
are compacted after ten days, as are operational events.
"""
from datetime import datetime, timezone
import time
import uuid
from psycopg.types.json import Jsonb

DAY=86400
LOCK=824527341
SCHEMA='''
CREATE TABLE IF NOT EXISTS cc_storage_maintenance (
 id integer PRIMARY KEY CHECK(id=1), last_attempt double precision,
 last_success double precision, last_error text,
 deleted_snapshots bigint NOT NULL DEFAULT 0, released_logical_bytes bigint NOT NULL DEFAULT 0,
 backfilled bigint NOT NULL DEFAULT 0, trimmed_jobs bigint NOT NULL DEFAULT 0,
 deleted_events bigint NOT NULL DEFAULT 0,
 busy_until double precision NOT NULL DEFAULT 0, lease text,
 latest jsonb NOT NULL DEFAULT '{}'
);
INSERT INTO cc_storage_maintenance(id) VALUES(1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS cc_storage_compacted_jobs (
 job_id text PRIMARY KEY REFERENCES cc_lab_jobs(id) ON DELETE CASCADE,
 compacted_at double precision NOT NULL
);
'''

def expiry_at(metadata,now):
    stamp=metadata.get('captured_at')
    if type(stamp) not in (int,float) or not 0<stamp<=now+60:
        return now+DAY # Unknown dates fail safe; never immediately purge.
    return stamp+DAY

def compact_result(value):
    if not isinstance(value,dict):return {'storage_compacted':True}
    keep=('state','status','success','ein','organization_name','matched_registry_name',
          'matched_registry_identifier','registration_date','renewal_filing_value','reason_code')
    result={k:value[k] for k in keep if k in value and isinstance(value[k],(str,bool,int,float,type(None)))}
    for key in ['comments','source_note','source_url']:
        if isinstance(value.get(key),str):result[key]=value[key][:600]
    return result|{'storage_compacted':True,'online_evidence_expired':True}

def idle(c):
    return not c.execute("SELECT EXISTS(SELECT 1 FROM cc_lab_workflows WHERE finished IS NULL) "
        "OR EXISTS(SELECT 1 FROM cc_lab_jobs WHERE phase IN ('running','stopping','quarantined')) "
        "OR EXISTS(SELECT 1 FROM cc_alert_orgs WHERE workflow IS NOT NULL) AS busy").fetchone()['busy']

def backfill(c,now,limit):
    # Materialize IDs before reading potentially toasted JSON metadata. Only a
    # bounded set is decompressed, avoiding a full archive scan every minute.
    rows=c.execute("""WITH candidates AS MATERIALIZED (
      SELECT s.id FROM cc_state_snapshots s
      LEFT JOIN cc_state_snapshot_scratch q ON q.id=s.id
      LEFT JOIN cc_alert_artifacts a ON a.id=s.id
      WHERE q.id IS NULL AND a.id IS NULL ORDER BY s.id LIMIT %s
    ) SELECT s.id,s.metadata FROM candidates x JOIN cc_state_snapshots s ON s.id=x.id""",(limit,)).fetchall()
    count=0
    for row in rows:
        expires=datetime.fromtimestamp(expiry_at(row['metadata'],now),timezone.utc)
        count+=c.execute('INSERT INTO cc_state_snapshot_scratch(id,discard_after) VALUES(%s,%s) ON CONFLICT DO NOTHING',(row['id'],expires)).rowcount
    return count

def delete_snapshots(c,now,limit):
    rows=c.execute("""WITH expired AS (
      SELECT q.id FROM cc_state_snapshot_scratch q
      JOIN cc_state_snapshots s ON s.id=q.id
      LEFT JOIN cc_alert_artifacts a ON a.id=s.id
      WHERE q.discard_after<=to_timestamp(%s) AND a.id IS NULL
        AND coalesce(s.metadata->>'alerts_owned','false')<>'true'
        AND NOT EXISTS (SELECT 1 FROM cc_alert_confirmed r WHERE r.evidence IN
          ('/state-snapshots/'||s.id||'.pdf','/state-evidence/'||s.id||'/search-history.pdf'))
        AND NOT EXISTS (SELECT 1 FROM cc_alert_changes h WHERE h.evidence IN
          ('/state-snapshots/'||s.id||'.pdf','/state-evidence/'||s.id||'/search-history.pdf'))
        AND NOT EXISTS (SELECT 1 FROM cc_alert_auto_matches m WHERE m.previous->>'evidence' IN
          ('/state-snapshots/'||s.id||'.pdf','/state-evidence/'||s.id||'/search-history.pdf'))
      ORDER BY q.discard_after,q.id LIMIT %s FOR UPDATE OF q,s SKIP LOCKED
    ) DELETE FROM cc_state_snapshots s USING expired x WHERE s.id=x.id
      RETURNING octet_length(s.source)+coalesce(octet_length(s.pdf),0) AS bytes""",(now,limit)).fetchall()
    return len(rows),sum(x['bytes'] for x in rows)

def trim_jobs(c,now,limit):
    rows=c.execute("""WITH candidates AS MATERIALIZED (
      SELECT j.id FROM cc_lab_jobs j JOIN cc_lab_workflows w ON w.id=j.workflow_id
      LEFT JOIN cc_storage_compacted_jobs x ON x.job_id=j.id
      WHERE j.phase='done' AND j.finished<%s AND w.finished<%s
        AND w.phase IN ('completed','canceled','expired') AND j.result IS NOT NULL AND x.job_id IS NULL
        AND NOT EXISTS(SELECT 1 FROM cc_alert_artifacts a WHERE a.workflow=w.id)
        AND NOT EXISTS(SELECT 1 FROM cc_alert_auto_matches a WHERE a.workflow=w.id)
        AND NOT EXISTS(SELECT 1 FROM cc_alert_changes a WHERE a.workflow=w.id)
      ORDER BY j.finished,j.id LIMIT %s FOR UPDATE OF j SKIP LOCKED
      ) SELECT j.id,j.result FROM candidates x JOIN cc_lab_jobs j ON j.id=x.id""",(now-10*DAY,now-10*DAY,limit)).fetchall()
    for row in rows:
        c.execute('UPDATE cc_lab_jobs SET result=%s WHERE id=%s',(Jsonb(compact_result(row['result'])),row['id']))
        c.execute('INSERT INTO cc_storage_compacted_jobs VALUES(%s,%s) ON CONFLICT DO NOTHING',(row['id'],now))
    return len(rows)

def delete_events(c,now,limit):
    return c.execute("""WITH expired AS (SELECT e.sequence FROM cc_lab_events e
      WHERE e.at<%s AND NOT EXISTS(SELECT 1 FROM cc_lab_workflows w WHERE w.id=e.workflow_id AND w.finished IS NULL)
      ORDER BY e.sequence LIMIT %s FOR UPDATE SKIP LOCKED)
      DELETE FROM cc_lab_events e USING expired x WHERE e.sequence=x.sequence""",(now-10*DAY,limit)).rowcount

class Maintenance:
    def __init__(self,pool):self.pool=pool
    def status(self):
        with self.pool.connection(timeout=.25) as c:
            c.execute("SET LOCAL statement_timeout='500ms'")
            return c.execute('SELECT * FROM cc_storage_maintenance WHERE id=1').fetchone()
    def batch(self,*,snapshots=128,jobs=64,events=256,enroll=128,lease=None):
        if any(type(x) is not int or not 0<=x<=1024 for x in [snapshots,jobs,events,enroll]):raise ValueError('Invalid maintenance batch size')
        started=time.monotonic()
        try:
            with self.pool.connection(timeout=.25) as c:
                c.execute("SET LOCAL statement_timeout='1500ms'")
                if not c.execute('SELECT pg_try_advisory_xact_lock(%s) AS ok',(LOCK,)).fetchone()['ok']:return {'deferred':'another_cleanup'}
                now=float(c.execute('SELECT extract(epoch FROM clock_timestamp()) AS t').fetchone()['t'])
                state=c.execute('SELECT * FROM cc_storage_maintenance WHERE id=1 FOR UPDATE').fetchone()
                if state['busy_until']>now and state['lease']!=lease:return {'deferred':'maintenance_lease'}
                if not idle(c):
                    c.execute("UPDATE cc_storage_maintenance SET last_attempt=%s,latest=%s WHERE id=1",(now,Jsonb({'deferred':'active_check'})))
                    return {'deferred':'active_check'}
                filled=backfill(c,now,enroll) if enroll else 0
                removed,raw=delete_snapshots(c,now,snapshots) if snapshots else (0,0)
                # Optional history maintenance must never roll back successful
                # artifact expiry. A savepoint isolates each secondary stage.
                deferred=[];trimmed=0;purged=0
                if jobs:
                    try:
                        with c.transaction():trimmed=trim_jobs(c,now,jobs)
                    except Exception as exc:deferred.append('job_payloads:'+type(exc).__name__)
                if events:
                    try:
                        with c.transaction():purged=delete_events(c,now,events)
                    except Exception as exc:deferred.append('events:'+type(exc).__name__)
                report=dict(backfilled=filled,deleted_snapshots=removed,released_logical_bytes=raw,trimmed_jobs=trimmed,deleted_events=purged,seconds=round(time.monotonic()-started,3))
                if deferred:report['deferred_stages']=deferred
                c.execute("UPDATE cc_storage_maintenance SET last_attempt=%s,last_success=%s,last_error=%s,"
                    "backfilled=backfilled+%s,deleted_snapshots=deleted_snapshots+%s,released_logical_bytes=released_logical_bytes+%s,"
                    "trimmed_jobs=trimmed_jobs+%s,deleted_events=deleted_events+%s,latest=%s WHERE id=1",
                    (now,now,';'.join(deferred) or None,filled,removed,raw,trimmed,purged,Jsonb(report)))
                return report
        except Exception as exc:
            try:
                with self.pool.connection(timeout=.25) as c:
                    c.execute("SET LOCAL statement_timeout='500ms'")
                    c.execute('UPDATE cc_storage_maintenance SET last_attempt=extract(epoch FROM clock_timestamp()),last_error=%s WHERE id=1',(type(exc).__name__,))
            except Exception:pass
            raise

def acquire_maintenance(c,now,seconds=300,queue_lock=4823915721):
    """Reserve an idle maintenance window under the queue admission lock."""
    c.execute('SELECT pg_advisory_xact_lock(%s)',(queue_lock,))
    state=c.execute('SELECT * FROM cc_storage_maintenance WHERE id=1 FOR UPDATE').fetchone()
    if state['busy_until']>now or not idle(c):raise RuntimeError('Checks must be idle before maintenance.')
    token=uuid.uuid4().hex
    c.execute('UPDATE cc_storage_maintenance SET busy_until=%s,lease=%s WHERE id=1',(now+seconds,token))
    return token

def release_maintenance(c,token):
    c.execute('UPDATE cc_storage_maintenance SET busy_until=0,lease=NULL WHERE id=1 AND lease=%s',(token,))
