# Alabama rejected-code dialog recovery — local candidate

Summary: YWCA USA was reported to stop after a verification-code error. Before
the user reserved the browser for their own tests, a read-only staging view
showed YWCA USA, Inc. (13-1624103), AL Unable to Confirm and a generic incomplete
lookup comment. No current failing AL trace was saved, so the exact live cause
remains unconfirmed. Subsequent work was entirely offline; no browser use.

The old `alVerificationRequest` clicked the public rejection dialog's Ok button
and immediately treated its continued visibility as a failed lookup. A synthetic
asynchronous dialog reproduced that stop with the old code. The fix observes
before dismissal and waits for closure within the lesser of four seconds and
the original command budget, then prepares the currently displayed image for
the existing signed continuation. It preserves the master's two-submission
limit, image binding, privacy, identity rules and conservative incomplete result.
It neither resubmits the rejected code nor extends the lookup deadline.

Files changed: `browser-connector/registry-content.js`,
`testing/run_al_verification_guardrails.cjs`, `testing/run_al_public_dom.cjs`,
and this release note. The latter two exercise real source/package functions
with synthetic DOM fixtures. No master backend, worker, geometry or permissions
were changed. The existing review-registry release note's separate user-directed
Colorado disposition is preserved outside this change.

Deployment: none. Existing enabled 0.6.132 TN Verification Trace and live 29.2FC
remain untouched. A separate unactivated `connector-0.6.132-al-dialog-recovery`
folder/ZIP differs from the trace base only in registry-content.js and manifest
name/description metadata. It requires no backend admission update.

Tests run: `node --test` across 12 source files (587/587), across 8 actual
candidate-package control files using CC_TEST_TRIAL_DIR (282/282), and
`python -m unittest testing.run_al_verification_guardrails
testing.run_al_completed_names testing.run_final_four_source_guardrails`
(287/294 tests passed; seven failed). The explicit relevant master runner
`run_al_focused_master_controls.py` passed 31/31 tests, distinct from the
approved 31-organization regression group. Exact commands, timings and logs are
in outputs/review-registry-fixes-20261014/al-dialog-offline-test-summary.json.

Smoke results: offline recovery, blocked-dialog/deadline controls, AL completed
current/adverse/empty/partial searches, YWCA national-versus-local identity,
verified alias and conflicting EIN, signed continuation, and mature IL EIN-first
positive/negative controls passed. Pre-fix reproduction had two failures and
one pass; the new lifecycle controls pass after the narrow fix. These are not
live registry checks or a demonstration of OCR accuracy on YWCA's failed image.

Regression results: source/package controls passed. Full fresh approved
31-organization AL regression, YWCA post-fix check, comparable discovery/execution
speed and native popup bounds remain pending because the user reserved the
browser. No sheet expectations were changed. Do not claim full regression or
performance validation.

Known issues: broad master suite has seven failed assertions in four unique
tests: NV optional-filing status (duplicated through inheritance), old 29.2DD
release label, and two historical whole-source change-boundary assertions
(duplicated through imported test classes). Their runtime/tests match HEAD;
the AL patch changes none of those Python files. Failures are preserved, not
rewritten to pass. Actual YWCA failure causality and live recovery remain open.
Earlier Tennessee required-checkbox completion remains unverified; the exact
original Tennessee breaking commit remains unproved. Colorado source naming
is informational only per the user's direction, with no fix or blocker.

History audit: saved 0.6.122–0.6.131 plus 0.6.132 Smart/Trace packages all have
the identical immediate-stop AL recovery function. AL OCR and continuation
functions also match across the inspected ten explicit historical releases and
current HEAD. Shared failure wording changed, so no claim is made that all
master functions were unchanged. Missing older Git parent history prevents
identifying the original introducing commit. Available saved-package equality
does not prove which version was installed in an earlier successful live run.

Production touched: No.

Recommendation: Do not promote. Keep the user's current testing session intact;
resume live verification only after the browser is released. Preserve first-pass
YWCA evidence before retry, install only the separately prepared candidate when
appropriate, and complete the outstanding release gates before promotion.
