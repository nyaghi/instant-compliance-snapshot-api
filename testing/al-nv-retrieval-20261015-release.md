# Alabama recovery and Nevada source-contract repair — local candidate

Summary: Nevada's current public grid leaves Entity Type blank for the matched
Partnership for Civil Justice Fund and Opportunity@Work records. The unchanged
collector rejects the complete grid as REGISTRY_NV_RESULTS_INCOMPLETE before
opening a detail. Current details identify both as Charitable Solicitation
Registration Statement, a category absent from the master's supported types.
The saved 0.6.130 Partnership result used the same NV identifier but the older
Foreign Entities Not Required to Register In Nevada category. The time of the
state-side change is unknown; these are current observed source differences,
not proof that a recent CharityClarity commit introduced the Nevada failure.

The general repair retains only a blank-type row that has a valid issued NV ID,
a valid separate entity number, a name and loaded status. It remains unclassified
search evidence. Existing matching decides whether to inspect it. The master
must verify the same detail ID/name and an explicit supported type before using
its status/date. Explicit business categories are still excluded, malformed or
partial rows fail closed, and changed details/wrong EIN cannot become a positive.
The current explicit charity-registration category is supported and labeled as
such in comments. No type, registration status, alias or address is invented.
No organization-specific runtime rule, extra history fetch, deadline change,
queue change, permission change or geometry change is included.

The same prepared connector includes the prior AL rejected-code dialog fix:
observe and await closure within the original command deadline, then use the
existing bounded continuation. The master's two-submission limit is unchanged.

Files changed: browser-connector/registry-content.js; registry_snapshot_server.py;
testing/run_nv_public_dom.cjs; testing/run_nv_missing_type_guardrails.py;
testing/fixtures/nv-public-type-gap-20261015.json; this release note. The AL code
and tests are in prior local commit 5ca7d17. Separate GiGi/user instruction
corrections are preserved and are not runtime changes.

Deployment: none. Current 29.2FC and enabled 0.6.132 TN Verification Trace remain
active. A separate immutable connector-0.6.132-al-nv-recovery folder/ZIP is built,
unactivated, and requires the matching local master repair. It supersedes the
AL-only candidate for combined validation; neither candidate has been activated.

Tests run: observed NV collector reproduction failed before the fix; after the
fix, NV DOM99/99, master missing-type and signed-continuation8/8, relevant master
source/identity and saved-control regression99/99, broader connector source589/589
and actual combined-package284/284 passed. Saved source fixtures cover both
reported cases and the unrelated Opportunity Works LLC; adverse mutations cover
missing fields, wrong detail ID/name/EIN, unsupported types, incomplete search,
and completed no-record results. The saved21 NV selector controls are included
in the master regression, not represented as a current live31 group.

Smoke results: local replay of the captured current source gives Partnership
Delinquent and Opportunity Current with the observed IDs and explicit charity
type. Mature AL/NC/TN/IL identity/status guards remain covered offline. No claim
is made that the candidate has passed live staging or native popup checks.

Regression results: candidate fresh10-organizations x38-state validation and
the current full affected-state31 controls are not complete. This does not meet
the user's new deployment gate. No deployment is permitted by these offline
results alone. Existing broad Python-suite failures in unchanged historical
release/whole-source assertions and the old optional-NV-history fixture were
previously recorded; those expectations were not rewritten to produce a pass.

Speed evidence: saved user full38 traces show FII–National2:08.024 and Summit
Ministries2:44.958. Exclusive current-release reruns completed in1:16 (discovery
0:01, four names) and0:38 (discovery0:00, two names), respectively. Partnership's
exclusive full38 was1:20 and Opportunity's0:47; both discovery0:00, two names.
The clean user GiGi rerun was0:51.388. User historical runs had uncontrolled
interference/cache conditions; exclusive reruns are new baselines, not proof of
candidate speed or a comparison with EW. FII's slow trace contains Illinois
verification and queue waits; Summit's has a later45-second Tennessee failure.
Do not generalize from last-result time alone. Timed runs had no parallel tests,
builds, history scans or unrelated source actions. All exports and separate
discovery/execution records are retained in the evidence directory.

Known issues: candidate live AL recovery, fresh full NV31, the10x38 candidate
matrix, candidate speed and native placement remain unvalidated. The current
Nevada collector still fails until the paired repair is admitted. Deployment
ordering must comply with the user's explicit predeployment gate; a preparatory
staging test release requires an explicit exception if needed for live testing.
Do not claim a completed run has validated the local candidate. Colorado source
naming and GiGi's superseded contaminated-run report are not current defects.

Production touched: No.

Recommendation: Do not promote or deploy under the current gate. Preserve the
one prepared combined candidate and measured baselines; use a fixed10-case
all38 matrix and approved affected-state controls for the authorized next test.
