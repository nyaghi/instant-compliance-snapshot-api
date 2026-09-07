# Massachusetts submitted Form PC fiscal periods — 2026.09.07.3 staging

User authorized live staging correction of Firehouse Subs Public Safety Foundation's incorrect June 30 fiscal year end. The state filing shows December 31, 2024. No organization-specific values are encoded in runtime logic.

## Scope

- Master backend opens the latest electronic Form PC, selected by its row year, and verifies the AGO account, filing year, Submitted status, and full fiscal period end. A single bounded detail read is added; no blanket timeout, concurrency, or batch changes.
- Remove both Massachusetts June 30 defaults. Preserve source-backed fiscal dates through normalization, comments and response evidence.
- Calculate the following annual period from the submitted period. Include Massachusetts's automatic six-month extension for registered charities in compliance with annual reporting requirements, explicitly disclosing that eligibility is inferred from the submitted prior report rather than separately certified. Preserve any explicit adverse registration status.
- No assumed date when details are absent, invalid, ambiguous or unavailable. Do not select an older electronic form over a newer scanned Form PC. These cases remain Unable to Confirm rather than an unsupported delinquency.
- Web staging version label only, from 2026.09.07.2 to 2026.09.07.3. Preserve the deployed assets, redirects, headers and existing functions.

Official sources: https://www.mass.gov/info-details/online-charity-filing-portal and https://www.mass.gov/info-details/frequently-asked-questions-about-charitable-organizations . Massachusetts's public registry cautions that absent public filings do not independently establish delinquency.

## Tests and expected-result handling

158 offline guardrails pass: 14 MA, 10 NMDP, 11 NM history, 30 OK certificate, 16 reconciliation, 30 core matching fixtures, 18 filing-evidence and 29 comments. Compilation and whitespace checks pass.

Local Firehouse: latest filed period 12/31/2024; next period 12/31/2025; base due 5/15/2026; inferred extended due 11/15/2026; Upcoming Filing.

Affected-state regression uses testing/weekly-data-regression-baseline.json without editing approved expected values. Fresh pre-release staging comparison was also captured:

- Firehouse MA: Delinquent to Upcoming Filing. Code bug: incorrect fixed fiscal year end and extension handling.
- Reading Is Fundamental MA: Upcoming Filing to Current. Code bug: actual submitted period ends 9/30/2025, next period 9/30/2026; inferred extended due 8/15/2027.
- Make-A-Wish MA: Delinquent to Unable to Confirm. Code bug/source limitation: old output used an unsupported June 30 date; source exposes older scans without electronic Form PC fiscal details. Scan extraction remains outside this surgical fix.
- Junior Achievement MA: Unable to Confirm on fresh staging before the release and locally after; no annual documents shown. Source limitation. Older baseline Delinquent is retained and flagged as expected sheet drift.
- RMHC MA and Prevent Child Abuse MA remain Delinquent using their actual December 31 submitted periods, with corrected dates.
- Make-A-Wish CO remains Current. Synthetic MA EIN 991234567 returns Not Registered. Initial all-zero EIN control returned Unable to Confirm on both pre-release staging and local; it is retained in evidence but is not used as proof of a completed negative search.

Evidence and final live release verification: outputs/firehouse-ma-fix-20260907 in the workspace root. No production files, configuration, environment variables or deployment targets are changed. Production promotion requires user review of the retained differences and source limitations.
