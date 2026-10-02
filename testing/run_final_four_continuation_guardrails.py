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
        # A completed empty legal-name query must still try the reviewed alias.
        # A fully confirmed legal-name positive has a separate early-end control.
        evidence = self.provider(response['query'])
        evidence.update(rows=[], total=0)
        _, next_response = self.advance(response, evidence)
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

    def test_failure_and_ui_retry_preserve_every_reviewed_alias(self):
        for state in self.orgs:
            with self.subTest(state=state):
                aliases = ['Verified Former Name', 'Distinct Reviewed Acronym']
                _, first = self.start(state, alternate_names=aliases)
                _, failed = self.request({'action': 'fail', 'check_token': first['check_token'],
                                          'reason': 'NY_CONNECTOR_TIMEOUT'})
                result = failed['result']
                self.assertEqual(result['reviewed_alternate_names'], aliases)
                # This is the normal results-page Retry input, including its
                # historical empty-array fallback that caused the regression.
                _, retry = self.start(state, alternate_names=result.get('reviewed_alternate_names', []))
                record = cc.ny_connector_unpack(retry['check_token'], self.auth['email'], self.auth['device_id'])
                self.assertEqual(record['alternate_names'], aliases)
                self.assertEqual(cc.REVIEWED_NAME_CONTEXT.get(), {})

    def test_invalid_evidence_failure_also_preserves_names(self):
        _, first = self.start('NV', alternate_names=['Reviewed Former Name'])
        _, failed = self.advance(first, evidence={'complete': False})
        self.assertEqual(failed['result']['reviewed_alternate_names'], ['Reviewed Former Name'])

    def test_search_cleaner_rejects_payload_and_nesting_limits(self):
        query = {'state': 'AL', 'operation': 'search', 'name': 'YWCA'}
        payload = {'state': 'AL', 'query': query, 'complete': True, 'verification_pending': False,
                   'headers': AL_HEADERS, 'rows': AL_ROWS, 'total': 2}
        self.assertEqual(cc.final_four_clean_evidence(payload, query), payload)
        for change in [{'rows': [AL_ROWS[0]]*501}, {'rows': [['x'*1501]*11]}, {'rows': [[[[[[['nested']]]]]]]}]:
            with self.assertRaises(ValueError): cc.final_four_clean_evidence({**payload, **change}, query)

    def test_nc_search_recovery_preserves_evidence_deadline_and_rotates_query(self):
        with patch.object(cc.time, 'time', return_value=1000):
            _, first = self.start('NC', recovery_protocol='nc-fresh-search-v1', alternate_names=['Example National Charity'])
            evidence = self.provider(first['query']); evidence.update(rows=[], total=0)
            _, pending = self.advance(first, evidence)
        with patch.object(cc.time, 'time', return_value=1060):
            _, recovered = self.request({'action':'fail', 'check_token':pending['check_token'],
                                        'query_id':pending['query_id'], 'reason':'NY_CONNECTOR_TAB_READY_TIMEOUT'})
            self.assertEqual(recovered['phase'], 'search')
            self.assertEqual(recovered['query'], pending['query'])
            self.assertNotEqual(recovered['query_id'], pending['query_id'])
            record = cc.ny_connector_unpack(recovered['check_token'], self.auth['email'], self.auth['device_id'])
            self.assertEqual(record['issued'],1000); self.assertEqual(record['expires'],1300)
            self.assertEqual(record['completed'],[{'query':first['query'],'evidence':evidence}])
            self.assertEqual(recovered['lookup_remaining_ms'],240000)
            self.assertEqual(self.advance(recovered, query_id=pending['query_id'])[0],409)
            _, final = self.request({'action':'fail','check_token':recovered['check_token'],
                                    'query_id':recovered['query_id'],'reason':'NY_CONNECTOR_TAB_READY_TIMEOUT'})
            self.assertEqual(final['phase'],'complete');self.assertEqual(final['result']['status'],'Unable to Confirm')

    def test_nc_recovery_never_retries_verification_other_states_or_expired_budget(self):
        for state, protocol, reason, delay, wrong_query in [
                ('NC','nc-fresh-search-v1','NY_CONNECTOR_NC_VERIFICATION_PENDING',60,False),
                ('NC','nc-fresh-search-v1','NY_CONNECTOR_TAB_READY_TIMEOUT',250,False),
                ('NC','nc-fresh-search-v1','NY_CONNECTOR_TAB_READY_TIMEOUT',60,True),
                ('NC','','NY_CONNECTOR_TAB_READY_TIMEOUT',60,False),
                ('NV','nc-fresh-search-v1','NY_CONNECTOR_TAB_READY_TIMEOUT',60,False),
                ('AL','nc-fresh-search-v1','NY_CONNECTOR_TAB_READY_TIMEOUT',60,False),
                ('TN','nc-fresh-search-v1','NY_CONNECTOR_TAB_READY_TIMEOUT',60,False)]:
            with self.subTest(state=state, reason=reason, delay=delay, protocol=protocol, wrong_query=wrong_query):
                with patch.object(cc.time,'time',return_value=1000):
                    _, response=self.start(state,recovery_protocol=protocol)
                with patch.object(cc.time,'time',return_value=1000+delay):
                    _, final=self.request({'action':'fail','check_token':response['check_token'],
                                          'query_id':'wrong' if wrong_query else response['query_id'],'reason':reason})
                    self.assertEqual(final['phase'],'complete')
                    self.assertEqual(final['result']['status'],'Unable to Confirm')

    def test_nc_recovery_never_reopens_an_unconfirmed_detail(self):
        _, response=self.start('NC',recovery_protocol='nc-fresh-search-v1')
        _, detail=self.advance(response)
        self.assertEqual(detail['query']['operation'],'detail')
        _, final=self.request({'action':'fail','check_token':detail['check_token'],
                              'query_id':detail['query_id'],'reason':'NY_CONNECTOR_TAB_READY_TIMEOUT'})
        self.assertEqual(final['phase'],'complete')

    def test_detail_identity_contact_and_history_are_bounded(self):
        query = {'state': 'NC', 'operation': 'detail', 'identifier': NC['License'], 'url': NC['profile_url']}
        payload = {'query': query, 'complete': True, 'fields': NC_PROFILE}
        self.assertEqual(cc.final_four_clean_evidence(payload, query), payload)
        for fields in [{**NC_PROFILE, 'Registration #': 'SL999999'}, {**NC_PROFILE, 'Phone': 'private'}]:
            with self.assertRaises(ValueError): cc.final_four_clean_evidence({**payload, 'fields': fields}, query)
        with self.assertRaises(ValueError):
            cc.final_four_clean_evidence({**payload, 'filings': {'rows': [{'type': 'Renewal', 'date': '1/1/2025', 'contact': 'private'}]}}, query)

    def test_nv_optional_filing_failure_diagnostic_survives_signed_replay(self):
        _, response = self.start('NV')
        _, detail = self.advance(response)
        payload = self.provider(detail['query'])
        payload['filings'] = {'complete': False, 'failure_code': 'REGISTRY_RESPONSE_INCOMPLETE'}
        self.assertEqual(cc.final_four_clean_evidence(payload, detail['query']), payload)
        _, continued = self.advance(detail, payload)
        # Scope remains unconfirmed, but valid core identity survives and the
        # master can finish its remaining names instead of failing this bridge.
        if continued['phase'] == 'search':
            saved = cc.ny_connector_unpack(continued['check_token'], self.auth['email'], self.auth['device_id'])
            self.assertEqual(saved['completed'][-1]['evidence']['filings'], payload['filings'])
        else:
            self.assertEqual(continued['result']['status'], 'Unable to Confirm')
            self.assertTrue(any(x['completed'] for x in __import__('json').loads(continued['result']['debug_trace'])['queries_attempted']))
        for bad in [{'complete': True, 'failure_code': 'REGISTRY_RESPONSE_INCOMPLETE'},
                    {'complete': False, 'failure_code': 'contact@example.com'},
                    {'complete': False, 'failure_code': 'REGISTRY_RESPONSE_INCOMPLETE', 'secret': 'private'}]:
            with self.assertRaises(ValueError):
                cc.final_four_clean_evidence({**payload, 'filings': bad}, detail['query'])

    def test_nv_large_complete_grid_is_compacted_only_after_master_matching(self):
        _, first=self.start('NV',alternate_names=['Example Alternate Charity'])
        payload=self.provider(first['query'])
        target=payload['rows'][0]
        unrelated=[{'name':'Unrelated Plumbing Business '+str(i),'identifier':'NV'+str(90000000+i),
                    'entity_type':'Domestic Limited Liability Company (86)','raw_status':'Active'} for i in range(1500)]
        alias={**target,'name':'Example Alternate Charity','identifier':'NV8888888'}
        unsupported={**target,'identifier':'NR20260930-1000','entity_type':'','raw_status':'Active'}
        payload.update(rows=unrelated+[target,alias,unsupported],total=len(unrelated)+3)
        _, continued=self.advance(first,payload)
        self.assertEqual(continued['phase'],'search')
        record=cc.ny_connector_unpack(continued['check_token'],self.auth['email'],self.auth['device_id'])
        saved=record['completed'][0]['evidence']
        self.assertEqual(saved['rows'],[target,alias,unsupported])
        self.assertEqual(saved['master_search_audit'],{'source_total':1503,'rejected':1500})
        self.assertLess(len(continued['check_token']),15000)
        self.assertEqual(cc.REVIEWED_NAME_CONTEXT.get(),{})
        # A client cannot claim that it filtered a complete grid itself.
        with self.assertRaises(ValueError): cc.final_four_clean_evidence(saved,first['query'])

    def test_nv_larger_bound_never_accepts_truncated_duplicate_or_oversized_grids(self):
        _, first=self.start('NV')
        payload=self.provider(first['query'])
        for change in [{'total':6000},{'rows':payload['rows']*6000,'total':6000},
                       {'rows':payload['rows']*10001,'total':10001},
                       {'complete':False},{'verification_pending':True}]:
            with self.subTest(change=list(change)),self.assertRaises(ValueError):
                cc.final_four_clean_evidence({**payload,**change},first['query'])

    def test_compaction_preserves_all_possible_and_conflicting_nv_candidates(self):
        record={'state':'NV','organization_name':'Example National Charity','ein':'123456789','alternate_names':[]}
        rows=[{'name':name,'identifier':'NV'+str(i),'entity_type':'Foreign Non-Profit Corporation (80)'}
              for i,name in enumerate(['Exact','Possible','Conflicting','Rejected'])]
        decisions=iter(['accepted','possible','conflict','rejected'])
        payload={'query':{'state':'NV','operation':'search','name':'Example'},'rows':rows,'total':4}
        with patch.object(cc,'score_candidate',side_effect=lambda *a,**kw:{'decision':next(decisions)}):
            compact=cc.final_four_compact_search_evidence(record,payload)
        self.assertEqual(compact['rows'],rows[:3])
        for state in ['AL','NC','TN']:
            self.assertIs(cc.final_four_compact_search_evidence({**record,'state':state},payload),payload)

    def test_nv_compacted_replay_preserves_positive_adverse_and_no_match_outcomes(self):
        org=self.orgs['NV']
        record={'state':'NV','organization_name':org.organization_name,'ein':org.ein,'alternate_names':[]}
        unrelated=[{'name':'Unrelated Plumbing Business','identifier':'NV90000001',
                    'entity_type':'Domestic Limited Liability Company (86)','raw_status':'Active'}]
        for raw_status, keep_target in [('Active',True),('Permanently Revoked',True),('Active',False)]:
            with self.subTest(raw_status=raw_status, keep_target=keep_target):
                def provider(query):
                    evidence=copy.deepcopy(self.provider(query))
                    if query['operation']=='search':
                        evidence['rows']=(evidence['rows'] if keep_target else [])+unrelated
                        evidence['total']=len(evidence['rows'])
                    else: evidence['fields']['Entity Status']=raw_status
                    return evidence
                original=cc.final_four_browser_lookup(org,'NV',provider)
                def compact_provider(query):
                    return cc.final_four_compact_search_evidence(record,provider(query))
                compact=cc.final_four_browser_lookup(org,'NV',compact_provider)
                for key in ['status','matched_registry_name','matched_registry_identifier','success']:
                    self.assertEqual(getattr(original,key,None),getattr(compact,key,None))


if __name__ == '__main__':
    unittest.main(verbosity=2)
