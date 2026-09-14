# Maryland registry-name display correction

Candidate: 2026.09.14.5-staging. Baseline: a31a7402a985818f9dc6f6653f51ca905dcf1b77.

Maryland's entries response contains a primary organization-name field and
JSON-escaped markup in its DBA field. Generic label extraction could mistake
the DBA `Name(s)` label for the primary name, exposing markup in `Registry match`.

The master response assembly now reads Maryland's primary name and Charity ID
from the same exact-EIN entry selected by the existing duplicate-selection
helper. It requires a matching nine-digit EIN, one selected entry, a clean
primary name, and a numeric Charity ID. Conflicting existing identifiers do
not get overwritten. Unsupported bodies retain existing behavior.

No registry search, candidate ranking, status, filing calculation, timeout,
batch, connector, downloadable-data or PDF-generation rule changes. Other
states return immediately from the Maryland display helper. The two staging
HTML changes only update the visible version.

Validation scope: seven captured public-source fixtures; eight focused tests;
all 41 existing regression suites plus the new display suite; nine before/after
live-source controls covering Current, Upcoming Filing, Pending, Delinquent,
Exempt, Closed and Not Registered in MD, plus an unchanged Colorado EIN-first
control. Both affected results also exercise the real web report download.

Deploy only to the two existing staging backend services and the existing
staging web site. Post-deployment controls use the deployed frontend. Preserve
the previous 900-check validation and spreadsheet expectations. Record actual
results and deployment evidence in outputs/md-display-name-20260914.

Production promotion requires separate explicit user approval.
