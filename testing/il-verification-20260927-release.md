# Illinois verification readiness follow-up

## Evidence and root cause

On September 27, the official Illinois `/search` document's inline initialization code was inspected through the public DOM. It hides `.k-button` controls until the site's own verification callback reports success; expiration and the five-minute verification reset hide them again. No verification value, cookie, response token, or private application state was read or changed.

The earlier 0.5.9 audit captured two `IL_FORM_MISSING` failures in hidden tabs before search submission. It also captured successful searches with the same code. A prior independent page became ready when made visible. The verification gate is confirmed; background-tab visibility as the cause of every failed challenge is not yet proven. The previous generic fresh-page retry restarted this gate and mislabeled its hidden button as a missing form.

## Change

* Recognize a present but hidden Search button together with the public verification-widget element.
* Give that condition a 12-second initial wait, preserving the ordinary 45-second readiness allowance for other form conditions.
* Retain the same page, activate only the connector-owned Illinois tab in the originating window, and give the state one 45-second normal verification opportunity within the existing overall budget.
* Restore the prior active tab only if the user has not switched elsewhere or navigated the Illinois tab away.
* Never enable hidden controls, solve verification challenges, access challenge data, or turn incomplete searches into negatives.
* Surface `NY_CONNECTOR_IL_VERIFICATION_PENDING` with a distinct master-backend explanation. Matching, status calculation, query order, and expected spreadsheet values are unchanged. No organization or EIN is hardcoded in runtime behavior.

## Validation and release gate

* 110 Node tests passed, including recovery without reload, persistent verification, focus restoration, user tab changes, deadline bounds, source navigation, stale grids, pagination, and NY/GA controls.
* 738 backend tests in 39 approved regression suites passed.
* One added test initially assumed a failed job's owned tab remained open. Existing cleanup correctly removed it; the assertion now measures activation calls. The initial failure log is retained alongside the passing run.
* Independent official Morgan Stanley EIN search confirmed CO01039680, FEIN527082731, Good Standing, and annual-report due date 11/15/2026. This is source verification, not new-connector acceptance.
* Chrome control was disconnected during this follow-up. The in-app browser can inspect the state site, but cannot run the installed Chrome extension. 0.5.10 activation and repeated live acceptance are not yet confirmed.

Recommendation: **Do not promote** until the new connector passes the two reported organizations and known-current/no-record/NY/GA controls in live Chrome. Preserve the earlier first-pass failures. Staging deployment and final live health/asset/control results are recorded separately in `outputs/illinois-verification-fix-20260927`; production is not authorized.
