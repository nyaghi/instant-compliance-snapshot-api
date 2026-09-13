"""A new organization submission must not collide with an in-progress refresh."""
import json,sys,unittest
from unittest.mock import Mock,patch
from run_ny_connector_browser import BrowserIntegration,ROW,c

class RefreshSubmission(BrowserIntegration):
    def test_new_submission_waits_for_connection_refresh_without_busy_result(self):
        self.check_submission_during_refresh(True)

    def test_failed_refresh_keeps_new_submission_inconclusive_without_busy_result(self):
        self.check_submission_during_refresh(False)

    def check_submission_during_refresh(self, accepted):
        self.reset_repair(False)
        cls=type(self);cls.accepted=False;cls.mode='positive';cls.trace=[];cls.state_calls=[];cls.failure='';cls.verifies=0
        cls.verification_responses=[];cls.search_responses=[]
        page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/full-ui')
        page.locator('#stagingEmail').fill('browser-test@compliance-express.com')
        page.locator('#stagingPasscode').fill(c.ADMIN_PASSCODE);page.locator('#stagingUnlockButton').click()
        page.locator('#organizationName').fill(ROW['orgName']);page.locator('#ein').fill(ROW['ein'])
        page.locator('#clearStatesButton').click()
        for state in ['CO','NY']:page.locator('input[value="'+state+'"]').check()
        page.locator('#consent').check()
        detail=Mock();detail.json.side_effect=lambda:{'success':True,'statusCode':200,'data':{**ROW,'regType':'NFP','regStatute':'7A','documents':{'Annual Filing for Charitable Organizations':[{'fiscalYearEnd':'12/31/2025'}]}}}
        session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False);session.get.return_value=detail
        holder=None
        try:
            with patch.object(c,'public_profile_for_ein',return_value={}),patch.object(c.curl_requests,'Session',return_value=session):
                page.locator('#submitButton').click()
                page.wait_for_function("latestResults.length===2&&!document.querySelector('#submitButton').disabled",timeout=60000)
                self.reset_repair(True) # Simulate the previous pause having elapsed.
                cls.accepted=accepted
                holder=self.context.new_page();holder.goto(c.NY_CONNECTOR_ORIGIN+'/refresh-holder')
                holder.evaluate("""()=>{window.granted=false;window.addEventListener('message',e=>{if(e.data?.direction==='response'&&e.data.id==='aaaaaaaaaaaaaaaaaaaa'&&e.data.ok)granted=true;});window.postMessage({channel:'cc-ny-staging-v1',direction:'request',action:'acquire',id:'aaaaaaaaaaaaaaaaaaaa',lookup_id:'bbbbbbbbbbbbbbbbbbbb'},location.origin);} """)
                holder.wait_for_function('granted',timeout=15000)
                page.locator('[data-connector-refresh]').click()
                page.wait_for_function("document.querySelector('[data-connector-recovery]').textContent.includes('current New York check')",timeout=10000)
                with patch.dict(ROW,{'orgName':'Second Charity Foundation','ein':'987654321','orgID':'30-40-50'}):
                    page.locator('#organizationName').fill(ROW['orgName']);page.locator('#ein').fill(ROW['ein'])
                    page.locator('#submitButton').click()
                    page.wait_for_function("document.querySelector('#progressCount').textContent==='1 of 2'||!document.querySelector('#submitButton').disabled",timeout=10000)
                    page.wait_for_timeout(600)
                    self.assertTrue(page.locator('#submitButton').is_disabled(),json.dumps(page.evaluate('latestResults')))
                    holder.close()
                    page.wait_for_function("!document.querySelector('#submitButton').disabled",timeout=45000)
                    results=page.evaluate('latestResults')
                    self.assertEqual({r['state']:r['status'] for r in results},{'CO':'Current','NY':'Current' if accepted else 'Unable to Confirm'})
                    self.assertTrue(all(r['ein'].replace('-','')=='987654321' for r in results))
                    if accepted:
                        self.assertEqual([e['query'] for e in self.trace],[{'ein':'987654321'}])
                        session.get.assert_called_once()
                    else:
                        self.assertEqual(next(r for r in results if r['state']=='NY')['status_reason'],'NY_CONNECTOR_RECOVERY_REJECTED')
                        self.assertEqual(self.trace,[])
                        session.get.assert_not_called()
        finally:
            if holder and not holder.is_closed():holder.close()
            page.close()

if __name__=='__main__':
    names=[name for name in RefreshSubmission.__dict__ if name.startswith('test_')]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(RefreshSubmission(name) for name in names))
    sys.exit(not result.wasSuccessful())
