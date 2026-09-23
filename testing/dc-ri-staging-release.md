# DC and Rhode Island staging integration

Baseline: `6c3504f`, stable staging `2026.09.23.2`. Target: `2026.09.23.3-staging`.

The June expansion lab (`e1fa349`) supplied the DC public-license source and RI
charitable-credential workflow. The master implementation adapts those sources
to their current contracts instead of merging the older lab backend.

## Sources and interpretation

- DC: official DCRA/DLCP public GIS business-license extract. The current schema
  uses BUSINESSACTIVITY, ENTITYNAME and ENTITYTRADENAME; the lab's PRIMARYACTIVITY
  filter no longer exists. Query errors, stale extracts and incomplete pagination
  cannot establish a negative. Every result discloses the source refresh date.
- Rhode Island: the official DBR public portal's normal public token, search and
  detail endpoints. Only Charitable Organization credentials qualify. Search
  result totals and pagination are checked; selected detail identity is checked
  again. This is the same public data displayed by the portal, not an account API.
- Both are name-search sources. Every supplied reviewed name precedes generated
  phrases. The generated fallback uses up to three master high-signal phrases per
  name; it does not submit hundreds of speculative permutations.
- Identity uses the existing master name/EIN score and EIN-linked location
  reconciliation. New adapter-only street/state/ZIP corroboration handles different
  city labels when a same-EIN CA/CO organization record supplies the same address.
  Agent/mailing records, different EINs and different street/ZIP values cannot
  clear a conflict. Names must independently qualify.
- Current accepted records can supersede old inactive/expired records of the
  same entity. An uncorroborated campaign alias cannot displace an exact primary
  registration. Tied conflicting statuses remain Needs Review.
- Explicit adverse status precedes expiration math. Active Pending Renewal and
  pending initial registrations remain Pending. An old displayed expiration alone
  cannot establish delinquency while the state reports renewal processing. RI law
  preserves a license during a timely, sufficient renewal application; the public
  record does not establish those conditions, so no automatic extension or Current
  status is invented. Source: https://webserver.rilegislature.gov/Statutes/TITLE42/42-35/42-35-14.htm

## Date provenance

DC Initial Issue Date is the initial date of the selected license, not an inferred
earliest registration across historical licenses. License Start Date is labeled
Current period effective, not Renewal filed. The state can set an effective date
before its issue date. RI fields are accepted only from selected registration
sections. Relationship/fundraiser start dates, incorporation dates and expiration
dates never fill registration or renewal columns. Missing dates stay blank.

## Preservation and validation

No runtime sidecar, new deployment service, paid capacity, environment-variable,
name-discovery concurrency or state-run concurrency change. Existing 30-state
routing indices are preserved by appending DC/RI; the UI lists them alphabetically.
Reports accept the supplied supported-jurisdiction count, now 32.

`run_dc_ri_guardrails.py` tests matching, active/inactive duplicates, address roles,
source errors/truncation, freshness, date provenance and 32-result reports. AST
parity compares every existing master function to the stable baseline, allowing
only the four scoped routing/presentation entry points. Discovery, connector,
state modules and frontend run-state scheduling remain byte-for-byte unchanged.

Live evidence and final test summaries are stored in the project output folder
`outputs/dc-ri-staging-20260923`. The refreshed Fresh Test Orgs!A1:AK31 supplies
the first 30 organizations and expected DC/RI values. Discovery precedes all
checks and those discovered names are passed to the registration calls.
Spreadsheet expectations are never modified. Uncorroborated source locations and
state-versus-sheet differences remain listed for review. Production is untouched.
