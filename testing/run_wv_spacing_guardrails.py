"""Joined words must be retrievable without accepting a different entity."""
import sys
import json
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
import run_wv_sc_selection_guardrails as selection


class SpacingTests(unittest.TestCase):
    def test_literal_apostrophe_precedes_generated_spellings(self):
        for name, expected in [("GiGi's Playhouse, Inc.", "GiGi's Playhouse"),
                               ("Children\u2019s Health Care Foundation", "Children's Health Care Foundation"),
                               ("O'Brien Relief, Inc.", "O'Brien Relief")]:
            with self.subTest(name=name), patch.object(c, 'known_names_for_ein', return_value=[]):
                queries = c.wv_preferred_query_variants(name, '', limit=10)
                self.assertEqual(queries[0], expected)
                self.assertEqual(len({q.casefold() for q in queries}), len(queries))

    def test_stripped_or_spaced_probe_cannot_replace_literal_search(self):
        planned = ["GiGi's Playhouse", 'GiGis Playhouse', "Gi Gi's Playhouse, Inc."]
        self.assertFalse(c.wv_core_search_completed(planned[1:], planned))
        self.assertTrue(c.wv_core_search_completed(planned[:2], planned))

    def test_literal_candidate_still_requires_correct_entity(self):
        fixture = selection.SelectionTests()
        for candidate, accepted in [("GiGi's Playhouse, Inc.", True),
                                    ("GiGi's Playhouse - Charleston", False),
                                    ("GiGi's Playhouse Foundation", False)]:
            with self.subTest(candidate=candidate), patch.object(c, 'known_names_for_ein', return_value=[]):
                result, selected = fixture.wv([('control', candidate, 'Closed')], name="GiGi's Playhouse, Inc.")
                self.assertEqual(bool(result.matched_registry_identifier), accepted)
                if accepted:
                    self.assertEqual(result.status, 'Closed / Withdrawn / Canceled')

    def test_query_is_early_bounded_and_does_not_depend_on_discovery(self):
        with patch.object(c, 'known_names_for_ein', return_value=[]):
            queries = c.wv_preferred_query_variants('CurePSP, Inc.', '', limit=10)
        self.assertEqual(queries[:2], ['CurePSP', 'Cure PSP, Inc.'])
        self.assertLessEqual(len(queries), 10)

    def test_spacing_keeps_every_letter_and_preserves_normal_names(self):
        self.assertEqual(c.case_boundary_name_variant('GreenABC Trust'), 'Green ABC Trust')
        self.assertEqual(c.case_boundary_name_variant('ABCResearch'), 'ABC Research')
        for name in ['Autism Research Institute', 'AIR FORCE ACADEMY FOUNDATION', 'A Call to Action']:
            self.assertEqual(c.case_boundary_name_variant(name), '')

    def test_full_spaced_record_is_accepted_with_existing_safeguards(self):
        fixture = selection.SelectionTests()
        with patch.object(c, 'known_names_for_ein', return_value=[]):
            result, selected = fixture.wv([('3478', 'Cure PSP, Inc.', 'Active')], name='CurePSP, Inc.')
        self.assertEqual(result.matched_registry_identifier, '3478')
        self.assertEqual(len(selected), 1)
        self.assertTrue(result.success)

    def test_similar_records_and_locations_remain_rejected(self):
        original = 'CurePSP, Inc.'
        fixture = selection.SelectionTests()
        for candidate in ['Cure PSP West Virginia, Inc.', 'Cure PSP Foundation', 'Cure CBD, Inc.',
                          'Cure PSP - Milton', 'A Cure PSP, Inc.']:
            with self.subTest(candidate=candidate):
                with patch.object(c, 'known_names_for_ein', return_value=[]):
                    result, _ = fixture.wv([('999', candidate, 'Active')], name=original)
                self.assertFalse(result.matched_registry_identifier)

    def test_indefinite_article_requires_reviewed_identity(self):
        fixture = selection.SelectionTests()
        for entered, candidate in [
            ('CurePSP, Inc.', 'A Cure PSP, Inc.'),
            ('A Cure PSP, Inc.', 'Cure PSP, Inc.'),
            ('Animal Relief Initiative, Inc.', 'An Animal Relief Initiative, Inc.'),
        ]:
            with self.subTest(entered=entered, candidate=candidate), patch.object(c, 'known_names_for_ein', return_value=[]):
                result, _ = fixture.wv([('999', candidate, 'Active')], name=entered)
                self.assertFalse(result.matched_registry_identifier)
        with patch.object(c, 'known_names_for_ein', return_value=[]):
            result, _ = fixture.wv([('3478', 'The Cure PSP, Inc.', 'Active')], name='CurePSP, Inc.')
        self.assertEqual(result.matched_registry_identifier, '3478')
        with patch.object(c, 'is_reviewed_alias', return_value=True):
            self.assertFalse(c.wv_unreviewed_indefinite_article_conflict('CurePSP, Inc.', 'A Cure PSP, Inc.', '010885377'))

    def test_missing_spacing_probe_cannot_complete_a_negative(self):
        self.assertFalse(c.wv_core_search_completed(['CurePSP', 'CurePSP, Inc.'],
            ['CurePSP', 'Cure PSP, Inc.', 'CurePSP, Inc.'], ['Cure PSP, Inc.']))
        self.assertTrue(c.wv_core_search_completed(['CurePSP', 'Cure PSP, Inc.'],
            ['CurePSP', 'Cure PSP, Inc.', 'CurePSP, Inc.'], ['Cure PSP, Inc.']))


class LegalDbaTests(unittest.TestCase):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 12)

    class Lookup:
        def __init__(self, registry_name='Fritsch Foundation, Inc. dba ACIR (The)', detail_dba='ACIR',
                     legal_query='Fritsch Foundation'):
            self.registry_name = registry_name
            self.detail_dba = detail_dba
            self.legal_query = legal_query
            self.queries = []

        def search(self, query):
            self.queries.append(query)
            if query != self.legal_query:
                return 'No records found', []
            return 'Search results', [{
                'index': 0, 'count': 5,
                'values': ['24035', self.registry_name, 'Active'], 'target': '10727',
            }]

        def detail(self, target, identifier):
            assert (target, identifier) == ('10727', '24035')
            return (f'Organization Name\n{self.registry_name}\nExpiration Date\n02/14/2027\n'
                    f'Contact Name\nControl\nStatus\nActive\nStreet Address\nAddress\n'
                    f'County\nDBA\nName\n{self.detail_dba}\nTax Information\nIRS Exempt\nYes')

    def run_lookup(self, registry_name='Fritsch Foundation, Inc. dba ACIR (The)', detail_dba='ACIR',
                   name='The Fritsch Foundation \u2014 ACIR', legal_query='Fritsch Foundation'):
        lookup = self.Lookup(registry_name, detail_dba, legal_query)
        with patch.object(c, 'known_names_for_ein', return_value=[]), patch.object(c, 'date', self.Today):
            result = c.search_wv_precise(None, c.checker.Organization(name, '473974944'), public_lookup=lookup)
        return result, lookup.queries

    def test_legal_name_probe_is_early_and_dba_detail_confirms_identity(self):
        result, queries = self.run_lookup()
        self.assertEqual(queries[:2], ['The Fritsch Foundation - ACIR', 'Fritsch Foundation'])
        self.assertEqual(result.status, 'Upcoming Filing')
        self.assertEqual(result.matched_registry_identifier, '24035')
        self.assertEqual(result.identity_evidence['detail_dba'], 'ACIR')
        org = c.checker.Organization('The Fritsch Foundation \u2014 ACIR', '473974944')
        data = c.response_data_for_lookup(result, '', org, org.organization_name,
                                          org.ein, 'WV', time.perf_counter())
        self.assertEqual(data['reason_code'], 'MATCH_WV_DETAIL_LEGAL_DBA')
        self.assertEqual(data['identity_anchor'], 'MATCH_WV_DETAIL_LEGAL_DBA')
        self.assertEqual(data['identity_evidence']['detail_dba'], 'ACIR')
        self.assertEqual(json.loads(data['debug_trace'])['accepted_candidate']['decision'], 'accepted')

    def test_independent_descriptive_legal_name_and_acronym(self):
        result, queries = self.run_lookup(
            registry_name='Regional Community Outreach Foundation, Inc. dba RCOF',
            detail_dba='RCOF', name='Regional Community Outreach Foundation \u2014 RCOF',
            legal_query='Regional Community Outreach Foundation')
        self.assertEqual(queries[1], 'Regional Community Outreach Foundation')
        self.assertEqual(result.status, 'Upcoming Filing')
        self.assertEqual(result.identity_evidence['detail_dba'], 'RCOF')

    def test_same_legal_name_with_different_dba_requires_user_review(self):
        result, _ = self.run_lookup(detail_dba='OTHER')
        self.assertEqual(result.status, 'Needs Review')
        self.assertEqual(result.reason_code, 'WV_LEGAL_DBA_IDENTITY_REVIEW')
        self.assertFalse(result.matched_registry_identifier)
        self.assertEqual(result._cc_identity_review['records'][0]['identifier'], '24035')

    def test_safe_legal_name_does_not_skip_dba_check(self):
        with patch.object(c, 'registry_name_is_safe_against_targets', return_value=True):
            result, _ = self.run_lookup(detail_dba='OTHER')
        self.assertEqual(result.status, 'Needs Review')
        self.assertEqual(result.reason_code, 'WV_LEGAL_DBA_IDENTITY_REVIEW')

    def test_user_review_accepts_identity_without_overriding_wv_status(self):
        result, _ = self.run_lookup(detail_dba='OTHER')
        data = {'state': 'WV', 'ein': '47-3974944',
                'organization_name': 'The Fritsch Foundation \u2014 ACIR',
                'status': result.status, 'comments': result.source_note,
                'matched_registry_name': '', 'matched_registry_identifier': ''}
        with patch.object(c, 'APP_VERSION', '29.2-test-staging'), \
                patch.object(c, 'NY_CONNECTOR_SIGNING_KEY', 'a' * 64), \
                patch.object(c, 'date', self.Today):
            c.attach_identity_review(data, result._cc_identity_review)
            self.assertEqual(data['identity_review']['candidates'][0]['identifier'], '24035')
            payload = {'token': data['identity_review']['token'], 'ein': data['ein'],
                       'state': 'WV', 'action': 'accept',
                       'candidate_id': data['identity_review']['candidates'][0]['id']}
            accepted = c.resolve_identity_review(payload, 'reviewer@example.org', 'test-device')
            self.assertEqual(accepted['status'], 'Upcoming Filing')
            self.assertEqual(accepted['matched_registry_identifier'], '24035')
            rejected = c.resolve_identity_review({**payload, 'action': 'reject'},
                                                  'reviewer@example.org', 'test-device')
            self.assertEqual(rejected['status'], 'Unable to Confirm')
            self.assertFalse(rejected['matched_registry_identifier'])

    def test_location_or_branch_is_not_authorized_by_legal_probe(self):
        result, _ = self.run_lookup(registry_name='Fritsch Foundation - Charleston')
        self.assertFalse(result.matched_registry_identifier)
        self.assertNotEqual(result.status, 'Upcoming Filing')

    def test_ordinary_dashed_location_and_multiword_names_keep_existing_plan(self):
        self.assertIsNone(c.explicit_legal_dba_acronym('Cure PSP - Charleston'))
        self.assertIsNone(c.explicit_legal_dba_acronym('Service Year Exchange \u2014 Service Year Alliance'))
        self.assertEqual(c.wv_preferred_query_variants('Cure PSP - Charleston', '')[0],
                         'Cure PSP Charleston')


class AcronymRetrievalTests(unittest.TestCase):
    class Lookup:
        def __init__(self, query, registry_name):
            self.query, self.registry_name, self.queries = query, registry_name, []

        def search(self, query):
            self.queries.append(query)
            if query != self.query:
                return 'No records found', []
            return 'Search results', [{'index': 0, 'count': 5,
                    'values': ['471', self.registry_name, 'Active'], 'target': '1'}]

        def detail(self, target, identifier):
            assert (target, identifier) == ('1', '471')
            return (f'Organization Name\n{self.registry_name}\nExpiration Date\n09/15/2027\n'
                    'Contact Name\nControl\nStatus\nActive\nStreet Address\nAddress\n'
                    'County\nDBA\nName\nNo Records\nTax Information')

    def run_lookup(self, name, query, registry_name):
        lookup = self.Lookup(query, registry_name)
        with patch.object(c, 'known_names_for_ein', return_value=[]):
            org = c.checker.Organization(name, '123456789')
            result = c.search_wv_precise(None, org, public_lookup=lookup)
            data = c.response_data_for_lookup(result, '', org, name, org.ein, 'WV', time.perf_counter())
        return data, lookup.queries

    def test_expanded_initialism_probes_exact_entered_legal_segment(self):
        name = 'WGU Corporation \u2014 Western Governors University'
        data, queries = self.run_lookup(name, 'WGU Corporation', 'WGU Corporation')
        self.assertEqual(queries[:2], ['WGU Corporation - Western Governors University', 'WGU Corporation'])
        self.assertEqual((data['status'], data['matched_registry_identifier']), ('Current', '471'))
        self.assertEqual(data['reason_code'], 'MATCH_WV_ENTERED_ACRONYM_EXPANSION')
        self.assertEqual(json.loads(data['debug_trace'])['accepted_candidate']['decision'], 'accepted')

    def test_dotted_initialism_probes_literal_registry_spelling(self):
        data, queries = self.run_lookup('ASPEN Rhoads Research Foundation',
                                        'A.S.P.E.N. Rhoads Research Foundation',
                                        'A.S.P.E.N. Rhoads Research Foundation, Inc.')
        self.assertEqual(queries[:2], ['ASPEN Rhoads Research Foundation',
                                       'A.S.P.E.N. Rhoads Research Foundation'])
        self.assertEqual((data['status'], data['matched_registry_identifier']), ('Current', '471'))
        self.assertEqual(data['reason_code'], 'MATCH_WV_DOTTED_ACRONYM')

    def test_unrelated_expansion_and_nearby_dotted_record_are_not_accepted(self):
        self.assertIsNone(c.explicit_legal_acronym_expansion('WGU Corporation - Western Governors College'))
        self.assertIsNone(c.explicit_legal_acronym_expansion('WGU Corporation - Charleston'))
        self.assertEqual(c.dotted_leading_acronym('River Rhoads Research Foundation'), '')
        data, _ = self.run_lookup('ASPEN Rhoads Research Foundation',
                                  'A.S.P.E.N. Rhoads Research Foundation',
                                  'A.S.P.E.N. Rhoads Foundation')
        self.assertFalse(data['matched_registry_identifier'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
