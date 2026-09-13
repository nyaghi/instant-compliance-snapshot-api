"""Actual extension recovery and page integration; synthetic registry responses only."""
import json, sys, unittest
from unittest.mock import Mock, patch
from run_ny_connector_browser import BrowserIntegration, ROW, c

class RecoveryIntegration(BrowserIntegration):
    def test_repair_retries_same_ein_and_confirms_detail(self):
        result, session = self.run_case(verification_responses=[(401,False),(401,False),(200,True)], repair_available=True, expected_tabs=2)
        self.assertEqual(result['status'],'Current')
        self.assertEqual(result['connector_version'],'0.3.1')
        self.assertEqual(self.verifies,3)
        self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']}])
        session.get.assert_called_once()
        self.assertEqual(self.worker.evaluate('repair.phase'),'verified')
        self.assertTrue(all(not o['active'] for o in self.worker.evaluate('testCreatedOptions')))

    def test_persistent_rejection_stops_after_one_repair(self):
        result, session = self.run_case(accepted=False, repair_available=True, expected_tabs=2)
        self.assertEqual(result['status'],'Unable to Confirm')
        self.assertEqual(result['status_reason'],'NY_CONNECTOR_RECOVERY_REJECTED')
        self.assertEqual(self.verifies,4)
        self.assertEqual(self.trace,[])
        session.get.assert_not_called()
        state=self.worker.evaluate('repair')
        self.assertEqual(state['phase'],'failed')
        self.assertGreater(state['nextAllowedAt'],state['attemptedAt'])

    def test_repair_cannot_replace_completed_ein_and_name_searches(self):
        result, session = self.run_case('empty', verification_responses=[(401,False),(401,False),(200,True)], repair_available=True, expected_tabs=2)
        self.assertEqual(result['status'],'Not Registered')
        self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']},{'orgName':ROW['orgName']}])
        session.get.assert_not_called()

    def test_search_401_repair_keeps_same_organization(self):
        result, session = self.run_case(search_responses=[401,401,200], repair_available=True, expected_tabs=2)
        self.assertEqual(result['status'],'Current')
        self.assertEqual((self.verifies,self.searches),(3,3))
        self.assertEqual([e['query'] for e in self.trace],[{'ein':ROW['ein']}])
        session.get.assert_called_once()

    def test_schema_failure_after_repair_is_never_a_negative(self):
        result, session = self.run_case(failure='schema-missing', verification_responses=[(401,False),(401,False),(200,True)], repair_available=True, expected_tabs=2)
        self.assertEqual(result['status'],'Unable to Confirm')
        self.assertEqual(result['status_reason'],'NY_CONNECTOR_SEARCH_EIN_MISSING')
        self.assertEqual(self.trace,[])
        session.get.assert_not_called()

    def test_user_owned_registry_page_prevents_cleanup(self):
        user_page=self.context.new_page();user_page.goto('https://charities-search.ag.ny.gov/RegistrySearch')
        user_page.evaluate("localStorage.setItem('user-work','preserved')")
        try:
            result, session=self.run_case(accepted=False,repair_available=True)
            self.assertEqual(result['status_reason'],'NY_CONNECTOR_RECOVERY_PAGE_OPEN')
            self.assertEqual(result['status'],'Unable to Confirm')
            self.assertEqual(user_page.evaluate("localStorage.getItem('user-work')"),'preserved')
            self.assertEqual(self.worker.evaluate('repair'),{})
            session.get.assert_not_called()
        finally:user_page.close()

    def test_manual_refresh_rechecks_only_failed_ny_and_preserves_results(self):
        self.reset_repair(False)
        cls=type(self);cls.accepted=False;cls.mode='positive';cls.trace=[];cls.state_calls=[];cls.failure='';cls.verifies=0
        cls.verification_responses=[];cls.search_responses=[]
        page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/full-ui')
        page.locator('#stagingEmail').fill('browser-test@compliance-express.com')
        page.locator('#stagingPasscode').fill(c.ADMIN_PASSCODE);page.locator('#stagingUnlockButton').click()
        page.locator('#organizationName').fill(ROW['orgName']);page.locator('#ein').fill(ROW['ein'])
        page.locator('#clearStatesButton').click()
        for state in ['CO','NY','PA']:page.locator('input[value="'+state+'"]').check()
        page.locator('#consent').check()
        detail=Mock();detail.json.return_value={'success':True,'statusCode':200,'data':{**ROW,'regType':'NFP','regStatute':'7A','documents':{'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'12/31/2025'}]}}}
        session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False);session.get.return_value=detail
        with patch.object(c,'public_profile_for_ein',return_value={}),patch.object(c.curl_requests,'Session',return_value=session):
            page.locator('#submitButton').click()
            page.wait_for_function("latestResults.length===3&&!document.querySelector('#submitButton').disabled",timeout=90000)
            before=page.evaluate("({other:latestResults.filter(r=>r.state!=='NY'),stamp:document.querySelector('#resultTimestamp').textContent})")
            self.assertEqual(next(r for r in page.evaluate('latestResults') if r['state']=='NY')['status'],'Unable to Confirm')
            # Move the fixture's repair deadline into the past, simulating elapsed
            # time without changing the production interval or repair rules.
            self.worker.evaluate("async()=>{repair.nextAllowedAt=Date.now()-1;await chrome.storage.local.set({ccnyRepair:repair});}")
            cls.accepted=True
            page.locator('[data-connector-refresh]').click()
            page.wait_for_function("latestResults.find(r=>r.state==='NY')?.status==='Current'",timeout=90000)
            after=page.evaluate("({other:latestResults.filter(r=>r.state!=='NY'),stamp:document.querySelector('#resultTimestamp').textContent})")
            self.assertEqual(after,before)
            self.assertEqual(self.state_calls,[['CO'],['PA']])
            session.get.assert_called_once()
            self.assertEqual(len(self.trace),1)
            self.assertIn('verification succeeded',page.locator('[data-connector-recovery]').inner_text())
        page.close()

    def test_manual_network_failure_has_accurate_page_message(self):
        self.manual_failure('network','NY_CONNECTOR_VERIFICATION_NETWORK_ERROR','interrupted during verification')

    def test_manual_timeout_has_accurate_page_message(self):
        self.manual_failure('no-response','NY_CONNECTOR_TIMEOUT','did not finish within the time allowed')

    def test_manual_unconfirmed_response_is_not_labeled_rejected(self):
        self.manual_failure('unconfirmed','NY_CONNECTOR_VERIFICATION_REQUIRED','did not confirm verification')

    def manual_failure(self, failure, reason, message):
        self.reset_repair(True)
        cls=type(self);cls.accepted=True;cls.mode='positive';cls.trace=[];cls.state_calls=[];cls.failure='';cls.verifies=0
        cls.verification_responses=[];cls.search_responses=[]
        def response(route):
            if failure=='network':route.abort('failed')
            elif failure=='no-response':route.fulfill(status=200,content_type='application/json',body='{}',headers={'Access-Control-Allow-Origin':'*'})
            else:route.fulfill(status=200,content_type='application/json',body='{"verified":false}',headers={'Access-Control-Allow-Origin':'*'})
        # A form whose handler does not issue a request exercises the actual
        # page timeout without network sleeps or changing production deadlines.
        def form_without_request(route):
            from run_ny_connector_browser import FORM
            route.fulfill(content_type='text/html',body=FORM.replace('x.send();','if(!path.endsWith("/verify"))x.send();'))
        pattern='https://charities-search-api.ag.ny.gov/**/recaptcha/verify'
        self.context.route(pattern,response)
        if failure=='no-response':self.context.route('https://charities-search.ag.ny.gov/RegistrySearch',form_without_request)
        page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/full-ui')
        try:
            page.locator('#stagingEmail').fill('browser-test@compliance-express.com');page.locator('#stagingPasscode').fill(c.ADMIN_PASSCODE);page.locator('#stagingUnlockButton').click()
            page.locator('[data-connector-refresh]').click()
            page.wait_for_function("text=>document.querySelector('[data-connector-recovery]').textContent.includes(text)",arg=message,timeout=45000)
            self.assertNotIn('rejected',page.locator('[data-connector-recovery]').inner_text())
            self.assertEqual(self.worker.evaluate('repair.reason'),reason)
            self.assertEqual(self.trace,[]);self.assertEqual(self.state_calls,[])
        finally:
            page.close();self.context.unroute(pattern,response)
            if failure=='no-response':self.context.unroute('https://charities-search.ag.ny.gov/RegistrySearch',form_without_request)

    def test_worker_restart_interrupts_queue_and_preserves_repair_budget(self):
        self.reset_repair(True)
        cls=type(self);cls.accepted=True;cls.mode='positive';cls.trace=[];cls.failure='';cls.verifies=0
        cls.verification_responses=[];cls.search_responses=[]
        holder=self.context.new_page();holder.goto(c.NY_CONNECTOR_ORIGIN+'/restart-holder')
        holder.evaluate("""()=>{window.granted=false;window.addEventListener('message',e=>{if(e.data?.direction==='response'&&e.data.id==='aaaaaaaaaaaaaaaaaaaa'&&e.data.ok)granted=true;});window.postMessage({channel:'cc-ny-staging-v1',direction:'request',action:'acquire',id:'aaaaaaaaaaaaaaaaaaaa',lookup_id:'bbbbbbbbbbbbbbbbbbbb'},location.origin);} """)
        holder.wait_for_function('granted',timeout=15000)
        self.worker.evaluate('async()=>{await lookupTab(active);}')
        owned_ids=self.worker.evaluate('[...owned]')
        owned_pages=[p for p in self.context.pages if p.url.startswith('https://charities-search.ag.ny.gov/')]
        self.assertEqual(len(owned_pages),len(owned_ids))
        waiting=self.context.new_page();waiting.goto(c.NY_CONNECTOR_ORIGIN+'/restart-waiting')
        with patch.object(c,'public_profile_for_ein',return_value={}):
            waiting.evaluate("""args=>{window.restartResult=null;window.restartProgress='';CCNYConnector.lookup({...args,onProgress:m=>restartProgress=m}).then(r=>restartResult=r);} """,{'organization_name':ROW['orgName'],'ein':ROW['ein'],'email':'browser-test@compliance-express.com','admin_passcode':c.ADMIN_PASSCODE,'device_id':'restart-waiting'})
            waiting.wait_for_function("restartProgress.includes('queue')",timeout=10000)
            budget=self.worker.evaluate("async()=>{await saveRepair({phase:'repairing',attemptedAt:Date.now(),nextAllowedAt:Date.now()+1200000});return repair.nextAllowedAt;}")
            # DevTools attaches only to this disposable test profile to exercise
            # real MV3 worker termination. The shipped extension has no debugger API.
            cdp=self.context.new_cdp_session(holder);versions=[]
            cdp.on('ServiceWorker.workerVersionUpdated',lambda event:versions.extend(event['versions']))
            cdp.send('ServiceWorker.enable');holder.wait_for_timeout(100)
            version=next(v for v in reversed(versions) if v.get('scriptURL')==self.worker.url and v.get('runningStatus')=='running')
            restarted=[];self.context.on('serviceworker',lambda worker:restarted.append(worker))
            cdp.send('ServiceWorker.stopWorker',{'versionId':version['versionId']})
            waiting.wait_for_function('restartResult!==null',timeout=15000)
            result=waiting.evaluate('restartResult')
            self.assertEqual(result['status'],'Unable to Confirm')
            self.assertEqual(result['status_reason'],'NY_CONNECTOR_INTERRUPTED')
            holder.evaluate("""()=>{window.restartPing=null;window.addEventListener('message',e=>{if(e.data?.direction==='response'&&e.data.id==='cccccccccccccccccccc')restartPing=e.data;});window.postMessage({channel:'cc-ny-staging-v1',direction:'request',action:'ping',id:'cccccccccccccccccccc'},location.origin);} """)
            holder.wait_for_function('restartPing?.ok===true',timeout=15000)
            state=holder.evaluate('restartPing.recovery')
            self.assertEqual(state['phase'],'failed')
            self.assertEqual(state['nextAllowedAt'],budget)
            self.assertTrue(all(p.is_closed() for p in owned_pages))
            self.assertEqual(self.trace,[])
            cdp.detach()
        waiting.close();holder.close()

if __name__=='__main__':
    names=[name for name in RecoveryIntegration.__dict__ if name.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(RecoveryIntegration(name) for name in names))
    sys.exit(not result.wasSuccessful())
