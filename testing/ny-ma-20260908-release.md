# NY retrieval and MA status release — 2026.09.08.1-staging

Scope: user-authorized NY latency correction and Massachusetts classification updates. Master backend only; no new runtime scripts or services.

NY: increase per-response allowance from 12 to 42 seconds; 65-second overall lookup deadline. At most one retry across search and detail for transport timeouts/connectivity errors or HTTP 408/429/500/502/503/504, with remaining-budget enforcement. Completed negative, ambiguous identity and invalid-schema responses are not retried. Existing filing-history calculation and exemption precedence retained. Explicit timeout comment.

MA: observe successful official public all-filings responses and identity-confirmed charity detail. A completed, truly empty history with no contradictory state status produces inferred Delinquent, clearly disclosed in comments. Missing requests, partial responses, unavailable Form PC details, filtered/registration-document lists and nonempty non-Form-PC histories do not prove emptiness. User-approved mapping: exact Charity_Status__c "Not Doing Business in Mass" maps to Closed / Withdrawn / Canceled. Preserve the state's wording and disclose this is grouping an inactive status, not claiming formal cancellation. Other contradictory statuses remain conservative. GiGi's MA has that inactive status and a Schedule-A2 row; its result follows the explicit status mapping, not the empty-history rule.

Files: registry_snapshot_server.py; testing/run_ny_retrieval_guardrails.py; testing/run_ma_form_pc_guardrails.py; web-staging/index.html; this release note.

Local validation: compile and git diff --check pass. 192 offline checks pass across 10 suites, including a real 13-second NY detail response, bounded retry/deadline tests, MA response/identity guards and mature-state matching/status/comment tests. Targeted live smoke confirms GiGi's MA Closed / Withdrawn / Canceled, GiGi's NY Exempt, Year Up NY Delinquent, Firehouse MA Upcoming Filing, CO Current and completed MA/NY no-record cases. America's Charities still exceeded the bounded allowance; retained as source limitation, not a negative result. An initial RIF smoke EIN typo is retained in output and corrected against approved data for subsequent testing.

Approved 25-case regression expectations remain unchanged. Full local/staging regression, live version/target checks and 30-state batch evidence are recorded under outputs/ny-ma-fix-20260908. Final counts and differences belong to that verification report.

Deployment authorization: live staging only, both existing Render staging services and the existing Netlify staging site. Preserve all other web files, functions, redirects and headers. No environment-variable changes. Production not touched. Do not promote to production until retained differences and source limitations are reviewed and promotion is explicitly authorized.
