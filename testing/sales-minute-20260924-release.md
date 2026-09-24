# Sales one-minute deadline and 32-state experiment

Summary: Sales now stops waiting 60 seconds after Run is clicked. Completed states remain unchanged; unfinished and not-yet-started states receive Unable to Confirm with a specific time-limit explanation. No identity or status rule was weakened. The requested 32-concurrent-state experiment was measured but not adopted: normal Sales retains 15 total state requests including NY.

## Root cause and change

The user's preserved America's Charities (54-1517707) Sales run completed 31 states by 54.773 seconds. Maine returned an underlying Site Not Reachable at 181.156 seconds, displayed as Unable to Confirm. Sales reused Standard's up-to-five-minute transport without an overall cutoff. This saved evidence does not establish that duplicate records caused Maine's timeout; the UI timeout problem is proven independently of that cause.

A single Sales deadline now closes all unresolved rows and aborts outstanding browser requests. Workers stop starting queued states. Deadline/results are scoped to the run, so a late response cannot overwrite a deadline status or a new organization's rows. NY accepts an optional abort signal during ping, admission, API and search, then invokes the installed extension's existing finish/cleanup operation. No extension installation/reload or settings change is needed. Standard passes no signal and retains its existing five-minute request timer and full lookup behavior. Discovery, state matching, budgets, filing calculations and installed extension files are unchanged.

## Live post-validation

One organization, same entered name and EIN, no advance discovery (the released Sales workflow), all 32 states selected in normal work-profile Chrome. Runs were sequential in order 15, 32, 32, 15. Timings are browser UI measurements; no NY checks are omitted from the state count.

| Run | Concurrent states | Final elapsed | Definitive displayed outcomes | One-minute cutoffs |
|---|---:|---:|---:|---|
| live-15-first | 15 | 50.7s | 31/32 | None |
| live-32-first | 32 | 60.0s | 30/32 | OK |
| live-32-second | 32 | 46.3s | 31/32 | None |
| live-15-second | 15 | 48.4s | 31/32 | None |

All 31 non-NY states agreed wherever a definitive result was obtained. All available matched registry identifiers agreed. Only Oklahoma changed from Current to Unable to Confirm in the first 32-lane trial because it did not finish before the limit; it returned Current in the other three runs. The real cutoff finalized at 60.011 seconds, ordinary timer scheduling overhead. The other runs finished early. This is a one-organization, warm-cache comparison, not a statistical capacity certification or a 15-organization load test. Canceled HTTP requests can still have bounded server work finishing, so the second 32-lane run is not an independently cold capacity measurement.

New York returned Unable to Confirm in all four Sales runs. A separate released validation-page control without any Sales deadline reproduced Site Not Reachable in 3.948 seconds. Its raw source note is “New York did not provide a complete, confirmed registry record. HTTP Error 401:”, reason PORTAL_ERROR, installed connector 0.4.0. Thus the observed failure occurs before the Sales cutoff and also occurs without a Sales signal. The state/API rejected access; these results do not establish the deeper cause of that 401. No false registration conclusion was assigned.

Independent post-deployment Standard API controls: Colorado Current (5.875s, mature EIN lookup); Louisiana Not Registered (1.203s, expected completed no-record). Both passed.

## Files changed

- web-staging/sales-mode.js — overall deadline, stable final rows, timeout explanation, unchanged normal 15 lanes.
- web-staging/index.html — optional cancellation on requestSingleState, staging version and cache keys.
- web-staging/ny-connector.js — optional Sales cancellation, retaining Standard behavior and existing extension cleanup.
- deployment/prepare_web_release.py — staging frontend version only.
- testing/sales_test_dom.cjs — controllable clock and cancellation fixture.
- testing/run_sales_deadline_guardrails.cjs — seven deadline, late-reply, transport and unchanged-source controls.
- testing/run_ny_sales_abort_guardrails.cjs — seven Standard/NY cancellation controls.
- testing/run_sales_restoration_guardrails.cjs and testing/run_dc_ri_guardrails.py — preserve unrelated parity, replace obsolete whole-bridge equality with behavioral cancellation controls.
- This release record and output evidence.

## Deployment

Live staging frontend: 2026.09.24.1. Backend remains 2026.09.23.4-staging.
Final Netlify staging deploy: 6ab5225c80f1ea1cfe6f73e6.
Pre-change rollback: 6ab4689b2f8a266c164ae908.
The temporary 32-lane test page and script were removed from the final deploy. Four changed release assets were verified byte-for-byte after final publish. Existing site assets/functions were preserved. Staging API destinations were verified; no production API target was added. No backend or environment deployment.

## Commands and results

- node --test testing/run_sales_mode_guardrails.cjs testing/run_sales_restoration_guardrails.cjs testing/run_sales_deadline_guardrails.cjs testing/run_ny_sales_abort_guardrails.cjs testing/run_ny_connector_lifecycle.cjs testing/run_ny_resume_guardrails.cjs testing/run_ny_cleanup_guardrails.cjs testing/run_ny_timeout_guardrails.cjs — 88 passed.
- node testing/run_registration_date_ui_guardrails.cjs — passed 32-state date blanks/labels, Excel values and syntax.
- python -m unittest testing.run_dc_ri_guardrails testing.run_standard_sales_followup_guardrails testing.run_core_matching_guardrails testing.run_me_budget_guardrails testing.run_discovery_capacity_guardrails — 70 passed.
- python deployment/prepare_web_release.py --environment staging --out <output>/web-overlay — passed.
- Output deploy_frontend.py draft/publish and finalize_deploy.py draft/publish — staging only; complete.
- git diff --check — passed.

Smoke results: current, no-record, full 32-state streaming, live deadline, controls re-enabled, repeated runs, NY no-Sales-deadline control collected.
Regression results: 158 automated tests plus UI/date validation passed; all definitive non-NY live results and available IDs agreed across four Sales trials. No spreadsheet expectation changed.

## Known issues and limits

- NY HTTP 401 remains unresolved. This release is not a clean 32-state definitive match claim.
- One-minute limit ends the Sales user-facing wait and browser requests; the synchronous server may finish existing bounded work after disconnection. No claim of 60-second server resource reclamation or increased multi-user capacity.
- A suspended device/browser cannot guarantee wall-clock UI updates. On resume, overdue responses are rejected rather than accepted as on-time; deterministic late-timer controls pass.
- Standard's existing longer investigations and known prior validation discrepancies are outside this narrowly scoped change.

Production touched: No.
Recommendation: Needs review. Keep the one-minute Sales cutoff and 15 lanes on staging. Do not promote the wider release while material NY/previous validation issues remain open.

Evidence directory: C:/Users/nyagh/OneDrive/Desktop/Compliance Express/Projects/CharityClarity/outputs/sales-minute-20260924
