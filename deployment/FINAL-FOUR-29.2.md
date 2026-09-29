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
  unchanged. A separate 0.6.3 trial package uses only the trial origin, public
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

## Confirmed date interpretation

The user confirmed on September 29 that a displayed extension end date is the
deadline to use instead of the original expiration date. The source does not
need to repeat "extension" in its status label. Preserve both dates as evidence
and explain the extension in comments. Explicit adverse registry statuses still
take priority. Expiration and extension deadlines are not last-renewal dates.

## Confirmed Nevada interpretation

On September 29 the user directed Nevada to use the matching nonprofit
corporation's displayed status and Annual Renewal Due Date/Expiration Date.
Exclude registered-agent records and do not use registered-agent addresses as
organization addresses. Evaluate matching duplicate nonprofit records through
the master selector. Comments identify this as nonprofit-corporation standing
and preserve any separate solicitation flag; do not imply a CSRS/CSRX filing has
been verified when it has not. Formation is not a last renewal, and the annual
due date is not a last-filed date.
