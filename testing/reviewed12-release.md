# Reviewed identity and period corrections — 2026.09.16.1-staging

The twelve marked workbook cases reproduced with the original inputs before implementation. This release corrects source-confirmed DBA lists, prioritizes current complete identity in KY/NH/ME, improves distinct-name coverage in WI, confirms WI primary credentials and available WI/ME organization locations against EIN-linked evidence, completes equivalent CT searches before accepting inactive records, and handles valid short IRS periods and disclosed missing-date assumptions.

EIN remains strongest. A matching city cannot overcome a different EIN or regional-entity name. Missing addresses do not disqualify records; agent addresses are not treated as headquarters. A conflicting name-only organization location requires resolution. Multiple addresses attached to the same verified WI credential can corroborate its identity, as with YWCA USA's Washington location.

WI query completion is shared across bounded direct retries. The final no-results fallback must complete all required names. Reader pages request fresh data. An unreadable newer equivalent credential must not make an older expired credential the conclusive result. This additional safeguard came from the Reading Partners control, whose active credential is 23779-800.

No per-organization status overrides, dependencies, runtime sidecars, downloadable files, production configuration, or connector changes were added. Connector remains 0.3.1. No spreadsheet expectations were edited.

## Required identities

| Organization | State | Expected identifier | Status |
|---|---|---|---|
| Ronald McDonald House Global | WI | 2812-800 | Delinquent |
| Prevent Child Abuse America | HI | 23-7235671 | Delinquent |
| Prevent Child Abuse America | KY | 1087 | Delinquent |
| Firehouse Subs Public Safety Foundation | HI | 20-3588745 | Current |
| NAACP Empowerment Programs | KY | 684 | Delinquent |
| NAACP Empowerment Programs | ME | CO5572 | Upcoming Filing |
| NAACP Empowerment Programs | NH | 3717 | Upcoming Filing |
| Comic Relief | WI | 20018-800 | Current |
| First Responders Children's Foundation | CT | CHR.0013079 | Upcoming Filing |
| Autism Research Institute | KY | 13927 | Upcoming Filing |
| Christian Ministry Alliance | MI | No record after completed queries | Not Registered |
| YWCA USA | WI | 3108-800 | Current |

## Validation and evidence

Evidence is retained in the project output folder `outputs/reviewed12-fix-20260916`.

- `cases.json`: fixed twelve cases plus thirty controls selected reproducibly from the approved regression export across WI, KY, NH, ME, CT, HI, MI, CA, FL, and ND. Each matched control checks its record ID and status.
- `local-validation.json`: all 42 checks pass. The final delta affected four WI-only functions; 36 unchanged non-WI checks were retained after an AST-equivalence audit and all six WI checks rerun. The original failed Reading Partners observation is preserved.
- `regression-summary.json`: authoritative final suite results, with exact source hash and per-suite logs. Includes the existing suites and `run_reviewed12_guardrails.py`.
- `javascript-checks.json`: staging page/validation-page script checks.
- `preparation.json` and `deployment-verification.json`: release gates and live staging verification, when deployment completes.
- `staging-all.json`: post-deployment repeat of the 42 checks, when it completes.

QA commands are in `tmp/reviewed12_fix_qa.py`, `tmp/reviewed12_finish_local.py`, and `tmp/reviewed12_release.py`; these are release tools, not runtime state readers. The release gate requires passing regression, local controls, JavaScript checks, exact backend commit/version, correct staging API target, and unchanged non-version web assets.

The 5/10/15 concurrent whole-workflow test uses controlled registry responses to verify name-context isolation across all 30 state slots. It is not a live service-capacity certification. The deferred platform-wide concurrency feature is unchanged.

## Interpretation limits

Firehouse's scan does not provide machine-confirmable fiscal override boxes at the required OCR confidence. Its result explicitly discloses the approved December 31 assumption. Actual March/June short-period evidence is preserved for Prevent Child Abuse America and Autism Research Institute. A newer IRS return is not represented as a filing received by a state.

NH does not expose EINs in its list. Provider outages and unresolved identity conflicts remain inconclusive, never negative registrations. This release does not resolve unrelated issues from earlier validation runs or establish production readiness.

Production promotion requires the user's explicit approval after staging review.
