# Live follow-up: Illinois budget and pagination

Candidate: 2026.09.26.4-staging / connector 0.5.7.

The .3 live run confirmed First Responders / GA Delinquent (CH016629,
expiration April 11, 2026), Air Force Academy / GA Exempt, and American
Independent Media / IL Not Registered / Non-Compliant. Preserve that run.

Two further failures require correction before completion:

- Air Force Academy / IL passed formerly failing searches but eventually used
  its five-minute active allowance. The backend token expired before the
  frontend could record the terminal failure, returning a generic New York
  expiry message. IL/GA signed continuations now permit 60 seconds solely for
  terminal cleanup. No late evidence is accepted and no search is continued
  after five minutes. New York retains its original expiry policy.
- Illinois's Veterans fallback returns 154 rows. The public page-size menu
  supports 10, 20, 50, and 100. The connector now selects 100 using that visible
  menu, reducing 16 pages to two, with first-page, stable-total, and full-count
  checks. No Kendo internal API, verification token, or hidden endpoint is used.

The master retains every reviewed Illinois name and removes only generated
phrases already covered by a shorter literal substring query in the same
plan. Punctuation is preserved. Every covering query still must complete,
and every selected record must pass the existing exact-EIN check. GA, DC,
RI, and other state query plans are unchanged. For the saved Air Force Academy
case, generated queries fall from 25 to seven while all nine reviewed names
remain. No expected-sheet value is changed.

Local validation: 434 backend tests across 24 suites plus 30 matching fixtures;
82 connector/frontend tests. All passed. New tests cover broad-query failure,
punctuation coverage, preserved reviewed names, late evidence rejection,
bounded cleanup, unchanged New York expiry, 154-row pagination, and count drift.

Live staging validation remains required. Production is not authorized.
