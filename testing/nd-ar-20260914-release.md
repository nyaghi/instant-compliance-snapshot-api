# North Dakota and Arkansas follow-up — 2026.09.14.2-staging

## Approved behavior

The user approved these changes on September 14, 2026 after reviewing the
first-70 results and the 23 affected North Dakota records.

- North Dakota: use the selected record's explicit `AR Extended Due Date`
  instead of its base `AR Due Date`. Existing adverse, exempt, pending,
  unavailable and no-record handling retains priority. The extension must be
  on or after the base date and no later than December 1 of that annual cycle.
  Missing or invalid extensions retain existing handling. This does not assume
  an automatic extension or change discovery/name matching.
- Arkansas: for requested EIN `83-2985088` and legal name `Chemical Coaters
  Association International Finishing Education Foundation, Inc.`, accept the
  public row `Chemical Coaters Association International` as explicitly
  authorized by the user. Use the row's live status, not a hardcoded Current
  result. The comment states that the shorter-name record was used and says
  `Confirm the EIN with Arkansas.` A conflicting EIN on the row still rejects
  the match. Other names, EINs and states do not inherit this exception.

The Arkansas exception is an accepted name-based workaround, not independently
verified EIN evidence. It is contained in the master backend. No runtime
sidecar, shared matching relaxation, connector change or production change is
included.

## Validation plan

- `run_nd_ar_followup_guardrails.py`: explicit extension boundaries and
  adverse overrides, master response/report deadline agreement, exact Arkansas
  approval scope, conflicting EIN, active-record tie-breaking and controls.
- Run the established regression suites, including mature EIN-first states,
  prior false-positive safeguards, matching and report rules.
- Live controls include all 23 confirmed ND extension records, seven other ND
  cases and eight Arkansas/other-state controls.
- Verify live staging backends/frontend/version/API target and report smoke.
- Post-validate a random sample of 30 organizations from the approved first
  70, across all 30 states. Select and save the seed/sample before the run.
  Record the approved ND result changes explicitly; retain the original sheet
  values. Investigate retrieval errors and substantive mismatches. Preserve
  failed attempts and fresh recovery evidence.

Execution evidence is saved in `outputs/nd-ar-followup-20260914` in the project
workspace, including the source hashes, sample plan, controls, regression logs,
deployment verification and post-validation results. Passing unit tests alone
does not establish completion or production readiness.
