# Georgia results-layout correction after next-40 audit

The original 1,360-pair audit remains pinned to .4-staging and connector 0.5.2. Do not update installed files or deploy .5 until the baseline has finished.

## Concrete change
Georgia exposes both a six-column public search layout and a seven/eight-column city/state layout. The collector previously skipped data rows whose width was not six. The patch validates the known headers and preserves rows from either layout. Unknown headers, malformed rows and missing pagination fail conservatively. Paid solicitor records remain excluded.

The master now accepts connector version 0.5.3 in the same signed New York evidence flow as 0.5.2. No identity scoring or status classification rules change. Application version is .5-staging for traceability.

## Validation already completed
- 367 backend tests in 21 suites; zero failures, including mature EIN-first state and shared identity/status guardrails.
- 30 matching fixtures in the regression run.
- 64 browser connector tests; zero failures, including NY lifecycle/protocol regression and seven new Georgia public-table tests.

## Required live follow-ups
- All 40 Georgia pairs after the update.
- Bounded retry of incomplete Illinois pairs.
- Two corrected Unicode organization inputs across all 34 states, including New York.
- Confirm live staging version and API routing. No production deployment is authorized.
