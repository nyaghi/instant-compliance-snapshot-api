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


### Authorized staging test release 29.2FD

The user explicitly approved one staging-only paired AL/NV test release on
October 15, 2026, to enable the candidate live ten-organization/all-38-state
matrix. This is a narrow exception to the predeployment gate, not a declaration
that candidate regression or speed passed. Production remains excluded, and
no further deployment is authorized by this exception. The existing staging
API and three worker instances retain their environment and capacity.
The matching immutable connector is connector-0.6.132-al-nv-recovery.
Current-release baselines now cover all ten planned organizations, including
the user's clean GiGi export. All first-pass exports and displayed durations
are preserved separately from later retries. Release labels change to 29.2FD;
source, status, adverse-identity and packaged controls were completed locally
before this test deployment. Native popup bounds and live candidate outcomes
remain pending. Recommendation remains Do not promote.


### Focused live source-failure reconciliation — October 15, 2026

The user stopped broad tests after the first two all38 candidate runs, directing
problem-state checks before expansion. Both reported Nevada records now retrieve
their verified charity-statement detail: Partnership Delinquent and Opportunity
Current. Alabama remained Unable to Confirm. Focused YWCA/AL discovery was0:16,
execution0:15, with zero new verification attempts and a public generic Error
dialog. Clearing the leftover code and dismissing that dialog before one targeted
retry triggered one fresh verification attempt, but the same generic Error
returned; this intervened retry is not a clean candidate pass.

The user independently reproduced the same Error through a manual Alabama
search. Captured public source code distinguishes Invalid Captcha from the
grid AJAX handlers that display Error. A separate public grid-configuration
metadata probe returned HTTP202, empty body, after14.613 seconds while the page
loaded HTTP200. No organization query, challenge token, or verification code was
submitted in that metadata probe. The browser search HTTP response itself was
not captured; the exact state infrastructure failure remains unknown. Classify
this observed failure as a source retrieval/access limitation, not an established
CharityClarity verification regression. The offline dialog-close race remains a
separate latent defect, not the proved cause of this source error.

Broad candidate matrix: stopped at2/10. Full affected-state controls, live speed
and native popup bounds remain unvalidated. No additional runtime edits or
deployment followed this finding. Production untouched. Do not promote.


### User-directed Alabama rollback and37-state scope

The user requested restoring the Alabama change and excluding Alabama until
source recovery. The complete AL verification/search region is byte-identical
to5ca7d17's parent in both source and the prepared connector. The Nevada repair,
backend, permissions, scheduling and geometry are unchanged. No server deployment
is needed. Prepared connector: connector-0.6.132-nv-recovery-al-restored.
Four additive tests for the withdrawn dialog-wait behavior were reverted with
the feature and archived intact in the evidence directory; no regression-sheet
expectations changed. The remaining source controls pass585/585, actual package
controls280/280, with no skipped tests. Commands and logs are in
al-restored-test-summary.json. These are offline controls, not live AL validation.
Activation and focused Nevada live controls remain pending. After those pass,
continue at least ten organizations across the remaining37states, logging the
explicit AL source exclusion. Original all38 first passes remain preserved and
are not relabeled as37-state candidate passes. Production untouched; do not
promote. Root AGENTS.md now requires source-first triage, demonstrated mechanism,
surgical changes, multi-organization affected-state live validation before
expansion, and explicit coverage/timing limits.
