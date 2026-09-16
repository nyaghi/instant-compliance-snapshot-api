"""Browser contracts for reviewed discovery and local validation inputs; no live requests."""
import json,sys,unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
W=Path(__file__).resolve().parents[1]
ORIGIN='https://staging.compliance-express.com'
HTML='''<input id="organizationName"><input id="ein"><input id="email"><section id="organizationIdentity"><button id="findAlternateNames">Find</button><button id="addAlternateName">Add</button><div id="alternateNameList"></div><p id="identityMessage"></p><div id="identityReview" hidden><p id="identitySummary"></p></div></section>'''
def item(name,source='California'):
    return {'name':name,'verified':True,'historical':False,'evidence':[{'source':source,'type':'Registered name','url':'https://example.gov','retrieved_at':'2026-09-16'}]}

class IdentityBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=sync_playwright().start();cls.browser=cls.p.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.p.stop()
    def setUp(self):
        self.page=self.browser.new_page();self.requests=[]
        self.response={'names':[item('Example National Foundation')],'sources':[{'source':'CA','complete':True},{'source':'NY','complete':False}],'partial':True}
        def route(r):
            if r.request.url.endswith('/api/discover-names'):
                self.requests.append(r.request.post_data_json);r.fulfill(status=200,content_type='application/json',body=json.dumps(self.response))
            elif r.request.url==ORIGIN+'/fixture':r.fulfill(status=200,content_type='text/html',body=HTML)
            else:r.abort()
        self.page.route('**/*',route);self.page.goto(ORIGIN+'/fixture')
        self.page.evaluate("""() => {
          window.CCIdentityConfig=()=>({apiBase:location.origin,email:'test@example.invalid',admin_passcode:'TEST-ONLY',device_id:'test-device'});
          window.CCNYConnector={lookup:async args=>{window.nyArgs=args;return {state:'NY',identity:{complete:true,names:[{name:'Example Public Name',verified:true,historical:false,evidence:[{source:'New York',type:'Registered name',url:'https://example.gov'}]}]}}}};
        }""")
        self.page.add_script_tag(path=str(W/'web-staging/organization-identity.js'))
        self.page.locator('#organizationName').fill('Example Foundation');self.page.locator('#ein').fill('01-2345678')
    def tearDown(self):self.page.close()
    def discover(self):
        self.page.locator('#findAlternateNames').click();self.page.wait_for_function('CCIdentity.ready()')
    def test_sources_merge_but_only_reviewed_selected_names_are_used(self):
        self.discover()
        self.assertEqual(self.page.evaluate('nyArgs.purpose'),'identity')
        self.assertEqual(self.page.evaluate('nyArgs.ein'),'01-2345678')
        self.assertEqual(self.page.evaluate('CCIdentity.names()'),['Example National Foundation','Example Public Name'])
        self.page.get_by_label('Use alternate name 1',exact=True).uncheck()
        self.page.get_by_label('Alternate name 2',exact=True).fill('Edited Public Name')
        self.assertEqual(self.page.evaluate('CCIdentity.names()'),['Edited Public Name'])
        self.assertIn('not independently verified',self.page.locator('#alternateNameList').inner_text())
        self.assertEqual(len(self.requests),1)
    def test_partial_source_keeps_confirmed_names_and_no_registration_result(self):
        self.response['sources'].append({'source':'MD','complete':False,'limitation':'Malformed name field excluded.'})
        self.discover();self.assertIn('MD: Malformed name field excluded.',self.page.locator('#identityMessage').inner_text())
        self.assertEqual(len(self.page.evaluate('CCIdentity.names()')),2)
        self.assertNotIn('state',self.requests[0])
    def test_no_new_york_connection_does_not_discard_other_names(self):
        self.page.evaluate("() => { CCNYConnector.lookup=async()=>{throw Error('Unavailable')}; }")
        self.discover();self.assertEqual(self.page.evaluate('CCIdentity.names()'),['Example National Foundation'])
        self.assertIn('NY:',self.page.locator('#identityMessage').inner_text())
    def test_changed_ein_invalidates_review_and_32_names_remain_editable(self):
        self.response['names']=[item('Specific Identity '+str(i)) for i in range(31)]
        self.discover();self.assertEqual(len(self.page.evaluate('CCIdentity.names()')),32)
        self.assertFalse(self.page.locator('#addAlternateName').is_enabled())
        self.page.locator('#ein').fill('98-7654321')
        self.assertFalse(self.page.evaluate('CCIdentity.ready()'));self.assertEqual(self.page.evaluate('CCIdentity.names()'),[])
    def test_local_validation_settings_do_not_enter_results_or_storage(self):
        self.page.unroute('**/*')
        def route(r):
            if r.request.url==ORIGIN+'/connector/validation.html':r.fulfill(status=200,content_type='text/html',body=(W/'web-staging/connector/validation.html').read_text(encoding='utf-8'))
            else:r.abort()
        self.page.route('**/*',route);self.page.goto(ORIGIN+'/connector/validation.html')
        data={'email':'test@example.invalid','admin_passcode':'LOCAL-TEST-SECRET','cases':[{'organization':'Example','ein':'01-2345678'}]}
        self.page.locator('#settingsFile').set_input_files({'name':'settings.json','mimeType':'application/json','buffer':json.dumps(data).encode()})
        self.page.wait_for_function("document.getElementById('progress').textContent.includes('Local settings loaded')")
        self.assertEqual(self.page.locator('#passcode').input_value(),'LOCAL-TEST-SECRET')
        self.assertNotIn('LOCAL-TEST-SECRET',self.page.locator('#results').inner_text())
        self.assertEqual(self.page.evaluate('localStorage.length + sessionStorage.length'),0)
        self.assertEqual(self.page.locator('#settingsFile').input_value(),'')

if __name__=='__main__':unittest.main(verbosity=2)
