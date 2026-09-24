# Local enterprise capacity experiment

This directory is **not imported or deployed by CharityClarity**. It is an isolated
candidate routing experiment at application commit
`35e61ae38f83ec00cba48776712d8fe2b34194c3`. It contains no live service URLs,
credentials, browser automation, or state-specific matching/status changes.

## What is implemented

`router.py` implements a single shared coordinator for multiple worker pools:

- Up to 15 admitted organization workflows, with excess workflows queued.
- Up to 15 state jobs per workflow, subject to actual available worker slots.
- Round-robin workflow fairness and least-occupied eligible worker selection.
- Resource classes so a download/API task need not wait behind all browser tasks.
- Optional registry/profile limits and pacing, without special organization rules.
- Workflow cancellation and deadlines; expired queued work is never dispatched.
- Cooperative running-task cancellation; capacity remains occupied until the
  task actually returns, including when an adapter ignores cancellation.
- Workspace/workflow namespacing, immutable copies of submitted identities and
  aliases, response EIN/state guards, and unchanged successful result payloads.
- Worker health exclusion, conservative failed outcomes, and scheduling traces.

Namespacing is not user authentication. The caller must be a trusted master
backend, which derives the authorized workspace from the session.

`master_adapter.py` is the local integration seam to the actual master request
normalizer and reviewed-name scope. Its controls route 15 organizations across
all 32 states with stubbed registry execution, including aliases and result
identity/address/date fields. It is not wired into the HTTP handler.

One isolated master-code candidate is included: `resolved_organization_name`
returns a supplied name immediately instead of fetching two unused fallback
names first. Missing-name fallback order is unchanged. An AST guard proves the
rest of the master module is unchanged; the live/staging checkout is untouched.

`replay.py` starts two temporary **127.0.0.1-only** HTTP fixture endpoints and
replays 450 saved responses for 15 distinct organizations. All non-loopback
socket connections are rejected. Every endpoint is closed before exit. Tests
compare complete response hashes, not just statuses. Historical inconclusives
are retained. Recorded delay is compressed 100x; wall times are not production
throughput predictions.

`model.cjs` runs the unchanged Standard and Sales scheduling functions against
recorded durations for three organizations repeated five times. It models the
300-second Standard request limit, Sales' 60-second total cutoff, one versus
fifteen New York profiles, and New York's three-second inter-job pace. It assumes
cooperative cancellation. It does not simulate CPU/memory exhaustion, CAPTCHA,
network failures, cache gains, or changing records. Recorded lookup durations
can already include waiting, so the model is a sensitivity experiment rather
than a server-sizing forecast.

## Local commands

Run from the isolated worktree root:

```powershell
python testing/capacity_lab/test_router.py
python testing/capacity_lab/test_master_adapter.py
python testing/capacity_lab/replay.py --root '<original project root>' --out '<local output directory>'
node testing/capacity_lab/model.cjs '<original project root>' '<local output directory>'
node --test "--test-skip-pattern=only the Standard scheduler and footer changed" testing/run_sales_deadline_guardrails.cjs testing/run_standard_concurrency_guardrails.cjs testing/run_ny_sales_abort_guardrails.cjs
```

The skipped test is an old release-specific assertion that the entire backend
has no edits. It correctly detects this local candidate edit. Its intended
scope protection is replaced here by the stricter candidate-specific AST guard;
the original test file was not weakened or changed. All 20 behavioral JavaScript
controls pass. Four existing Python suites also pass (51 tests) with socket/DNS
connections disabled: identity discovery, identity transport, Standard/Sales
follow-ups, and discovery capacity.

## Required integration before a live pilot

1. **Master-owned lifecycle.** Introduce a workflow start/progress/cancel contract
   in the master backend. Derive workspace/authorization server-side; snapshot
   reviewed names and EIN-linked address evidence. Keep the current matching and
   state status engine authoritative.
2. **Shared durable coordination.** The experimental coordinator is one process
   with an in-memory queue. It is not a globally enforced limit across replicated
   API gateways and does not survive restarts. A live design requires one durable
   scheduling authority or atomic shared admission/worker leases, with expiry,
   fencing, recovery, idempotent submission and exactly-once accepted completion.
   The per-process router must not simply be instantiated once in every replica.
3. **Authorized worker routing.** Route from the trusted master to an explicit
   worker allowlist with scoped service authentication. Do not remove
   `PUBLIC_SINGLE_STATE_ONLY`, expose internal worker URLs/credentials to the
   browser, or accept caller-selected worker destinations. Keep proxy-hop limits.
   Health failures should remove workers from new admission; do not blindly
   duplicate an in-progress registry search.
4. **Real resource budgets.** Benchmark a small number of browser jobs per worker
   and reserve headroom for discovery, server memory, and parsing. The replay's
   two browser slots per logical worker is a test configuration, not a proven
   safe setting for a one-core/2-GiB Render instance. State and discovery browser
   work must share accounting for the same underlying physical resources.
5. **Real cancellation.** Existing state adapters do not yet accept this `Control`
   object. Propagate deadlines into queue admission, network/browser timeouts and
   retry boundaries. Legacy blocking adapters need bounded job isolation and
   verified process-tree cleanup. Client abort alone is insufficient. Never free
   capacity while an orphaned browser continues running.
6. **Client transport.** Preserve the 15-state per-organization UI behavior, but
   represent backend queue/progress explicitly. For Standard, a job queue and
   progress channel should avoid holding a single HTTP request open while queued.
   Preserve absolute workflow/state deadlines; do not reset them on polling or
   silently hide long queue time. Sales must retain its requested overall minute.
7. **New York.** Keep the released connector untouched until a separate validation
   can establish safe parallelism. One Chrome profile is currently serialized.
   Independent user profiles improve that particular constraint, but a shared
   office IP, verification state, and the common backend still require testing.

## Live qualification plan, outside demo staging

Use a separate performance environment based on the frozen staging release,
with no traffic to either existing staging backend and no access to the user's
Chrome profile. Provisioning and spending have not been performed or authorized
by these local tests.

First compare healthy isolated 1-organization results against 2, 3, 5, 10, and 15
concurrent organizations on the **same** representative cohort. Measure first
responses, identity/record/status agreement, discovery completeness, queue time,
registry execution time, browser slots, memory, CPU, process restarts, and p50/p95
end-to-end completion. Stop increases on a result regression or resource failure.
Vary worker count/size separately from routing so causes remain attributable.

Then run fresh diverse controls, mixed discovery plus registration, mixed
Sales/Standard, repeated batches, cancellation, worker loss, restart/recovery,
and 15 separate profiles/users. Test a sixteenth workflow queues correctly and
does not consume a sixteenth active-workflow slot. Preserve source failures and
first responses rather than replacing them silently with successful retries.

Passing one-profile/15-organization testing would be a valuable stress test; it
does not replace multi-user authorization, workspace isolation, connection,
profile and IP testing. No current local result is a live capacity certification.
