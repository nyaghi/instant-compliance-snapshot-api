# Michigan / West Virginia corrections — September 13, 2026

Candidate: 2026.09.13.2-staging. Baseline: d03bcea465d363d1bd6c714f43adae811f7b0dbd (2026.09.13.1-staging).

## Reproduced causes

- MI, Beth Israel Deaconess Hospital – Milton, Inc. (04-2103604): the EIN search completes without candidates, then the public name form rejects the en dash in the original name. The form displays “‘Organization Name’ field - invalid format; some special characters are not permitted.” No search POST occurs. The existing navigation wait therefore expires and surfaces Site Not Reachable. This is a query-format incompatibility, not proof of a registry outage. The same source form accepts an ordinary hyphen, completes navigation, and returns zero records; a punctuation-free full-name control also completes.
- WV, Milton and Beth Israel Deaconess Medical Center (04-2103881): staging selects Beth Israel Deaconess Hospital - Needham, Inc., WV ID 22209, Exempt. The master’s existing full-name matcher rejects Needham for both requested entities. However, the WV loop ranked candidates using search-query variants, retained an unsafe candidate, and then reused the broadened query targets on the detail page. The broad discovery phrase “Beth Israel Deaconess” thus became acceptance evidence.

Evidence: ../../../outputs/mi-wv-location-fixes-20260913/before-controls.json, mi-source-trace.json, mi-form-0.html, mi-query-0.txt, mi-query-1.txt.

## Scope

Only two runtime functions change, both in the master backend:

- search_mi_name_fallback: convert typographic dashes to ASCII hyphens in submitted query strings, reuse existing apostrophe canonicalization, deduplicate equivalent queries, and preserve full-name query priority. The original organization and safe match targets remain unchanged. EIN-first routing, query count, time budget, result parsing, and status rules remain unchanged.
- search_wv_precise: score and confirm against the original safe identity targets; discard unsafe rows before selection; carry the same original targets into detail confirmation. Broad queries remain available for discovery. Active status still breaks ties only after equivalent matching identity.

No shared matcher, date rule, alias table, state route, downloadable dataset, connector extension, production configuration, or environment variable changes. Frontend edits are the staging version labels and the internal validation page’s allowance for 55 organizations.

## Verification required

- New reproductions fail before the respective fixes and pass afterward.
- Existing full regression suites plus MI/WV controls, including typographic punctuation, correct location, mismatched location, active sibling versus exact closed record, detail-name mismatch, active duplicate selection, ordinary EIN-first states, known current and no-record cases.
- Browser integration tests and fresh local live controls.
- Both staging backends and live frontend verified, correct version and API targets, unchanged downloadable data and extension.
- Fresh first-55 post-validation: 55 organizations × 30 states = 1,650 results. Preserve original attempts, investigate errors, and record any reconciliations separately without editing expected spreadsheet values.

Actual outcomes and release identifiers are recorded in the release artifact report; this plan alone is not a completion claim.
