"""Saved public ORION evidence; no live transport or speed claim."""
import copy
import json
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as cc

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/nv-entity-number-exemption.json').read_text())
HEADERS = ['Filed Date', 'Effective Date', 'Filing Number', 'Filing Type', 'Source', 'No. of Pages']

class AsOf(date):
    @classmethod
    def today(cls): return cls(2026, 10, 14)

class EntityNumberControls(unittest.TestCase):
    def setUp(self):
        for key, value in [('trial_identity', {'label': 'trial'}), ('date', AsOf)]:
            p = patch.object(cc, key, return_value=value) if key == 'trial_identity' else patch.object(cc, key, value)
            p.start(); self.addCleanup(p.stop)
        self.fields = copy.deepcopy(FIXTURE['fields'])
        self.identifier = self.fields['Entity Number']

    def history(self, fields=None):
        fields = fields or self.fields
        return dict(identifier=fields['Entity Number'], name=fields['Entity Name'],
                    headers=HEADERS, rows=copy.deepcopy(FIXTURE['filing_rows']), total=1, complete=True)

    def test_real_exemption_and_independent_equivalent_shape(self):
        for fields in [self.fields, {**self.fields, 'Entity Name': 'Independent Community Arts Organization',
                                      'Entity Number': 'E76543212026-2'}]:
            with self.subTest(name=fields['Entity Name']):
                row = cc.nv_charity_detail_evidence(fields, fields['Entity Number'])
                self.assertEqual(row['status'], 'Unable to Confirm')
                self.assertTrue(row['requires_solicitation_history'])
                result = cc.nv_charity_filings_evidence(row, self.history(fields))
                self.assertEqual(result['status'], 'Exempt')
                self.assertEqual(result['solicitation_exemption_filed'], date(2026, 2, 20))

    def test_wrong_detail_identity_type_and_populated_business_id_refused(self):
        for changes in [{'Entity Number': 'E76543212026-2'}, {'NV Business ID': 'NV20261234567'},
                        {'Entity Type': 'Foreign Non-Profit Corporation (80)'}, {'Entity Number': ''}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cc.nv_charity_detail_evidence({**self.fields, **changes}, self.identifier)

    def test_incomplete_foreign_or_noncharity_history_never_establishes_exemption(self):
        record = cc.nv_charity_detail_evidence(self.fields, self.identifier)
        for changes in [{'identifier': 'E76543212026-2'}, {'name': 'Unrelated Corporation'},
                        {'complete': False}, {'total': 2}, {'rows': [], 'total': 0},
                        {'rows': [['02/20/2026', '02/20/2026', '123', 'Annual List', 'Email', '1']]}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cc.nv_charity_filings_evidence(record, {**self.history(), **changes})
        self.assertEqual(record['status'], 'Unable to Confirm')

    def test_expired_adverse_future_or_conflicting_exemption_stays_inconclusive(self):
        for fields in [{**self.fields, 'Entity Status': 'Revoked'},
                       {**self.fields, 'Annual Renewal Due Date/Expiration Date': '02/28/2026'}]:
            with self.assertRaises(ValueError):
                cc.nv_charity_filings_evidence(cc.nv_charity_detail_evidence(fields, self.identifier), self.history())
        for col, value in [(0, '02/20/2099'), (1, '02/20/2099'), (1, ''), (4, ''), (5, ''), (5, '0')]:
            history = self.history(); history['rows'][0][col] = value
            with self.subTest(column=col), self.assertRaises(ValueError):
                cc.nv_charity_filings_evidence(cc.nv_charity_detail_evidence(self.fields, self.identifier), history)
        history = self.history()
        history['rows'].append(['03/01/2026', '03/01/2026', '456', 'Charitable Solicitation Registration Statement', 'Email', '1'])
        history['total'] = 2
        with self.assertRaises(ValueError):
            cc.nv_charity_filings_evidence(cc.nv_charity_detail_evidence(self.fields, self.identifier), history)

    def lookup(self, history=True):
        def provider(query):
            if query['operation'] == 'search':
                return dict(query=query, state='NV', complete=True, verification_pending=False, total=1,
                            rows=[dict(name=self.fields['Entity Name'], identifier=self.identifier,
                                       entity_number=self.identifier, business_identifier_missing=True,
                                       entity_type=self.fields['Entity Type'], raw_status='Registered')])
            data = dict(query=query, complete=True, fields=self.fields, source_url=FIXTURE['source_url'])
            if history: data['filings'] = self.history()
            return data
        org = cc.checker.Organization(self.fields['Entity Name'], '72-0408946')
        with patch.object(cc, 'reconciled_registry_address', return_value={'decision':'not_available'}):
            return cc.final_four_browser_lookup(org, 'NV', provider, time.monotonic() + 10)

    def test_master_lookup_preserves_real_exemption_and_explicit_source_basis(self):
        result = self.lookup()
        self.assertEqual(result.status, 'Exempt')
        self.assertEqual(result.matched_registry_identifier, self.identifier)
        self.assertIn('source-confirmed exemption filing', result.source_note)

    def test_master_missing_history_is_not_negative_or_exempt(self):
        self.assertEqual(self.lookup(False).status, 'Unable to Confirm')

    def test_exemption_does_not_override_a_conflicting_ein(self):
        self.fields['FEIN'] = '13-1624103'
        result = self.lookup()
        self.assertNotEqual(result.status, 'Exempt')
        self.assertFalse(getattr(result, 'matched_registry_identifier', ''))

    def test_signed_detail_cleaner_accepts_only_exact_entity_number_detail(self):
        query = dict(state='NV', operation='detail', identifier=self.identifier)
        payload = dict(query=query, complete=True, fields=self.fields, source_url=FIXTURE['source_url'])
        self.assertEqual(cc.final_four_clean_evidence(payload, query)['fields'], self.fields)
        for changes in [{'Entity Number': 'E76543212026-2'}, {'NV Business ID': 'NV20261234567'},
                        {'Entity Type': 'Registered Agent'}]:
            with self.assertRaises(ValueError):
                cc.final_four_clean_evidence({**payload, 'fields': {**self.fields, **changes}}, query)

if __name__ == '__main__': unittest.main(verbosity=2)
