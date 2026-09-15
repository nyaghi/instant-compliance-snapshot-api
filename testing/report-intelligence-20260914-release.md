# Report intelligence — 2026.09.14.6-staging / template 1.2.0

The generated report now explains the nature of the returned findings, the upcoming workload, and the evidence needed to resolve open questions. It uses completed results in the existing master-backend report endpoint. It does not make new registry calls or change state matching, classification, extensions, or search behavior.

## Behavior

- One presentation model supplies summary groups, state lists, calendars and insights. Closed records count toward record-based results and are identified separately. Unresolved checks remain unconfirmed.
- The report displays `No registration found` for the existing `Not Registered` result. Its obligation assessment remains Unknown; underlying API and main-page statuses are preserved.
- The forecast groups overdue, 0–30, 31–60, 61–90, 91–180, later and unconfirmed dates. It distinguishes expiration from filing/renewal deadlines where the snapshot establishes the type. A 30-day preparation target is explicitly a planning suggestion, not a state deadline. Base/extended dates and qualifications are retained.
- Filing comparisons require explicitly filed fiscal periods with matching month/day and at least two records supporting the later period. Next-required periods and year-only labels never become a confirmed outlier. New Mexico's Tax Year 2024 / FYE June 30, 2025 example remains aligned with the other June 2025 filings.
- Exemption follow-up starts with existing determination letters and the no-record states. No exemption category, eligibility, legal obligation or state-specific rule is invented. A maintained legal rules table and organization questionnaire are outside this report-only change.
- Closure review asks whether withdrawal was intentional and whether relevant activity, a replacement registration or an exemption explains the result. It does not prescribe automatic reinstatement.
- Full comments, raw evidence and source notes survive PDF pagination. Ordinary state findings stay together. Long source fields can split across pages without dropping text. Source timing stays with the affected state; there is no standalone data-freshness section.

## Regression design

The historical Christian Research Institute fixture is reconstructed from the user-supplied report and screenshots, not from a new API run. It retains that report's .2 statuses and dates; individual check times and raw excerpts were not available. See the fixture's provenance note. The user-facing sample is marked as a historical illustration.

Control coverage includes 30 previously validated organizations / 900 captured state results. Report replay compares validation, status/risk preservation, count reconciliation, full comment/source content and page totals. It does not re-run registry checks or modify spreadsheet expectations. Existing escaped Maryland source text from the older capture is retained as input fidelity coverage; the separate .5 Maryland display repair remains unchanged.

The report guardrails also cover date boundaries, inferred extensions, ambiguous dates, no-record/incomplete cases, intentional closures, safe links and literal markup, maximum-length evidence, authorization, input immutability and zero registry work. Browser smoke exercises the real Generate report button for a 30-state example and Current, no-record, Pending and incomplete controls. Staging additionally checks the second backend.

Deployment remains restricted to the existing staging branch, two staging backends and the existing Netlify staging site. Production and the New York connector are outside this change. Exact commands, results, hashes and deployment IDs are recorded in `outputs/report-intelligence-20260914` in the parent workspace.
