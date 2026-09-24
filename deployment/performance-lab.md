# Performance lab deployment

The user authorized replacing the retired expansion lab on September 24, 2026.
Only Render service `srv-d8u0hsu7r5hc73aqfsg0` is a deployment target. Its existing
Standard plan and one instance were retained for the initial baseline. The user
then authorized increasing actual worker capacity and improving queue handling.
The next experiment uses one Pro (2 CPU / 4 GB) instance at the documented
$85/month compute rate instead of $25/month, prorated for use. No staging service
is a target for these changes.

The branch starts from release commit `35e61ae38f83ec00cba48776712d8fe2b34194c3`.
The master remains the sole implementation of all 32 states. Its only candidate
logic edit returns an already-supplied organization name before unused metadata
fallbacks. Existing EIN, alias, location, date and status interpretation is kept.

## Technical reason for the entry point

`python -u deployment/performance_lab.py` wraps the master HTTP handler with a
lab-only access boundary, private copies of existing frontend assets and request
telemetry. It runs the same master in the same process. It is not a new state
checker, satellite or state-logic sidecar. It refuses staging/production service
IDs/origins and refuses shared helper, overflow, fanout or lead-webhook URLs.
Python DNS requests to application environments are also rejected as a second
defense. Registry URLs and interpretation remain unchanged.

The one-instance baseline starts with four browser slots and eight admitted HTTP
state requests. Other non-secret state timing settings were copied read-only from
the current serving configuration. These are starting measurements, not a claim
of safe capacity. Discovery's existing browser cap remains four; registration
and discovery are measured separately first.

`performance-lab-env.json` contains the public configuration. `CE_LAB_ACCESS_KEY`
is generated separately, stored outside Git and supplied through Render. It is
also the lab's internal passcode. Never copy the production/staging passcode,
New York signing key, sidecar secret or lead-webhook credentials into this lab.
All requests except `/health` and `/healthz` require lab Bearer authentication or
HTTP Basic (`lab` / private key). The existing master access gate remains active.

The frontend is served from the frozen `web-staging` files with lab-only origin
substitution at response time; those source assets are not edited. Standard and
Sales scheduling and Sales' one-minute limit remain unchanged. The lab banner
identifies the experimental environment. No production or staging page is used.

## Known qualification gaps

- New York's browser collector is not configured. The user's extension/profile
  must not be used or changed. The 32-state routing list does not prove 32-state
  live coverage. Initial backend measurements exclude NY and label this clearly.
- Shared Wisconsin/New Mexico fallback functions are disconnected. Direct master
  registry paths still run, but fallback parity must be measured and, if needed,
  supplied separately before making a full-capacity claim.
- `testing/capacity_lab/router.py` is an in-memory prototype and is not imported
  by this deployment. Durable coordination/cancellation still requires a later
  integrated candidate. Increasing replicas alone does not provide that.
- Saved regression expectations are frozen; differences must be retained and
  investigated, not silently changed. Stop increasing load on result degradation.

No normal staging or production deployment is authorized by this branch. Any
later change in plan/instance count requires an explicit cost-aware decision.

## Fair admission candidate, perf.4

`lab_capacity.py` replaces the master handler's single-state admission semaphore
with an eight-slot, bounded, organization-fair queue in the private lab process.
The same eight reservations cover identity browser work (at most four discovery
browser tasks). Admission prefers organizations with less active work, then uses
round-robin order. Excess requests wait at the existing 150-second queue budget.
The separate browser gate stays at eight: admitted registration plus discovery
work cannot exceed that reserved total. Registry timeouts, retries, aliases,
matching, status, dates and source parsing are unchanged.

This is a conservative reservation for a whole state workflow, including direct
HTTP or download stages. It is not an exact live browser-process counter and
does not claim that every helper opens at most one browser. Private evidence
generation and nonbrowser discovery sources are not covered by this admission
pool. These remain qualification gaps for mixed workloads.

Queue metrics distinguish waiting from execution and expose bounded event
history without names/credentials. Response data are preserved; timing is added
in Server-Timing headers. A full/expired queue remains an explicit capacity
response, not a registration status. Capacity is retained until work returns.
The queue's cancellation primitive is tested but not wired to a durable workflow
cancel API; an HTTP client abort does not yet cancel a running registry adapter.

This queue is SINGLE INSTANCE and in memory. It must not be represented as an
enterprise-global limit or durable acceptance queue. Scaling to hundreds of
simultaneous submitted workflows still needs persistent jobs, atomic shared
worker leases, workspace-scoped authorization and deduplication, resumable
progress and safe cancellation, registry-wide pacing, independent NY collection,
and multiple-worker failure/restart validation. None of that is proven by one
larger server or by simulated fixture throughput.
