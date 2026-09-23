# Sales restoration — September 23, 2026

## Scope and release

Restored the Sales workflow from 41a5306 on the current 32-state frontend. The registration-date branch had returned to the stable Standard-only page. The requested controls now read **Standard** and **Sales**, with a yellow SVG lightning bolt after Sales. Standard remains the default. Sales retains the earlier 16 direct-EIN states and all-state choices; all-state coverage now contains DC and Rhode Island.

Frontend release: **2026.09.23.4**. Backend stays **2026.09.23.3-staging**. No backend, registry, discovery, connector, environment, instance-count or timeout changes. The deployment manifest explicitly distinguishes frontend and backend versions so the dedicated validator still checks the correct backend version.

Sales retains three concurrent non-NY state calls and the separate NY lane. Standard retains its existing sequence. Selected Standard states are restored when returning from Sales. Mode changes and duplicate submission are blocked while checks run. Result rendering uses the mode captured at submission; changing the next workflow does not reclassify prior results. Sales display labels retain all underlying statuses, comments, date fields and export evidence. DC/RI are excluded from the 16-EIN scope and included in all-32 scope.

## Commands and tests

- `node --test testing/run_sales_mode_guardrails.cjs testing/run_sales_restoration_guardrails.cjs testing/run_identity_review.cjs`: **16 passed**.
- `python testing/run_dc_ri_guardrails.py`: **39 passed**. Its Standard parity assertion now excludes only the authorized Sales branch before comparing the complete Standard path; executable scheduler tests independently verify both branches.
- `node testing/run_registration_date_ui_guardrails.cjs`: passed 32-state blank/date-column coverage, 12 Sales status and evidence controls, export preservation and inline JavaScript syntax.
- `python deployment/prepare_web_release.py --environment staging --out <outputs>/sales-restoration-20260923/web-overlay`.
- Deployment overlay script `deploy_frontend.py draft`, then `publish`: uploaded only index.html, instant-compliance-snapshot.html and sales-mode.js to the verified staging site. All 329 other assets and the existing functions were preserved.
- `git diff --check`: passed.

An initial test-harness read hit Node's output-buffer limit on the large master file; increasing that test buffer resolved it. The original DC/RI frontend parity check correctly detected the newly authorized Sales branch and was narrowed to compare Standard's complete path. A missing test-only import was corrected. All final checks above passed.

## Live staging smoke

- Preview and live staging asset bytes match the prepared build.
- No production API target appears in the staging page.
- Authenticated live browser shows version .4, Standard and Sales with yellow bolt.
- Sales selects exactly 16 EIN states; all-state Sales selects all 32 including DC/RI.
- Returning to Standard restores the exact Alaska/Washington selection.
- National Center for Family Philanthropy (52-2055016): live discovery completed in 20 seconds. HI, NM and some OH discovery data were unavailable, clearly disclosed; verified names from other sources remained usable.
- Standard live lookup: Alaska Not Registered; Washington Current; completed in 30 seconds. Both matched the preserved validation results. Detailed report control and both date headings remain present.
- No new live Sales load/capacity benchmark was performed. Executable controls verify its bounded scheduler and result presentation. The earlier 960-check validation covers the unchanged backend, not a fresh Sales performance claim.

## Deployment and remaining issues

Netlify staging site: `37bff787-45ea-4a1c-a073-4f64fe1d65bb`.
Published deploy: `6ab447e1d6ba04001611efc3`.
Rollback: `6ab42d414267a5777df2fa35`.
URL: https://staging.compliance-express.com/

The preceding last-30/all-32 run is preserved under project `outputs/last30-all32-20260923`: 960 checks, 909 matches, 51 differences. Florida accounts for 30 failures with an independently confirmed public server error. Eleven differences are proposed sheet/rule changes. Four application-result issues concern NLIHC/DC, Resist/WV, Momentum/MA and Renaissance/RI. Six other differences need source/manual reconciliation. A separate discovery placeholder issue is also documented. No spreadsheet expectations were changed and no state fixes were bundled into this UI restoration.

**Production touched: No. Recommendation: Do not promote while those material validation issues remain.**
