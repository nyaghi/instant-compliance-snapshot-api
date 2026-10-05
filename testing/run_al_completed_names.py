"""Completed Alabama identities must not depend on redundant generated probes."""
import copy
import unittest
from unittest.mock import patch
import registry_snapshot_server as cc
from testing.run_final_four_source_guardrails import AL_HEADERS, AL_ROWS, LookupControls


class AlabamaCompletedNames(unittest.TestCase):
    def setUp(self):
        fixture = LookupControls()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.org = fixture.orgs['AL']
        self.primary = self.org.organization_name
        self.row = copy.deepcopy(AL_ROWS[1])
        self.row[5] = '08/31/2026'
        self.calls = []
        p = patch.object(cc, 'trial_identity', return_value={'origin': 'isolated'})
        p.start()
        self.addCleanup(p.stop)

    def payload(self, query, rows):
        self.calls.append(query['name'])
        return {'state': 'AL', 'query': query, 'complete': True,
                'verification_pending': False, 'headers': AL_HEADERS,
                'rows': copy.deepcopy(rows), 'total': len(rows)}

    def test_completed_adverse_identity_avoids_redundant_generated_timeout(self):
        for primary in [self.primary, 'Beacon Literacy Network']:
            with self.subTest(primary=primary):
                self.calls.clear()
                org = cc.checker.Organization(primary, self.org.ein)
                row = [primary, *self.row[1:]]
                def source(query):
                    if query['name'] == 'broad generated phrase':
                        raise TimeoutError('Redundant generated probe failed')
                    return self.payload(query, [row] if query['name'] == primary else [])
                with patch.object(cc, 'licensed_charity_names', return_value=(
                        [primary, 'Reviewed Former Name'], ['broad generated phrase'])):
                    result = cc.final_four_browser_lookup(org, 'AL', source)
                self.assertEqual(result.status, 'Delinquent')
                self.assertTrue(result.success)
                self.assertEqual(self.calls, [primary, 'Reviewed Former Name'])

    def test_incomplete_reviewed_alias_is_not_skipped(self):
        def source(query):
            if query['name'] == 'Reviewed Former Name':
                raise TimeoutError('Required alias incomplete')
            return self.payload(query, [self.row])
        with patch.object(cc, 'licensed_charity_names', return_value=(
                [self.primary, 'Reviewed Former Name'], ['broad generated phrase'])):
            with self.assertRaisesRegex(TimeoutError, 'Required alias'):
                cc.final_four_browser_lookup(self.org, 'AL', source)

    def test_later_reviewed_name_can_retrieve_newer_current_registration(self):
        def source(query):
            row = copy.deepcopy(self.row)
            if query['name'] == 'Reviewed Former Name':
                row[1], row[5] = 'AL26-999', '09/30/2027'
            return self.payload(query, [row])
        with patch.object(cc, 'licensed_charity_names', return_value=(
                [self.primary, 'Reviewed Former Name'], ['broad generated phrase'])):
            result = cc.final_four_browser_lookup(self.org, 'AL', source)
        self.assertEqual(result.status, 'Current')
        self.assertEqual(result.matched_registry_identifier, 'AL26-999')
        self.assertEqual(self.calls, [self.primary, 'Reviewed Former Name'])

    def test_completed_no_match_still_uses_generated_retrieval(self):
        def source(query):
            return self.payload(query, [] if query['name'] == self.primary else [self.row])
        with patch.object(cc, 'licensed_charity_names', return_value=(
                [self.primary], ['generated useful phrase'])):
            result = cc.final_four_browser_lookup(self.org, 'AL', source)
        self.assertEqual(result.status, 'Delinquent')
        self.assertEqual(self.calls, [self.primary, 'generated useful phrase'])

    def test_ambiguous_identity_does_not_skip_generated_retrieval(self):
        with patch.object(cc, 'licensed_charity_names', return_value=(
                [self.primary], ['generated useful phrase'])), patch.object(
                cc, 'select_licensed_charity', return_value=(None, 'Identity needs review')):
            result = cc.final_four_browser_lookup(self.org, 'AL', lambda q:self.payload(q, [self.row]))
        self.assertEqual(result.status, 'Needs Review')
        self.assertEqual(self.calls, [self.primary, 'generated useful phrase'])

    def test_unreviewed_numberless_record_does_not_finish_early(self):
        missing = copy.deepcopy(self.row)
        missing[1], missing[3] = '', 'Private Foundation'
        with patch.object(cc, 'licensed_charity_names', return_value=(
                [self.primary], ['generated useful phrase'])):
            result = cc.final_four_browser_lookup(self.org, 'AL', lambda q:self.payload(q, [self.row, missing]))
        self.assertEqual(self.calls, [self.primary, 'generated useful phrase'])
        self.assertFalse(result.success)

    def test_nontrial_planner_is_unchanged(self):
        with patch.object(cc, 'trial_identity', return_value=None), patch.object(
                cc, 'licensed_charity_names', return_value=([self.primary], ['generated useful phrase'])):
            result = cc.final_four_browser_lookup(self.org, 'AL', lambda q:self.payload(q, [self.row]))
        self.assertEqual(result.status, 'Delinquent')
        self.assertEqual(self.calls, [self.primary, 'generated useful phrase'])


if __name__ == '__main__':
    unittest.main()
