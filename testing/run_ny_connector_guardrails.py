"""Staging connector contract, isolation, and unchanged master NY interpretation."""
import copy, json, os, subprocess, sys, threading, time, unittest, urllib.request, urllib.error
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

ROW = {'orgName': 'Example National Foundation', 'ein': '123456789', 'orgID': '10-20-30'}
DETAIL = {**ROW, 'regType': 'NFP', 'regStatute': '7A', 'documents': {
    'Annual Filing for Charitable Organizations': [{'fiscalYearEnd': '12/31/2025'}]}}
class Clock(date):
    @classmethod
    def today(cls): return cls(2026, 9, 11)

class ConnectorTests(unittest.TestCase):
    def setUp(self):
        key=patch.object(c,'NY_CONNECTOR_SIGNING_KEY','test-only-signing-key-not-a-real-secret-20260911');key.start();self.addCleanup(key.stop)
        self.auth = {'email': 'connector-test@compliance-express.com', 'admin_passcode': c.ADMIN_PASSCODE, 'device_id': 'test-browser-session-a'}
        for target, value in [('date', Clock), ('public_profile_for_ein', Mock(return_value={}))]:
            p=patch.object(c,target,value);p.start();self.addCleanup(p.stop)
        p=patch.object(c,'build_search_queries',return_value=['Example National Foundation','Example National']);p.start();self.addCleanup(p.stop)
        self.session=Mock();self.session.__enter__=Mock(return_value=self.session);self.session.__exit__=Mock(return_value=False)
        p=patch.object(c.curl_requests,'Session',return_value=self.session);p.start();self.addCleanup(p.stop)
        response=Mock(status_code=200);response.json.return_value={'success':True,'statusCode':200,'data':copy.deepcopy(DETAIL)}
        self.session.get.return_value=response
    def request(self, **fields): return c.ny_connector_request({**self.auth,**fields},c.NY_CONNECTOR_ORIGIN)
    def start(self):
        code, state=self.request(action='start',organization_name=ROW['orgName'],ein=ROW['ein'])
        self.assertEqual(code,200);self.assertEqual(state['phase'],'search');return state
    def submit(self,state,rows=...,**override):
        evidence={'query':state['query'],'http_status':200,'success':True,'statusCode':200,'rows':[ROW] if rows is ... else rows}
        return self.request(action='advance',check_token=state['check_token'],query_id=state['query_id'],evidence={**evidence,**override})
    def test_ein_first_no_search_http_request_before_browser_response(self):
        self.assertEqual(self.start()['query'],{'ein':ROW['ein']});self.session.get.assert_not_called()
    def test_positive_details_are_fetched_from_state_and_existing_rules_apply(self):
        state=self.start();code,result=self.submit(state)
        self.assertEqual(code,200);self.assertEqual(result['phase'],'complete')
        self.assertEqual(result['result']['status'],'Current');self.assertEqual(result['result']['computed_due_date'],'11/15/2027')
        self.session.get.assert_called_once()
        self.assertEqual(self.session.get.call_args.args[0],c.NY_REGISTRY_API+'/RegistryDetail')
        self.assertEqual(self.session.get.call_args.kwargs['params'],{'orgID':ROW['orgID']})
    def test_no_record_only_after_all_master_queries_complete(self):
        state=self.start();queries=[]
        for _ in range(3):
            queries.append(state['query']);_,state=self.submit(state,[])
        self.assertEqual(queries,[{'ein':ROW['ein']},{'orgName':ROW['orgName']},{'orgName':'Example National'}])
        self.assertEqual(state['result']['status'],'Not Registered');self.session.get.assert_not_called()
    def test_name_match_after_completed_empty_ein(self):
        state=self.start();_,state=self.submit(state,[]);self.assertEqual(state['query'],{'orgName':ROW['orgName']})
        _,result=self.submit(state);self.assertEqual(result['result']['status'],'Current')
    def test_ambiguous_exact_eins_do_not_choose_first(self):
        _,result=self.submit(self.start(),[ROW,{**ROW,'orgID':'11-22-33'}])
        self.assertEqual(result['result']['status'],'Unable to Confirm');self.session.get.assert_not_called()
    def test_wrong_first_row_does_not_win(self):
        _,result=self.submit(self.start(),[{**ROW,'ein':'987654321','orgName':'Other Corporation','orgID':'11-22-33'},ROW])
        self.assertEqual(result['result']['status'],'Current')
        self.assertEqual(self.session.get.call_args.kwargs['params'],{'orgID':'10-20-30'})
    def test_wrong_live_detail_ein_or_id_is_inconclusive(self):
        for field,value in [('ein','987654321'),('orgID','11-22-33')]:
            self.session.get.return_value.json.return_value={'success':True,'statusCode':200,'data':{**DETAIL,field:value}}
            _,result=self.submit(self.start());self.assertEqual(result['result']['status'],'Unable to Confirm')
    def test_exemption_preserved(self):
        self.session.get.return_value.json.return_value={'success':True,'statusCode':200,'data':{**DETAIL,'regStatute':'EXEMPT'}}
        _,result=self.submit(self.start());self.assertEqual(result['result']['status'],'Exempt')
    def test_missing_filing_data_is_inconclusive(self):
        self.session.get.return_value.json.return_value={'success':True,'statusCode':200,'data':{**DETAIL,'documents':None}}
        _,result=self.submit(self.start());self.assertEqual(result['result']['status'],'Unable to Confirm')
    def test_verification_timeout_closed_browser_and_missing_connector_never_negative(self):
        for reason in ['NY_CONNECTOR_VERIFICATION_REJECTED','NY_CONNECTOR_VERIFICATION_REQUIRED','NY_CONNECTOR_TIMEOUT','NY_CONNECTOR_BROWSER_CLOSED','NY_CONNECTOR_UNAVAILABLE','NY_CONNECTOR_BUSY','NY_CONNECTOR_VERIFICATION_NETWORK_ERROR','NY_CONNECTOR_SEARCH_NETWORK_ERROR','NY_CONNECTOR_UPDATE_REQUIRED']:
            state=self.start();_,result=self.request(action='fail',check_token=state['check_token'],reason=reason)
            self.assertEqual(result['result']['status'],'Unable to Confirm');self.assertFalse(result['result']['success']);self.assertEqual(result['result']['status_reason'],reason)
    def test_incomplete_malformed_wrong_query_extra_filters_are_inconclusive(self):
        cases=[{'http_status':401},{'success':False},{'statusCode':500},{'rows':None},
               {'rows':[{'orgName':'Missing identity'}]}, {'rows':[{**ROW,'orgID':'https://example.com'}]},
               {'query':{'ein':'987654321'}},{'query':{'ein':ROW['ein'],'state':'NY'}}, {'rows':[{**ROW,'token':'not-public-evidence'}]}]
        for fields in cases:
            _,result=self.submit(self.start(),**fields)
            self.assertEqual(result['result']['status'],'Unable to Confirm')
    def test_malformed_failure_reason_and_action_are_safe(self):
        for reason in [{}, [], None, 42]:
            state=self.start();code,result=self.request(action='fail',check_token=state['check_token'],reason=reason)
            self.assertEqual(code,200);self.assertEqual(result['result']['status'],'Unable to Confirm')
            self.assertEqual(result['result']['status_reason'],'NY_CONNECTOR_INCOMPLETE')
        for action in [{}, [], None, 42]:
            self.assertEqual(self.request(action=action)[0],400)
    def test_tokens_bound_to_device_and_email(self):
        state=self.start()
        for fields in [{'device_id':'another-browser-session'},{'email':'another@compliance-express.com'}]:
            code,_=self.request(action='advance',check_token=state['check_token'],query_id=state['query_id'],**fields);self.assertEqual(code,410)
    def test_query_nonce_blocks_replays_and_cross_check_responses(self):
        a=self.start();b=self.start()
        code,_=self.request(action='advance',check_token=a['check_token'],query_id=b['query_id']);self.assertEqual(code,409)
        _,next_state=self.submit(a,[])
        code,_=self.request(action='advance',check_token=next_state['check_token'],query_id=a['query_id']);self.assertEqual(code,409)
        self.assertNotEqual(a['query_id'],next_state['query_id'])
    def test_short_lived_retry_refetches_live_detail_and_cannot_extend_expiry(self):
        state=self.start();self.submit(state);code,result=self.submit(state)
        self.assertEqual(code,200);self.assertEqual(result['result']['status'],'Current');self.assertEqual(self.session.get.call_count,2)
        with patch.object(c.time,'time',return_value=time.time()+301):self.assertEqual(self.submit(state)[0],410)
    def test_expired_and_tampered_tokens_fail_closed(self):
        state=self.start()
        with patch.object(c.time,'time',return_value=time.time()+301):self.assertEqual(self.submit(state)[0],410)
        original=state['check_token']
        for token in ['x'+original[1:],original[:-1]+('a' if original[-1]!='a' else 'b'),'malformed',original+'.extra']:
            self.assertEqual(self.submit({**state,'check_token':token})[0],410)
        self.assertEqual(self.request(action='cancel',check_token=original)[1]['phase'],'canceled')
    def test_staging_origin_internal_auth_and_valid_identity_required(self):
        for origin in ['','https://compliance-express.com','https://staging.compliance-express.com.evil.example']:
            self.assertEqual(c.ny_connector_request(self.auth,origin)[0],404)
        with patch.object(c,'APP_VERSION','2026.09.11.1'):
            self.assertEqual(self.request(action='start')[0],404)
        self.assertEqual(self.request(action='start',admin_passcode='invalid')[0],403)
        for ein in ['000000000','123','1234567890']:
            self.assertEqual(self.request(action='start',organization_name='Example',ein=ein)[0],400)
    def test_missing_or_different_signing_key_fails_closed(self):
        state=self.start()
        with patch.object(c,'NY_CONNECTOR_SIGNING_KEY',''):
            self.assertEqual(self.request(action='start')[0],503)
        with patch.object(c,'NY_CONNECTOR_SIGNING_KEY','a-different-test-only-key-12345678901234567890'):
            self.assertEqual(self.submit(state)[0],410)
    def test_continuation_works_across_fresh_processes_without_shared_memory(self):
        child='''import json,sys;from unittest.mock import patch;import registry_snapshot_server as c
p=json.load(sys.stdin);p.update(email='process-test@compliance-express.com',admin_passcode=c.ADMIN_PASSCODE,device_id='cross-process-browser')
with patch.object(c,'public_profile_for_ein',return_value={}),patch.object(c,'build_search_queries',return_value=['Example National Foundation']):
 print(json.dumps(c.ny_connector_request(p,c.NY_CONNECTOR_ORIGIN)))
'''
        def process(payload):
            env={**os.environ,'CE_NY_CONNECTOR_SIGNING_KEY':c.NY_CONNECTOR_SIGNING_KEY}
            result=subprocess.run([sys.executable,'-X','utf8','-c',child],input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8',env=env,cwd=Path(__file__).resolve().parents[1],timeout=20)
            self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
        code,state=process({'action':'start','organization_name':ROW['orgName'],'ein':ROW['ein']});self.assertEqual(code,200)
        code,next_state=process({'action':'advance','check_token':state['check_token'],'query_id':state['query_id'],'evidence':{'query':state['query'],'http_status':200,'success':True,'statusCode':200,'rows':[]}})
        self.assertEqual(code,200);self.assertEqual(next_state['query'],{'orgName':ROW['orgName']})
        code,final=process({'action':'fail','check_token':next_state['check_token'],'reason':'NY_CONNECTOR_UNAVAILABLE'})
        self.assertEqual(code,200);self.assertEqual(final['result']['status'],'Unable to Confirm')
    def test_real_http_handler_contract(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),c.RegistrySnapshotHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/ny-connector',data=json.dumps({**self.auth,'action':'start','organization_name':ROW['orgName'],'ein':ROW['ein']}).encode(),headers={'Content-Type':'application/json','Origin':c.NY_CONNECTOR_ORIGIN})
        with urllib.request.urlopen(request,timeout=3) as r:
            self.assertEqual(r.headers['Cache-Control'],'no-store');self.assertEqual(json.load(r)['query'],{'ein':ROW['ein']})

if __name__=='__main__':unittest.main(verbosity=2)
