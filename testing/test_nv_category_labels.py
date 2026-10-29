"""Category-label regression: saved source shape, no live registry requests."""
import unittest
from unittest.mock import patch
from testing.test_nv_entity_number import EntityNumberControls, FIXTURE
import registry_snapshot_server as cc


class CategoryLabelControls(EntityNumberControls):
    def test_category_variants_reach_same_filing_status(self):
        original = self.fields['Entity Type']
        for label in [original, original.replace(' to ', ' To '),
                      original.upper(), original.lower(),
                      '  ' + ' \t '.join(original.split()) + '\n']:
            with self.subTest(label=label):
                self.fields['Entity Type'] = label
                result = self.lookup()
                self.assertEqual(result.status, 'Exempt')
                self.assertEqual(result.matched_registry_identifier, self.identifier)
                self.assertEqual(self.lookup(False).status, 'Unable to Confirm')

    def test_unknown_types_are_not_promoted_by_normalization(self):
        for label in ['Registered Agent', 'Foreign Corporation (80)', '',
                      'Foreign Entities Not Required To Register In Nevada Extra',
                      'Foreign Entities Required To Register In Nevada']:
            with self.subTest(label=label):
                self.fields['Entity Type'] = label
                with self.assertRaises(ValueError):
                    cc.nv_charity_detail_evidence(self.fields, self.identifier)

    def test_grid_detail_case_difference_is_allowed_but_changed_type_is_not(self):
        parse = cc.nv_charity_detail_evidence
        def changed(fields, identifier):
            return {**parse(fields, identifier), 'entity_type': fields['Entity Type'].upper()}
        with patch.object(cc, 'nv_charity_detail_evidence', side_effect=changed):
            self.assertEqual(self.lookup().status, 'Exempt')
        def wrong_type(fields, identifier):
            return {**parse(fields, identifier), 'entity_type': 'Charitable Solicitation Registration Statement'}
        with patch.object(cc, 'nv_charity_detail_evidence', side_effect=wrong_type):
            with self.assertRaises(ValueError):
                self.lookup()

    def test_all_allowed_labels_and_unknown_values(self):
        for label in cc.NV_CHARITY_ENTITY_TYPES:
            for variant in [label, label.upper(), label.lower(), '  ' + ' \t '.join(label.split())]:
                self.assertTrue(cc.nv_entity_type_in(variant))
        for value in [None, 1, {}, '', 'Registered Agent', 'Foreign Corporation (80)']:
            self.assertFalse(cc.nv_entity_type_in(value))

    def test_evidence_cleaner_retains_original_category_text(self):
        query = dict(state='NV', operation='detail', identifier=self.identifier)
        for label in [self.fields['Entity Type'].upper(), '  ' + '  '.join(self.fields['Entity Type'].split())]:
            fields = {**self.fields, 'Entity Type': label}
            payload = dict(query=query, complete=True, fields=fields, source_url=FIXTURE['source_url'])
            self.assertEqual(cc.final_four_clean_evidence(payload, query)['fields'], fields)

    def test_variant_still_rejects_wrong_identity_and_conflicting_ein(self):
        self.fields['Entity Type'] = self.fields['Entity Type'].upper()
        with self.assertRaises(ValueError):
            cc.nv_charity_detail_evidence(self.fields, 'E76543212026-2')
        self.fields['FEIN'] = '13-1624103'
        self.assertNotEqual(self.lookup().status, 'Exempt')


if __name__ == '__main__':
    unittest.main(verbosity=2)
