"""Signed browser continuation controls; no live requests or credentials."""
import copy
import json
import time
import unittest
from unittest.mock import patch

import registry_snapshot_server as cc
from testing import run_final_four_source_guardrails as source_controls
from testing.run_final_four_source_guardrails import AL_HEADERS, AL_ROWS, NC, NC_PROFILE


class ContinuationControls(unittest.TestCase):
    provider = source_controls.LookupControls.provider

    def setUp(self):
        source_controls.LookupControls.setUp(self)
        self.origin = 'https://fixture-final-four.onrender.com'
        for key, opts in [('trial_identity', {'return_value': {'origin': self.origin}}),
                          ('is_verified_internal_passcode', {'return_value': True})]:
            p = patch.object(cc, key, **opts); p.start(); self.addCleanup(p.stop)
        p = patch.object(cc, 'NY_CONNECTOR_SIGNING_KEY', 'test-only-not-a-real-secret-'*3)
        p.start(); self.addCleanup(p.stop)
        self.auth = {'email': 'test@compliance-express.com', 'admin_passcode': 'fixture', 'device_id': 'fixture-device'}

    def request(self, payload, origin=None):
        return cc.final_four_connector_request({**self.auth, **payload}, self.origin if origin is None else origin)

    def start(self, state='NC', **kwargs):
        org = self.orgs[state]
        return self.request({'action': 'start', 'state': state, 'organization_name': org.organization_name,
                             'ein': org.ein, **kwargs})

    def advance(self, response, evidence=None, **kwargs):
        return self.request({'action': 'advance', 'query_id': response['query_id'],
                             'check_token': response['check_token'],
                             'evidence': self.provider(response['query']) if evidence is None else evidence, **kwargs})

    def test_all_four_complete_through_signed_master_replay(self):
        for state in self.orgs:
            code, response = self.start(state)
            iterations = 0
            while response.get('phase') == 'search' and iterations < 30:
                iterations += 1
                self.assertEqual(code, 200)
                code, response = self.advance(response)
            self.assertEqual(response.get('phase'), 'complete', (state, response))
            self.assertIn(response['result']['status'], ['Current', 'Upcoming Filing'], (state, response))

    def test_disabled_or_wrong_origin_never_enters_auth_or_source_lookup(self):
        for origin in ['https://staging.compliance-express.com', 'https://www.compliance-express.com', '', self.origin+'.evil.test']:
            with patch.object(cc, 'is_verified_internal_passcode', side_effect=AssertionError('No authentication on wrong origin')):
                self.assertEqual(self.request({'action': 'start'}, origin)[0], 404)
        with patch.object(cc, 'trial_identity', return_value=None):
            self.assertEqual(self.start()[0], 404)

    def test_authentication_and_signed_device_binding_are_required(self):
        with patch.object(cc, 'is_verified_internal_passcode', return_value=False):
            self.assertEqual(self.start()[0], 403)
        _, response = self.start()
        self.assertEqual(self.advance(response, device_id='another-device')[0], 410)
        self.assertEqual(self.advance(response, check_token=response['check_token']+'bad')[0], 410)
        self.assertEqual(self.advance(response, query_id='wrong-query')[0], 409)

    def test_other_connector_continuation_cannot_be_reused(self):
        _, response = self.start()
        record = cc.ny_connector_unpack(response['check_token'], self.auth['email'], self.auth['device_id'])
        record['protocol'] = 'other'
        self.assertEqual(self.advance(response, check_token=cc.ny_connector_pack(record))[0], 410)

    def test_budget_is_fixed_and_sales_is_sixty_seconds(self):
        with patch.object(cc.time, 'time', return_value=1000):
            _, response = self.start(mode='sales')
            record = cc.ny_connector_unpack(response['check_token'], self.auth['email'], self.auth['device_id'])
            self.assertEqual(record['expires'], 1060)
        with patch.object(cc.time, 'time', return_value=1030):
            _, second = self.advance(response)
            self.assertEqual(second['lookup_remaining_ms'], 30000)
        with patch.object(cc.time, 'time', return_value=1061):
            self.assertEqual(self.advance(second)[0], 410)

    def test_reviewed_names_survive_signed_round_trip_and_precede_generated_names(self):
        _, response = self.start('AL', alternate_names=['YWCA USA, Inc.'])
        _, next_response = self.advance(response)
        self.assertEqual(next_response['query']['name'], 'YWCA USA, Inc.')
        self.assertEqual(cc.REVIEWED_NAME_CONTEXT.get(), {})

    def test_incomplete_foreign_and_extra_private_data_never_become_negative(self):
        for change in [{'complete': False}, {'query': {}}, {'captcha': 'do-not-retain'}, {'total': 100},
                       {'rows': [{**NC, 'Contact': 'Do not forward this'}]}]:
            _, response = self.start()
            evidence = {**self.provider(response['query']), **change}
            code, final = self.advance(response, evidence)
            self.assertEqual(code, 200)
            self.assertEqual(final['result']['status'], 'Unable to Confirm')

    def test_failure_explains_verification_and_cancel_is_local(self):
        _, response = self.start('AL')
        code, final = self.request({'action': 'fail', 'check_token': response['check_token'], 'reason': 'NY_CONNECTOR_AL_VERIFICATION_REQUIRED'})
        self.assertEqual(code, 200)
        self.assertEqual(final['result']['status'], 'Unable to Confirm')
        self.assertIn('verification', final['result']['comments'])
        self.assertEqual(self.request({'action': 'cancel', 'check_token': response['check_token']})[1], {'phase': 'canceled'})

    def test_failure_diagnostics_expose_public_query_stage_without_secrets(self):
        _, response = self.start('NC')
        _, second = self.advance(response)
        _, final = self.request({'action': 'fail', 'check_token': second['check_token'], 'reason': 'NY_CONNECTOR_TAB_READY_TIMEOUT'})
        trace = json.loads(final['result']['debug_trace'])['queries_attempted']
        self.assertTrue(trace[0]['completed'])
        self.assertFalse(trace[-1]['completed'])
        self.assertEqual(trace[-1]['query']['state'], 'NC')
        rendered = json.dumps(trace)
        for secret in [self.auth['email'], self.auth['device_id'], second['check_token'], 'profile_url', 'evidence']:
            self.assertNotIn(secret, rendered)

    def test_search_cleaner_rejects_payload_and_nesting_limits(self):
        query = {'state': 'AL', 'operation': 'search', 'name': 'YWCA'}
        payload = {'state': 'AL', 'query': query, 'complete': True, 'verification_pending': False,
                   'headers': AL_HEADERS, 'rows': AL_ROWS, 'total': 2}
        self.assertEqual(cc.final_four_clean_evidence(payload, query), payload)
        for change in [{'rows': [AL_ROWS[0]]*501}, {'rows': [['x'*1501]*11]}, {'rows': [[[[[[['nested']]]]]]]}]:
            with self.assertRaises(ValueError): cc.final_four_clean_evidence({**payload, **change}, query)

    def test_detail_identity_contact_and_history_are_bounded(self):
        query = {'state': 'NC', 'operation': 'detail', 'identifier': NC['License'], 'url': NC['profile_url']}
        payload = {'query': query, 'complete': True, 'fields': NC_PROFILE}
        self.assertEqual(cc.final_four_clean_evidence(payload, query), payload)
        for fields in [{**NC_PROFILE, 'Registration #': 'SL999999'}, {**NC_PROFILE, 'Phone': 'private'}]:
            with self.assertRaises(ValueError): cc.final_four_clean_evidence({**payload, 'fields': fields}, query)
        with self.assertRaises(ValueError):
            cc.final_four_clean_evidence({**payload, 'filings': {'rows': [{'type': 'Renewal', 'date': '1/1/2025', 'contact': 'private'}]}}, query)


if __name__ == '__main__':
    unittest.main(verbosity=2)
