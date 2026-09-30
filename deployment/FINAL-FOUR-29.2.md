# Final four states: isolated 29.2 trial

## Authorization and baseline

The user approved preparation and activation of a temporary matching trial on
September 29, 2026, expecting no more than five days at approximately $16/day.
Use a conservative maximum of $80 total and 120 hours from the first paid
resource activation, whichever comes first. Do not extend either limit without
new authorization. Develop and run local controls before activating resources.
Estimated four-worker and queue-database compute is about $12/day, excluding
applicable ancillary charges. Track those charges against the same $80 cap.

Approved staging is 2026.09.29.1. Its source baseline is tag
`approved-2026.09.29.1` (05d6af3); the deployed runtime commit is e73988d.
Staging currently sends execution to the existing performance-lab pool. That
pool is part of the protected baseline, despite its historical lab name.

## Isolation

- Keep both staging APIs, the staging frontend, the existing four workers,
  their configuration, and the existing queue database unchanged.
- Use branch `performance-final-four-20260929` and a distinct 29.2 origin,
  private access key, service IDs and queue database.
- Keep all state implementations inside the master backend. Deployment
  wrappers own infrastructure only; no runtime state sidecars.
- Prepare an allowlisted teardown command and timed shutdown before activation.
  Export validation evidence before deleting the temporary queue. Cleanup must
  target only resource IDs created and recorded for this trial.
- Do not claim that a stopped application also stops database/storage billing.
  Verify retirement of every temporary paid resource.

## Scope and validation

Add Alabama, North Carolina, Nevada and Tennessee using the current master
name, alias, identity, status, timeout and comment protections. Preserve original
registration and renewal/last-filed evidence only when explicitly supported by
the source; unavailable date fields remain blank.

For each new state verify a positive, a completed no-record search, ambiguous
identities, punctuation/alias variants, unavailable/incomplete responses, and
date/status interpretation. Human verification must never yield Not Registered.
Corporate and charitable-solicitation evidence must be labeled accurately; see
the explicit Nevada interpretation below.

Run the mature-state regression controls and compare the same organizations
under the old 34-state scope and new 38-state scope, in Standard and Sales.
Report discovery timing separately from state execution, first-attempt
conclusiveness, source limitations, and all categorized spreadsheet differences.
Refresh the approved spreadsheet and never alter its expected results.

## Source investigation in progress

- AL: official Attorney General iGov public lookup requires a verification code;
  a supported export or data-access route has not yet been established.
- NC: the user confirmed there is no subscription and explicitly requested the
  ordinary public-page connector on September 29. Use observed public form,
  result-card, profile and filing-history navigation. No private endpoint or
  verification bypass. The source notice about automated/bulk searches remains
  a source-access consideration; this user instruction is not state permission.
- NV: official site now links to the ORION public registry. Use the matched
  nonprofit-corporation status under the user-confirmed interpretation below.
- TN: production TNCaB public search exists; the old expansion placeholder used
  a test domain. The live form requires human verification before searching.

No new state is considered integrated merely because it appears in a selector.
Do not activate paid trial resources while source access prevents a meaningful
validation run.

## Candidate integration and safeguards (September 29)

- Master source parsers, bounded reviewed-name plans, identity scoring and
  signed continuation are implemented locally for AL/NC/NV/TN. Explicit source
  extensions and exemptions are preserved; optional filing-history failures do
  not invalidate a complete core record, but the missing date stays blank.
- Alabama's broad type-only request returned a source error. Name searches on
  the same human-verified page succeeded, including the national/local YWCA
  control and a completed synthetic no-record control. No working bulk export
  has been established. The trial connector retains only its own Alabama tab
  for up to 30 idle minutes; every query requires a fresh observed response.
  It does not solve, copy, store or transmit CAPTCHA codes. A fresh challenge
  requires human completion. Do not describe this as unattended access yet.
- North Carolina's YWCA national record is EX003050, explicitly CSL Exempt;
  its absent expiration is a legitimate blank. America's Charities has an
  explicit extension through November 15, 2026 and a separately labeled last
  renewal filing of November 17, 2025. These are fixture controls, never rules
  keyed to an organization or EIN.
- Trial UI assembly derives from the approved frontend and adds all four
  selectors. The approved frontend files and installed 0.5.10 connector are
  unchanged. A separate 0.6.4 trial package uses only the trial origin, public
  registry permissions and session storage; it has no production/staging page
  permission, NY page injection, cookie access or browsing-data permission.
  New York continues on the isolated worker backend. Its ordinary 29.1 browser
  connector remains separate. Trial DOM channels are namespaced.
- The existing connector has one serial active lane. The trial reserves one
  actual browser slot, leaving 14 Standard or 19 Sales internal state slots.
  Reserving six slots for six queued sources would waste capacity; it is not
  used. Whether the six browser sources finish quickly enough is a live-test
  question, not an assertion from unit tests. No Sales deadline extension.
- Child workers retain validated trial identity and the existing performance
  paths after database/control-plane credentials are stripped. The parent must
  validate the resource manifest before producing a secret-free child context.
- Local regression: 302 Python and 198 JavaScript checks passed before the
  final child-context change; its 19 focused isolation/UI checks also passed.
  Live connector activation, deployed smoke, refreshed-sheet post-validation,
  and measured 34-vs-38-state performance remain outstanding.

## Live trial checkpoint (September 29, 20:48 UTC)

- Separate Render API, three background processes and queue database are live;
  four healthy queue workers were confirmed after rolling deployment settled.
  The manifest records only the new resource IDs. A local retirement guard and
  hourly backup enforce retirement by 118 hours or the $80 spending cap.
- Read-only comparison of all six protected service configurations found no
  changes to staging, production or the older performance pool used by staging.
- The first trial connector rejected a search after acquisition because a
  message without repeated intent defaulted to NY. The admission now retains
  its registry, and reconnect checks the saved job's registry authorization.
  Controls cover all six browser sources and refuse registry switching.
- Tennessee's Rocky Mountain Elk control matched CO3674 and Missoula, MT,
  returned Upcoming Filing and both available date fields in 9.6 seconds.
- Alabama's YWCA control used five freshly discovered aliases (21.0 seconds),
  matched the national Washington, DC record AL97-431 instead of the Birmingham
  chapter, and returned Upcoming Filing in 2.8 seconds. A human completed the
  currently displayed verification first; this is not proof of unattended access.
- Mature Colorado controls returned Current for Make-A-Wish and Not Registered
  for Junior Achievement USA, as expected. Their wall times were 6.6 and 100.7
  seconds; the negative used two source attempts. Do not infer overall run speed
  from the faster positive control.
- NC and NV initial live attempts remained inconclusive. The next candidate
  distinguishes a loaded verification/shell document from a ready registry form,
  without bypassing human verification or widening source deadlines. Its live
  validation is outstanding. Specific failure comments and elapsed times are
  preserved through master response formatting.
- Latest local controls: 313 JavaScript checks and 34 focused Python checks pass.
  One old NY test still expected a 30-second verification cutoff; approved 29.1
  already used 45 seconds. Only that test's boundary cases were corrected. The
  NY runtime and its separate 30-second search-response cutoff were unchanged.
- Full first-30 spreadsheet post-validation and paired performance remain open.
  Do not promote this trial based on these partial controls.

### Follow-up controls

- Make-A-Wish passed Alabama with fresh discovery but Tennessee repeated an
  incomplete response in 38.4 seconds. Live observation showed its correct
  national record CO1629 opened, followed by a broader reviewed-alias search.
  The candidate now awaits Kendo's asynchronous modal close before submitting
  the next query and retains specific TN failure stages. This is a candidate
  transport correction, not yet a verified resolution of the live failure.
- 339 connector JavaScript tests pass, including all four new public collectors,
  NY/IL/GA behavior, routing and reconnect isolation. A broader indiscriminate
  run of historical UI scripts also exposed two older harness failures (20.6
  production overlay expectation and a missing window mock in registration-date
  UI tests). Those untouched frontend/runtime files were not changed to satisfy
  obsolete harness assumptions; this broader run is not reported as passing.
- Connector 0.6.2 live repeat completed Make-A-Wish Tennessee in 25.5 seconds
  with all six reviewed aliases, matching CO1629. NC reached the profile but
  rejected its address: the descendant selector included the outer "Address"
  label along with four nested values. The 0.6.3 candidate scopes those values
  to the nested block. Nevada's ready check now also waits for its search-type
  dropdown to populate, matching the collector's existing form requirements.
  These last two changes still require live verification. 341 connector tests
  and 97 four-state Python controls pass, including unchanged mature logic ASTs.

### Live 0.6.3 follow-up and 0.6.4 candidate

- NC Make-A-Wish completed in 26.8 seconds and used its March 15, 2027 extension
  rather than the January 15 base expiration. Its missing renewal date exposed
  an attachment-link span in a filing row; the collector now excludes link spans
  while still requiring exactly one valid date for every filing entry.
- Nevada reached both matching national corporate records, but its return from
  the first detail mounted search inputs before the search-type dropdown. The
  candidate applies the initial form-readiness check on that return path too.
  Tests cover two matching records, delayed dropdowns and deadline expiry; source
  parse errors now retain their specific failure stage.
- NC Junior Achievement's negative control twice stopped on a later generated
  fallback, with the query filled but Search still idle. The collector previously
  acknowledged submission before its zero-delay click timer ran. The candidate
  dispatches that ordinary click synchronously and tests with background timers
  suspended. This remains a hypothesis pending the live 0.6.4 repeat.
- These changes are trial collectors only. Local controls are passing; full live
  validation remains open, and no promotion is recommended yet. The existing
  32-backend-state regression is running separately without a deployment mid-run.

### Existing-state regression finding: NJ blank-number exemption

- The first 16 organizations completed 512 backend checks, with 508 spreadsheet
  matches, three proposed source/sheet differences and one inconclusive result.
  Differences are Reading Is Fundamental FL (Current), Earthjustice MI (Pending),
  Year Up RI (Current), and Young Life NJ (Unable to Verify). Expectations remain
  unchanged. This count excludes all six browser states and is not final acceptance.
- Young Life NJ repeated the same failure individually. Its public EIN search
  visibly shows one Exempt row, matching EIN and Colorado Springs address, with
  no NJ registration number. Both existing acquisition paths rejected the blank
  number. The narrow candidate accepts only a complete, unique, exact-EIN row
  with explicit Exempt status and blank number, using the existing interpreter.
- Six new controls cover the exception and reject wrong EIN, other statuses,
  malformed/duplicate/partial/error responses and unbound browser queries. 119
  Python controls pass, including existing NJ positive, negative, timeout and
  fallback behavior plus final-four/isolation tests. The AST audit normalizes
  only the two exact NJ acquisition additions and independently tested helper;
  all other mature matching/status/timing remains compared with approved 29.1.
- This correction is trial-only pending live Young Life and prior NJ controls.
  No approved staging or production files/targets were changed.

### Live exemption control and interim regression follow-up

- All 16 NJ controls passed on f3708e4, including Young Life returning Exempt
  in 6.52 seconds. The original failed 32-state run is retained separately.
- Focus on the Family subsequently repeated two conservative outcomes. Its NJ
  EIN search shows zero records, while the name search shows an Exempt record
  with both EIN and registration number blank. Its 8605 Explorer Drive address
  agrees with same-EIN CA/CO records. That case is outside the exact-EIN exception
  and remains open for identity review, rather than broadening the correction.
- Mississippi shows the longer name "Focus on the Family, a California nonprofit
  religious corporation", Current - Exempted, file 100002691. Its address is 8655
  Explorer Drive; same-EIN CA/CO records show 8605. The current name matcher
  conservatively returns Needs Review. No broad descriptor-stripping change or
  spreadsheet correction has been made. Remaining independent controls continue.
- The isolated validation form now reports the active connector version using
  its existing, origin-bound ping. It sends no credentials or registry query for
  this diagnostic and does not reload an extension. This avoids inferring an
  active version from the installed files alone. The approved frontend is unchanged.
- Compatibility review found that Illinois's existing one-time fresh-page
  recovery accepted only version 0.5.10. The separate 0.6.4 package contains that
  same recovery capability, but the backend version gate would disable it in
  the trial. A failing control demonstrated the omission. The trial-only gate
  now admits 0.6.4 while preserving the original deadline, evidence, one-retry
  limit, query binding and approved-environment behavior. This backend change
  requires no additional connector version or extension reload.

### 0.6.4 live controls and 0.6.5 candidate

- The active 0.6.4 connector completed 15 controls (five organizations across
  NC/NV/TN). All five TN results were conclusive. NC Make-A-Wish and Reading Is
  Fundamental were conclusive and both populated their renewal filing dates.
  NC Junior Achievement and Prevent Child Abuse still timed out; the earlier
  synchronous-click change did not establish a fix. RMHC hit a duplicate-name
  parser guard. All five NV controls failed with SEARCH_NOT_STARTED. Original
  results are preserved; none are replaced by later retries.
- Source inspection confirmed that some NC cards carry multiple legal names
  and DBAs under one license. The candidate retains these as source aliases,
  binds the display name to the card header and license, and lets the master
  compare all aliases. Duplicate scalar statuses, licenses and dates remain
  errors. Profiles still require the same public URL and license and a name
  explicitly observed on that card. No shared matching rule was relaxed.
- ORION replaces its Search button following filter edits and restores prior
  results when returning from a detail. The candidate waits for the edited
  form/button to settle within the original deadline. It opens subsequent
  records from the restored result set only after checking the original query,
  every identifier/name/type/status and the complete result count. Fresh
  searches, including negatives, still require an observed loading cycle.
  This correction remains a candidate until its installed version passes live
  checks; it is not yet proven to resolve all five NV failures.
- Failure traces now retain completed and pending public queries, without
  credentials, device identity, source pages or signed continuation tokens.
  The trial accepts 0.6.4 and 0.6.5 during activation; 29.1 access remains
  unchanged. 0.6.5 is the next package to validate.

## Confirmed date interpretation

### 0.6.5 live follow-up and 0.6.6 candidate

- Ten targeted 0.6.5 checks completed: TN Junior Achievement remained Not
  Registered, NC Reading Is Fundamental remained Current, and NC Prevent Child
  Abuse completed as Upcoming Filing using its extension date. Seven results
  remained inconclusive. These originals are retained separately from retries.
- NV Make-A-Wish now completed its search and both national details. Its next
  alias search timed out because ORION changes the hash within the same document
  while the worker required a new document ID. A corrected Chrome navigation
  fixture reproduces that failure. The NV-only correction still waits for the
  rendered search form, bound filters and a fresh response loading cycle.
- Four other NV first searches failed before completion. A separately observed
  Reading Is Fundamental repeat completed its search/detail, then reached the
  same hash-navigation defect. Initial ORION inputs are visible while its loader
  is active; the candidate now waits for that loader to finish before editing
  the form. This readiness correction still requires live confirmation.
- NC's RMHC fallback exposed EX011792 labeled Charitable Organization. The
  public Junior search also showed SL007110 labeled CSL Exempt Organization.
  The state parser incorrectly derived record category from the identifier
  prefix. The candidate validates both supported prefixes and both explicit
  charity categories independently; adverse status and identity checks remain.
- NC Junior Achievement still stalled at the broad Junior fallback. Manual
  search completed with 30 rows, including two In-Process cards without license
  numbers. A later initial navigation remained on the source's visible security
  verification page with no interactive control. This source condition is now
  reported distinctly; no verification is solved or bypassed. The earlier form
  submission timeout remains unresolved. Public inspection also confirmed
  In-Process cards have legal/DBA names and profile links but no issued license.
  The candidate preserves those cards for master name filtering: unrelated
  applications do not spoil a complete negative, while a matching application
  without a confirmed license produces Needs Review, never Not Registered.
- Reading Is Fundamental NV exposes both a Withdrawn nonprofit corporation and
  a Registered record labeled Foreign Entities Not Required to Register In
  Nevada. That second category is outside the approved corporation mapping.
  A matching unsupported category now prevents an inactive-only conclusion;
  it remains a scope review rather than a guessed registration status.
- No approved staging, production or other-state timeout behavior was changed.

The user confirmed on September 29 that a displayed extension end date is the
deadline to use instead of the original expiration date. The source does not
need to repeat "extension" in its status label. Preserve both dates as evidence
and explain the extension in comments. Explicit adverse registry statuses still
take priority. Expiration and extension deadlines are not last-renewal dates.

## Confirmed Nevada interpretation

### 0.6.6 live controls and 0.6.7 candidate

- Ten 0.6.6 checks completed with three conclusive results: Junior Achievement
  TN Not Registered, RMHC NC Exempt, and Reading Is Fundamental NC Current.
  Seven remained inconclusive; all initial results are retained separately.
- The Nevada first-search failure still occurs before completed search evidence.
  A controlled fixture reproduces the same generic timeout when unrelated DOM
  animation repeatedly resets the Search button's 200 ms settling clock. The
  candidate retains the settling candidate only while it is the identical
  button with the same bound input values. Replaced buttons and changed filters
  reset it; the original three-second budget and fresh-response requirement stay.
  This is a local reproduction and candidate, not yet live proof.
- Junior Achievement NV completed its first three searches, then failed on the
  broad Junior result set. Manual inspection of all five pages showed 103 rows,
  including NR20230725-22746 with a blank entity type. Preserve that public row
  for master identity filtering. A matching NR row remains an unsupported-scope
  review and can never be opened or classified as an issued corporation. Unknown
  identifiers and blank types for ordinary NV business IDs remain errors.
- An isolated NC Junior diagnostic advanced after an ordinary manual Search
  click, then exposed a separate source count inconsistency: Records Found 30,
  but 31 rendered cards. Issued and In-Process records appear for the same legal
  name, with different public profile IDs. Do not guess the state's counting
  semantics or accept an incomplete negative. The error comment now describes
  the result-count conflict. The manually assisted repeat is not a successful
  normal-run control. The candidate also requires document completion before
  invoking NC's inline form action; its effect on the earlier stall is unproven.
- Some separate manual source inspection occurred during the ten-case run;
  performance acceptance must use a subsequent run without such interactions.
  Approved staging, production, budgets and other-state default behavior remain
  unchanged. Complete the remaining live controls and performance checks before
  proposing promotion.

On September 29 the user directed Nevada to use the matching nonprofit
corporation's displayed status and Annual Renewal Due Date/Expiration Date.
Exclude registered-agent records and do not use registered-agent addresses as
organization addresses. Evaluate matching duplicate nonprofit records through
the master selector. Comments identify this as nonprofit-corporation standing
and preserve any separate solicitation flag; do not imply a CSRS/CSRX filing has
been verified when it has not. Formation is not a last renewal, and the annual
due date is not a last-filed date.

### 0.6.7 live controls and 0.6.8 bounded Nevada recovery

The six-case 0.6.7 control produced four unattended Nevada SEARCH_NOT_STARTED results on the first query. North Carolina Prevent Child Abuse completed as Upcoming Filing in 16.451 seconds. Observing the RMHC Nevada page did not resolve its stalled search, so visibility is not established as the cause. For the final Nevada diagnostic, an ordinary manual Search click started the stalled query and the collector then advanced through its aliases. Its final unsupported-category review remains unresolved; that assisted run is not a passing unattended control. Raw results and the assistance note are retained in the validation output.

Candidate 0.6.8 retries the current Nevada Search once after three seconds only if no loading cycle has been observed. It rechecks the bound name, blank identifier filters, Starts With mode and current visible enabled button. It never retries a pending source response, extends the existing command deadline or treats a blank initial grid as a negative. This is an evidence-based recovery for a missed first submission; the source application's internal cause is not proven. Other state collectors and all status/identity rules remain unchanged. Live validation is still required.

### Nevada charitable-solicitation-only records, September 29

Random-sample source inspection found that `Foreign Entities Not Required to
Register In Nevada` can have actual Charitable Solicitation Registration
Statements. The earlier type whitelist stopped before inspecting that history.
The master now opens this precise category, but cannot classify it until the
complete, query-bound filing history contains an explicitly dated statement and
the record displays its renewal deadline. Annual Lists, Foreign Qualifications,
exemption declarations and blank histories do not establish this category's
charity scope. Registered-agent records remain excluded. Existing nonprofit
corporation interpretation is unchanged.

The original registration date is shown only when the earliest explicit
statement date agrees with the record's formation date. The latest statement
submission is labeled separately from the displayed renewal deadline. An
inconsistent solicitation Boolean is preserved and explained in comments;
explicit adverse statuses continue to take precedence.

Commit d0a65e849c6a10349cf364baa053375d79c73ad3 is deployed only to the
disposable trial. All 198 Python controls passed. The live Five Below Foundation
control returned Current in 44.6 seconds, initial registration 2022-05-12 and
latest statement filed 2026-05-05, with renewal due 2027-05-31. Colorado Current
and Not Registered controls also passed. Connector 0.6.8 is unchanged by this
backend correction. Broader random-30 validation is still in progress; the
separate Nevada navigation timeouts are not claimed resolved.

### Random-30 evidence and 0.6.9 candidate

The random sample exposed an unrelated RMHC chapter row with an explicitly
blank NV Business ID, a visible Entity Number E38494562024-0, and a complete
Expired status. Rejecting the entire search before master name filtering was
too strict. The candidate preserves such rows with their visible entity number
as the row key and an explicit missing-business-ID marker. The master can reject
an unrelated name, but a matching row without a usable NV ID remains review-only.
It cannot trigger detail navigation or a guessed registration status. Duplicate,
unknown and malformed identities still fail conservatively. Restored result
sets must preserve all of these row identities.

A read-only observation during Partnership for a Healthier America's Nevada
run caught a returned form with the visible selected search-type label
STARTS_WITH, rather than Starts With. The candidate accepts this precise enum
label only with the selected public DOM choice's STARTS_WITH identity and its
matching removal control. Partial controls and other search modes remain
unready. This observation identifies a readiness weakness, but is not proof
that it caused every timeout: that particular run later advanced and failed
on the broad PHA query's pagination. Local controls cover the enum label,
missing choice identity, wrong mode, no-response negative prevention, restored
rows, optional history, adverse statuses and existing-state isolation.

The candidate passed 369 JavaScript and 200 Python checks. It is not a live
validated fix yet. The running 0.6.8 random sample is preserved before any
activation. Broad-alias completion failures, Alabama verification and remaining
source/identity reviews are separate open issues; do not promote the expansion.


### September 29: complete primary positives and literal alias templates

The trial master may finish a complete query once every potentially matching
record has been inspected and the existing selector accepts a positive primary
identity (explicit matching EIN or a full legal name with at least two
distinctive tokens). Unresolved candidates, unissued applications, address
conflicts, alias-only identities, short names and adverse statuses preserve the
remaining reviewed-name search requirements. No status or identity threshold
was relaxed; timeouts and partial searches remain inconclusive.

Discovery drops only quoted/bracketed literal Chapter Name placeholders from
DBA/AKA/Other Name source fields. Legal names, real chapter names and user-edited
alternatives remain unchanged. This centralizes Tennessee's existing cleanup.

Validation: 308 Python controls, 41 DC/RI behavioral controls and 30 core matching
fixtures pass. Three historical DC/RI source-parity tests fail identically on the
previously deployed HEAD because they compare against an older release; the
approved 29.1 isolation comparison passes outside the exact audited additions.
The six connector 0.6.9 Nevada controls returned four conclusive results and two
return-to-search timeouts. Those initial results are preserved; deployment alone
is not a claim that the remaining live navigation/verification failures pass.

### September 29 evening: native navigation, paging and passive verification

The 0.6.9 post-backend controls completed ten state checks: seven were conclusive.
ELI and RMEF returned Upcoming Filing in both NC and TN, CHLA returned Current in
NV, and PHA and Classical 98.1 returned Upcoming Filing in NC. Initial failed
attempts remain in the random-30 report. Give Something Back and Operation
Homefront remain incomplete on NC verification/readiness, and RMHC remains
incomplete on NV pagination. The broader Nevada continuation is separate.

Two direct public-page observations inform candidate connector 0.6.10:

* NV reported 38 RMHC-prefix results at 25 per page, but its second page began
  after two missing rows and ended at 36 of 38. Selecting its public 50-row
  option exposed all 38 rows, including those two chapter records. The candidate
  selects 50 or 100 through the public pager, keeps the original total, checks
  the selected page size and row count, and still requires complete unique rows.
  It never treats a shortened page as a completed negative.
* Native Return To Search restored NV's working form in manual controls. An Aeon
  0.6.9 repeat still timed out after a complete detail when starting its next
  alias. The candidate follows the native button and waits for the hydrated
  Business form. It does not guess a URL or accept a partially restored form.

The Man in the Mirror continuation also reached an unrelated complete public
row with identifier C20180913-0530, the same Entity Number, an Expired status,
and an explicitly blank entity type. This dated C identifier now follows the
existing NR unclassified-row path. An unrelated row can be rejected by master
matching; a matching row remains review-only and cannot open a business detail.
No corporation, charity license, or compliance status is inferred from it.

Colorectal Cancer Alliance's CCA alias exposed the same dated C row shape.
Give Something Back's Something fallback exposed an unrelated issued NV LLC
with an explicitly blank Status cell in a complete 89-row result. Issued NV
identities with a populated entity type now retain that blank for master
filtering. A matching record still requires its complete detail; a blank search
status never becomes a compliance classification. Unclassified and missing-ID
rows retain their stricter requirements.

NC's public page visibly showed Performing security verification in a failed
background check. A subsequent interactive search returned the Give Something
Back record immediately. The candidate applies Illinois's bounded visibility
pattern only to the connector-owned NC page when verification is observed. It
allows the state's own passive check to finish without a reload or additional
request, stays inside the original readiness deadline, and restores the prior
tab unless the user has switched or navigated. It does not solve a CAPTCHA,
click a verification checkbox, manipulate verification tokens/cookies, or
guarantee that a persistent challenge will clear. That hypothesis requires a
live post-activation test.

The changes are trial-only and do not alter matching thresholds, status rules,
discovery concurrency, worker capacity or approved 29.1 deployment targets.
Candidate activation and live validation remain required; do not promote.

### 0.6.10 live outcome and 0.6.11 submission recovery

The 13-organization, 18-check activation control finished with 11 conclusive
results and seven reviews/incomplete results. PCJF and Federation of Jewish
Communities completed the previously failing NV return-navigation path and
returned Delinquent. Give Something Back completed all NV aliases and returned
Not Registered. Summit's IL and GA controls both remained Current. Aeon, Man in
the Mirror and CCA now complete collection but retain unclassified-entity
reviews; resolving collection does not establish their identity or status.

NC still timed out after acknowledging ordinary Search actions. In a same-input
repeat, the observed page showed the submitted query with an enabled Search
button, no visible verification, and no results navigation. The failing alias
changed between repeats. Candidate 0.6.11 removes an unnecessary search-type
change event and allows one same-query public resubmission after three seconds,
only while the same document is a complete, enabled ordinary search form.
The content handler rechecks the exact query, Starting With and printable-view
controls. Processing, changed queries, other documents and verification pages
cannot trigger this action. It keeps the original 45-second readiness deadline
and the enclosing job deadline. No extra capacity or broader permissions.

The remaining ELI NV failure has a separate cause: the public Starts With alias
query returns 5,463 records (219 pages), exceeding the 500-record bound. Exact
Match returns five candidates in manual diagnosis, but that narrower search has
not been adopted or substituted for application evidence. RMHC's subsequent
alias continuation remains under investigation. No negative is inferred from
either incomplete lookup. Alabama's displayed verification remains pending.

This candidate does not change any state's identity thresholds, compliance
classification, discovery plan, concurrency or timeout allocation. Activation
and live post-validation are required before calling the NC recovery verified.
NV incomplete responses now identify whether the return form, input settling,
or page-size menu failed. These diagnostic distinctions do not relax source
completion or cause an additional request; the remaining RMHC failure must be
observed at its actual failing phase before another navigation change is made.

### 0.6.11 live controls and mature-route compatibility repair

The live six-check control recovered Operation Homefront NC (Current, 24.367s)
and retained Environmental Law Institute NC (Upcoming Filing, 5.027s). Give
Something Back still timed out on a later generated query after collecting its
expired SL012308 record. No classification was substituted for the failed run.
RMHC NV completed Return To Search and the Ronald McDonald House query; the
later generated Ronald query exceeded the 500-record bound. Manual public
search returned 1,322 rows. ELI's separate 5,463-row prefix remains incomplete.

The same control exposed a release compatibility defect: the IL/GA request
start allowlist omitted 0.6.11 although IL's recovery allowlist included it.
Both mature controls were rejected before registry collection. Add the installed
version to the trial-only start allowlist and test the actual packaged version
through both start routes, including rejection outside the trial and rejection
of unknown versions. The exact origin-gated AST audit is updated to match this
one allowance. No collector update, installation, status-rule change, additional
capacity or change to approved staging 29.1 is included in this repair.

### North Carolina transport recovery (trial only)

The 0.6.11 live Give Something Back control found and read SL012308, then a later name search stayed on the ordinary enabled form until its readiness deadline. A separate visible lookup confirmed the record. No status is inferred from that partial attempt.

The trial master may authorize one fresh browser transport only for a pending NC search with TAB_READY_TIMEOUT, a matching signed query ID, and more than 60 seconds left. Completed evidence, aliases, issue/expiry times, and the pending query survive; the query ID rotates to reject late replies. Verification, detail failures, other states, canceled/expired checks and repeat failures remain inconclusive. The trial frontend reuses the approved Illinois cleanup/reacquisition sequence. Approved web-staging assets and installed connector remain unchanged.

Validation: 315 Python regression controls passed, including 17 frontend scenarios executed against the assembled trial NC client. Live validation remains required.
