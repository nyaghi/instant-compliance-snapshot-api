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

### Four-worker queue-efficiency experiment (perf.14)

The approved fourth Pro node remains in place; no capacity purchase is part of
this experiment. The only runtime-code change is `Queue.claim`: independent
database reads and the final claim writes use psycopg pipeline mode inside the
existing advisory-locked transaction. Idle claims skip duration-history
aggregation when no pending work exists. The worker heartbeat and settlement
still run. All history used for priority remains fresh; no approximate cached
capacity, stale results, new source parallelism or shorter search is introduced.

The global 15-workflow ceiling, 15-state per-organization ceiling, source caps,
12 physical reservations per worker, CPU/memory admission, queue-inclusive
deadlines, leases, cancellation, process-tree isolation, matching and status
rules are unchanged. Transaction rollback and idle heartbeat/history behavior
have dedicated integration controls, in addition to the existing independent
worker, crash, deadline, fairness and identity tests. All state functions and
the entire master source must equal perf.13 before a lab deployment is allowed.

The performance comparison separates registration from discovery: the same
reviewed names are supplied to five simultaneous live 32-state Standard runs
before and after deployment. Fresh discovery plus registration is also checked
afterward. A 60-second complete-results maximum is a test target, not a promise:
state response times and justified recovery can exceed it. Staging, production
and the user's browser are excluded. Evidence lives under the phase16 trial.

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


## perf.15: isolated import reuse and Washington hidden-input wait

The authorized lab optimization adds an import-only Linux forkserver template.
It never receives organization data or runs a lookup. Each task receives a new
process, its own session/process group, result file and browsers. A readiness
handshake confirms isolation before execution. Cancellation, deadline and lost
supervisor handling terminate the group before releasing its queue reservation.
The absolute task deadline includes startup. No completed result, alias cache,
registry session or browser is reused between organizations.

This is process-startup infrastructure inside the existing master worker, not
a state sidecar or an additional service. CE_LAB_WARM_ENGINE=1 activates it only
for the Linux master command; the cold process path is retained. The private lab
build additionally runs test_warm_engine against actual Linux processes before
Render can replace live instances. No worker count, price, registry cap or lookup
budget changes. The existing database is not exposed to task processes/template.

The sole master lookup edit prevents Washington name fallback from clearing a
hidden EIN input. All existing name submission, search, identity and status
rules remain intact. Whole-master AST controls compare every other operation
to perf.14. Local negative timing was 61.1 -> 30.8 seconds with the same completed
Not Registered result; the positive control retained the verified EIN/status.
These two local controls are not a cloud throughput qualification.

Pennsylvania is excluded from the next 31-state registration trials due to the
user-reported source outage. Discovery still uses its normal sources and reports
incompleteness. Advance load only after reviewing first-response discrepancies;
record actual timings rather than claiming the requested minute/ten-organization
target has been achieved before the live trial.

## perf.16: prevent discovery starvation during mixed workflows

The first ten fresh discovery-to-registration workflows on perf.15 completed
only eight organizations. One discovery never started before its 90-second
deadline; another waited 69 seconds and had only 21 seconds left to execute.
Registration jobs repeatedly occupied one of the sources discovery needed to
reserve together. The registration-only trial had completed all ten, so that
trial alone does not qualify ten complete user workflows.

The scheduler now protects one permit on each needed source for the oldest
eligible multi-source job. It does not preempt running work or reserve capacity
for jobs outside the active-workflow ceiling or beyond the worker's physical
capacity. Spare permits and unrelated sources remain usable. A ready protected
job gets the next eligible turn; cancellation removes its priority. Actual
claims still use the existing atomic cap, version, weight and deadline checks.

Four new real-Postgres controls cover spare-capacity use, the workflow ceiling,
small-worker fit and cancellation. The master backend, source limits, deadlines,
CPU/memory admission rules and four-node configuration are unchanged from
perf.15. Only the lab release version environment value changes. This remains
a lab candidate until a fresh ten-organization end-to-end repeat passes.

## perf.17: order overlapping work by workflow age

Perf.16 completed discovery for all ten organizations once, but the repeat lost
one discovery after 42 seconds queued and approximately 48 seconds executing.
Florida is not a discovery source and is separately deferred by the user because
of a source outage. A single reserved permit did not sufficiently protect earlier
discovery work from the overlapping workload submitted as other discoveries
finished. Both original trials remain evidence; neither is an unconditional pass.

The lab queue now defers younger single-source jobs that overlap an earlier
eligible queued or running multi-source workflow. Older registration jobs and
unrelated sources remain eligible. A stream of new discovery requests therefore
cannot preempt already submitted registrations. Running jobs are never canceled
or preempted, and all source caps, physical weights, deadlines and admission
thresholds are unchanged. New tests cover completion of the whole earlier group,
older registration fairness and continuation of unrelated work. The master and
its identity, status, alias and date logic are byte-for-byte unchanged.

Local HTTP regression also reproduced connection resets when rejecting legacy
POST endpoints with unread request bodies. The private lab handler now consumes
bounded ignored bodies before replying to rejected or cancellation requests.
Invalid/oversized lengths do not execute or cancel work. Saved initial failures,
body-consumption controls and repeated actual HTTP requests cover this fix;
normal workflow submission and production/staging handlers are unchanged.
# September 25: DC identity recovery and twenty-workflow experiment

The user authorized resolving the National Low Income Housing Coalition DC false
negative and measuring/optimizing twenty concurrent organizations in the private
performance lab. Staging, production, customer browsers, expected spreadsheet
values and paid instance counts are unchanged. Florida is excluded at the user's
request; PA and the isolated official NY collector remain in scope.

DC's source joins duplicated fragments onto a complete EIN-linked legal name.
The master now recovers this narrow condition only when the full name and exact
street/state/ZIP are independently corroborated by a same-EIN organization
record. The displayed source name is retained. A different entity at the same
address remains rejected; unavailable corroboration yields review, not a false
negative. Dedicated DC controls and a complete master AST comparison protect all
other state behavior.

`CE_LAB_WORKFLOW_LIMIT` defaults to 15 and is explicitly set to 20 for this
experiment. The lab schema maximum is 20. Activation requires an idle, audited
settings migration; startup rejects configuration disagreement. Per-organization
state concurrency remains 15, each node retains 12 weighted slots, and source
limits and deadline values remain unchanged for the first trial. The existing
four Pro nodes are the entire paid compute scope. Twenty submissions and twenty
active workflows must be reported separately using actual claim evidence.

Every first-response run is saved under a new evidence label. Do not increase
source pressure or call spreadsheet agreement proof of identity. Compare state
status, matched identity, dates, names, conservative failures and execution/queue
time against controlled baselines. Any subsequent optimization must have its
own configuration record and repeat trial.
# September 25: twenty-workflow first-response findings (perf.19 candidate)

The first twenty-user trial on perf.18 produced eleven usable discoveries and
nine deadline failures. Several failed discoveries waited 75–90 seconds and
then received less than fifteen seconds of execution. The 341 completed state
checks preserved their control identities, dates and statuses. This partial run
does not qualify twenty-organization capacity.

Discovery now has a bounded 270-second queue allowance. Its unchanged
90-second task execution allowance activates atomically on the first claim.
The master collector's own 60-second source deadline is unchanged. Recovery
does not reset execution time; expired waiting requests cannot start. Standard
registration (900 seconds including queue), Sales (60 seconds including queue),
state execution limits, four nodes and source caps are unchanged. Actual elapsed
time must be reported; a larger waiting allowance is not a speed improvement.

Two solo controls exposed independent headless NY transport gaps. A second
same-EIN detail now returns through browser history to the same results page.
A subsequent name search uses the official Clear fields button and fills only
the requested filter: entering an empty EIN string made the portal submit
`ein=`, which its API rejects. The existing EIN-first interpreter, duplicate
selection, address checks and status rules remain unchanged. Customer browser
extensions, staging and production are not modified.

DC query OR predicates that are already covered by another predicate are
removed. Generated-candidate controls and an ABBA official API comparison
confirm an identical complete result set, including the separate same-address
Policy Center. This reduces query complexity; it is not evidence that all
source-side timeouts have been eliminated.

## perf.20: pipeline independent job lease renewals

Perf.19 completed two actual twenty-organization, fresh-discovery trials across
31 states (Florida deferred by the user). Both reached twenty active registration
workflows, produced 620 conclusive first responses without retries, and preserved
all controlled identities, statuses, dates and name lists. Twelve weighted slots
per node finished the batch in 416.2 seconds; eight slots finished in 425.5 seconds.
This small difference does not establish a universal optimum. Eight slots did
not improve average registration time and made discovery slower, so twelve slots
remain the selected tested configuration on the existing four Pro nodes.

Worker observations also recorded substantial time in queue transactions. The
heartbeat previously waited for a separate database round trip per running job.
Independent lease updates are now pipelined inside the original advisory-locked
transaction. The owner, token, running phase and execution-deadline predicates,
20-second lease, input order, settlement and worker heartbeat are unchanged.
New real-database controls cover mixed eligible/ineligible leases and atomic
rollback if a renewal fails. Actual whole-workflow timing must confirm any speed
benefit; aggregated worker transaction time is not a causal partition of a
user's elapsed time. All state interpreters are unchanged from perf.19.

## perf.21: preserve DC corroboration in diagnostic metadata

The selected DC result and its public comment were correct, but generic debug
metadata re-scored the malformed source name alone and emitted a rejection reason
and empty identity anchor. The selected record's verified name/address decision
now survives serialization as `cross_state_name_address`, with its matching
reason and an accepted debug candidate. The original registry name is retained.
This changes diagnostic metadata only; selecting the record and interpreting its
status are unchanged. A complete-master AST comparison and end-to-end response
controls enforce that scope. The perf.20 queue implementation and its 33 passing
PostgreSQL controls are unchanged. The final performance trial waits for this
diagnostic correction so the result and its audit evidence agree.

The offline HTTP suite also reproduced an intermittent Windows connection reset
on an unauthorized POST with an unread JSON body. The private lab denial path
now drains at most 32 KiB with an absolute one-second read deadline before the
401 reply; invalid lengths, timeout and oversized bodies still cannot execute or
cancel work. Authorized requests are unchanged. The failed initial test output
is retained, with body-bound/timeout controls and a full follow-up offline run.

## perf.22: release completed discovery sources and index duration history

The isolated discovery child reports when each existing master source function
has actually returned, including its browser cleanup. The supervisor reads a
private atomic progress file at most once per three seconds per discovery job.
The queue checks the owner, token, live lease, job phase and deadline before
releasing only those source reservations. IRS stays held until whole-process
cleanup because other collectors use IRS metadata for alias verification.
The job retains all four physical weighted slots until its entire process tree
is stopped. Missing progress, an unknown source, cancellation, stale evidence or
a failed database write cannot release unfinished work. Proven-dead recovery
restores all original source reservations before a second attempt.

Earlier discoveries retain priority on their unfinished sources. Their completed
sources can serve later registrations. Master matching, name discovery sources,
alias evidence, state interpretation and time allowances are unchanged. The
source observer is confined to one lab task's isolated master process and never
receives database credentials. It cannot change the collected result.

Scheduling still uses the last twenty successful first-attempt durations per
state within the past day, bounded to 300 seconds. An indexed lateral top-N
query retrieves that same sample instead of sorting all completed daily jobs on
every scheduling turn. This does not change workflow fairness or source caps.

Validation measures both lab Standard and Sales across all 32 states, including
Florida and the isolated New York browser collector. Sales retains its 60-second
queue-inclusive cutoff; incomplete checks are failures of full coverage, not
successful classifications. These are durable backend load trials, not a claim
that the customer's browser extension or UI was load-tested. Standard receives
fresh discovered aliases; Sales receives the entered name and EIN, matching its
current UI. A preliminary three-case Sales diagnostic supplied aliases and is
labeled separately from faithful Sales trials. The unchanged UI scheduling and
conservative display grouping have separate JavaScript regression controls.

No extra compute, staging deployment or production deployment is part of this
trial. The baseline remains four Pro nodes, twelve weighted slots each, twenty
active workflows and at most fifteen concurrent state jobs per organization.

## perf.23: Sales priority within the unchanged one-minute window

The unchanged-version synchronized twenty-organization Sales baseline completed
only 71 of 640 requested checks before its deadline. Standard's longest-estimated
duration-first rule was being used for Sales too. Under a hard one-minute cutoff,
that spent early capacity on long tasks while many shorter checks never ran.

Sales now starts the shortest recently measured states first within each
organization's fair turn. Standard retains longest-first ordering. Every one of
the selected states remains queued, with identical identity/status rules, source
caps and deadlines. No named-state or organization exceptions, cached compliance
results or estimated statuses are introduced. This can improve conclusive
coverage at the cutoff; it cannot promise all registries finish within a minute.

## perf.24: progress reads and alternate-name identity control

Twenty synchronized Sales workflows still completed only 95/640 checks after
shortest-first ordering (71/640 before). Worker observations showed substantial
claim/heartbeat transaction time. Every progress poll previously acquired the
same global scheduler lock and ran all queue settlement writes. Ordinary polls
now read a consistent, read-only repeatable-read snapshot. If their workflow
deadline or running-worker lease has expired, they still invoke the original
locked settlement and resnapshot. Claims, ownership, source/worker reservations,
result acceptance, cancellation and worker-death recovery remain authoritative
and serialized. Polling cannot release capacity or publish a late result.

The all-state consistency gate also found a pre-existing Florida alias collision:
an EIN-linked program name was accepted as another organization's legal name.
The earlier baseline was wrong; a later primary-name result must not hide it.
Florida now corroborates a reviewed-alias-only candidate's existing header
location with the master EIN-linked office helper. A missing/conflicting identity
remains unconfirmed while other queries continue. A valid primary result can
still win. Exact primary-name matches require no new request, and discovery and
all other state logic remain unchanged. The response retains the address basis
or explains why identity could not be confirmed. No organization-specific rule
or newly invented alias is introduced.

Optional Florida issuance-date blanks were separately traced to transport
timeouts, with the same status and credential. They remain blank when the bounded
date read fails; no date is fabricated and the primary status is preserved.

Sales' current UI supplies entered name/EIN only. Its all-state diagnostic also
exposed name-only negative results where Standard's reviewed names found records.
This is an open product/identity input limitation, not a successful accuracy
comparison. Backend performance results do not qualify the customer UI or NY
extension for equivalent concurrent use. No staging/production deployment or
additional compute purchase is part of these experiments.

## perf.25: completion persistence within the unchanged Sales cutoff

Sales stops at 60 seconds including queue time. Maximize reliable answers before
that hard cutoff; do not let unfinished checks continue for later answers. The
Standard ceiling remains 900 seconds. Per-state execution budgets, cancellation,
lease fencing, physical reservations, registry limits and ordering are unchanged.
Report conclusive answers before the cutoff separately from expired/inconclusive
jobs. Stopping and reaping processes may finish later, but late results are never
accepted. The temporary local soft-cutoff interpretation was rejected by the
user and reverted before deployment; its exploratory test logs are not release
qualification evidence.

Supervisors persist already-stopped and reaped tasks in one transaction when
several are ready together. Every owner/token/identity/state/version fence is
preserved. A failed commit keeps reservations for retry; invalid output is
isolated so it cannot discard an independent valid result. No live task releases
capacity through batching. This targets queue transaction overhead without
increasing worker or registry concurrency.
Queue settlement also skips rewriting a workflow whose derived phase has not
changed. The same phase rules remain authoritative; unchanged active workflows
no longer generate a new database row version on every scheduler transaction.

Passive Florida request/response/failure timing is attached to lab results.
The observer excludes query strings, headers and cookies, detaches after each
attempt, and preserves original exceptions and return values. It does not alter
Florida transport, matching, interpretation or budgets. Florida timeouts also
occurred with no other states running, so cross-state CPU contention is not a
sufficient root-cause explanation.

The main Sales trial uses entered name/EIN, as its unchanged customer UI does.
Standard uses reviewed discovery names. An optional paired-input diagnostic can
supply those reviewed names to both modes, but must be labeled as a separate
experiment and cannot qualify current Sales behavior. Discovery time is reported
separately. Lab evidence does not qualify the unchanged customer UI or browser
connector. No staging/production changes, new compute or database purchase are
authorized by this revision.

## perf.26: remove the redundant Florida advisory request

The perf.25 Florida-only 20-organization trial matched all 20 control statuses
and identifiers. One record nevertheless needed two attempts: its first POST
and subsequent GETs received no document response before timing out. The gap
before recovery also contained a redundant availability probe with a 15-second
timeout. That probe never gated execution: both success and failure proceeded
to the same browser lookup. Removing it avoids this extra request/wait on every
attempt. It does not establish that external response stalls have been fixed.

The actual search, certificate verification/recovery, query order, alias and
address checks, interpretation, confirmation and per-state budgets are unchanged.
Only the probe is removed from the master; a full-master AST control verifies
that scope, alongside current, negative and unavailable-path controls. Florida
diagnostics now retain document requests only so fonts/images cannot exhaust
the trace before a slow recovery. Sales still rejects all results after 60
seconds. Existing queue/database controls remain applicable because those
modules are unchanged from the 49-test perf.25 PostgreSQL run.

## perf.27: South Carolina possible-name identity guard

The hard-cutoff Sales20 trial completed 227/640 checks before 60 seconds versus
120/640 in the prior run; this is an observed run comparison, not an isolated
causal speedup claim. Its broader completed set exposed a pre-existing SC path
that accepted a possible name as a definitive status. The national organization
was assigned a different local coalition's expired registration. Speed does not
qualify a wrong identity.

SC now uses the master's identity score and exact safe target variants before
accepting a candidate without filing evidence. Possible/related candidates must
confirm the requested EIN using the existing bounded state-filed Form 990 reader.
Missing or different EIN proof cannot fall through to a weaker browser lookup;
it remains unconfirmed while other permitted queries are evaluated. Exact legal,
explicit slash/DBA and reviewed names retain their existing fast path. The same
status/date interpreter is preserved. Filing-confirmed matches retain the EIN
basis in diagnostics. No organization-specific exception was introduced.

Local live reproduction returned Unable to Confirm in 2.69 seconds with entered
name only, and the correct P40435/Upcoming Filing in 0.29 seconds with the verified
alias. Separate Sales input gaps remain in DC, NH and RI when current Sales omits
reviewed discovery names. An alias-fed experiment must not be labeled as current
customer Sales validation. Neither it nor this guard extends the Sales deadline.


## Bounded Sales identity assistance (lab candidate, September 26)

Sales with no submitted alternate names receives one internal `@sales_identity`
job before state dispatch. The master backend reads current IRS organization
metadata and Colorado exact-EIN public records in parallel for at most six
seconds. No financial pages, historical IRS returns, previous Standard results,
or organization-specific overrides are used. The worker reserves CO and IRS
permits together and has an eight-second process allowance **inside** the
unchanged 60-second workflow deadline, including queue time. Failure or worker
loss never resets that deadline.

Only verified names bound to the workflow's EIN and source version enter that
workflow's state queries. Existing master identity/address and classification
rules remain authoritative. Standard and Sales with explicitly submitted names
retain those inputs. Name-only negatives become inconclusive if this limited
identity step fails. This assistance is not full alternate-name discovery.

Preparation evidence is returned separately from the requested state rows, so
32 states still means 32 checks. No additional paid resources, runtime sidecar,
staging frontend changes, or production changes are included. This candidate
requires the queue integration, isolation, deadline, live issue-control and
all-state comparison tests before promotion. The staging Sales disclaimer must
be reviewed if this candidate is later explicitly promoted; staging is untouched.
