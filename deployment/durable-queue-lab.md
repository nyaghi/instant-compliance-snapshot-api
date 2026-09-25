# Durable multi-worker candidate (lab only)

This candidate is not a production/team-access rollout. It runs the existing
master state engine in supervised, disposable processes. No state-specific
adapter, matching, alias, EIN/address, status, comment, or date rule is copied.

## Concrete topology

- Existing private performance-lab web service remains the acceptance/progress
  API and hosts one resource-aware, 12-reservation worker supervisor on its Pro node.
- The independent Pro background service now runs two instances using the same
  branch/master code and database. Each instance has 12 physical reservations.
  These are task slots, not CPU cores: each of the three Pro nodes has two CPUs
  and 4 GB RAM, for six CPUs and 12 GB total.
- PostgreSQL stores inputs, submission keys, workflow/state jobs, worker leases,
  results and lifecycle events. All schedulers share one transactional authority.
- The new database `charityclarity-performance-lab-queue` is currently a free
  experiment, expiring October 25, 2026. It is not approved production storage,
  high availability, or a backed-up enterprise database.
- No changes to staging, production, user Chrome, or the NY connector.

Each Pro instance is $85/month at the pricing reviewed September 25, 2026,
prorated. The user separately approved the second and third instances on
September 25. The third was activated for the phase12 hardware-only trial.
Combined lab compute is now $255/month, up from $170/month.
The temporary database adds no charge. A later paid 256 MB
database is $6/month plus applicable storage ($0.30/GB/month), and requires its
own explicit resource decision. No automatic paid database upgrade is included.

### Phase12 five-organization follow-up

The three-worker trial passed at three simultaneous organizations: 96/96 state
results, compared fields and name sets unchanged; mean registration 72.2 seconds
versus 56.4 solo. Five simultaneous organizations completed all 160 state checks
in 146.5 seconds, with all statuses matching after the user's accepted
Conservation Nation DC correction. However, five did not pass the advancement
gate: mean registration was 92.6 versus 51.5 seconds solo (80% slower), three
organizations lost source-provided name entries, and one WA diagnostic identity
anchor changed. No higher-load trial was started.

All missing entries returned in separate solo discovery diagnostics. Four were
PA prior names; one CA DBA was a prefixed form of a name retained elsewhere.
Source exceptions are currently swallowed, so the exact failure type cannot be
recovered from the original responses. WA selected the same FEIN detail and
status, but its serialized identity anchor was recomputed from the changed alias
list. Neither observation supports changing matching or status rules broadly.

Mean state queue wait rose from 8.7 to 42.4 seconds; execution from 12.2 to 16.3.
All three nodes reached two CPU cores in sparse Render samples. Claim-only
admission logs cannot separate CPU blocking from other dispatch waits. The next
narrow work is source-failure and admission-block diagnostics, evidence-based
transient-source recovery, and preserving verified WA FEIN audit provenance.
These changes were not made during the hardware-only comparison. Staging,
production and the user's browser remain untouched. Raw first responses and
separate follow-ups are preserved in the phase12 evidence beside
THIRD-WORKER-RESULTS-20260925.md in the project's performance-lab output directory.

### Authorized phase13 corrections

The next lab release preserves all state selection/classification rules and all
capacity/deadline settings. CA and PA discovery may recover once from a timeout,
connection failure, or eligible transient HTTP status, within the original
60-second discovery deadline. Completed/invalid responses, identity conflicts,
TLS errors and access-denied responses are not retried. Retry-After advice must
fit a bounded delay; otherwise the source remains explicitly partial. Safe
failure category, request step, elapsed time and attempts are retained without
exception messages, request URLs, credentials or headers.

WA retains the exact FEIN verified on its selected detail as audit provenance.
It clears that provenance on a missing/conflicting detail and does not replace
the registry credential identifier. Existing status/date interpretation is
AST-identical to perf.11. All unrelated master functions remain protected by
the earlier baseline AST comparison, with these authorized functions isolated.

The worker groups admission observations into constant-size heartbeat windows:
CPU pressure, memory headroom, launch pacing, physical slots, claim transactions
and no eligible work. These observations do not alter dispatch decisions or
limits. They share the existing heartbeat transaction; no new database schema
or extra per-loop network request is introduced. Only the lab release label and
idle queue source-version guard change at deployment. Three existing Pro nodes
remain the only paid compute; staging and production are excluded.

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
- Each node has at most 12 reservations, subject to CPU/memory admission.
  Missing resource measurements retain the eight-slot fallback.
  A complete discovery reserves four
  and also reserves each participating registry for its lifetime; ordinary
  state jobs reserve one. This conservative starting policy must be measured.
- Registry-wide whole-job caps: ME/AR one each, NY two, FL three, other states four.
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
  registry status. NY is enabled through the master headless registry flow.
  If deliberately disabled, it returns `NY_COLLECTOR_NOT_CONFIGURED`.
  Neither path contacts the user's browser.

## Active lab deployment

Both services run commit `36a8c466d814b9090fa811ba4f894484264a96c4` as
`2026.09.25.perf.11-performance-lab`. The API/worker service is
`srv-d8u0hsu7r5hc73aqfsg0`; the independent background worker is
`srv-dar7adgu01pc738fsmgg`. Both have automatic deployment disabled.
The shared free database is `dpg-dar6utvavr4c7380ou60-a`.
Only the isolated lab has these changes; staging and production are unchanged.

Build: `pip install -r deployment/requirements-lab.txt && PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install chromium`

Existing lab API start remains `python -u deployment/performance_lab.py`.
Set CE_LAB_DURABLE_QUEUE=1, CE_LAB_QUEUE_WORKER=1, CE_LAB_WORKER_SLOTS=12,
CE_LAB_RESOURCE_ADMISSION=1, CE_LAB_NY_BROWSER=1,
CE_APP_VERSION=2026.09.25.perf.11-performance-lab, and the separate internal
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
NY passed the small real-registry sample below. Customer Chrome-extension
behavior, customer authorization, mixed workload capacity and hundreds of users
remain unqualified. Do not promote this candidate based on fixture success alone.

Sources: https://render.com/pricing and https://render.com/docs/postgresql-creating-connecting.

## Approved third-worker capacity trial

The approved hardware-only trial scales the existing background service from
one to two identical Pro instances, retaining the single API worker. Total
capacity is six CPUs and 12 GB RAM across three instances. Application
commit, state rules, environment, registry caps and queue limits stay unchanged.
Render supports manually scaling background workers; each additional instance
is billed at its compute rate, prorated by the second. The additional instance
is $85/month, bringing lab compute from $170 to $255/month. Existing workspace
and other charges are separate and unchanged. The user approved this new
recurring cost, and Render accepted the scale action. Three distinct live
worker identities were verified before beginning fresh solo controls.

`deployment/capacity_trial.py` validates the exact lab services, unchanged live
code, idle queue, worker identities, slot counts and safe 1-to-2 replica change.
It also keeps CPU/memory measurements separate per replica and calculates
aggregate values only at complete, aligned timestamps. It never provisions
resources. The external evidence controller `scale_phase12.py` defaults to
read-only preparation; execution is a separate, explicit approval step. Its
rollback returns the background service to one instance after draining work.

Verify three live workers before running new solo controls,
then repeat the three-organization full-32-state test using fresh discovered
names. Compare all 20 result fields, statuses and name sets with solo controls;
retain first responses. Advance to five organizations only if there are no
unresolved differences and mean registration and end-to-end time remain below
1.5 times solo. A third worker is a test hypothesis, not a capacity guarantee.

Sources: https://render.com/docs/scaling,
https://api-docs.render.com/reference/scale-service and https://render.com/pricing.

## Authorized full-state follow-up (September 25)

Perf.11 is live on the two existing services at code commit 36a8c466d814b9090fa811ba4f894484264a96c4.
Seven live smoke controls passed. Three complete solo and three concurrent
discovery-plus-32-state workflows preserved all 96 statuses, 20 compared result
fields and returned name sets. Concurrent discovery averaged 25.5 seconds;
registration averaged 95.9 seconds, versus 56.0 solo. Group elapsed time was
143.2 seconds. This improves perf.10's 125.4-second concurrent registration
average, but still exceeds the 50% slowdown stop threshold. No five/ten/fifteen
organization qualification was attempted. Both workers reached full CPU;
memory peaks were below limits. The queue is drained, staging is unchanged,
and production was not touched. Additional actual CPU capacity is the next
controlled trial; no further paid service was activated.

Name-source completeness is not perfect: some source responses remained
partial, although alias sets stayed identical and all registration checks
completed. Cloud NY checks use the real registry through the existing master
headless transport; customer Chrome-extension behavior is a separate scope.
The detailed evidence is in FULL-STATE-CAPACITY-RESULTS-20260925.md under the
project's outputs/performance-lab-live-20260924 directory. Do not promote this
lab build as enterprise-ready based on this small sample.

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

### Five-organization admission/readiness follow-up

The perf.12 five-organization run retained every discovered-name set and 159/160
reviewed statuses, but one NY browser failed before lookup with an undifferentiated
readiness error. Mean registration was 92.0 seconds, total 129.9 seconds;
same-build solo means were 53.0 and 81.9 seconds. Both slowdown gates failed.
No higher load was launched. Each node reached its two-core CPU allocation;
memory remained below the admission limit. Admission observations show 211.7
aggregate worker-seconds held for CPU; these are not attributed job-wait seconds.

The next lab candidate corrects undersized CPU samples: sub-250ms polls reuse
the previous measurement, and completed samples use at most a two-second window.
The 85% threshold, memory headroom, physical slots, global/per-org/registry limits,
launch pacing and workflow deadlines remain unchanged. This is a measured lab
experiment; improved capacity is not asserted before live comparison.

NY navigation now waits for navigation commit followed by its actual Verify
control, sharing the original 27-second readiness allowance. No resource block,
verification bypass, extra verification retry, matching or status change is
introduced. Failures retain the precise startup/navigation/control step without
exception messages or secrets. The old failed response does not identify its
exact step, so CPU causation of that individual NY failure remains unproven.

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
