"""Real extension queue integration against routed public-response fixtures only."""
import json,sys,unittest
from unittest.mock import Mock,patch
from run_ny_connector_browser import BrowserIntegration,ROW,c

class QueueIntegration(BrowserIntegration):
    def test_5_10_15_sessions_wait_then_complete(self):
        cls=type(self)
        for count in [5,10,15]:
            cls.accepted=True;cls.mode='positive';cls.trace=[];cls.failure='';cls.verifies=0;cls.state_calls=[]
            cls.verification_responses=[];cls.search_responses=[];cls.advance_delay=0
            detail=Mock();detail.json.return_value={'success':True,'statusCode':200,'data':{**ROW,'regType':'NFP','regStatute':'7A','documents':{'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'12/31/2025'}]}}}
            session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False);session.get.return_value=detail
            pages=[]
            with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'public_profile_for_ein',return_value={}):
                for i in range(count):
                    page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/queue-fixture')
                    page.evaluate("""args => {
                      window.queueMessages=[];window.queueResult=null;
                      window.CCNYConnector.lookup({...args,onProgress:m=>queueMessages.push(m)})
                        .then(r=>{window.queueResult=r}).catch(e=>{window.queueResult={error:e.message}});
                    }""",{'organization_name':ROW['orgName'],'ein':ROW['ein'],'email':'browser-test@compliance-express.com','admin_passcode':c.ADMIN_PASSCODE,'device_id':'queue-session-'+str(i)})
                    pages.append(page)
                for page in pages:page.wait_for_function('window.queueResult !== null',timeout=180000)
                results=[page.evaluate('({result:queueResult,progress:queueMessages})') for page in pages]
            self.assertTrue(all(r['result'].get('status')=='Current' for r in results),results)
            self.assertTrue(any('position' in msg for r in results for msg in r['progress']))
            self.assertEqual(len(self.trace),count)
            self.assertTrue(all(r['result']['connector_version']=='0.2.0' for r in results))
            self.assertEqual(self.worker.evaluate('async()=>{const ts=await chrome.tabs.query({});return ts.filter(t=>testCreatedTabs.includes(t.id)).length;}'),0)
            for page in pages:page.close()
            print(json.dumps({'real_extension_sessions':count,'completed':len(results),'busy_failures':0,'passed':True}),flush=True)
    def test_other_state_completes_while_ny_is_queued(self):
        cls=type(self);cls.accepted=False;cls.mode='positive';cls.trace=[];cls.failure='';cls.verifies=0;cls.state_calls=[]
        cls.verification_responses=[];cls.search_responses=[]
        holder=self.context.new_page();holder.goto(c.NY_CONNECTOR_ORIGIN+'/queue-holder')
        holder.evaluate("""() => {
          window.granted=false;
          window.addEventListener('message',e=>{if(e.data?.direction==='response'&&e.data?.id==='aaaaaaaaaaaaaaaaaaaa'&&e.data.ok)window.granted=true;});
          window.postMessage({channel:'cc-ny-staging-v1',direction:'request',action:'acquire',id:'aaaaaaaaaaaaaaaaaaaa',lookup_id:'bbbbbbbbbbbbbbbbbbbb'},location.origin);
        }""")
        holder.wait_for_function('window.granted',timeout=15000)
        page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/full-ui')
        page.locator('#stagingEmail').fill('browser-test@compliance-express.com')
        page.locator('#stagingPasscode').fill(c.ADMIN_PASSCODE);page.locator('#stagingUnlockButton').click()
        page.locator('#organizationName').fill(ROW['orgName']);page.locator('#ein').fill(ROW['ein'])
        page.locator('#clearStatesButton').click()
        for state in ['CO','NY','PA']:page.locator('input[value="'+state+'"]').check()
        page.locator('#consent').check()
        with patch.object(c,'public_profile_for_ein',return_value={}):
            page.locator('#submitButton').click()
            page.wait_for_function("document.getElementById('progressCount').textContent==='2 of 3'",timeout=15000)
            self.assertEqual(self.state_calls,[['CO'],['PA']])
            self.assertIn('queue',page.locator('#nyQueueProgress').inner_text())
            self.assertEqual(self.trace,[])
            holder.close()
            page.wait_for_function("document.querySelectorAll('#resultRows tr').length===3",timeout=30000)
        self.assertEqual({r['state']:r['status'] for r in page.evaluate('latestResults')},{'CO':'Current','NY':'Unable to Confirm','PA':'Current'})
        page.close()

if __name__=='__main__':
    suite=unittest.TestSuite(QueueIntegration(name) for name in ['test_5_10_15_sessions_wait_then_complete','test_other_state_completes_while_ny_is_queued'])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
