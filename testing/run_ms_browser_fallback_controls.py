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

    def test_descriptive_dash_component_retrieves_record_without_relaxing_identity(self):
        name = 'WGU Corporation - Western Governors University'
        org = cc.checker.Organization(name, '12-3456789')
        registry_name = 'Western Governors University'
        row = {'name': registry_name, 'identifier': '100000801',
               'raw_status': 'Current - Registered'}
        searched = []

        def evidence(query):
            if query['operation'] == 'detail':
                return self.detail(query, name=registry_name)
            searched.append(query['name'])
            return self.search(query, [row] if query['name'] == registry_name else [])

        result = cc.ms_browser_lookup(org, evidence)
        self.assertEqual(result.status, 'Upcoming Filing')
        self.assertEqual(searched, [name, 'WGU Corporation', registry_name])
        self.assertEqual(result.matched_registry_identifier, '100000801')

        # A matching search response containing a different entity is not a match.
        unrelated = {**row, 'name': 'Western Governors Foundation'}
        def unrelated_evidence(query):
            return self.search(query, [unrelated] if query['name'] == registry_name else [])
        unmatched = cc.ms_browser_lookup(org, unrelated_evidence)
        self.assertNotIn(unmatched.status, {'Current', 'Upcoming Filing', 'Exempt'})

    def test_exact_acronym_legal_component_needs_reviewed_identity(self):
        name = 'ABC Corporation - Atlantic Benefit College'
        org = cc.checker.Organization(name, '12-3456789')
        row = {'name': 'ABC Corporation', 'identifier': '100000801',
               'raw_status': 'Current - Registered'}
        searched = []

        def evidence(query):
            if query['operation'] == 'detail':
                return self.detail(query, name=row['name'])
            searched.append(query['name'])
            return self.search(query, [row] if query['name'] == row['name'] else [])

        # The exact supplied side is searched, but a row without corroborated
        # identity cannot be promoted from the combined name alone.
        uncorroborated = cc.ms_browser_lookup(org, evidence)
        self.assertIn('ABC Corporation', searched)
        self.assertNotIn(uncorroborated.status, {'Current', 'Upcoming Filing', 'Exempt'})

        searched.clear()
        corroborated = cc.ms_browser_lookup(org, evidence, ['ABC Corporation'])
        self.assertEqual(corroborated.status, 'Upcoming Filing')
        self.assertEqual(searched[:2], [name, 'ABC Corporation'])

    def test_empty_completed_searches_are_required_for_negative(self):
        calls = []
        def evidence(query):
            calls.append(query)
            return self.search(query, [])
        result = cc.ms_browser_lookup(self.org, evidence)
        self.assertEqual(result.status, 'Not Registered')
        self.assertGreater(len(calls), 1)
        self.assertEqual(len(calls), len(result.queries_attempted))

    def test_case_equivalent_discovery_name_does_not_repeat_public_searches(self):
        org = cc.checker.Organization('National Church Residences Foundation', '20-2308665')
        searched = []
        def evidence(query):
            searched.append(query['name'])
            return self.search(query, [])
        result = cc.ms_browser_lookup(org, evidence, ['NATIONAL CHURCH RESIDENCES FOUNDATION'])
        self.assertEqual(result.status, 'Not Registered')
        self.assertEqual(searched, cc.ms_name_search_plan(org.organization_name))
        self.assertEqual(len(result.queries_attempted), len(searched))

    def test_distinct_reviewed_alias_still_reaches_confirmed_record(self):
        org = cc.checker.Organization('Example Foundation', '58-2366765')
        searched = []
        def evidence(query):
            if query['operation'] == 'detail':
                return self.detail(query)
            searched.append(query['name'])
            return self.search(query, [self.row] if query['name'] == self.row['name'] else [])
        result = cc.ms_browser_lookup(org, evidence,
                                      ['EXAMPLE FOUNDATION', 'Better World Fund, Inc.'])
        self.assertEqual(result.status, 'Upcoming Filing')
        self.assertIn('Better World Fund, Inc.', searched)
        self.assertEqual(searched.count('Example Foundation'), 1)

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
