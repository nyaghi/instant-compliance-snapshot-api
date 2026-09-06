# CharityClarity automatic report — 2026.09.06.5-staging

Scope: authenticated staging-only PDF endpoint in the master backend, deterministic report presentation module, real Compliance Express/CharityClarity assets, and Generate report button on the existing live staging frontend. No registry routing, matching, deadlines, state classification, environment or production changes.

The report uses the displayed results without performing another registry lookup. One organization, 1–30 unique supported states, 3–5 pages. Executive summary, three-level risk legend, grouped action items and state findings. No record found does not establish a filing obligation or violation. Incomplete checks cannot yield an overall Low assessment; High/Moderate with incomplete checks is provisional. Input status, dates and evidence are preserved; evidence excerpts are visibly shortened. Download dates come from the actual supplied snapshot, not the current manifest or PDF generation time.

LA and OR freshness notes were already present in fresh live staging API results. Explicit coverage added for current, negative and unavailable outcomes and report preservation; no speculative state-parser edits.

Local gates: 12 Oklahoma recovery, 16 manual reconciliation, 14 New York, 30 mature matching, 10 downloadable data, 16 report tests (98 total). Report tests cover unavailable results, incorrect entities, unsupported states/statuses, duplicate rows, markup and unsafe links, actual endpoint authentication, zero additional state calls, and five-page worst-case layouts. Browser report smoke: five-page PDF downloaded, one report request, zero state lookups, zero JS errors. Every sample PDF page visually inspected. ReportLab pinned to 4.4.9.

Regression: original five ×30 on live 2026.09.06.4-staging (unchanged state logic in .5): 150 conclusive first submitted requests, 138 manual matches, 12 differences, zero harness reruns. An additional KS no-record control passed. Eleven differences carry forward documented sheet drift/source limitations; RIF OR changed to Upcoming Filing with refreshed data. Expected values remain unchanged. The backend's existing bounded internal recovery may run within a submitted request; first submission does not mean one upstream request.

Known issue: Oklahoma previously reproduced HTTP 520 on both existing staging backends. A successful full regression does not prove the external certificate service reliable. The existing bounded recovery and honest Site Not Reachable result remain. No cached certificate policy was introduced without the requested clarification.

Deployment evidence, post-deployment smokes, new national candidate runs and final comparisons are retained under outputs/staging-expansion-20260906. Production promotion remains blocked pending resolution/review of material limitations. Production untouched.
