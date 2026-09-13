"""Real extension queue integration against routed public-response fixtures only."""
import json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import urlparse,parse_qs
from run_ny_connector_browser import BrowserIntegration,ROW,c

class QueueIntegration(BrowserIntegration):
    @classmethod
    def route(cls,route):
        url=urlparse(route.request.url)
        if getattr(cls,'distinct_rows',{}) and url.hostname=='charities-search-api.ag.ny.gov' and url.path.endswith('/RegistrySearch'):
            query=parse_qs(url.query);cls.searches+=1
            found=cls.distinct_rows.get(query.get('ein',[''])[0])
            route.fulfill(status=200,content_type='application/json',body=json.dumps({'success':True,'statusCode':200,'data':[found] if found else []}),headers={'Access-Control-Allow-Origin':'*'})
        else:super().route(route)
    def test_5_10_15_sessions_wait_then_complete(self):
        self.run_bursts([5,10,15])
    def test_15_sessions_share_one_successful_repair(self):
        self.run_bursts([15],repair=True)
    def test_failed_repair_does_not_reset_for_each_of_15_sessions(self):
        self.run_bursts([15],repair=True,accepted=False)
    def run_bursts(self,counts,repair=False,accepted=True,distinct=False):
        cls=type(self)
        for count in counts:
            self.reset_repair(True)
            cls.accepted=accepted;cls.mode='positive';cls.trace=[];cls.failure='';cls.verifies=0;cls.state_calls=[]
            cls.searches=0
            requested=[{'ein':str(900000000+i),'orgName':f'Queue Control Foundation {i+1:02}','orgID':f'99-00-{i+1:02}'} for i in range(count)] if distinct else [ROW]*count
            cls.distinct_rows={r['ein']:r for r in requested} if distinct else {}
            cls.verification_responses=[(401,False),(401,False)] if repair else [];cls.search_responses=[];cls.advance_delay=0
            before_tabs=self.worker.evaluate('testCreatedTabs.length')
            detail=Mock();detail.json.return_value={'success':True,'statusCode':200,'data':{**ROW,'regType':'NFP','regStatute':'7A','documents':{'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'12/31/2025'}]}}}
            session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False);session.get.return_value=detail
            if distinct:
                def get_detail(url,**kwargs):
                    row=next(r for r in requested if r['orgID']==kwargs['params']['orgID'])
                    response=Mock();response.json.return_value={'success':True,'statusCode':200,'data':{**row,'regType':'NFP','regStatute':'7A','documents':{'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'12/31/2025'}]}}};return response
                session.get.side_effect=get_detail
            pages=[]
            with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'public_profile_for_ein',return_value={}):
                for i in range(count):
                    page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/queue-fixture')
                    page.evaluate("""args => {
                      window.queueMessages=[];window.queueResult=null;
                      window.CCNYConnector.lookup({...args,onProgress:m=>queueMessages.push(m)})
                        .then(r=>{window.queueResult=r}).catch(e=>{window.queueResult={error:e.message}});
                    }""",{'organization_name':requested[i]['orgName'],'ein':requested[i]['ein'],'email':'browser-test@compliance-express.com','admin_passcode':c.ADMIN_PASSCODE,'device_id':'queue-session-'+str(i)})
                    pages.append(page)
                for page in pages:page.wait_for_function('window.queueResult !== null',timeout=180000)
                results=[page.evaluate('({result:queueResult,progress:queueMessages})') for page in pages]
            expected='Current' if accepted else 'Unable to Confirm'
            self.assertTrue(all(r['result'].get('status')==expected for r in results),results)
            if distinct:
                self.assertEqual([r['result']['ein'].replace('-','') for r in results],[r['ein'] for r in requested])
                self.assertEqual([r['result']['matched_registry_identifier'] for r in results],[r['ein'] for r in requested])
                self.assertEqual([r['result']['matched_registry_name'] for r in results],[r['orgName'] for r in requested])
                self.assertEqual([call.kwargs['params']['orgID'] for call in session.get.call_args_list],[r['orgID'] for r in requested])
            self.assertTrue(any('position' in msg for r in results for msg in r['progress']))
            self.assertEqual(len(self.trace),count if accepted else 0)
            self.assertEqual(session.get.call_count,count if accepted else 0)
            self.assertEqual(cls.verifies,count+(2 if repair else 0) if accepted else 4)
            self.assertEqual(self.worker.evaluate('testCreatedTabs.length')-before_tabs,count+(1 if repair else 0) if accepted else 2)
            if not accepted:self.assertTrue(all(r['result']['status_reason']=='NY_CONNECTOR_RECOVERY_REJECTED' for r in results))
            version=json.loads((Path(__file__).resolve().parents[1]/'browser-connector/manifest.json').read_text())['version']
            self.assertEqual(self.worker.evaluate('chrome.runtime.getManifest().version'),version)
            # Check the backend release metadata separately from the loaded extension.
            self.assertTrue(all(r['result']['connector_version']=='0.3.1' for r in results))
            self.assertEqual(self.worker.evaluate('async()=>{const ts=await chrome.tabs.query({});return ts.filter(t=>testCreatedTabs.includes(t.id)).length;}'),0)
            for page in pages:page.close()
            print(json.dumps({'real_extension_sessions':count,'completed':len(results),'distinct_organizations':distinct,'verification_accepted':accepted,'repair_episode':repair,'busy_failures':0,'passed':True}),flush=True)
    def test_other_state_completes_while_ny_is_queued(self):
        self.reset_repair(False)
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
    suite=unittest.TestSuite(QueueIntegration(name) for name in ['test_5_10_15_sessions_wait_then_complete','test_15_sessions_share_one_successful_repair','test_failed_repair_does_not_reset_for_each_of_15_sessions','test_other_state_completes_while_ny_is_queued'])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
