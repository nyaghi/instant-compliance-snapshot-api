# GiGi's Playhouse connector timing and rail regression

Summary: On October 15 the user reported GiGi's Playhouse took more than five
minutes, connector states started late, and NY/NC windows appeared outside the
gray rail. These are user-observed failures, not independently captured window
bounds or a measured trace. The user is still testing and explicitly requires
background work only. No further browser actions, refreshes or activation.

Files changed: this evidence note and background diagnostic/checkpoint files in
outputs/review-registry-fixes-20261014. No runtime code changed for this issue.

Deployment: none. Keep active 0.6.132 TN Verification Trace and 29.2FC unchanged
while the user tests. The separately prepared Alabama candidate is unactivated.

Tests run: `node outputs/review-registry-fixes-20261014/reproduce_packaged_rail_and_queue.cjs`
executes the exact saved trace package's placement function and scheduler in
synthetic fixtures, without browser or network access.
`python outputs/review-registry-fixes-20261014/audit_packaged_coordination_history.py`
compares the same functions across twelve saved packages (0.6.122–0.6.131 plus
0.6.132 Smart and Trace).

Smoke results: two positive geometry controls with current viewport data stayed
inside the fixture's visible rail. Four adverse NY/NC controls, with an absent
live measurement and either absent or resized cached measurements, entered
three-column fallback geometry outside that rail. This script intentionally
demonstrates violations; its zero exit code does not mean placement is safe.
The exact scheduler admitted two of six workspace states and left four queued
for 299,999 simulated milliseconds while the first pair remained held. When
the fixture modeled release at five minutes, NV/NY were admitted with 300,000ms
queue time and new active budgets. No registry or actual browser run took place.

Regression results: the scheduler, placement function, six workspace states and
acquire-time viewport capture are identical across the twelve inspected saved
packages. This rules out a direct recent edit to those particular functions;
it does not exclude another change lengthening a state and exposing the queue,
shared worker/lifecycle interactions, a changed viewport or a source stall.
NV's last full live31 was 0.6.130, whereas later 0.6.132 live checks covered
CO/TN. Offline checks and isolated-state runs did not validate the complete
latest all-state workflow or native outer window bounds. The current full-state
speed and placement gates are failed on user evidence, not merely unverified.

Known issues and surgical follow-up: preserve GiGi's full first-pass export and
trace when the browser is released. Compare workflow dispatch, queue admission,
first command, each command duration and slot release per browser state. Do not
assume every late window means the frontend dispatched late: its current code
starts connector work before awaiting ordinary backend results, while workspace
admission can still delay source opening. Identify the actual slot holders
before changing scheduling; do not raise concurrency, reset deadlines or turn
timeouts into negatives. Read NY/NC placement inputs, live/cached dimensions,
fallback diagnostics and actual native bounds. A repair must retain correct rail
placement during delayed measurement without silently creating a stricter
dependency or moving collectors over the application. No speculative runtime
patch is included. Revalidate the latest complete package in the full workflow,
including AL, NV, NY, NC, TN and mature controls, with live timing and native
placement. Keep the approved31 state regression requirement and original
first-pass evidence; do not substitute successful retries for first passes.

Production touched: No.

Recommendation: Do not promote. Current user reports supersede any suggestion
that unverified placement or recent isolated-state timings establish readiness.
Nevada failures for Partnership for Civil Justice Fund and Opportunity at Work,
the YWCA Alabama post-fix check, and TN required-checkbox validation remain open.
