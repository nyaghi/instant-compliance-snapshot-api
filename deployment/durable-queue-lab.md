# Durable multi-worker candidate (lab only)

This candidate is not a production/team-access rollout. It runs the existing
master state engine in supervised, disposable processes. No state-specific
adapter, matching, alias, EIN/address, status, comment, or date rule is copied.

## Concrete topology

- Existing private performance-lab web service remains the acceptance/progress
  API and hosts one eight-reservation worker supervisor on its existing Pro node.
- A second independent Pro background worker uses the same branch/master code,
  the same database and its own eight physical reservations.
- PostgreSQL stores inputs, submission keys, workflow/state jobs, worker leases,
  results and lifecycle events. All schedulers share one transactional authority.
- The new database `charityclarity-performance-lab-queue` is currently a free
  experiment, expiring October 25, 2026. It is not approved production storage,
  high availability, or a backed-up enterprise database.
- No changes to staging, production, user Chrome, or the NY connector.

The additional Pro worker is $85/month at the pricing reviewed September 25,
2026, prorated. The existing Pro lab is also $85/month: combined compute would
be $170/month. The temporary database adds no charge. A later paid 256 MB
database is $6/month plus applicable storage ($0.30/GB/month), and requires its
own explicit resource decision. No automatic paid database upgrade is included.

## Public-to-private contract

All endpoints require the existing unique private lab Bearer/Basic credential.
The server derives the fixed `private-performance-lab` scope. It rejects
client-supplied scope, credentials, URLs, executables and unsupported inputs.
This is deliberately not customer workspace authentication.

`POST /api/lab/workflows` with `Idempotency-Key` accepts only organization_name,
ein, alternate_names, states, mode and kind. Kind is registration or discovery.
Discovery is a separate first step; returned aliases are reviewed and explicitly
submitted with registration. The scheduler never silently adds unreviewed names.
The response contains a durable ID and progress URL. Poll
`GET /api/lab/workflows/{id}`; cancel with
`POST /api/lab/workflows/{id}/cancel`. Closing the caller does not cancel a job.

Immutable fingerprint includes entered/reviewed names, EIN, states, mode and
source release. Retries return the original job. Identical simultaneous work
deduplicates within its scope. Changed inputs while that EIN is active conflict
instead of silently joining an incompatible run. Historical idempotency keys
continue returning their original completed workflow; use a new key for a new run.

While durable mode is enabled, direct `/api/check`, `/api/discover-names`, NY
connector and evidence execution are disabled. They cannot bypass shared
admission. The frozen product UI is not yet migrated to the queue API; use the
private experiment client. Health/metrics and private assets remain available.

## Limits, fairness and recovery

- At most 15 started, unfinished workflows across every worker/connection.
  Additional accepted workflows remain queued. Backlog is bounded at 1,000.
- Each node has at most eight reservations. A complete discovery reserves four
  and also reserves each participating registry for its lifetime; ordinary
  state jobs reserve one. This conservative starting policy must be measured.
- Registry-wide whole-job caps: ME/AR one each, FL three, other states four.
  These cover top-level state/discovery jobs; indirect cross-state identity
  helpers can still consult other sources. They are not a complete per-request
  rate limiter. Existing master limits remain in place within each task.
- Prefer workflows with fewer running jobs, then least recently dispatched.
  No workflow gets more than 15 state jobs at once.
- Sales: 60 seconds including queue wait. Standard: 900-second workflow ceiling
  and 300-second maximum per admitted state. Discovery: 90 seconds including
  queue wait. Existing adapter timeouts/retries remain unchanged.
- Worker heartbeat every three seconds, 20-second lease. Loss of connectivity
  stops child work locally; the queue does not infer death from elapsed time.
- Linux uses a separate process group; Windows uses kill-on-close Job Objects.
  Stop/cancel/timeout kills and reaps descendants before releasing capacity.
  A Linux child additionally watches parent lifetime and its own deadline.
- Lost leases become quarantined and retain capacity. Only a supervisor with
  verified process-tree termination, or an operator with hosting-instance death
  evidence, may fence/requeue them. Old owners cannot overwrite replacement jobs.
  Confirmed-loss retries are bounded to two attempts and remain in the audit.
- Unfinished tasks have explicit transport/lifecycle error codes, no invented
  registry status. NY is explicitly unqualified and returns
  `NY_COLLECTOR_NOT_CONFIGURED`; it never contacts the user's browser.

## Deployment switches (candidate, not active configuration)

Build: `pip install -r deployment/requirements-lab.txt && PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install chromium`

Existing lab API start remains `python -u deployment/performance_lab.py`.
Set CE_LAB_DURABLE_QUEUE=1, CE_LAB_QUEUE_WORKER=1, CE_LAB_WORKER_SLOTS=8,
CE_APP_VERSION=2026.09.25.perf.7-performance-lab, and the separate internal
CE_LAB_DATABASE_URL. Preserve all disabled helper/fanout values. Keep secrets
outside Git. The new worker starts `python -u deployment/queue_worker.py` with
CE_LAB_ROLE=worker, its exact CE_LAB_WORKER_SERVICE_ID and fixed Render name
`charityclarity-performance-lab-worker-1`. The API service ID remains hard-bound
to the retired expansion lab; protected staging IDs are explicitly refused.

Database initialization never silently changes a live version or limits. Before
activating a new release, drain all work, verify zero held reservations, record
the current settings, and explicitly update the lab settings to the new release.

## Qualification gates

Real PostgreSQL controls verify concurrent duplicate submission, 15-workflow
ceiling across worker connections, scope rejection, registry limits, queue time,
cancel/deadline races, restart recovery, stale-owner fencing, and descendant
termination. Master adapter tests preserve full result fields and reviewed names.

These tests establish correctness properties, not live registry throughput.
Cloud post-validation must still compare the same one/two-org controls, then
increase to 3/5/10/15 only while identities/status/dates remain consistent and
mean per-org time is below the agreed 50% slowdown stop rule. Preserve first
responses and explicitly separate registry availability from capacity failures.
NY, customer authorization, mixed workload capacity and hundreds of users remain
unqualified. Do not promote this candidate based on fixture success alone.

Sources: https://render.com/pricing and https://render.com/docs/postgresql-creating-connecting.
