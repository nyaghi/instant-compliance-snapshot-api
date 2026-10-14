# 29.2EX candidate: identity confirmation and filing evidence

This candidate starts from staging EW (`3c576dd`). Production is outside its
scope. Reported organization identifiers occur only in tests and fixture
provenance, never in runtime exceptions. No spreadsheet expectation was edited.

## Changes and reproduced mechanisms

- Public legacy review results use `Unable to Confirm`; a specific pending
  signed candidate displays `Confirm match` with the existing identity controls.
  Screen and Excel labels agree. Acceptance establishes identity only; the
  existing master state interpretation determines status. An incomplete search
  cannot become a negative through rejection.
- Discovery exposes organization addresses already retrieved for the exact EIN,
  retaining available source dates and historical context. Registered-agent and
  foreign-EIN records are excluded. It adds no source request or Sales dependency.
- A shared institutional-name guard prevents a hospital or institutional
  foundation from becoming the entered clinic solely through a name prefix or
  shared city. Exact EINs and authorized full aliases retain their positive paths.
  Arkansas, Mississippi and North Dakota retain sufficiently plausible specific
  records for signed confirmation instead of ending in an unactionable bucket.
- Kentucky's ambiguous legal/DBA rows receive exclusive signed choices. The
  selected row is rechecked in the current snapshot using the ordinary filing
  period rules; the user's choice supplies no filing date or status.
- North Carolina accepts the observed numberless `Charitable Organization` /
  `In-Process` card as Pending. A numberless `In-Process` / `Denied` card remains
  an unissued denied application. Existing issued-license denial behavior stays.
- Massachusetts can index a FY2020 paper Form PC under FY2022 while also
  supplying a valid submitted FY2022 electronic form. Previously the paper
  label/year mismatch discarded the newer usable evidence. Only when reconciling
  an already verified electronic form may an exact-EIN, same-AGO paper form's
  actual earlier period enter the existing distinct-period comparison. Unreadable,
  conflicting, overlapping, duplicate or unexpectedly newer periods stay guarded.
- Hawaii can host a group Form 990 under a subordinate's state filing. The old
  reader cannot find that subordinate EIN in the main header. Recovery requires
  an explicit Form 990 Item H included-subordinate list naming the requested EIN
  and the same unique group-return EIN shown on the header, within the identical
  downloaded PDF. A second bundled return cannot inherit membership or dates.
  The ordinary period reader still reads that header; a missing fiscal period
  retains the existing disclosed calendar assumption rather than an invented date.

The original MA popup wait and HI transport retry behavior are preserved. No new
runtime deadline, alias-discovery dependency, browser-window coordination, or
Sales input/deadline rule is introduced. The existing connector package is copied
from 0.6.128 with only the NC parser and version metadata changed for 0.6.129.

## Source fixtures

`fixtures/review-registry-period-sources.json` records public source URLs,
identities, dates, observations and SHA256 hashes for the unchanged MA TIFF and
HI PDF. The HI included-subordinate interpretation follows the IRS 2024 Form 990
instructions, Item H: https://www.irs.gov/pub/irs-prior/i990--2024.pdf .

The real fixtures are supplemented with independent organizations and adverse
controls for conflicting EINs/accounts, excluded or absent group members,
different filing years, bundled returns, incomplete searches and identity choices.

## Validation and release limits

The first EX live Lahey pass and its targeted MS retry exposed a collection-order
gap: a possible row was saved, later name variants replaced the browser's grid,
and the eventual detail request failed the collector's current-grid safeguard.
Read and validate the bounded candidate details while their originating grid is
current, then retain those source fields while completing the remaining search
plan. The existing ten-record bound, signed choices, incomplete-search guards,
source-derived status and connector deadlines remain. No connector update beyond
0.6.129 is needed. Independent multi-variant and overflow controls model this
failure; a later incomplete search cannot become a negative.

The supplemental MS/control suite passes 120 checks after excluding four
independently reproduced prior-EX assertions: two obsolete public Needs Review
expectations, a historical whole-file scope assertion, and an existing optional
NV filing assertion. Their original failures are retained in the evidence logs.
The full attempted suite was 124 checks with those four failures; do not describe
it as fully passing. Prior live first passes remain saved when the revised
backend is deployed; do not overwrite them or mix their timings.

Commands (from this repository):

```text
node --test testing/run_nc_public_dom.cjs testing/run_identity_review.cjs testing/run_user_match_controls.cjs testing/run_final_four_connector.cjs
python -B testing/run_surgical_discovery_nc_controls.py
python -B -m unittest testing.test_hi_group_return_period testing.test_ma_indexed_scan_period testing.test_review_registry_20261014 testing.run_ky_hi_completion_guardrails testing.run_ma_form_pc_guardrails testing.run_user_match_decisions testing.test_ky_nv_review_choices testing.run_nd_inactive_consensus_guardrails testing.test_separator_entity_scope testing.run_sales_supplied_identity.SuppliedIdentityTests testing.run_fresh40_guardrails.MassachusettsPeriodTests
python -B testing/replay_review_registry_controls.py
git diff --check
```

Use the isolated Python 3.12 evidence environment with the repository's existing
OCR pins for the actual TIFF test. Cold OCR initialization has a documented local
fixture timeout; warmed tests do not establish cold live speed.

The saved-result replay covers all 31 approved organizations and 198 comparisons
without baseline-to-candidate changes. It does not replay changed collectors or
establish live speed. Eleven current-sheet differences also occur on EW.

Fresh unchanged-EW baselines and candidate live checks must be retained separately,
including identity decisions, discovery/execution durations, source limitations,
NC 429 cooldown and deferred recovery. At this candidate checkpoint the live
31-organization work is still in progress. Nevada is deferred by user instruction
until the other work is done. Its blank page and original missing-detail cause
remain unresolved; no speculative Nevada or Tennessee rule was added.

Retain six documented exclusions in the shared runner and the packaged connector's
pre-existing MS 300-second-versus-60-second historical assertion. Imported SC
historical assertions also fail on unchanged EW; they are not passing tests.
Do not adjust these runtime rules merely to satisfy obsolete whole-file assertions.

Do not promote until affected-state live regression, comparable speed and actual
popup outer-bound placement are validated. Staging requires a paired API/worker
deployment and matching connector. Any deployment must name the actual target;
the user-designated Performance Lab staging origin and old staging domain remain
separate. Production still requires explicit user authorization.
