# September 12 staging repair

Candidate: 2026.09.12.1-staging; NY connector 0.2.0. Production is not authorized.

- Normalize typographic apostrophes to the existing ASCII semantics in the master matching/query helpers. Put bounded possessive discovery phrases within the existing query budgets. Acceptance still checks the complete organization identity.
- Accept a complete exact legal name before an explicit registry DBA/AKA, including short names such as Aeon. Preserve geographic, chapter and institutional guards.
- Wisconsin retains the original short name. A closely related Association credential that omits the requested Foundation is Needs Review with its credential evidence; it is not an accepted identity or a completed negative.
- Virginia retains exact-EIN entity identity and the public restriction when the registration response is empty. Do not infer a suspended or expired registration from a restriction alone.
- The NY extension queues originating staging tabs FIFO per Chrome profile. Queue wait is bounded at 20 minutes; active lookup lifetime remains five minutes and starts independently. The signed master continuation is created after queue admission.
- Wait three seconds between NY organization lookups. Retry HTTP 429 at most twice after five and fifteen seconds. The existing single shared 401 retry remains intact. Other errors remain inconclusive.
- Run NY alongside the existing serial non-NY state lane, joining both before completing the report. This does not implement the deferred platform-wide 15-workflow coordinator.

Validation evidence lives in the workspace outputs/fresh45-fixes-20260912 directory. Approved sheet capture is Orgs!A1:AH46 (45 organizations / 30 states); expected values remain unchanged. Controls distinguish approved behavior from source limitations: Al-Ayn VA remains unconfirmed, and the Farrier WI identity requires review.

Local test commands:
- Python testing/run_fresh45_guardrails.py
- Python testing/run_ny_connector_browser.py
- Python testing/run_ny_queue_browser.py
- Node --test testing/run_ny_connector_lifecycle.cjs testing/run_ny_connector_protocol.cjs
- Established state/matching/status regression suites and setup UI tests.
- 27 live local controls: 17 established positive/no-record cases and ten reported non-NY cases.

The first browser pass overlapped other browser suites and live controls. It produced a readiness timeout and timing failures. Preserve that evidence; sequential browser verification is the release gate. The immediate-network-error timing assertion measures active time after admission, excluding intentional queue wait.
