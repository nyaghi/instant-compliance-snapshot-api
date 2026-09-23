# Original Sales restoration — September 23, 2026

## Summary

Supersedes the Sales UI restored in ebada44. That change used an earlier experimental mode with preset scope and three non-NY lanes. The requested later release was in outputs/sales30-capacity-20260923/web-overlay. Its separate red Sales page and 15-state scheduler are now integrated into canonical source and the staging builder, so subsequent frontend builds preserve them.

Sales now has a red **Sales** button with a yellow inline lightning bolt, all 32 supported jurisdictions available, no automatic selections or preset dropdown, explicit Select all / Clear controls, and any manually selected subset. Fifteen total requests includes New York. Each returned result renders immediately. Input and selection controls are locked during a run and restored afterward. The original simplified status presentation and no-discovery Sales workflow remain. Failed checks never become Not Found.

Standard inline JavaScript is identical to e069ad6. The master backend, identity discovery, and NY connector files also match that release exactly. DC/RI and Standard registration/filing columns remain intact.

## Files changed

- web-staging/index.html: remove the wrong integrated experiment; restore Standard source and load the correct Sales extension after initialization; frontend version .5.
- web-staging/sales-mode.js: restore the later Sales implementation, add explicit 32-state selection and yellow bolt, retain 15 workers and streaming results.
- web-staging/sales-charityclarity.png: track the original Sales image in the canonical source.
- deployment/prepare_web_release.py: .5 staging UI label and include the Sales image in staging builds; backend version remains .3.
- testing/run_sales_mode_guardrails.cjs, testing/run_sales_restoration_guardrails.cjs, testing/sales_test_dom.cjs: behavioral controls for the corrected workflow.
- testing/run_registration_date_ui_guardrails.cjs, testing/run_dc_ri_guardrails.py: restore unchanged Standard parity checks, retaining 32-state date coverage.
- This release record.

## Deployment

Live staging frontend 2026.09.23.5; backend 2026.09.23.3-staging unchanged.
Netlify staging deploy: 6ab44df38df24fae5ae069d4.
Previous staging deploy / rollback: 6ab447e1d6ba04001611efc3.
Only /index.html, /instant-compliance-snapshot.html and /sales-mode.js changed in the published manifest. The original Sales image was already deployed; it is now tracked locally too. Other 329 assets and existing functions were preserved. Four targeted assets were verified byte-for-byte on the draft and live URL. Staging API destinations were confirmed; production API destinations were absent.

## Commands and tests run

- node --test testing/run_sales_mode_guardrails.cjs testing/run_sales_restoration_guardrails.cjs — 8 passed.
- node testing/run_registration_date_ui_guardrails.cjs — passed 32-state blank/populated date rendering, source labels, Excel values and inline JavaScript syntax checks.
- python testing/run_dc_ri_guardrails.py — 39 passed, including mature-state parity and DC/RI identity/status controls.
- python deployment/prepare_web_release.py --environment staging --out <release-output>/web-overlay — passed.
- Release output deploy_frontend.py draft and publish — staging only; completed.
- git diff --check — passed.

## Live smoke and timing

Normal Chrome with the connected New York extension, YWCA USA Inc., EIN 13-1624103, all 32 states selected explicitly. First response: 0.581 seconds. The 30 non-maintenance states all completed by **46.693 seconds**; last was NJ. NY completed Current at 3.447 seconds. The page showed results progressively (11 at 8.9 seconds; 29 at 32.0 seconds). FL and WI were still waiting when the user confirmed both were under maintenance and authorized excluding them. Their completion is not claimed. The test tab was closed on turn interruption after the 30 completed results had been saved.

This is one observed timing sample, not a guarantee of all-organization or 32-state completion within one minute. It measures the original Sales workflow without advance alternate-name discovery. Its Not Found results are preliminary; YWCA aliases in AR/NH are a known limitation of that original mode, not a new matching regression.

The saved earlier no-discovery baseline covers 28 completed overlapping states: 27 displayed statuses agree; NY improved from the earlier isolated-browser Unable to Confirm to Current in normal Chrome. DC and RI were additions to that baseline. No spreadsheet expectation was changed.

A separate live subset smoke selected only Alaska and Washington for National Center for Family Philanthropy (52-2055016). Both completed in 16.8 seconds: Alaska Not Found and Washington Current, matching the preceding control results. Observed peak concurrency was two. Controls re-enabled at completion; switching back to Standard left its state selection empty, switching to Sales preserved the chosen subset, and Clear returned Sales to zero selected. Computed Sales button background was rgb(198,40,40), and the lightning path fill was #FFD54F. Final screenshot capture timed out, but the prior screenshot and final DOM checks verified the appearance and behavior.

## Known issues

Florida and Wisconsin excluded from this validation at the user's instruction because of maintenance. Earlier separately reported Standard validation discrepancies remain outside this UI restoration; this report does not claim they were fixed. No new matching or classification rule was introduced.

Evidence: project outputs/sales-original-restoration-20260923, including ywca-progress.json, baseline-comparison.json and deployment manifests.

Production touched: **No**.

Recommendation: **Needs review** — restored Sales is ready for user review on staging; this is not approval to promote unresolved state findings to production.
