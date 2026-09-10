# Michigan name fallback correction

Michigan still searches EIN first. After a completed EIN no-result response, the master backend searches the supplied organization name before generated variants. It evaluates all returned candidates against the original identity and recognized aliases instead of selecting one alphabetically convenient row. Explicit activity only breaks exact identity ties when the main row exposes status.

America's Charities is the motivating case: an unrelated America's Best Charities row previously prevented selection of the correct AG file 9927, expiration 12/31/2026. The corrected live name-fallback replay returned Upcoming Filing.

The same bundle permits actual one-word legal names, continues rejecting isolated generated fragments, and skips word-superset queries only after a completed zero-result Includes / All words query. Distinct punctuation/alias queries remain. The final response retains completed/incomplete name-search diagnostics.

Name form initialization uses the existing Michigan browser helpers consistently. Subsequent variants reuse the accepted registry session. Name navigation waits allow up to 12 seconds, clamped by the remaining existing master Michigan lookup budget; the conflicting 36-second fallback cutoff is removed. This follows measured late valid responses: FoodCorps arrived about 0.9 seconds after the former eight-second navigation cutoff, and National Marrow Donor Program arrived about 3.6 seconds after the nested fallback cutoff. The overall state budget and retry counts are unchanged.

Timeouts, missing frames, unrecognized responses and unmatched/incomplete detail evidence remain inconclusive rather than becoming an EIN-only negative. A completed negative retains the EIN-and-name completion reason and query trace. No registry status or filing-date interpretation rule was changed, and no runtime sidecar or environment-variable change is introduced.

Validation is recorded outside this worktree in outputs/mi-name-fix-20260910. The focused suite is testing/run_mi_name_fallback_guardrails.py; the broader timing-gate-summary.json lists 21 suites. The live control plan is all 30 approved Michigan organizations plus nine mature-state/targeted controls. Historical failures and recovered checks are preserved separately. FIX_TRACKER.md in the parent project is the single current status list.

Staging candidate version: 2026.09.10.3-staging. This document describes the release; it does not claim a successful deployment before live verification. Production is not authorized. New York remains excluded from the approved 30-organization rerun. Pennsylvania's America's Charities expectation was corrected to Current by the user.
