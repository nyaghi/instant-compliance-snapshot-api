# Exact-match main-result selection and Alaska completion

## Requested behavior

When a registry main search returns multiple exact matches for the requested organization (including a recognized legal-name/alias variant), prefer the explicitly active record. Preserve identity matching ahead of activity. Do not add visits to competing detail pages to discover status. Existing state interpretation of the selected record remains intact.

## Implementation

The master supplies an exact-name activity tie-breaker and labeled main-result field readers. Updated main-result paths: CA, CO dataset fallback, CT, FL, HI, LA where its export exposes status, MD, MI, MS, NH, NJ, OH, OK, PA and WV. The shared checker rule reaches ME, MN and ND. KS already preferred Registered; the comparison now excludes Not Registered. AR and WA already give active/current main rows precedence after identity matching. VA uses the status on the returned entity; existing registration retrieval and interpretation remain intact.

No active status is inferred for AK registration-cycle evidence, KY filing-year exports, OR financial-period rows, MA's name-only charity dropdown, or NM's single-FEIN history. Wisconsin's main result has name, credential and dates; its existing detail-status handling is unchanged. New York is excluded from live checks at the user's request because its site is down. This policy does not expand pagination or introduce new registry classifications.

SC preserves the deployed legal-name/alias fix. When its main table exposes a Status column, that field breaks exact-match ties; otherwise existing matching remains. Only the selected record's detail is opened.

Alaska ties EIN-search completion to the observed EventOccurred response for the submitted Search button. Identical no-record text can complete without waiting for an impossible text change. A failed year receives at most one retry within the shared search deadline; completed years are retained. A negative is marked complete only after every required EIN year completes. Confirmed completed negatives are not automatically repeated three times. Persistent incomplete searches remain Unable to Verify, with accurate completed-year diagnostics. Existing confirmed-registration interpretation is unchanged.

## Kansas integrity correction

The weekly manifest hashes the complete KS_weekly_checker.py, including its embedded data. Changing selection code required updating this checksum. The Sunday September 6 download, all embedded data, source metadata and record count are unchanged. The original failed local control and corrected recheck are preserved. Live staging was unaffected.

## Release gate

See parent outputs/active-ties-ak-20260910 for regression logs and live control responses. Source: Fresh Test, Orgs A1:AG31; 30 organizations, 29 included states, 870 final checks. Expected sheet values are read-only. The corrected 35-organization scope is obsolete.

This is implementation documentation, not a claim that deployment or the final rerun is complete. Staging deployment requires passing controls, regression and the weekly-data integrity suite. Production is not authorized. Pause the rerun on a mismatch, preserve first responses, and ask the user whether to investigate.
