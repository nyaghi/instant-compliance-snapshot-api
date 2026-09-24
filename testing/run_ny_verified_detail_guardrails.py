"""The verified browser must supply fresh details without changing NY rules."""
import ast, copy, json, subprocess, unittest
from pathlib import Path
from unittest.mock import patch
from testing import run_ny_connector_guardrails as base

c = base.c
ROOT = Path(__file__).resolve().parents[1]

class VerifiedDetails(unittest.TestCase):
    def setUp(self):
        self.legacy = base.ConnectorTests()
        self.legacy.setUp()
        self.addCleanup(self.legacy.doCleanups)

    def start(self, rows=None):
        code, state = self.legacy.request(action='start', organization_name=base.ROW['orgName'],
            ein=base.ROW['ein'], connector_version='0.4.1')
        self.assertEqual(code, 200)
        self.assertEqual(state['query'], {'ein': base.ROW['ein']})
        _, state = self.legacy.submit(state, [base.ROW] if rows is None else rows)
        return state

    def finish(self, state, detail):
        code, result = self.legacy.submit(state, detail=detail)
        self.assertEqual(code, 200)
        self.legacy.session.get.assert_not_called()
        return result

    def test_current_uses_browser_detail_no_direct_server_request(self):
        state = self.start()
        self.assertEqual(state['query'], {'orgID': base.ROW['orgID']})
        result = self.finish(state, base.DETAIL)['result']
        self.assertEqual(result['status'], 'Current')
        self.assertEqual(result['computed_due_date'], '11/15/2027')

    def test_stale_and_empty_histories_preserve_existing_delinquency_rules(self):
        for documents in [{}, {'Annual Filing for Charitable Organizations': [{'fiscalYearEnd': '12/31/2023'}]}]:
            with self.subTest(documents=documents):
                result = self.finish(self.start(), {**base.DETAIL, 'documents': documents})['result']
                self.assertEqual(result['status'], 'Delinquent')

    def test_wrong_record_wrong_ein_and_incomplete_history_fail_closed(self):
        for change in [{'orgID': '11-22-33'}, {'ein': '987654321'}, {'documents': None},
                       {'documents': {'Annual Filing for Charitable Organizations': [{'fiscalYearEnd': 'bad'}]}},
                       {'documents': {'Annual Filing for Charitable Organizations': [{}]}}]:
            with self.subTest(change=change):
                result = self.finish(self.start(), {**base.DETAIL, **change})['result']
                self.assertEqual(result['status'], 'Unable to Confirm')

    def test_unrequested_detail_and_credentials_cannot_cross_contract(self):
        for field in ['token', 'cookie', 'authorization', 'password']:
            result = self.finish(self.start(), {**base.DETAIL, field: 'must-not-accept'})['result']
            self.assertEqual(result['status'], 'Unable to Confirm')
        state = self.start()
        _, result = self.legacy.submit(state, detail=base.DETAIL, query={'orgID': '99-99-99'})
        self.assertEqual(result['result']['status'], 'Unable to Confirm')

    def test_duplicate_records_both_details_required_before_selection(self):
        other = {**base.ROW, 'orgID': '11-22-33', 'orgName': 'Example National Foundation Former'}
        state = self.start([other, base.ROW])
        self.assertEqual(state['query'], {'orgID': other['orgID']})
        state = self.finish(state, {**base.DETAIL, **other, 'status': 'Inactive'})
        self.assertEqual(state['phase'], 'search')
        self.assertEqual(state['query'], {'orgID': base.ROW['orgID']})
        result = self.finish(state, {**base.DETAIL, 'status': 'Active'})['result']
        self.assertEqual(result['status'], 'Current')
        self.assertEqual(result['matched_registry_name'], base.ROW['orgName'])

    def test_equally_matching_duplicates_remain_inconclusive(self):
        other = {**base.ROW, 'orgID': '11-22-33'}
        state = self.start([base.ROW, other])
        state = self.finish(state, base.DETAIL)
        result = self.finish(state, {**base.DETAIL, **other})['result']
        self.assertEqual(result['status'], 'Unable to Confirm')

    def test_no_record_requires_all_completed_searches_and_no_detail(self):
        state = self.start([])
        while state['phase'] == 'search':
            self.assertNotIn('orgID', state['query'])
            _, state = self.legacy.submit(state, [])
        self.assertEqual(state['result']['status'], 'Not Registered')
        self.legacy.session.get.assert_not_called()

    def test_exempt_and_name_only_identity_controls(self):
        result = self.finish(self.start(), {**base.DETAIL, 'regType': 'EXEMPT'})['result']
        self.assertEqual(result['status'], 'Exempt')
        detail = {k:v for k,v in base.DETAIL.items() if k != 'documents'}
        self.assertEqual(self.finish(self.start(), {**detail, 'regStatute': 'Exempt'})['result']['status'], 'Exempt')
        state = self.start([])
        _, state = self.legacy.submit(state, [{**base.ROW, 'ein': ''}])
        result = self.finish(state, {**base.DETAIL, 'ein': ''})['result']
        self.assertEqual(result['status'], 'Current')

    def test_detail_failure_explanation_and_no_network_fallback(self):
        for reason in ['NY_CONNECTOR_DETAIL_INCOMPLETE', 'NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT', 'NY_CONNECTOR_DETAIL_LINK_MISSING']:
            state = self.start()
            _, response = self.legacy.request(action='fail', check_token=state['check_token'], reason=reason)
            self.assertEqual(response['result']['status'], 'Unable to Confirm')
            self.assertEqual(response['result']['status_reason'], reason)
        self.legacy.session.get.assert_not_called()

    def test_old_connector_gets_update_explanation_for_new_detail_401(self):
        self.legacy.session.get.return_value.status_code = 401
        self.legacy.session.get.return_value.raise_for_status.side_effect = OSError('HTTP Error 401: Invalid recaptcha token.')
        _, result = self.legacy.submit(self.legacy.start())
        self.assertEqual(result['result']['status'], 'Unable to Confirm')
        self.assertEqual(result['result']['status_reason'], 'NY_CONNECTOR_UPDATE_REQUIRED')

    def test_status_matching_discovery_and_other_state_functions_unchanged(self):
        before = subprocess.check_output(['git', 'show', 'fb193e6:registry_snapshot_server.py'], cwd=ROOT).decode('utf-8')
        after = (ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8')
        funcs = lambda source: {n.name: ast.dump(n) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
        old, new = funcs(before), funcs(after)
        self.assertEqual({k for k in old if old[k] != new.get(k)},
            {'search_ny_direct', 'ny_connector_advance', 'ny_connector_request', 'ny_connector_clean_response', 'ny_connector_failure'})

if __name__ == '__main__': unittest.main()
