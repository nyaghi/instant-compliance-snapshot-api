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
2026, prorated. The user approved and activated this worker on September 25.
The existing Pro lab is also $85/month: combined compute is $170/month.
The temporary database adds no charge. A later paid 256 MB
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

## Active lab deployment

Both services run commit `07e6924fddcddfc5aabaaeae3d47b4bec7167434` as
`2026.09.25.perf.9-performance-lab`. The API/worker service is
`srv-d8u0hsu7r5hc73aqfsg0`; the independent background worker is
`srv-dar7adgu01pc738fsmgg`. Both have automatic deployment disabled.
The shared free database is `dpg-dar6utvavr4c7380ou60-a`.
Only the isolated lab has these changes; staging and production are unchanged.

Build: `pip install -r deployment/requirements-lab.txt && PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install chromium`

Existing lab API start remains `python -u deployment/performance_lab.py`.
Set CE_LAB_DURABLE_QUEUE=1, CE_LAB_QUEUE_WORKER=1, CE_LAB_WORKER_SLOTS=8,
CE_APP_VERSION=2026.09.25.perf.9-performance-lab, and the separate internal
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

## Authorized full-state follow-up (September 25)

The perf.11 lab candidate addresses measured CPU pressure without changing any
matching or status rule bodies. Bounded caches reuse pure punctuation/acronym
keys and target variants; the variant key includes the complete reviewed alias
tuple and returns a fresh list. Kansas's parser caches one exact workbook byte
sequence, leaving weekly asset validation, current metadata and all record
selection unchanged. Offline profiles found 24 identical workbook parses in
one negative KS lookup and almost 20,000 repeated target generations in NH.

The existing two Pro services may each admit up to 12 weighted task slots with
CE_LAB_RESOURCE_ADMISSION=1. This is not additional paid CPU: cgroup CPU/memory
measurements pause new starts at 85% CPU or without 384 MiB of memory headroom
below 85% of the allocation, and pace process launches by at least 250 ms.
Missing measurements retain the former eight-slot ceiling. Running work keeps
its reservation and deadline; the 15-workflow global cap, per-registry caps,
fair organization turns and safe termination rules are preserved. This is a
candidate to measure, not a claim that 24 CPU-heavy tasks can run at once.

Perf.10's real three-organization discovery-plus-32-state comparison preserved
all 96 statuses, identities and dates after correcting a Windows UTF-8 read in
the comparison harness. Florida retained its initial date and NY succeeded for
all three organizations. Registration averaged 125.4 seconds versus 63.4 solo;
mean state queue time rose from 12.1 to 57.8 seconds while execution rose from
19.0 to 19.6. Both workers reached their two-CPU limit; no retries or transport
errors occurred. The speed stop gate prevents increasing organization load
until the candidate is tested on the same controls.

The user authorized adding New York, improving queue/CPU pressure and Florida
date reliability, then increasing the controlled load. The perf.10 candidate
enables CE_LAB_NY_BROWSER=1 and routes NY through the existing master's verified
browser flow. It does not use a user profile, extension, alternate status engine
or runtime sidecar. NY has two registry reservations; its search and details
must both complete through the verified session. Customer extension behavior is
still a separate qualification from this headless backend transport.

Within each fair organization turn, the scheduler now starts historically
slower states first, using a median of up to 20 completed, unretried jobs per
state from the previous day. Unknown states retain a neutral estimate. This
does not change organization fairness, registry caps, deadlines or the current
eight physical reservations per worker. Per-task import and execution CPU/wall
measurements will guide subsequent capacity changes rather than guessing.

Florida's optional initial-date lookup now records its failing step and permits
one fresh, TLS-verified transport recovery. Its allowance is at most 12 seconds,
clamped to the remaining existing state budget. A wrong identity, malformed
date or incomplete response cannot supply a date, and optional date failure
cannot change the accepted status. No global budgets or matching rules changed.

All automated controls passed before lab deployment. Staging and production
remain excluded. Live results, including any cloud NY verification limitation,
will be preserved in the phase10 evidence before a capacity claim.

## Pennsylvania completion follow-up (September 25)

The user explicitly authorized fixing Pennsylvania and resuming the three-org
trial. The update changes only the master's two PA fallback access functions.
It waits for the response body for the exact submitted name query, excluding
earlier requests. A completed empty response advances directly to the next
variant. A nonempty response retains the bounded DOM parsing and existing
matching/classification. Request start/response/completion times and row counts
are saved with source observations. The existing incomplete-response guard,
fallback-query policy, queue capacity and all other state budgets are unchanged.

The first perf.9 live smoke completed the EIN query and all five existing name
queries for Junior Achievement USA. PA returned the expected Not Registered in
54.5 seconds with one semantic attempt; perf.7 had returned Unable to Verify in
113.8 seconds with two semantic attempts. The positive PA control and CO/LA
controls kept their expected results. This is a timing correction, not an
organization-specific override. Broader same-build solo/concurrent results are
recorded in the associated cloud-trial evidence before any capacity claim.

The resumed three-organization Standard trial completed on perf.9. Same-build
solo registration times were 56.8, 54.7 and 86.3 seconds; concurrent times were
99.8, 106.6 and 148.4 seconds (148.5-second group wall time). All 93 statuses and
matched identities agreed with the controls, including PA's complete EIN plus
five-name negative search. One Florida optional initial issue date disappeared
for Make-A-Wish; its CH164 identity and Suspended status stayed unchanged. Thus
92/93 state records retained all compared identity/status/date fields. The
average per-organization slowdown was 79.4%, exceeding the 50% stop threshold;
load was not increased. The trial does not qualify three organizations against
the complete acceptance gate.

Queue evidence shows no transport errors, reclaims or retries: mean state wait
rose from 6.6 to 38.2 seconds, while mean execution rose from 16.3 to 18.8 seconds.
Both two-CPU workers briefly reached full CPU; memory peaks stayed below their
limits. The Florida date helper silently returns an empty value for several
failure conditions, so its exact failure cause is unproven. Do not attribute it
to concurrency solely from this observation. NY and simultaneous discovery
were excluded from this registration comparison. See the separate
PA-COMPLETION-THREE-ORG-RESULTS.md evidence report for the full scope and commands.
