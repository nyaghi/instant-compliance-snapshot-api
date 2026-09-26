# Next 50 organizations: staging follow-up

Scope: Fresh Test, Orgs!A52:AM101, organizations 51–100, all 34 states.
The 1,700 expected values are preserved. Production is not authorized.

## Confirmed defects and changes

1. Short-name retrieval: Ceres, Inc. was missed in Georgia and Rhode Island because the existing generated search phrases omitted its short literal core. The master now appends its existing literal-name retrieval forms after the existing probes, within the same three-generated-probe limit. Candidate acceptance is unchanged.
2. Michigan pending status: the EIN-first name fallback classified a selected row using expiration alone and discarded its explicit Registration Pending text. The master retains pending from that selected row, including when no expiration is supplied. Other rows and the page-wide instructions cannot supply this status.
3. Georgia office evidence: the registry grid supplies city/state/ZIP without a comma. The shared address verifier could not parse that shape. The Georgia adapter now normalizes a complete city/state/ZIP before the existing shared identity checks. Full street strings, partial locations and malformed ZIPs are not converted. No new name-acceptance rule or organization-specific exception was added.

The Georgia defect was reproduced with Endicott College: the Beverly exemption record agrees with IRS organization metadata, while a second New York office is not corroborated. Tests confirm selection of the corroborated record and rejection of a conflicting office, including when its name is exact.

## Validation before deployment

- 628 backend tests across 34 suites and 30 existing matching fixtures passed.
- Python compilation and git diff whitespace checks passed.
- Evidence and logs are retained under outputs/next50-all34-postvalidation-20260926.
- The original live run is version 2026.09.26.5-staging with connector 0.5.8. Its browser continuations must finish before any master deployment.
- The planned 2026.09.26.6-staging follow-up repeats all 50 Georgia checks and four controls: Ceres RI, Beacon Center MI and RI, and Endicott CA. Preserve each row's returned version and original outcome.

## Release status

This file records prepared changes and local verification. It is not proof of deployment or final live validation. Record the actual commit, live API/frontend verification, follow-up results and remaining limitations in the final audit report. Production promotion requires explicit approval.
