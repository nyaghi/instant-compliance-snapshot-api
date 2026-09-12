"""Real extension, browser form, staging UI bridge and master API against fixtures.

Routes NY/Google traffic to deterministic local test documents. This test does
not claim live verification acceptance. No real state request is made.
"""
import json, sys, tempfile, threading, time, unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

WORK=Path(__file__).resolve().parents[1]
ROW={'orgName':'Example National Foundation','ein':'123456789','orgID':'10-20-30'}
FORM='''<!doctype html><input id="orgName"><input id="ein"><input id="orgID"><input id="city">
<button id="clear">Clear fields</button><button id="verify">Verify</button><button id="search" disabled>Search</button>
<div id="old">Old table row is deliberately present before the current query finishes.</div>
<script>
function request(path,method){return new Promise(resolve=>{const x=new XMLHttpRequest();x.open(method,'https://charities-search-api.ag.ny.gov'+path);x.onload=()=>resolve(JSON.parse(x.responseText));x.send();});}
clear.onclick=()=>{document.querySelectorAll('input').forEach(i=>i.value='');search.disabled=true;};
verify.onclick=async()=>{const p=await request('/api/recaptcha/verify','POST');if(p.verified)search.disabled=false;};
search.onclick=async()=>{const q=new URLSearchParams();['ein','orgName','orgID','city'].forEach(id=>{if(document.getElementById(id).value)q.set(id,document.getElementById(id).value);});q.set('token','fixture-token-must-not-cross-bridge');await request('/api/FileNet/RegistrySearch?'+q,'GET');};
</script>'''
PAGE='''<!doctype html><title>Connector browser integration fixture</title><script src="/ny-connector.js"></script>'''

class BrowserIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key_patch=patch.object(c,'NY_CONNECTOR_SIGNING_KEY','browser-test-only-signing-key-not-a-real-secret');cls.key_patch.start()
        cls.temp=tempfile.TemporaryDirectory(prefix='cc-ny-extension-test-')
        cls.playwright=c.checker.sync_playwright().start()
        extension_path=getattr(cls,'extension_path',WORK/'browser-connector')
        cls.context=cls.playwright.chromium.launch_persistent_context(cls.temp.name,headless=True,channel='chromium',
            args=[f'--disable-extensions-except={extension_path}',f'--load-extension={extension_path}'])
        cls.observations=[]
        cls.context.on('page',lambda page: page.on('pageerror',lambda error: cls.observations.append({'page_error':str(error),'stack':error.stack})))
        cls.context.route('**/*',cls.route)
        worker=cls.context.service_workers[0] if cls.context.service_workers else cls.context.wait_for_event('serviceworker')
        # Chromium extension-created tabs can start their initial navigation before
        # Playwright attaches. In this fixture harness only, defer navigation until
        # the context route is attached, preventing accidental real state traffic.
        cls.worker=worker
        worker.evaluate('''() => {globalThis.testCreatedTabs=[];globalThis.testCreatedOptions=[];const original=chrome.tabs.create.bind(chrome.tabs);chrome.tabs.create=async options=>{testCreatedOptions.push(options);
          const tab=await original({...options,url:'about:blank'});await new Promise(r=>setTimeout(r,500));
          testCreatedTabs.push(tab.id);await chrome.tabs.update(tab.id,{url:options.url});return tab;};}''')
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),c.RegistrySnapshotHandler)
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.trace=[];cls.accepted=True;cls.mode='positive';cls.state_calls=[];cls.failure='';cls.verifies=0;cls.advance_delay=0
    @classmethod
    def tearDownClass(cls):
        cls.context.close();cls.playwright.stop();cls.server.shutdown();cls.server.server_close();cls.temp.cleanup();cls.key_patch.stop()
    @classmethod
    def route(cls,route):
        from urllib.parse import urlparse,parse_qs
        u=urlparse(route.request.url)
        cls.observations.append({'host':u.hostname,'path':u.path})
        if u.hostname=='staging.compliance-express.com':
            if u.path=='/ny-connector.js':route.fulfill(content_type='application/javascript',body=(WORK/'web-staging/ny-connector.js').read_text())
            elif u.path=='/full-ui':route.fulfill(content_type='text/html',body=(WORK/'web-staging/index.html').read_text(encoding='utf-8'))
            else:route.fulfill(content_type='text/html',body=PAGE)
        elif u.hostname in {'instant-compliance-snapshot-api-staging-8dnk.onrender.com','instant-compliance-snapshot-api-staging.onrender.com'} and u.path=='/api/check':
            headers={'Access-Control-Allow-Origin':c.NY_CONNECTOR_ORIGIN,'Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'POST'}
            if route.request.method=='OPTIONS':route.fulfill(status=200,headers=headers)
            else:
                payload=route.request.post_data_json;cls.state_calls.append(payload['states'])
                result={'state':payload['states'][0],'status':'Current','success':True,'organization_name':ROW['orgName'],'ein':ROW['ein'],'comments':'Mature-state transport control.'}
                route.fulfill(status=200,content_type='application/json',body=json.dumps({'results':[result]}),headers=headers)
        elif u.hostname=='instant-compliance-snapshot-api-staging-8dnk.onrender.com' and u.path=='/api/ny-connector':
            if route.request.method=='OPTIONS':route.fulfill(status=200,headers={'Access-Control-Allow-Origin':c.NY_CONNECTOR_ORIGIN,'Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Methods':'POST'})
            else:
                payload=route.request.post_data_json
                if payload.get('action')=='advance':
                    cls.trace.append(payload['evidence'])
                    if len(cls.trace)==1 and cls.advance_delay:time.sleep(cls.advance_delay)
                code,response=c.ny_connector_request(payload,c.NY_CONNECTOR_ORIGIN)
                route.fulfill(status=code,content_type='application/json',body=json.dumps(response),headers={'Access-Control-Allow-Origin':c.NY_CONNECTOR_ORIGIN})
        elif u.hostname=='charities-search.ag.ny.gov':
            body=FORM
            if cls.failure=='fetch':
                body=body.replace("const x=new XMLHttpRequest();", "fetch('https://charities-search-api.ag.ny.gov'+path,{method}).then(r=>r.json()).then(resolve).catch(()=>{});return;const x=new XMLHttpRequest();")
            elif cls.failure=='abort':
                body=body.replace('x.send();', "x.send();if(path.endsWith('/verify')&&(window.testVerifyCount=(window.testVerifyCount||0)+1)===2)queueMicrotask(()=>x.abort());")
            elif cls.failure=='timeout':
                body=body.replace('x.send();', 'x.timeout=80;x.send();')
            elif cls.failure=='stale':
                body=body.replace('x.send();', "if(path.endsWith('/verify')){if(window.oldVerify)window.oldVerify.dispatchEvent(new Event('error'));else window.oldVerify=x;}x.send();")
            route.fulfill(content_type='text/html',body=body)
        elif u.hostname=='charities-search-api.ag.ny.gov':
            if u.path.endswith('/recaptcha/verify'):
                cls.verifies+=1
                if cls.verifies==2 and cls.failure in {'network','fetch'}:route.abort('failed');return
                if cls.verifies==2 and cls.failure in {'abort','timeout'}:
                    # Let the browser fire its own abort/80ms timeout first, then
                    # release the test route so teardown has no pending handler.
                    time.sleep(0.2);route.abort('aborted');return
                payload={'verified':cls.accepted};status=200 if cls.accepted else 401
                if getattr(cls,'verification_responses',[]):
                    status,verified=cls.verification_responses.pop(0);payload={'verified':verified}
            else:
                cls.searches=getattr(cls,'searches',0)+1
                if cls.failure=='search-network':route.abort('failed');return
                params=parse_qs(u.query);rows=[] if cls.mode=='empty' or (cls.mode=='name' and params.get('ein')) else [ROW]
                payload={'success':True,'statusCode':200,'data':rows};status=200
                if cls.failure=='schema-missing':payload['data']=[{k:v for k,v in ROW.items() if k!='ein'}]
                elif cls.failure=='schema-null':payload['data']=[{**ROW,'ein':None}]
                elif cls.failure=='null-wrong-name':payload['data']=[{**ROW,'ein':None,'orgName':'Unrelated Wildlife Society'}]
                elif cls.failure=='schema-type':payload['data']=[{**ROW,'ein':123456789}]
                elif cls.failure=='schema-format':payload['data']=[{**ROW,'ein':'invalid'}]
                elif cls.failure=='schema-identity':payload['data']=[{**ROW,'orgID':'bad'}]
                elif cls.failure=='schema-rows':payload['data']=None
                elif cls.failure=='schema-unsuccessful':payload['success']=False
                elif cls.failure=='blank-string':payload['data']=[{**ROW,'ein':''}]
                elif cls.failure=='focus-live-shape':payload['data']=[] if params.get('ein') else [json.loads((WORK/'testing/fixtures/ny_focus_null_ein.json').read_text())['search_row']]

                if getattr(cls,'search_responses',[]):
                    status=cls.search_responses.pop(0)
                    if status!=200:payload={'error':'Verification rejected'}
                    if status==401 and cls.failure=='search-html-rejection':
                        route.fulfill(status=401,content_type='text/html',body='<html>Unauthorized</html>',headers={'Access-Control-Allow-Origin':'*'});return
            route.fulfill(status=status,content_type='application/json',body=json.dumps(payload),headers={'Access-Control-Allow-Origin':'*'})
        elif u.scheme=='chrome-extension':route.continue_()
        else:route.abort()
    def run_case(self,mode='positive',accepted=True,failure='',verification_responses=None,search_responses=None):
        type(self).mode=mode;type(self).accepted=accepted;type(self).trace=[];type(self).failure=failure;type(self).verifies=0;type(self).verification_responses=list(verification_responses or []);type(self).search_responses=list(search_responses or []);type(self).searches=0
        before=self.worker.evaluate('testCreatedTabs.length')
        detail=Mock();detail.json.return_value={'success':True,'statusCode':200,'data':{**ROW,'regType':'NFP','regStatute':'7A','documents':{'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'12/31/2025'}]}}}
        requested=ROW
        if failure=='focus-live-shape':
            fixture=json.loads((WORK/'testing/fixtures/ny_focus_null_ein.json').read_text());requested=fixture['requested']
            detail.json.return_value={'success':True,'statusCode':200,'data':fixture['detail']}
        session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False);session.get.return_value=detail
        page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/connector-test')
        page.wait_for_function('!!window.CCNYConnector')
        with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'public_profile_for_ein',return_value={}),patch.object(c,'build_search_queries',return_value=[requested['orgName']]):
            timed=page.evaluate('''async args=>{
              let admitted=performance.now();
              const result=await window.CCNYConnector.lookup({...args,onProgress:message=>{
                if(message==='New York: checking the registry.')admitted=performance.now();
              }});
              return {result,activeSeconds:(performance.now()-admitted)/1000};
            }''',{'organization_name':requested['orgName'],'ein':requested['ein'],'email':'browser-test@compliance-express.com','admin_passcode':c.ADMIN_PASSCODE,'device_id':'fixture-browser-session'})
            result=timed['result'];self.last_active_seconds=timed['activeSeconds']
        if result.get('status_reason') in {'NY_CONNECTOR_INCOMPLETE','NY_CONNECTOR_TIMEOUT','NY_CONNECTOR_UNAVAILABLE'}:
            print(json.dumps({'mode':mode,'reason':result.get('status_reason'),'observations':self.observations}),flush=True)
        self.assertEqual(self.worker.evaluate('testCreatedTabs.length')-before,1,'Every query in this lookup must use one connector-owned tab')
        self.assertEqual(self.worker.evaluate('async()=>{const tabs=await chrome.tabs.query({});return tabs.filter(t=>testCreatedTabs.includes(t.id)).length;}'),0,'Completed lookups must close their owned tab')
        page.close();return result,session
    def test_real_extension_positive_pipeline(self):
        result,session=self.run_case();self.assertEqual(result['status'],'Current');session.get.assert_called_once()
        self.assertEqual(self.trace[0]['query'],{'ein':ROW['ein']});self.assertNotIn('fixture-token',json.dumps(self.trace))
    def test_real_extension_empty_ein_then_name_fallback(self):
        result,_=self.run_case('name');self.assertEqual(result['status'],'Current')
        self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']},{'orgName':ROW['orgName']}])
    def test_real_extension_completed_no_record(self):
        result,session=self.run_case('empty');self.assertEqual(result['status'],'Not Registered');session.get.assert_not_called()
    def test_real_extension_rejected_verification_is_inconclusive(self):
        result,session=self.run_case(accepted=False);self.assertEqual(result['status'],'Unable to Confirm')
        self.assertEqual(result['status_reason'],'NY_CONNECTOR_VERIFICATION_REJECTED');session.get.assert_not_called();self.assertEqual(self.trace,[])
        self.assertEqual(self.verifies,2);self.assertIn('after one retry',result['comments'])
    def test_first_rejection_recovers_with_one_fresh_normal_attempt(self):
        result,session=self.run_case(verification_responses=[(401,False),(200,True)])
        self.assertEqual(result['status'],'Current');self.assertEqual(self.verifies,2);session.get.assert_called_once()
        self.assertEqual(len(self.trace),1);self.assertNotIn('fixture-token',json.dumps(self.trace))
    def test_non_401_verification_failures_are_not_retried(self):
        for status in [200,403,500]:
            with self.subTest(status=status):
                result,session=self.run_case(verification_responses=[(status,False)])
                self.assertEqual(result['status_reason'],'NY_CONNECTOR_VERIFICATION_REQUIRED')
                self.assertEqual(result['status'],'Unable to Confirm');self.assertEqual(self.verifies,1)
                self.assertEqual(self.trace,[]);session.get.assert_not_called()
    def test_retry_budget_is_shared_with_name_fallback(self):
        result,session=self.run_case('name',verification_responses=[(401,False),(200,True),(401,False)])
        self.assertEqual(result['status_reason'],'NY_CONNECTOR_VERIFICATION_REJECTED')
        self.assertEqual(result['status'],'Unable to Confirm');self.assertEqual(self.verifies,3)
        self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']}]);session.get.assert_not_called()
    def test_unused_retry_can_recover_name_fallback(self):
        result,session=self.run_case('name',verification_responses=[(200,True),(401,False),(200,True)])
        self.assertEqual(result['status'],'Current');self.assertEqual(self.verifies,3)
        self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']},{'orgName':ROW['orgName']}]);session.get.assert_called_once()
    def test_recovered_verification_still_requires_completed_empty_searches(self):
        result,session=self.run_case('empty',verification_responses=[(401,False),(200,True),(200,True)])
        self.assertEqual(result['status'],'Not Registered');self.assertEqual(self.verifies,3)
        self.assertEqual(len(self.trace),2);session.get.assert_not_called()
    def test_search_rejection_restarts_normal_verify_and_search_once(self):
        result,session=self.run_case(search_responses=[401,200])
        self.assertEqual(result['status'],'Current');self.assertEqual((self.verifies,self.searches),(2,2))
        self.assertEqual(len(self.trace),1);session.get.assert_called_once();self.assertNotIn('fixture-token',json.dumps(self.trace))
    def test_search_rejection_with_non_json_body_can_recover(self):
        result,session=self.run_case(search_responses=[401,200],failure='search-html-rejection')
        self.assertEqual(result['status'],'Current');self.assertEqual((self.verifies,self.searches),(2,2))
        self.assertEqual(len(self.trace),1);session.get.assert_called_once()
    def test_repeated_search_rejection_is_explicit_and_inconclusive(self):
        result,session=self.run_case(search_responses=[401,401])
        self.assertEqual(result['status'],'Unable to Confirm');self.assertEqual(result['status_reason'],'NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED')
        self.assertEqual((self.verifies,self.searches),(2,2));self.assertEqual(self.trace,[]);session.get.assert_not_called()
    def test_verify_retry_consumes_search_retry_budget(self):
        result,session=self.run_case(verification_responses=[(401,False),(200,True)],search_responses=[401])
        self.assertEqual(result['status_reason'],'NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED')
        self.assertEqual((self.verifies,self.searches),(2,1));self.assertEqual(self.trace,[]);session.get.assert_not_called()
    def test_search_retry_consumes_verify_retry_budget(self):
        result,session=self.run_case(verification_responses=[(200,True),(401,False)],search_responses=[401])
        self.assertEqual(result['status_reason'],'NY_CONNECTOR_VERIFICATION_REJECTED')
        self.assertEqual((self.verifies,self.searches),(2,1));self.assertEqual(self.trace,[]);session.get.assert_not_called()
    def test_name_search_can_use_remaining_retry(self):
        result,session=self.run_case('name',search_responses=[200,401,200])
        self.assertEqual(result['status'],'Current');self.assertEqual((self.verifies,self.searches),(3,3))
        self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']},{'orgName':ROW['orgName']}]);session.get.assert_called_once()
    def test_name_search_cannot_repeat_consumed_retry(self):
        result,session=self.run_case('name',search_responses=[401,200,401])
        self.assertEqual(result['status_reason'],'NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED')
        self.assertEqual((self.verifies,self.searches),(3,3));self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']}]);session.get.assert_not_called()
    def test_non_401_search_errors_are_not_retried(self):
        for status in [403,500]:
            with self.subTest(status=status):
                result,session=self.run_case(search_responses=[status])
                self.assertEqual(result['status_reason'],'NY_CONNECTOR_SEARCH_HTTP_ERROR');self.assertEqual(result['status'],'Unable to Confirm')
                self.assertEqual((self.verifies,self.searches),(1,1));self.assertEqual(self.trace,[]);session.get.assert_not_called()
    def test_schema_failure_reasons_survive_the_entire_bridge(self):
        for failure,reason in [('missing','EIN_MISSING'),('type','EIN_TYPE'),('format','EIN_FORMAT'),('identity','IDENTITY_INVALID'),('rows','ROWS_INVALID'),('unsuccessful','UNSUCCESSFUL')]:
            with self.subTest(failure=failure):
                result,session=self.run_case(failure='schema-'+failure)
                self.assertEqual(result['status_reason'],'NY_CONNECTOR_SEARCH_'+reason)
                self.assertEqual(result['status'],'Unable to Confirm');self.assertFalse(result['success'])
                self.assertEqual(self.trace,[]);session.get.assert_not_called()
                self.assertEqual((self.verifies,self.searches),(1,1))
    def test_explicit_null_ein_reaches_existing_master_identity_confirmation(self):
        result,session=self.run_case(failure='schema-null')
        self.assertEqual(result['status'],'Current');self.assertTrue(result['success'])
        self.assertEqual(self.trace[0]['rows'][0]['ein'],'');session.get.assert_called_once()
    def test_null_ein_does_not_make_an_unrelated_name_a_positive_match(self):
        result,session=self.run_case(failure='null-wrong-name')
        self.assertEqual(result['status'],'Not Registered');session.get.assert_not_called()
        self.assertEqual(len(self.trace),2)
    def test_focus_null_search_ein_and_blank_detail_ein_confirm_exemption(self):
        result,session=self.run_case(failure='focus-live-shape')
        self.assertEqual(result['status'],'Exempt');self.assertTrue(result['success'])
        self.assertEqual(result['matched_registry_identifier'],'20-80-11')
        self.assertEqual([e['query'] for e in self.trace],[{'ein':'953188150'},{'orgName':'Focus on the Family'}])
        self.assertEqual(self.trace[1]['rows'][0]['ein'],'');session.get.assert_called_once()
    def test_blank_string_ein_still_uses_master_identity_confirmation(self):
        result,session=self.run_case(failure='blank-string')
        self.assertEqual(result['status'],'Current');self.assertTrue(result['success'])
        self.assertEqual(self.trace[0]['rows'][0]['ein'],'');session.get.assert_called_once()
    def test_search_recovery_requires_both_empty_searches_before_negative(self):
        result,session=self.run_case('empty',search_responses=[401,200,200])
        self.assertEqual(result['status'],'Not Registered');self.assertEqual((self.verifies,self.searches),(3,3))
        self.assertEqual(len(self.trace),2);session.get.assert_not_called()
    def test_second_verification_network_failure_is_immediate_and_inconclusive(self):
        for failure in ['network','abort','timeout','fetch']:
            with self.subTest(transport_failure=failure):
                started=time.monotonic();result,session=self.run_case('empty',failure=failure)
                self.assertEqual(result['status'],'Unable to Confirm')
                self.assertEqual(result['status_reason'],'NY_CONNECTOR_VERIFICATION_NETWORK_ERROR')
                self.assertLess(self.last_active_seconds,8,'After queue admission, do not wait for the old 15-second timeout')
                self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']}])
                session.get.assert_not_called()
    def test_search_network_failure_cannot_become_an_empty_result(self):
        result,session=self.run_case('empty',failure='search-network')
        self.assertEqual(result['status'],'Unable to Confirm');self.assertEqual(result['status_reason'],'NY_CONNECTOR_SEARCH_NETWORK_ERROR')
        self.assertEqual(self.trace,[]);session.get.assert_not_called()
    def test_stale_previous_query_network_event_cannot_fail_name_fallback(self):
        result,_=self.run_case('name',failure='stale')
        self.assertEqual(result['status'],'Current')
        self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']},{'orgName':ROW['orgName']}])
    def test_backend_pause_beyond_worker_idle_window_retains_same_lookup_tab(self):
        type(self).advance_delay=35
        try:
            result,_=self.run_case('name');self.assertEqual(result['status'],'Current')
        finally:type(self).advance_delay=0
    def test_rate_limit_at_verify_and_search_recovers_with_normal_form(self):
        for stage in ['verify','search']:
            kwargs={'verification_responses':[(429,False),(200,True)]} if stage=='verify' else {'search_responses':[429,200]}
            result,session=self.run_case(**kwargs)
            self.assertEqual(result['status'],'Current');session.get.assert_called_once()
            self.assertEqual(self.verifies,2)
    def test_full_staging_form_mixed_batch_preserves_mature_state_when_ny_fails(self):
        type(self).accepted=False;type(self).mode='positive';type(self).trace=[];type(self).state_calls=[];type(self).failure='';type(self).verifies=0
        page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/full-ui')
        page.locator('#stagingEmail').fill('browser-test@compliance-express.com')
        page.locator('#stagingPasscode').fill(c.ADMIN_PASSCODE);page.locator('#stagingUnlockButton').click()
        page.locator('#organizationName').fill(ROW['orgName']);page.locator('#ein').fill(ROW['ein'])
        page.locator('#clearStatesButton').click()
        page.locator('input[value="CO"]').check();page.locator('input[value="NY"]').check();page.locator('#consent').check()
        with patch.object(c,'public_profile_for_ein',return_value={}):
            page.locator('#submitButton').click()
            page.wait_for_function("document.querySelectorAll('#resultRows tr').length === 2",timeout=90000)
        results=page.evaluate('latestResults')
        self.assertEqual({r['state']:r['status'] for r in results},{'CO':'Current','NY':'Unable to Confirm'})
        self.assertEqual(self.state_calls,[['CO']]);self.assertEqual(self.trace,[])
        self.assertEqual(page.locator('#nyConnectorSetup').get_attribute('data-state'),'ready')
        page.close()

if __name__=='__main__':unittest.main(verbosity=2)
