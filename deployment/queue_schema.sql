-- Lab-only schema. One short transaction coordinates all API/worker replicas.
CREATE TABLE IF NOT EXISTS cc_lab_settings (
 id integer PRIMARY KEY CHECK (id = 1),
 workflow_limit integer NOT NULL CHECK (workflow_limit BETWEEN 1 AND 20),
 backlog_limit integer NOT NULL CHECK (backlog_limit > 0),
 source_version text NOT NULL,
 registry_limits jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS cc_lab_workflows (
 id text PRIMARY KEY, scope text NOT NULL, ein text NOT NULL,
 fingerprint text NOT NULL, payload jsonb NOT NULL, kind text NOT NULL,
 mode text NOT NULL, source_version text NOT NULL,
 phase text NOT NULL CHECK (phase IN ('queued','active','stopping','attention','completed','canceled','expired')),
 stop_reason text, submitted double precision NOT NULL,
 deadline double precision NOT NULL, started double precision, finished double precision,
 dispatched double precision NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS cc_lab_active_ein
 ON cc_lab_workflows(scope, ein) WHERE finished IS NULL;
CREATE TABLE IF NOT EXISTS cc_lab_submissions (
 scope text NOT NULL, key text NOT NULL, fingerprint text NOT NULL,
 workflow_id text NOT NULL REFERENCES cc_lab_workflows(id), PRIMARY KEY (scope,key)
);
CREATE TABLE IF NOT EXISTS cc_lab_workers (
 id text PRIMARY KEY, source_version text NOT NULL, slots integer NOT NULL,
 heartbeat double precision NOT NULL, retired boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS cc_lab_jobs (
 id text PRIMARY KEY, workflow_id text NOT NULL REFERENCES cc_lab_workflows(id),
 state text NOT NULL, resources jsonb NOT NULL, weight integer NOT NULL,
 phase text NOT NULL CHECK (phase IN ('queued','running','stopping','quarantined','done')),
 attempt integer NOT NULL DEFAULT 0, owner text REFERENCES cc_lab_workers(id),
 token text, claimed double precision, lease_until double precision,
 run_until double precision, finished double precision,
 result jsonb, error text, UNIQUE(workflow_id,state)
);
CREATE INDEX IF NOT EXISTS cc_lab_jobs_workflow ON cc_lab_jobs(workflow_id,phase);
CREATE INDEX IF NOT EXISTS cc_lab_jobs_owner ON cc_lab_jobs(owner,phase);
-- Completed discovery sources can release their own permits without releasing
-- the still-running job's physical weight. Recovery restores every reservation.
ALTER TABLE cc_lab_jobs ADD COLUMN IF NOT EXISTS released_resources jsonb NOT NULL DEFAULT '[]';
CREATE INDEX IF NOT EXISTS cc_lab_jobs_recent_duration ON cc_lab_jobs(state,finished DESC)
 WHERE phase='done' AND error IS NULL AND attempt=1 AND claimed IS NOT NULL;
CREATE TABLE IF NOT EXISTS cc_lab_events (
 sequence bigserial PRIMARY KEY, workflow_id text, job_id text,
 event text NOT NULL, at double precision NOT NULL, detail jsonb NOT NULL
);
