# 29.2EF lab-to-staging cutover

The user designated the already-validated Performance Lab as the new staging
environment. Its public origin, connector 0.6.125, API, three-worker pool,
Postgres queue, access credentials, version, and all registry logic stay paired.
The old staging site and production remain separate and untouched until a later
cutover decision. The staging entry point is the lab's existing Render URL;
`staging.compliance-express.com` still points to the old staging site.

`CE_PERMANENT_STAGING=1` and `CE_FINAL_FOUR_TRIAL=0` on both existing lab
services remove only the trial expiry. The committed resource manifest binds
this mode to the exact existing API, worker, database, and origin; an unrelated
Render service or database cannot claim it. The API continues to require the
private access key and the durable queue. The staging Sales limit remains 60
seconds. No state adapter, matching rule, registry timeout, concurrency value,
or worker count changes in this cutover.

The retired trial's local `trial_control.py guard` must not run again; no active
guard process or scheduled task was found at cutover. The trial manifest remains
as historical identity evidence, but the permanent staging branch does not
consult its expiry. Before declaring cutover complete, verify the live health
version and staging flag, the existing frontend and connector origin, worker
heartbeats, a private check, and the approved regression controls. Preserve the
old staging deployment until those checks pass and the user reviews cutover.

At current published Render plan rates, the retained one Pro API, three Pro
worker instances and small Postgres database cost about $359/month before
bandwidth and storage. The old staging overlap adds its own charges until
retirement. Unused mirror resources created for the abandoned copy approach
were deleted on October 10, 2026.
