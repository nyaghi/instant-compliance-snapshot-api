# September 13 approved state corrections

Release candidate: 2026.09.13.1-staging. Production is outside this release.

## Massachusetts

`Not Doing Business in Mass` is an activity description, not proof of formal closure or withdrawal. The exact phrase no longer blocks a confirmed submitted Form PC from the existing fiscal-period calculation. The comment retains the phrase and explains that extension eligibility is inferred. Explicit adverse statuses, ambiguous periods, incomplete retrieval and the existing confirmed-empty-history rule remain protected.

American Farrier's Association Foundation, EIN 87-2999231, AGO 069404: submitted 2024 Form PC ends December 31, 2024. The next period ends December 31, 2025; base deadline May 15, 2026, inferred extended deadline November 15, 2026. Upcoming Filing as of September 13, 2026.

Source: https://masscharities.my.site.com/FilingSearch/s/detail/a094U00001whng9QAA

## Virginia

An exact-EIN entity with a completed empty registration collection and explicit `Not Authorized to Solicit` uses the existing Suspended category. The comment quotes Virginia and discloses that neither a formal suspension order nor its cause was established. An expired/lapsed registration still means Delinquent under the existing rule. Name-only matches and incomplete registration requests do not gain the new override.

Al-Ayn Social Care Foundation, EIN 47-1614315, entity 74671.

Source: https://vdacs.evokeplatform.com/app/publicPortal/entity/74671

## Wisconsin

No generic matching threshold, suffix rule or cross-state alias changes. One documented reviewed identity association binds requested Foundation name and EIN 87-2999231 to credential 23067-800, source ID 945248, and observed state name AMERICAN FARRIERS ASSOCIATION INC. Each lookup must retrieve and confirm the public credential's primary name, credential number and interpretable status. A different requested EIN, source record, credential, name, or unreadable detail does not qualify. Status is read anew, never stored in the identity association.

The public credential does not display an EIN and lists no other names. Identity is therefore explicitly described as inferred from corresponding filing evidence. The user authorized this correction after review of the evidence. The separate American Farrier's Association has EIN 61-1424719; Foundation is not globally discarded.

The Wisconsin 2022 financial filing and Foundation's IRS-derived 2022 figures correspond: revenue $130,869, expenses $9,816 and ending net assets $122,273. The state's current status at review was Voluntary surrender.

Sources:

- https://apps.dfi.wi.gov/ice/berg/Registration/CredSummaryDetails.aspx?chid=945248&h=764579286
- https://apps.dfi.wi.gov/ice/berg/Registration/Financials.aspx?chid=945248&h=764579286
- https://projects.propublica.org/nonprofits/organizations/872999231
- https://cdn.ymaws.com/americanfarriers.org/resource/resmgr/convention_2026/2026_sponsorship_form.pdf

## Verification

New correction tests exercise final master responses, plus negative controls for wrong identity evidence, changed public statuses, explicit adverse statuses, incomplete histories and expired Virginia registrations. Existing Air Force Academy, NMDP, name/alias, all-state, batch, downloadable-data and NY connector suites remain release gates. The first-50 post-validation is a separate fresh 1,500-check run against the approved sheet; expectations are not edited. Detailed immutable attempts and release evidence are kept in the project's `outputs/ma-va-wi-fixes-20260913` directory.
