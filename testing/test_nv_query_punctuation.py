"""Source-rejected punctuation is a retrieval problem, never an identity override."""
import copy
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc
from testing import run_final_four_source_guardrails as fixtures


class NvPunctuationControls(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LookupControls('test_full_master_lookup_selects_expected_record_in_all_four')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        p = patch.object(cc, 'trial_identity', return_value={'permanent_staging': True})
        p.start()
        self.addCleanup(p.stop)
        self.calls = []

    def empty(self, query):
        self.calls.append(copy.deepcopy(query))
        return dict(state=query['state'], query=query, complete=True,
                    verification_pending=False, rows=[], total=0)

    def test_unspaced_unicode_dashes_complete_without_changing_identity(self):
        for name in ['Solid Rock\u2013Climbers for Christ', 'River Literacy\u2014Reading Alliance']:
            with self.subTest(name=name):
                self.calls.clear()
                org = cc.checker.Organization(name, '123456789')
                result = cc.final_four_browser_lookup(org, 'NV', self.empty)
                self.assertEqual(result.status, 'Not Registered')
                self.assertTrue(result.success)
                self.assertEqual(org.organization_name, name)
                self.assertEqual(org.ein, '123456789')
                self.assertEqual(self.calls[0]['name'], cc.ascii_dash_search_name(name))
                self.assertFalse(any(re.search(r'[\u2010-\u2015\u2212]', q['name']) for q in self.calls))

    def test_current_record_and_ordinary_word_hyphens_keep_matching(self):
        org = cc.checker.Organization('MAKE\u2013A\u2013WISH FOUNDATION OF AMERICA', '860481941')
        result = cc.final_four_browser_lookup(org, 'NV', self.fixture.provider)
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier, fixtures.NV['NV Business ID'])
        self.assertIn(result.status, ['Current', 'Upcoming Filing'])
        self.assertEqual(self.fixture.calls[0]['name'], 'MAKE-A-WISH FOUNDATION OF AMERICA')
        self.calls.clear()
        ordinary = cc.checker.Organization('MAKE-A-WISH FOUNDATION OF AMERICA', '860481941')
        cc.final_four_browser_lookup(ordinary, 'NV', self.empty)
        self.assertEqual(self.calls[0]['name'], ordinary.organization_name)

    def test_alias_queries_are_bounded_and_branch_qualifier_remains_required(self):
        name = 'River Learning Network \u2014 Portland, LLC'
        org = cc.checker.Organization(name, '123456789')
        token = cc.REVIEWED_NAME_CONTEXT.set({'123456789': [name, 'River Learning Network - Portland, LLC', 'Portland Chapter']})
        try:
            required, generated = cc.licensed_charity_names(org)
            cc.final_four_browser_lookup(org, 'NV', self.empty)
            self.assertLessEqual(len(self.calls), 3 * len(required) + len(generated))
            self.assertTrue(any('Portland' in q['name'] for q in self.calls))
            self.assertEqual(cc.score_candidate(name, org.ein, {'name': 'River Learning Network, Inc.'})['decision'], 'possible')
            self.assertEqual(cc.score_candidate(name, org.ein, {'name': 'River Learning Network, Inc.', 'ein': '987654321'})['decision'], 'rejected')
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_failed_search_does_not_become_a_negative_and_other_states_keep_literal(self):
        org = cc.checker.Organization('Solid Rock\u2013Climbers for Christ', '123456789')
        with self.assertRaises(ValueError):
            cc.final_four_browser_lookup(org, 'NV', lambda q: dict(state='NV', query=q,
                complete=False, verification_pending=False, rows=[], total=0))
        cc.final_four_browser_lookup(org, 'NC', self.empty)
        self.assertEqual(self.calls[0]['name'], org.organization_name)


if __name__ == '__main__':
    unittest.main()
