# Manual-check reconciliation — staging 2026.09.05.2

Scope: the September 5 manual discrepancies and the supplied five-organization, 30-state spreadsheet. Production deployment is not authorized.

Regression source: https://docs.google.com/spreadsheets/d/15McQtRw3pSbV_Bck_DC_nWaTcmnP1KWQJZ11iGfeamQ/edit

Expected spreadsheet results are preserved. The user explicitly selected Oklahoma's state-issued certificate expiration as the classification basis and confirmed that the Junior Achievement Oklahoma manual check probably selected a local chapter instead of Junior Achievement USA.

## Changes

- Master backend: preserve Connecticut's search session for detail retrieval; prevent incomplete details from becoming negative results; honor Maryland's current-registration extension; preserve Maine's explicit Failed to Renew status; distinguish Virginia's lapsed registration from an absent record.
- Master backend: reject unrelated South Carolina chapters; cross-check Wisconsin aliases sharing a license and prevent acronym-only rows from replacing full organization identities.
- Master backend: use Oklahoma registration certificates, bounded document retrieval and OCR, and qualifying registration filings. Exclude unrelated filing activity and future-dated history anomalies. Paginate results with full original-name acceptance rules.
- Master backend: classify New Mexico's next cycle after a completed registration, retain later adverse events, and preserve actual fiscal-year-end dates instead of substituting tax-year labels.
- Master backend: retain Ohio's exact-EIN compliance evidence when the state detail page fails, and use six calendar months for the shared upcoming window.
- Requirements: add pinned rapidocr-onnxruntime 1.4.4 for scanned Oklahoma certificates. OCR is lazy-loaded, serialized, and limited to the first two certificate pages with an entity-name and expiration-date check.
- Staging runtime: pin Python 3.12.14, the locally tested runtime. The first Render build used its unpinned Python 3.14 default and rejected the OCR dependency's Python compatibility requirement. No environment variable was changed.
- Tests: eleven targeted regression tests; fix the pre-existing expired-date fixture in the core suite by freezing its clock, without changing expected results.
- Staging frontend: version-only update prepared from the live staging HTML, retaining the verified staging-public API target.

## Local validation before staging

Commands:

```text
.venv-ocr\Scripts\python.exe -m py_compile registry_snapshot_server.py
.venv-ocr\Scripts\python.exe testing/run_manual_reconciliation_guardrails.py
.venv-ocr\Scripts\python.exe testing/run_core_matching_guardrails.py
git diff --check
```

Results: compile and diff checks passed; 11 targeted tests passed; 30 existing matching fixtures passed. Three actual scanned Oklahoma certificates yielded the verified expiration dates; the wrong-entity certificate test was rejected.

Live-source local smoke tests include known current, exempt, adverse, and no-record cases; mature EIN-first states; both additional Victims of Communism cases; and all original discrepancy states. The separate 150-case local regression and live staging regression are recorded in the delivery evidence, including reruns after later surgical changes.

## Evidence differences requiring disclosure

- Oklahoma Make-A-Wish: certificate expires October 17, 2026; Upcoming Filing.
- Oklahoma Reading Is Fundamental: certificate expires March 12, 2027; Current.
- Oklahoma Prevent Child Abuse America: certificate expires December 5, 2026; Upcoming Filing.
- Oklahoma Junior Achievement: the manually selected Oklahoma chapter is a different entity from national EIN 84-1267604.
- North Dakota Make-A-Wish: exact-name charitable record 0004011057 explicitly says Inactive - Involuntary, despite an AR due-date field in 2027.
- Michigan Make-A-Wish: explicit registration expiration is August 31, 2027.
- Ohio Make-A-Wish: exact-EIN search says In Compliance: Yes; the detail URL returns a state server error. No filing deadline is inferred from that failed page.

## Deployment and promotion gates

The live staging frontend is https://staging.compliance-express.com/. Its API is https://instant-compliance-snapshot-api-staging-8dnk.onrender.com/. Staging Render services track `staging`; production services track `main`. No production configuration, environment variables, files, or deployment target are changed.

This document records the release scope and local gate, not proof of a completed deployment. Delivery evidence must record the actual commit, live backend/frontend versions, post-deployment smoke results, complete spreadsheet regression, timings, and remaining limitations. Production promotion requires explicit user approval after that review.


## Final identity and certificate follow-up (2026.09.05.3)

The first 150-case staging run exposed additional legacy-name false negatives for Ronald McDonald House Global / RMHC. Connecticut CHR.0004532, Kansas 21-022470, and Oklahoma 4300661192 retain Ronald McDonald House Charities, Inc. The Connecticut and Oklahoma addresses match the national Chicago office. The supplied RMHC acronym now confirms a full expansion only when all preceding identity words match; geographic additions, acronym-only rows, and different EINs remain rejected. Kansas uses this shared rule for a unique row in its existing dataset. Its currently published official workbook was downloaded again and is byte-identical to the embedded source (SHA256 528862bb9761f7b5b6780df9059086745f23c85b07f47112ccfe32229c6a3c15); the source freshness limitation remains disclosed.

Oklahoma's Ronald McDonald certificate explicitly expires January 28, 2027. A fallback OCR pass at higher resolution handles its scanned legal name without lowering the 90% confidence threshold. Month spelling permits only an unambiguous one-letter substitution to a full month, retaining all date digits. The original fast OCR pass remains first and all four actual certificates were revalidated. A download timeout gets one bounded retry; successful checks add no request.

Local gates: 13 targeted tests, 30 existing matching fixtures, compilation, and diff whitespace checks passed. Live-source final local smoke returned Ronald McDonald Oklahoma Upcoming Filing (52.37 seconds), Prevent Child Abuse Oklahoma Upcoming Filing (28.23 seconds), Make-A-Wish Florida Suspended (7.04 seconds), and Junior Achievement USA Oklahoma Not Registered with chapter candidates rejected. Connecticut national legacy record is Upcoming Filing; Kansas national legacy record is Delinquent. Final staging regression must use version 2026.09.05.3 after its deployment.


## Final retrieval safeguards (2026.09.05.4)

The version 3 diagnostic run was stopped after a recurring Oklahoma certificate timeout and a version 2 New York false negative were investigated. A rejected or incompletely loaded New York detail no longer proves Not Registered. When the detail has finished loading with the exact EIN, a safe organization name, and annual filing rows, the master recovers the existing filing-cycle interpretation. Otherwise the response remains explicitly unconfirmed; a completed empty search still remains Not Registered. Prevent Child Abuse America national New York record 15-09-61 has EIN 23-7235671 and latest FYE December 31, 2024, supporting Delinquent.

Oklahoma now allows the first certificate download up to 30 seconds, followed by one 15-second retry only after a timeout. This changes the ceiling for a slow download, not the time taken by successful fast downloads. No global timeout was changed.

Final local live-source smokes: New York Junior Achievement Delinquent (12.05 seconds), Reading Is Fundamental Upcoming Filing (12.07), Prevent Child Abuse America Delinquent (15.98); Oklahoma Reading Is Fundamental Current (30.02), Make-A-Wish Upcoming Filing (38.48). Fourteen targeted tests and 30 existing matching fixtures pass. Version 4 is the required version for the final full staging run; prior diagnostic runs are retained separately.


## West Virginia query order and direct Oklahoma documents (2026.09.05.5)

The completed version 4 regression exposed a West Virginia no-match for Ronald McDonald House Global / RMHC. Its trace completed four redundant name/acronym forms and hit the state budget before the three-word legacy-name probe. The existing shared core query now runs second for explicit slash/acronym names, with unchanged full candidate acceptance. Local national record 2202 is Delinquent, found in 13.70 seconds. Controls remain Make-A-Wish Current (10.96 seconds) and Junior Achievement USA Not Registered (49.23 seconds).

Oklahoma's certificate link is an ASP.NET document-view postback. Replaying that same observed postback with the existing browser session returned both national Ronald McDonald and Make-A-Wish PDFs in approximately 2.4 seconds, while the browser download event had intermittently timed out. Direct PDF retrieval is now primary; only a validated filing-document link target is submitted, and only a PDF response proceeds to the existing strict certificate parser. The browser download remains a bounded fallback. There are no organization-specific date overrides or static status answers.

Sixteen targeted tests, 30 existing matching fixtures, compilation, and whitespace checks pass. Version 5 is required for the final full staging regression. Earlier completed versions 2 and 4 and the partial version 3 diagnostic run remain in the evidence directory.
`nFinal version 5 local Oklahoma live-source smoke: Make-A-Wish Upcoming Filing (39.16 seconds), Ronald McDonald Upcoming Filing (35.07), Reading Is Fundamental Current (44.23), Prevent Child Abuse America Upcoming Filing (25.89). All used the master direct-document path and the actual certificate parser.
