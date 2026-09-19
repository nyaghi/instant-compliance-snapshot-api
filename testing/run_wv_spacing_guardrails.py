"""Joined words must be retrievable without accepting a different entity."""
import sys
import unittest
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

    def test_missing_spacing_probe_cannot_complete_a_negative(self):
        self.assertFalse(c.wv_core_search_completed(['CurePSP', 'CurePSP, Inc.'],
            ['CurePSP', 'Cure PSP, Inc.', 'CurePSP, Inc.'], ['Cure PSP, Inc.']))
        self.assertTrue(c.wv_core_search_completed(['CurePSP', 'Cure PSP, Inc.'],
            ['CurePSP', 'Cure PSP, Inc.', 'CurePSP, Inc.'], ['Cure PSP, Inc.']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
