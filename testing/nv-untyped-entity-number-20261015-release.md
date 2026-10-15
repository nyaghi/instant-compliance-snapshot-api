# Nevada observed entity-number detail recovery

The current ordinary Nevada search for Loyola returns a loaded entity number
and Registered status with both Business ID and Entity Type blank. The selected
same-number detail explicitly identifies a Charitable Solicitation Registration
Statement and an Exemption to Charitable Solicitation Statement filing. The
saved EY source fixture described the same entity number with a different type;
the exact time that source presentation changed is not established.

The collector rejected the completed row before opening detail. Existing master
entity-number validation allowed only the older foreign-record category. The
repair extends the existing observed entity-number path: blank grid type remains
unclassified until its same-number detail supplies a supported explicit category.
Business ID must remain absent on that detail; names/numbers, FEIN when present,
complete history and filing dates retain their existing validation. Corporate,
registered-agent, changed-number and conflicting-EIN controls remain adverse.
The original issued-business-ID path and AL rollback are preserved.

The user's `Solicits Charitable Contribution? Yes` observation is useful
corroboration and remains validated in the detail. It does not supply legal
entity type, exemption or current status by itself. A Yes record with only an
Annual List remains Unable to Confirm; an explicit exemption filing establishes
the supported exemption. There are no organization-specific runtime exceptions.

This is separate from the mixed-connector failure. Live trace nv-handoff-01
proved that search and rejected detail replies came from different builds. The
user removed the older Sequence Trace, and the exact staging tab was reloaded.
After cleanup, Partnership is Delinquent in0:11 and Opportunity is Current in0:08,
each with discovery0:00/two names and successful same-worker search/detail replies.
Loyola then failed with RESULTS_INCOMPLETE in0:08; its one targeted retry also
failed. Fresh source evidence was captured before this functional repair.

Files: browser-connector/registry-content.js; registry_snapshot_server.py;
testing/run_nv_public_dom.cjs; testing/run_final_four_source_guardrails.py;
testing/test_nv_untyped_entity_number.py; fresh fixture alongside prior fixtures.
Existing test cases that required rejecting a blank type despite a valid observed
E-number were updated for the specifically changed retrieval contract, while
missing identity/status and adverse detail assertions remain. No spreadsheet
expectations were edited.

Commands: `python -X utf8 -B -m unittest testing.test_nv_untyped_entity_number
testing.test_nv_entity_number testing.run_nv_missing_type_guardrails` (22pass);
`node --test testing/run_nv_public_dom.cjs` (102pass);
`python -X utf8 -B run_nv_untyped_number_master_regression.py` from the evidence
directory (113pass, including the original21 saved selector controls);
actual-candidate selected worker/lifecycle124pass and collection/isolation274pass.
The actual bridge/protocol handoff controls passed earlier; transport files are
byte-identical to that Handoff build. Exact logs are retained in the evidence
directory. These are offline controls, not live speed or full31 regression.

Immutable connector: connector-0.6.132-nv-entity-detail-candidate. Only content
and manifest labels differ from NV Handoff Trace. Permissions, worker,
scheduling, original time budgets and geometry are unchanged. It requires the
matching master repair. Prepared locally; not installed or deployed.

Known gaps: no live repaired Loyola result, full31NV group or ten-by37 expansion;
native window bounds and comparable candidate speed unvalidated. Earlier
unrelated packaged MS budget assertion remains recorded, unchanged. AL excluded.
No further server release is currently authorized by the one-time FD exception.
Request a specific additional staging-test exception if needed; production
remains prohibited. Do not promote.

The user subsequently approved exactly this additional staging-only test
release,29.2FE, and matching candidate activation. Preserve existing staging
targets and instance counts; AL remains excluded and production untouched.
This approval enables live validation; it does not establish a live pass or
authorize another release.
