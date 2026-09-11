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
        cls.context=cls.playwright.chromium.launch_persistent_context(cls.temp.name,headless=False,
            args=[f'--disable-extensions-except={WORK / "browser-connector"}',f'--load-extension={WORK / "browser-connector"}'])
        cls.observations=[]
        cls.context.on('page',lambda page: page.on('pageerror',lambda error: cls.observations.append({'page_error':str(error),'stack':error.stack})))
        cls.context.route('**/*',cls.route)
        worker=cls.context.service_workers[0] if cls.context.service_workers else cls.context.wait_for_event('serviceworker')
        # Chromium extension-created tabs can start their initial navigation before
        # Playwright attaches. In this fixture harness only, defer navigation until
        # the context route is attached, preventing accidental real state traffic.
        cls.worker=worker
        worker.evaluate('''() => {globalThis.testCreatedTabs=[];const original=chrome.tabs.create.bind(chrome.tabs);chrome.tabs.create=async options=>{
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
            else:
                if cls.failure=='search-network':route.abort('failed');return
                params=parse_qs(u.query);rows=[] if cls.mode=='empty' or (cls.mode=='name' and params.get('ein')) else [ROW]
                payload={'success':True,'statusCode':200,'data':rows};status=200
            route.fulfill(status=status,content_type='application/json',body=json.dumps(payload),headers={'Access-Control-Allow-Origin':'*'})
        elif u.scheme=='chrome-extension':route.continue_()
        else:route.abort()
    def run_case(self,mode='positive',accepted=True,failure=''):
        type(self).mode=mode;type(self).accepted=accepted;type(self).trace=[];type(self).failure=failure;type(self).verifies=0
        before=self.worker.evaluate('testCreatedTabs.length')
        detail=Mock();detail.json.return_value={'success':True,'statusCode':200,'data':{**ROW,'regType':'NFP','regStatute':'7A','documents':{'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'12/31/2025'}]}}}
        session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False);session.get.return_value=detail
        page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/connector-test')
        page.wait_for_function('!!window.CCNYConnector')
        with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'public_profile_for_ein',return_value={}),patch.object(c,'build_search_queries',return_value=['Example National Foundation']):
            result=page.evaluate('args=>window.CCNYConnector.lookup(args)',{'organization_name':ROW['orgName'],'ein':ROW['ein'],'email':'browser-test@compliance-express.com','admin_passcode':c.ADMIN_PASSCODE,'device_id':'fixture-browser-session'})
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
        self.assertEqual(result['status_reason'],'NY_CONNECTOR_VERIFICATION_REQUIRED');session.get.assert_not_called();self.assertEqual(self.trace,[])
    def test_second_verification_network_failure_is_immediate_and_inconclusive(self):
        for failure in ['network','abort','timeout','fetch']:
            with self.subTest(transport_failure=failure):
                started=time.monotonic();result,session=self.run_case('empty',failure=failure)
                self.assertEqual(result['status'],'Unable to Confirm')
                self.assertEqual(result['status_reason'],'NY_CONNECTOR_VERIFICATION_NETWORK_ERROR')
                self.assertLess(time.monotonic()-started,8,'Do not wait for the old 15-second timeout')
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
