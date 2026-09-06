# Oklahoma certificate recovery — 2026.09.06.4-staging

Scope: master Oklahoma certificate retrieval and preservation of its attempt trace. Classification remains based on the actual state certificate expiration, as authorized. No matching changes, inferred deadlines, organization exceptions, state data changes, environment changes, or production deployment.

## Root cause evidence
Pre-fix staging produced three failures in ten OK checks. Twelve local direct requests succeeded; eight diagnostic sequential staging checks succeeded. A concurrent diagnostic run then reproduced Ronald McDonald failure: HTTP 520, text/html, 7,338 bytes. The error page identified a Cloudflare-to-Oklahoma-origin connection error (2026-09-06 13:22:21 UTC). The old fallback subsequently timed out waiting for download events.

Two distinct facts: the upstream server error is outside CharityClarity's control; the blind download-event recovery was within our control. No claim that the state server itself has been repaired. Session-cookie loss was tested locally and did not reproduce the issue. Sampled cloud CPU usage did not establish sustained saturation.

## Correction
Preserve the successful primary request. On failure, refresh the matched detail page, locate the same document number, and perform one bounded browser-native request with the refreshed form. Inspect actual response bytes; verify the PDF's organization name and explicit expiration with the existing parser. Replace the previous 30s + 15s download-event waits. Retain primary/recovery evidence in source_attempts. Persistent transport errors return Site Not Reachable, without an inferred deadline or negative registration conclusion. Temporary diagnostic HTML body excerpts removed.

## Local gate
11 certificate recovery tests; 16 manual reconciliation tests; 14 NY tests; 30 mature matching fixtures; nine downloadable-data tests. Actual live-browser controlled HTTP 520 recovery returned the correct Make-A-Wish certificate expiration, 10/17/2026, in 11.90 seconds. Controlled HTTP 200 HTML recovery also succeeded in 11.31 seconds. Current RIF and no-record national JA checks passed. Colorado current control and final compile/diff checks recorded with deployment evidence.

## Staging gate and limitations
Final deployment: both live staging backend services plus visible frontend version. Repeat five rounds with the same NY/MI/CO/OK lanes; supplement the other three Oklahoma organizations. Every first attempt retained. Compare against the approved regression export without changing manual expectations; previously explained Oklahoma certificate/chapter differences remain documented. No full 150-case run because runtime changes are confined to Oklahoma certificate recovery; no batch logic changes.

One NY RegistryDetail network timeout occurred in the diagnostic concurrent run before this OK fix (12 seconds, zero bytes received). It was correctly inconclusive and is separate from the fixed NY browser race. External source availability cannot be guaranteed by finite passing repeats.

Final results, timestamps, deployment IDs, and recommendation are recorded in outputs/ok-root-cause-20260906. Production remains untouched and requires explicit approval before promotion.
