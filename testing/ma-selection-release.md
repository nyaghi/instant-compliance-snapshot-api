# Massachusetts charity selection correction — local verification

Summary: Implemented locally on September 9, 2026. The master backend now completes the charity selection before Get Filings, confirms the returned record ID and requested EIN, and requires a completed filing-list response for that account before interpreting filings. Existing submitted-period, scanned-document, explicit-status and confirmed-empty-history rules remain in place. Incomplete selection and retrieval have distinct user-facing explanations and cannot become definitive negative findings.

Workspace: `.codex-build/ma-selection-fix`, branch `fix/ma-charity-selection-20260909`, based on staging commit `b181c57a92b658b515231c61f10221de8c4db1d9`. The parent workspace backend is older; it was not overwritten. No push or deployment was performed. No production files, configuration or environment variables were modified.

Files changed: `registry_snapshot_server.py`, `testing/run_ma_form_pc_guardrails.py`. Added this release note, `ma-selection-cases.json`, `ma-selection-comparison.json`, test logs, raw JSONL evidence and `ma-selection-fix.patch` under testing. Local Python environments and browser dependencies are test setup only, not runtime additions or deployment changes.

Selection: A single result from an EIN query may be opened for verification, including renamed charities. Multiple results require a unique safe name match using the existing master matcher. No classification occurs unless the selected record ID and requested EIN are confirmed. Name-only searches use the charity-name mode and the master name matcher. General matching rules were not changed.

Deployment: Not requested and not performed. The live staging site does not contain this local fix. Production untouched.

Tests run:

- Python 3.12.14 local virtual environment with the project's requirements.txt; Playwright Chromium installed in the location selected by the existing backend.
- `python -m py_compile registry_snapshot_server.py testing/run_ma_form_pc_guardrails.py` and `git diff --check`: pass.
- Eight existing guardrail suites: MA Form PC/selection, core matching, comment rationale, filing evidence, manual reconciliation, New Mexico status history, NMDP, Oklahoma certificate recovery. 167 checks total: 166 pass, one pre-existing Oklahoma compatibility assertion fails. See `ma-selection-guardrails.json` and per-suite logs.
- `python testing/run_weekly_data_smoke.py --cases testing/ma-selection-cases.json --output testing/ma-selection-python312-final.jsonl`: exit 0, eight completed live lookups using local code.
- Re-ran the failing NMDP suite against unchanged HEAD source: same `test_ok_http_200_document_error_qualifies_but_generic_html_does_not` assertion fails (`True != False`). Baseline evidence: `ma-selection-baseline-nmdp.log`. This unrelated existing failure was not changed.

Smoke results:

| Organization | State | Result | Seconds |
|---|---|---|---:|
| Anita Borg Institute for Women and Technology | MA | Delinquent, submitted period ending 12/31/2022 confirmed | 11.97 |
| Reading Is Fundamental, Inc. | MA | Current | 18.40 |
| Synthetic no-record EIN 99-1234567 | MA | Not Registered after completed No Charity Found response | 3.25 |
| Make-A-Wish Foundation of America | CO | Current | 5.66 |
| Make-A-Wish Foundation of America | MA | Delinquent, existing scan reader succeeded | 40.55 |
| Ronald McDonald House Global / RMHC | MA | Delinquent, exact EIN confirmed despite renamed record | 20.84 |
| Junior Achievement USA | MA | Delinquent under existing confirmed-empty-history inference | 19.90 |
| Prevent Child Abuse America | MA | Delinquent | 18.31 |

Regression results: Six cases copied without changing expected values from `weekly-data-regression-baseline.json`: all five MA entries and Make-A-Wish CO. Five match; Reading Is Fundamental is Current versus the saved Upcoming Filing expectation. Category: Expected sheet drift, already documented in the September 7 fiscal-period release; its submitted non-calendar fiscal period gives a future deadline. The expectation was not edited. The synthetic negative and Anita Borg are additional diagnostic smoke cases, not newly approved regression expectations. See `ma-selection-comparison.json`.

Known issues: One inherited Oklahoma assertion failure remains. The older RIF expected value still requires review. Initial exploratory tests on machine-default Python 3.14 could not load the existing OCR dependency; a first Python 3.12 run lacked the backend-specific browser install. Those environment issues were resolved and are superseded by the successful final Python 3.12 run. Source limitations and future registry outages remain possible and return inconclusive findings. Batch routing was not changed, so no separate batch regression was required. No full multi-state spreadsheet run or live staging verification was performed.

Production touched: No.

Recommendation: Do not promote to production. The local correction is ready for staging review/deployment when requested; review the inherited Oklahoma failure and retained RIF baseline difference before promotion.
