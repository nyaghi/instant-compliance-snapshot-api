# Production 20.6 release — September 22, 2026

The user clarified the ordered scope: first promote the demonstrated September 20.6 staging functionality; keep sales experiments and registration dates in staging until separately validated. This branch starts at the compatibility-only commit b13ee52, whose parent is the exact reference fc9f5e3.

## Scope

- Master state checks, name discovery, alias/identity matching, status rules, reports, and state budgets remain those of fc9f5e3.
- Permit the existing authenticated discovery and report endpoints on production. Preserve the current Compliance Express access controls and public one-state experience.
- Add production-origin support to the New York connector and signed backend continuation; use production-specific signing credentials. Correct the connector's readiness version label to read its manifest.
- Replace the $49 trial with the requested contact information. Build only CharityClarity assets over the existing production site manifest, preserving the marketing homepage and unrelated pages.
- Match staging's effective two-service, six-instance-per-service Standard capacity using production-only URLs and credentials.
- No Sales mode, additional frontend lanes, progressive-results change, registration-date extraction, or report 1.3.0 is included.

## Gates and rollback

The existing reference benchmark and compatibility smoke evidence are in outputs/production-sales-dates-20260922. Production must be checked on this isolated branch before claiming parity. Retain prior Render deployment IDs, branch/resource configuration, complete private environment snapshots and Netlify's published deploy ID and hash manifest. Review all result differences without changing spreadsheet expectations.

Chrome Web Store developer registration is complete per the user. Store submission/review remains distinct from production website deployment; do not claim the extension is available in the Store until the listing is approved. Chrome prevents the current browser-control tool from scripting the publisher dashboard.
