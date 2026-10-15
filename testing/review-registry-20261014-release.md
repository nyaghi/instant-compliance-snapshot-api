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

Fresh unchanged-EW baselines and candidate live checks are retained separately,
including identity decisions, discovery/execution durations, source limitations,
NC 429 cooldown and deferred recovery. Commit 03ac831 is deployed to the isolated
staging API and all three worker instances. All 31 controls and four reported
organizations completed the eleven-state non-Nevada pass: 381 first-pass checks,
358 exact sheet matches, 23 differences, no missing exports. Four initial NC
omissions were recovered separately after cooldown. Targeted retries and signed
identity decisions retain their own evidence and durations.

The final 03ac831 snapshot, including the separately deferred Loyola NV check,
has 386 checks, 382 conclusive results and 375 exact current-sheet matches. The
eleven remaining differences comprise two pending signed identities, two
conditional MA extension cases, two source-backed TN sheet discrepancies, three
pre-existing UTC/Eastern calendar-boundary differences, Lahey TN retrieval and
Loyola NV retrieval. No expected cells changed. Current Fresh Test was re-read;
seven older names had lossy punctuation in the saved JSON, with no changed status
expectations. The new current-sheet capture preserves the original punctuation.

Lahey TN remains a confirmed retrieval defect: the official completed search
shows exact LAHEY CLINIC INC, CO50375, Expired, expiration 03/31/2025; the final
candidate targeted retry remains Unable to Confirm. Its underlying collector
failure has not been isolated. No speculative Tennessee patch was added.

Only 22 approved controls have the same first-pass selected state set as EW.
Cache conditions were not independently established; nine differed through NC
cooldown omissions. Slow-state evidence is retained for RedRover and Better World;
FL source timeouts for Service Year and SACRED recovered in separate checks.
Performance is not validated. Popup outer bounds remain unverified because the
available browser capture does not show the actual native window borders; the
user will test after the agent session.

## Nevada entity-number candidate — 29.2EY / connector 0.6.130

Nevada was investigated last, as instructed. The live Loyola check still returned
Unable to Confirm after the public source recovered. ORION supplies a blank NV
Business ID but a valid Entity Number for its Foreign Entities Not Required to
Register In Nevada category. The existing collector preserved that row but the
master deliberately would not open it. The official clicked detail confirms the
same entity number, Registered standing, renewal 02/28/2027 and a complete one-row
history: Exemption to Charitable Solicitation Statement filed 02/20/2026.

The isolated recovery binds the observed row, exact entity number, blank Business
ID, supported category, official detail URL and completed same-entity filing
history. Exempt requires an explicit dated exemption, Registered standing and an
unexpired displayed deadline; missing, adverse, future or conflicting evidence
remains inconclusive. No organization-specific runtime exception was added.
Existing populated-Business-ID trial records retain their approved displayed-date
rule and do not acquire a filing-history dependency. Existing deadlines, query
scope, Sales inputs, window placement and unrelated collectors remain unchanged.

The offline builder copies the known working 0.6.129 package and applies only the
new NV deltas, including the private NY protocol copy. It preserves that package's
coordination fixes, punctuation repairs and permissions. The installed extension
is unchanged; 0.6.130 activation requires the user's manual Chrome action because
browser security prohibits controlling chrome://extensions.

Focused new backend tests: eight pass. Source NV DOM: 97 pass. Shared source
connector/lifecycle/NC/identity/window tests: 338 pass. Packaged NV/NC/NY-isolation
tests: 136 pass. Packaged worker suite: 286 pass, one unchanged historical MS
300000-versus-60000 assertion fails. Backend source suite: 151 pass before the
additional conflicting-EIN test, excluding two historical whole-file assertions;
the attempted unfiltered 153 had one historical scope failure and one missing
local psycopg dependency in that historical import. Identity/Sales controls: 51
pass. The 31-organization interpretation replay remains 198 comparisons, zero
changes; it is not live collector regression or speed validation. Counts overlap.

29.2EY (0aeec46) is deployed to the staging API and all three workers. Connector
130 is active. Loyola returns Exempt in 9s after 16s discovery. All 31 approved
NV controls match the re-read current sheet, with complete separate exports.
Thirty match archived EV statuses and identifiers. Solid Rock's EV search did not
start; its current completed search confirms NV20253326287 and agrees with the
sheet. The old trace does not establish which prior change resolved that failure.
Discovery: 10/15/28s min/median/max. NV execution: 7/15/32s. The gray area
is hidden after completion. There is no comparable full-31 EW NV-only timing
baseline, and native popup borders remain unverified. These remain release gates.
The final CO/TN smoke returns CO Suspended as expected and TN Unable to Confirm.

## Tennessee detail-click candidate — 29.2EZ / connector 0.6.131

The final EY Lahey observation shows the completed three-record public search
while the previous foundation detail remains hidden; TN still times out in 31s.
This narrows the problem to detail collection. A dropped click after Kendo closes
the prior modal is a hypothesis, not a proven explanation of that live failure.
The old connector reproduces a dropped-click failure in the DOM fixture.

The candidate repeats the same observed Details action once after 750ms, only
while no modal or public loading indicator has appeared and the complete row,
page, requested name and empty filters remain unchanged. It preserves the
original 25-second detail deadline, all identity/status safeguards and optional
financial-history rules. It never retries a visible wrong record or an observable
pending request. Failure remains inconclusive. New bounded failure codes identify
an action that still did not start. No organization-specific runtime rule.

Only registry-content.js and manifest metadata change in the 131 package, copied
from 130. Worker, protocol, private NY adapter, permissions and window geometry
are byte-identical. Source collector/shared tests: 457 pass. Actual packaged
TN/NV/NC/NY isolation: 158 pass. Focused TN tests: 22 pass. The new ignored-click
controls fail on 130 as retained in the reproduction log. The 31-organization
saved-result replay still has 198 comparisons and zero interpretation changes.
Counts overlap. After the user activated131 and unlocked staging on October15,
the Lahey CO/TN target returned CO Suspended and TN Unable to Confirm in31s
after13s discovery. DETAIL_RETRY_NOT_STARTED proves131 participated and made
its bounded retry, which did not resolve the live target. One separate targeted
retry also remained inconclusive; the hidden prior panel then contained Hospital
rather than Foundation. Both exports and business-only observations are saved.
A manual ordinary close/open on the retained source loaded exact Clinic.
The root cause of successive modal failure remains unproven. No matching or
status rule has been relaxed.130/131 share the staging message channel, so sole
active trial confirmation is pending before further live checks; interference
is a hypothesis, not an observed finding. The restricted Chrome Extensions page
requires user action and must not be inspected through alternate automation.
The user subsequently confirmed131 is the sole enabled trial, ruling out that
setup hypothesis. A later diagnostic retry stopped before opening any TN page
with connector unavailable; preserve it separately from the detail failures.
Full31 live TN controls remain held until the reported target succeeds. Keep
EY/130 available and do not call131 a verified fix.

### Tennessee diagnostic1 — activated, staging trace support prepared

The separate offline package `connector-0.6.131-tn-diagnostic1` retains semantic
version131 for admission to the existing29.2EZ backend and identifies itself by
manifest name/version_name as TN Diagnostic1. The package needs no new backend
version admission. Integration review found two existing staging trace filters
that omit TN, however;29.2FA adds TN to those filters so returned public facts
survive the existing DOM trace and Excel export. No master interpretation change.
It captures at most16 public lifecycle entries per command: elapsed time,
visibility, modal/loading booleans, retry observation and sanitized public
JavaScript error categories. It never collects raw errors, stacks, HTML,
contacts, names, tokens or additional registry data. The error observer is
removed after success or failure and does not cancel or alter page events.
The worker accepts only bounded enumerated entries for the TN trial path and
exports them through the existing bounded trial-diagnostics field. The offline
builder preserves NC diagnostics already in the known working package.

Source files changed for diagnosis: registry-content.js, registry-worker.js and
worker.js; tests run_tn_public_dom.cjs and run_final_four_connector.cjs. No click,
request, matching, classification, deadline, protocol, permission or geometry
changes. Source shared suite460pass; actual packaged DOM/isolation160pass;
actual packaged sanitized diagnostic-export test1pass. Counts overlap. Tests
show one successful normal detail still takes50ms in the fixture with one click,
and an unstarted detail still takes25000ms with at most two clicks; these are
offline assertions, not live speed validation. The user activated Diagnostic1
and unlocked the staging page. The trace-support change passed71 backend/UI
tests, including TN message-to-DOM/export, existing-state controls and the shared
identity/Sales checks. Saved-result replay remains198 comparisons with zero
interpretation changes and11 inherited sheet differences; it does not replay
collectors or validate speed. Paired staging deployment is prepared. The package
has not completed live regression and is not a verified repair. Its originally
recorded build metadata describes package admission only; the later trace-filter
correction requires a staging frontend refresh after deployment.

### Live diagnostic findings and TN Request Guard candidate — October15

29.2FA/31170e0 is live on API dep-db8b8bu89jmc73cti3l0 (1m46s) and worker
dep-db8b8imq1p3s73a8lf20 (1m50s,3/3instances). The user unlocked the refreshed
same staging tab. The first actual Lahey CO/TN run returned Suspended/Delinquent
in15s after14s discovery, selecting exact ClinicCO50375 with expiration03/31/2025.
Its first attempted submit had been blocked by an unchecked first-run diagnostic
acknowledgement; an empty UI capture is retained but is not a completed run.
The acknowledgement was completed and the same discovery reused. A retained
session repeat returned TN UTC32s after cached0s discovery. A later TN-only run
returned Delinquent14s, also with cached discovery. The repair is not repeatable.
All completed first-pass/repeat exports are retained separately. The current
Fresh Test was re-read: all31 approved TN names/EINs/expectations are unchanged.
Only the first approved control was started before the failed repeat was read;
National Parks Traveler returned Not Registered8s after14s discovery. The other
30TN controls are held, not passed. Native window borders remain unverified.

The active public source has no main_screen element. Its published Details
handler calls kendo.ui.progress on that absent target, so a real request can
have no observable loading mask. The750ms retry guard therefore cannot prove
the initial request never started. An independent slow-request fixture without
a mask makes Diagnostic1 click twice; the new guard clicks once. This establishes
an unsafe retry mechanism, not proof that it caused every historical130 failure.

The integrated registry-tn-main.js helper passively observes native public XHR
for exactly the selected row's public numeric grid ID and the known Details
endpoint. It reports ready/start/end/HTTPstatus only. No request is initiated,
replayed, modified or read; no headers, body, response, widgetConfig, credentials
or verification data are collected. This is a connector access component like
the existing public MS observer, not a standalone state check or sidecar. The
master continues to own identity, aliases, selection and classification. The
technical reason for the MAIN-world helper is that the isolated DOM collector
cannot observe the page's in-flight native XHR through a nonexistent DOM mask.

An observed pending request forbids a second click. A successful bound response
must finish before its exact detail fields can complete. If the observer is
unavailable, the ordinary single-click path remains available and a speculative
retry is disabled; it is not a new required helper dependency. The original
25-second detail deadline and the overall Sales/Standard deadline remain.
Tests also prevent a new click after observer readiness consumes the deadline.

The separate connector-0.6.131-tn-request-guard package retains semantic version
131 for existing admission, with explicit TN Request Guard name/version_name.
It preserves permissions, prior scripts and window geometry and adds only the
TN document-start MAIN observer. It does not overwrite any installed package.
Source focused36pass; shared472pass; actual packaged172pass plus packaged
diagnostic-export1pass. Counts overlap. The old Diagnostic1 slow-request control
fails as expected with2clicks instead of1. No master/backend interpretation delta
or new server deployment is required for this connector candidate. Activation,
fresh target/repeat checks, full31TN controls, speed and popup gates remain pending.

Production is untouched. Recommendation: do not promote while TN, identity,
calendar-policy, comparable performance and native popup-placement gates remain.

Retain six documented exclusions in the shared runner and the packaged connector's
pre-existing MS 300-second-versus-60-second historical assertion. Imported SC
historical assertions also fail on unchanged EW; they are not passing tests.
Do not adjust these runtime rules merely to satisfy obsolete whole-file assertions.

### 29.2FB Tennessee source-rate protection

The activated Request Guard established a specific new cause on Lahey's saved
31-second CO/TN run: Foundation detail returned HTTP200 after485ms; Hospital
detail returned HTTP429 after65ms. No second click occurred. This proves source
throttling for that run, not every earlier timeout. The run and export are saved
as candidate6-lahey-co-tn-first. TN probes stopped after that response.

The separate TN Paced package adds the connector's existing three-second pacing
interval between TN commands and persists timing-only cooldown across service
worker restarts. It honors a numeric or HTTP-date Retry-After on429; otherwise
five minutes is an operational starting cooldown, not a claimed registry limit.
New TN workflows fail fast during cooldown without navigating or submitting.
Other lanes remain independent; existing command/overall deadlines stay fixed.
The bound detail observer now reads only that one public timing header on429,
emitting only its parsed numeric interval. It still never reads response/body
content, credentials, widgetConfig or other headers. The master adds an explicit
source-cooldown explanation while retaining Unable to Confirm and no identity
or negative conclusion. No matching/status interpretation function changed.

Source shared479pass; actual package174pass and six worker controls pass;
backend72pass. Counts overlap. Current-sheet saved-evidence replay covers31orgs
and198comparisons: zero interpretation changes,11 inherited sheet differences.
Replay does not exercise collectors or establish live speed. The original
Request Guard package is untouched; TN Paced changes no permissions or layout.
Activation, repeated Lahey checks, full31TN live controls and speed remain pending.

### 29.2FC exact-first retrieval and bounded checkbox attempt

User requested three investigations: strongest-match-first detail order, an
ordinary action on the verification checkbox, and a last-ten-version regression
audit. Master prioritized_registry_candidates uses existing decision confidence,
exact EIN, exact entered legal name and score, with stable source-order ties.
Tennessee uses it after complete search validation. No candidate is accepted or
omitted by ranking; all qualifying credentials still reach existing selection.
No identity threshold, newer-credential rule, state status or deadline changes.

The current public TN page embeds Cloudflare Turnstile despite legacy recaptcha
container names. The separate132 connector adds one challenge-platform subframe
content script. Effective script access expands to that Cloudflare path; the
permissions/host_permissions arrays stay identical. Its ancestor must be TN and
the worker must authorize the active, owned TN readiness window. Only one visible,
enabled, unchecked, unambiguous checkbox may receive an ordinary click per job.
The used attempt is persisted before granting it. A changed/hidden control is
not clicked. No verification value, token, cookie, challenge callback or raw frame
HTML is read or transmitted. Only actual registry form readiness counts as
completion, within the existing deadline. A failed attempt remains inconclusive.
This integrated access helper is not a state checker or sidecar; master ownership
is unchanged. The approved connector manifest remains disabled for TN.

History audit covers ten distinct releases ES,ET,EU,EV,EW,EX,EY,EZ,FA,FB and actual
connector packages122through131. Sixteen common DOM contracts pass in each package
(saved fixtures, not live runs). TN search/detail function bodies are identical
through130. No automatic checkbox action existed in these versions. Same three
Lahey rows qualify across all ten master versions; institutional safeguards
changed their reason labels but did not add candidates. The original failure
therefore has no established breaking commit from this comparison. Saved EW
Lahey was Delinquent20s; later runs alternate success, detail failures,429 and
verification. EZ's750ms unobserved retry was a separate introduced risk, corrected
by Request Guard. It cannot explain failures that preceded EZ. Duo-mode closes
TN pages on completion in all ten packages, so recent repeats were new registry
documents, not proof of retained-session behavior. Earlier repeat labels mean
repeated checks in the same CE Chrome session; the diagnostic trace shows no
tn-session-reuse on those runs.

FB live: Lahey CO/TN first23s and repeat23s returned exact ClinicCO50375 Delinquent;
third46s returned TN verification pending. User directly observed its unchecked
human-verification box. Separate targeted retry returned Delinquent without
manual checkbox interaction. All first-pass and retry exports are preserved.
The repeated23s is slower than successful FA15s/14s, consistent with added pacing;
different source/session conditions prevent a comparable performance pass.

FC source shared556pass; actual package251pass plus six focused worker controls;
backend77pass. Counts overlap.31org/198saved-result replay: zero interpretation
changes and11 inherited sheet differences. New ranking/checkbox paths require
live target, full31TN controls, timing and actual native placement verification.
Checkbox support is an attempted ordinary interaction, not a claim that
Cloudflare has accepted it live. Recommendation remains do not promote.

Do not promote until affected-state live regression, comparable speed and actual
popup outer-bound placement are validated. Staging requires a paired API/worker
deployment and matching connector. Any deployment must name the actual target;
the user-designated Performance Lab staging origin and old staging domain remain
separate. Production still requires explicit user authorization.
# October 15 TN Smart live controls and verification trace

29.2FC/b9782de with manually enabled TN Smart 0.6.132 completed all 31 approved
organizations, CO and TN, in the existing Compliance Express staging tab.
All 62 first-pass checks and exports are preserved. Raw status comparison is
58/62: William & Mary's signed Foundation choice was separately rejected,
producing the expected completed-search negative; Rezilient Kidz and Stand for
the Silent have source-supported expiration-date differences from the sheet;
CASAA stopped at verification in both the first pass and one targeted retry.
No expectation cells were edited. No checkbox permission/action was recorded
for CASAA. Thus live checkbox success remains unproven; this is not a passed
verification fix. Lahey returned exact Clinic Delinquent in three smart runs
(29/24/22 seconds); its exact Clinic modal was visibly first in both observed
repeats. These were fresh TN documents in the same browser session.

Colorado's Stand for the Silent result initially looked like an identity-label
defect. A subsequent fresh exact-EIN search in the state's public browser page
itself displays Name SAVING MOSES with EIN 45-2317929, registration20213014216,
Stand for the Silent's Perkins address/website and the same filing dates. The
official exact-EIN dataset names that same registration STAND FOR THE SILENT.
The earlier product-bug classification is superseded by a source-name
inconsistency. The observation does not establish a wrong-entity selection or
a regression. Both source records and a screenshot are retained in
colorado-source-name-reconciliation.json and its referenced evidence. No source
name was hard-coded or expectation changed to conceal the conflict.

The separate `connector-0.6.132-tn-verification-trace` package adds bounded
count/boolean-only challenge-frame observations and parent readiness transitions
to distinguish absent frame-script evidence from no actionable ordinary checkbox.
No token, cookie, challenge content, URL or response is read. Permission and
one-click authorization rules, manifest access, geometry, state interpretation,
pacing and deadlines are unchanged. The user has now enabled the trace package.
CASAA returned Delinquent67s; three Lahey checks returned Delinquent23/21/33s.
All four gates enabled Search automatically, with frame-observed controls0 and
no actionable checkbox. This confirms frame-helper injection on those documents,
not success on a required checkbox. Full31 live trace controls are now complete:
62 CO/TN first passes,58 raw sheet-status matches,31 exports with matching UI
workflow boundaries. The signed William & Mary rejection and two expiration-date
differences are retained separately. Society for Scholarly Publishing47s stalled
at verification; its helper loaded, reported controls0, and never observed form
readiness. Its single targeted retry auto-recovered to Delinquent. No screenshot
was captured from the failed document before it closed; do not claim a checkbox
was visibly present there. Thirty other first passes auto-verified. No checkbox
click occurred, so live checkbox completion is still unverified. The last ten
versions contained no removed checkbox handler; an original breaking commit
remains unproven. Current trace execution median16s vs prior Smart17s, with
different cache/source conditions; original pre-pacing speed is not validated.
Fresh62 sheet cells were re-read after controls: no expectation changes. Saved
export statuses and workflow boundaries match31/31 original first-pass captures.
Latest evidence: tn-verification-trace-validation-report.txt and
candidate10-live-reconciliation.json. No new server deployment. Production
untouched; do not promote. Keep the current trace build for a captured visible
required-checkbox case; another installation is not needed.
Source suite 558/558 and packaged suite 253/253 pass, including adversarial
foreign-frame, no-control, ambiguity and exhausted-deadline controls. Test logs
are saved; a terminal summary print had a Windows encoding error after both test
logs were written, and their zero-failure totals were then verified from disk.

The final gray rail was display:none after results. Native outer window bounds,
comparable baseline speed and live checkbox behavior remain release gates.
Production untouched. Do not promote.

