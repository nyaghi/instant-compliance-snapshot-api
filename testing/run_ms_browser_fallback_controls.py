"""Bounded Mississippi public-browser fallback controls; no live registry calls."""
import unittest
from unittest.mock import patch
from pathlib import Path

import registry_snapshot_server as cc
from deployment import performance_lab


class MississippiBrowserFallbackControls(unittest.TestCase):
    def setUp(self):
        self.org = cc.checker.Organization('Better World Fund, Inc.', '58-2366765')
        self.row = {'name': 'Better World Fund, Inc.', 'identifier': '100000800',
                    'raw_status': 'Current - Registered'}

    def search(self, query, rows):
        return {'state': 'MS', 'query': query, 'complete': True,
                'verification_pending': False, 'rows': rows, 'total': len(rows)}

    def detail(self, query, *, name='Better World Fund, Inc.', filing='Current - Registered'):
        return {'query': query, 'complete': True,
                'fields': {'Name': name, 'Filing Number': query['identifier'],
                           'Filing Status': filing, 'Expiration Date': '11/15/2026',
                           'Registered Name': name}, 'source_url': cc.MS_BROWSER_SOURCE}

    def test_current_record_uses_master_identity_and_due_date(self):
        def evidence(query):
            return self.search(query, [self.row]) if query['operation'] == 'search' else self.detail(query)
        result = cc.ms_browser_lookup(self.org, evidence)
        self.assertEqual(result.status, 'Upcoming Filing')
        self.assertEqual(result.matched_registry_identifier, '100000800')
        self.assertIn('Expiration Date: 11/15/2026', result.raw_status_text)

    def test_empty_completed_searches_are_required_for_negative(self):
        calls = []
        def evidence(query):
            calls.append(query)
            return self.search(query, [])
        result = cc.ms_browser_lookup(self.org, evidence)
        self.assertEqual(result.status, 'Not Registered')
        self.assertGreater(len(calls), 1)
        self.assertEqual(len(calls), len(result.queries_attempted))

    def test_unrelated_and_ambiguous_records_are_never_assigned_positive_status(self):
        unrelated = {**self.row, 'name': 'Better World Community Fund'}
        with patch.object(cc, 'ms_name_search_plan', return_value=['Better World Fund, Inc.']):
            result = cc.ms_browser_lookup(self.org, lambda query: self.search(query, [unrelated]))
        self.assertNotIn(result.status, {'Current', 'Upcoming Filing', 'Exempt'})
        with patch.object(cc, 'ms_name_search_plan', return_value=['Better World Fund, Inc.']):
            result = cc.ms_browser_lookup(self.org, lambda query: self.search(query, [self.row, {**self.row, 'identifier': '100000801'}]))
        self.assertEqual(result.status, 'Needs Review')

    def test_partial_or_mismatched_evidence_cannot_become_not_registered(self):
        query = {'state': 'MS', 'operation': 'search', 'name': self.org.organization_name}
        for evidence in [
            {**self.search(query, []), 'total': 1},
            {**self.search(query, []), 'query': {**query, 'name': 'Different'}},
            {**self.search(query, []), 'complete': False},
        ]:
            with self.assertRaises(ValueError):
                cc.ms_browser_clean_evidence(evidence, query)

    def test_sales_uses_entered_name_only_while_standard_uses_signed_alias(self):
        entered = cc.checker.Organization('Example Foundation', '58-2366765')
        alias = 'Better World Fund, Inc.'
        searched = []
        def evidence(query):
            if query['operation'] == 'detail':
                return self.detail(query)
            searched.append(query['name'])
            return self.search(query, [self.row] if query['name'] == alias else [])
        def no_ein_discovery(ein):
            if ein:
                raise AssertionError('EIN discovery cache used')
            return []
        with patch.object(cc, 'ms_name_search_plan', side_effect=lambda name, ein: [name]), \
             patch.object(cc, 'known_names_for_ein', side_effect=no_ein_discovery):
            sales = cc.ms_browser_lookup(entered, evidence)
            self.assertEqual(sales.status, 'Not Registered')
            self.assertEqual(searched, ['Example Foundation'])
            searched.clear()
            standard = cc.ms_browser_lookup(entered, evidence, [alias])
            self.assertEqual(standard.status, 'Upcoming Filing')
            self.assertEqual(searched, ['Example Foundation', alias])

    def test_signed_trial_continuation_keeps_master_interpretation(self):
        origin = 'https://fixture-final-four.onrender.com'
        auth = {'email': 'test@compliance-express.com', 'admin_passcode': 'fixture',
                'device_id': 'fixture-device'}
        with patch.object(cc, 'trial_identity', return_value={'origin': origin}), \
             patch.object(cc, 'is_verified_internal_passcode', return_value=True), \
             patch.object(cc, 'NY_CONNECTOR_SIGNING_KEY', 'test-only-not-a-real-secret-'*3):
            code, response = cc.final_four_connector_request({**auth, 'action': 'start',
                'state': 'MS', 'mode': 'standard', 'organization_name': self.org.organization_name,
                'ein': self.org.ein}, origin)
            self.assertEqual(code, 200)
            self.assertEqual(response['phase'], 'search')
            for _ in range(10):
                query = response['query']
                evidence = self.search(query, [self.row]) if query['operation'] == 'search' else self.detail(query)
                code, response = cc.final_four_connector_request({**auth, 'action': 'advance',
                    'query_id': response['query_id'], 'check_token': response['check_token'],
                    'evidence': evidence}, origin)
                self.assertEqual(code, 200)
                if response['phase'] == 'complete': break
            self.assertEqual(response['phase'], 'complete')
            self.assertEqual(response['result']['status'], 'Upcoming Filing')

    def test_composed_lab_assets_route_ms_to_browser_connector(self):
        root = Path(performance_lab.__file__).resolve().parents[1] / 'web-staging'
        with patch.object(performance_lab, 'trial_identity', return_value={'origin': 'https://trial.example'}):
            index = performance_lab.final_four_asset('index.html', (root / 'index.html').read_text(encoding='utf-8'))
            workflows = performance_lab.final_four_asset('optimized-workflows.js', (root / 'optimized-workflows.js').read_text(encoding='utf-8'))
            connector = performance_lab.final_four_asset('ny-connector.js', (root / 'ny-connector.js').read_text(encoding='utf-8'))
        self.assertIn('!["NY", "IL", "GA", "AL", "NC", "NV", "TN", "NM", "MS"].includes(state)', index)
        self.assertIn('["NY", "IL", "GA", "AL", "NC", "NV", "TN", "NM", "MS"].includes(state)', index)
        self.assertIn("states.filter(s=>['NY','IL','GA','AL','NC','NV','TN','NM','MS'].includes(s))", workflows)
        self.assertIn('MS:"Mississippi"', connector)


if __name__ == '__main__':
    unittest.main()
