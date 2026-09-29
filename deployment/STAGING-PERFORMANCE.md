# Aurora staging execution integration

The staging master owns access, routing, source interpretation, identity review,
dates and comments. Its authenticated `/api/workflow` transport submits one
organization to the existing four Pro master workers. The worker uses this same
merged source tree; no state adapter or alternative status engine was added.

Standard allows 15 active state tasks per organization; Sales allows 20 and the
UI retains its 60-second cutoff. The existing IL/GA browser connector reserves
up to two of those slots until its tasks settle. New York uses the previously
validated isolated worker browser. Other tabs cannot reset its browser session.
Progress is polled from durable saved results; completed answers are never
replaced by a late response. Cancellation terminates/reaps worker processes
before capacity is released. Existing source concurrency limits remain intact.

Only the two staging Render service IDs and their exact staging URLs can enable
the transport. Required server-only variables are `CE_STAGING_WORKFLOW_ORIGIN`,
`CE_STAGING_WORKFLOW_KEY` and `CE_STAGING_WORKFLOW_VERSION`. The worker pool uses
`CE_AURORA_STAGING_BRIDGE=1` to return private identity-review evidence, which
the staging master signs using its own existing key and version. Worker secrets
are never included in the frontend, review tokens or public result payloads.

Name discovery retains Aurora's latest source list and shared master behavior.
Reports and existing Accept/Reject identity decisions retain staging's code.
No customer workspace, billing or new paid capacity is introduced here.

Release controls compare every nonconflicting master function against its
selected frozen parent (`a59c2d8` Aurora, `90ed42d` performance). Thirteen shared
functions are explicitly reconciled and behavior-tested. Historical experiment
tests asserting whole-file equality to an older experiment are retained as
history; the combined release uses the parent-preservation audit instead.

Deploy the merged master to the existing worker pool first. Run live controls
and the frozen 20-organization comparison before staging activation. Preserve
the 32-state timing comparison and report IL/GA's additional coverage separately.
Save exact service/environment/deploy metadata privately before mutations.
Rollback staging frontend and backend together, disable the workflow transport,
then restore the worker version/configuration only after its queue is idle.
Production is outside this release's target allowlist.
