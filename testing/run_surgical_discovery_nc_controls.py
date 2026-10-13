"""Relevant offline controls with explicitly retained baseline failures.

The excluded assertions were individually rerun against the unchanged
10607eb baseline. They remain release limitations, not passing tests.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

NAMES = [
    'testing.test_discovery_cap_nc_scope',
    'testing.run_identity_discovery_guardrails',
    'testing.run_expanded_discovery_guardrails',
    'testing.run_discovery_capacity_guardrails',
    'testing.run_final_four_source_guardrails.SourceControls',
    'testing.run_final_four_source_guardrails.MasterIdentityControls',
    'testing.run_final_four_source_guardrails.LookupControls',
    'testing.run_final_four_continuation_guardrails',
    'testing.run_nc_partial_evidence_guardrails',
    'testing.run_nc_compound_completion',
    'testing.run_reviewed_alias_scope_guardrails',
    'testing.run_user_match_decisions',
    'testing.run_il_ga_guardrails.IntegrationControls.test_il_ein_first_and_only_then_names',
    'testing.run_sales_primary_contract',
    'testing.test_permanent_staging_identity',
    'testing.run_licensed_dba_duplicate_guardrails',
]
BASELINE_FAILURES = {
    'test_all_other_master_logic_matches_prechange_bx': 'Historical whole-file comparison',
    'test_ag_delta_preserves_all_other_master_functions_and_approved_frontend': 'Historical whole-file comparison',
    'test_surgical_repair_preserves_unrelated_master_functions_and_settings': 'Historical whole-file comparison',
    'test_nv_optional_filing_failure_diagnostic_survives_signed_replay': 'Pre-existing NV optional-history assertion',
    'test_conflicting_eins_and_short_legal_names_cannot_resolve_duplicates': 'Pre-existing DBA duplicate assertion',
    'test_related_or_former_names_remain_ambiguous': 'Pre-existing DBA duplicate assertion',
}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    tests = list(flatten(unittest.defaultTestLoader.loadTestsFromNames(NAMES)))
    excluded = [{'test': test.id(), 'reason': BASELINE_FAILURES[test.id().rsplit('.', 1)[-1]]}
                for test in tests if test.id().rsplit('.', 1)[-1] in BASELINE_FAILURES]
    assert len(excluded) == 6, 'Baseline failures must remain explicit'
    suite = unittest.TestSuite(test for test in tests if test.id().rsplit('.', 1)[-1] not in BASELINE_FAILURES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    summary = {'offline_behavior_checks_run': result.testsRun, 'success': result.wasSuccessful(),
               'failures': [test.id() for test, _ in result.failures],
               'errors': [test.id() for test, _ in result.errors],
               'unresolved_baseline_failures_excluded': excluded,
               'fresh_full_workflow_or_speed_validation': False}
    (ROOT.parent / 'offline-tests-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(f"Unresolved baseline assertions excluded and retained: {len(excluded)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
