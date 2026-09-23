# Staging 2026.09.23.2: two-column renewal / filing display

The results table and PDF use **Initial Registration Date** and **Last Renewal / Filed Year**. Excel exports the same two primary values plus their existing provenance columns. A short label below each displayed value distinguishes renewal filing, current effective date, registration submission, fiscal period end, and filed year. Missing values and labels stay blank.

## Evidence selection

1. Preserve the verified renewal/current registration value from the prior release, with its precise source meaning.
2. Otherwise use a verified state-recorded filed fiscal period end.
3. Otherwise retain a state-listed filed year as four digits. Never invent December 31 or use a future due date as filing evidence.

Additional fallback sources:

| State | Already retrieved evidence |
|---|---|
| California | Accepted/submitted year from selected Annual Renewal Data; excludes pending and not submitted rows |
| Hawaii, Kentucky | EIN-linked state filing tax-period evidence; assumed/unconfirmed period shows only the state tax-year label |
| Massachusetts | Submitted Form PC period or confirmed legacy URS reporting period; does not treat supplemental-document dates as annual filings |
| Maryland | Year Represented bound to the selected Charity ID and EIN, including escaped HTML fields |
| Minnesota | Fiscal Year Ending, preserving a full date or a bare year |
| New Jersey | Selected fiscal-year-end field or existing state-derived last year; excludes adjacent renewal deadlines |
| New York | Latest FYE from the confirmed EIN record |
| Ohio | Most Recent Report Filing Year |
| Oregon | Confirmed Fiscal Period End; unresolved live/export evidence remains blank |
| South Carolina | End of the reported Fiscal Year range, not the Next Report range |

Together with existing registration/renewal extraction, 22 state paths can supply at least one of the two columns. Current inspected paths for AK, KS, LA, ME, MI, NH, PA and WA remain blank: no qualifying initial, completed renewal, or filed-period evidence is extracted. This does not assert that these states can never publish such evidence. Values in other states also depend on the individual record.

## Scope and controls

No new registry requests, state budgets, concurrency limits, discovery changes, matching changes, or status rules. Existing API `renewal_date` fields retain their date-only meaning; five additive `renewal_filing_*` fields support the combined display. Old completed snapshots remain reportable.

Release controls: 30-state blank/purity checks; identity conflicts and duplicate MD rows; assumed tax periods; future/invalid dates; renewal precedence; PDF validation; UI and Excel rendering; stable master AST, discovery, connector and frontend workflow parity; broader matching/status regression; recorded official-source replay; 45 live pre/post staging checks across 15 simultaneous organization workflows; focused YWCA source checks and PDF/UI visual review.

Runtime changes stay in the master backend. Testing/release scripts are not runtime sidecars. Detailed results are saved in the project output directory `outputs/renewal-filed-year-20260923`. Production is excluded from this release.
