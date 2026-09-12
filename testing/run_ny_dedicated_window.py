"""Dedicated validation page and window ownership, using public-response fixtures."""
import json,sys,unittest
from urllib.parse import urlsplit
from unittest.mock import patch
from run_ny_connector_browser import BrowserIntegration,ROW,WORK,c

class DedicatedWindow(BrowserIntegration):
    @classmethod
    def route(cls,route):
        url=urlsplit(route.request.url)
        if url.hostname=='staging.compliance-express.com' and url.path=='/connector/validation.html':
            route.fulfill(content_type='text/html',body=(WORK/'web-staging/connector/validation.html').read_text(encoding='utf-8'))
        else:super().route(route)

    def prepare(self,accepted):
        cls=type(self);cls.accepted=accepted;cls.mode='empty';cls.trace=[];cls.failure='';cls.verifies=0
        cls.verification_responses=[];cls.search_responses=[];cls.advance_delay=0
        page=self.context.new_page();page.goto(c.NY_CONNECTOR_ORIGIN+'/connector/validation.html')
        page.locator('#email').fill('browser-test@compliance-express.com');page.locator('#passcode').fill(c.ADMIN_PASSCODE)
        rows=[{'organization':ROW['orgName'],'ein':'12-3456789'},{'organization':'No Record Control Foundation','ein':'98-7654321'}]
        page.locator('#cases').fill(json.dumps(rows));return page

    def test_completed_background_cases_and_credentials_not_in_output(self):
        page=self.prepare(True)
        with patch.object(c,'public_profile_for_ein',return_value={}):
            page.locator('#start').click()
            page.wait_for_function("/^(Completed|Paused)/.test(document.querySelector('#progress').textContent)",timeout=60000)
        raw=page.locator('#results').inner_text();rows=json.loads(raw)
        self.assertEqual([r['result']['status'] for r in rows],['Not Registered','Not Registered'],raw)
        self.assertEqual([r['result']['ein'] for r in rows],['12-3456789','98-7654321'])
        self.assertNotIn(c.ADMIN_PASSCODE,raw);self.assertNotIn('check_token',raw)
        self.assertEqual(page.locator('#passcode').input_value(),'');page.close()

    def test_verification_failure_stops_new_background_cases(self):
        page=self.prepare(False)
        with patch.object(c,'public_profile_for_ein',return_value={}):
            page.locator('#start').click()
            page.wait_for_function("document.querySelector('#progress').textContent.startsWith('Paused for investigation')",timeout=30000)
        rows=json.loads(page.locator('#results').inner_text())
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['result']['status'],'Unable to Confirm')
        self.assertEqual(type(self).verifies,2,rows);page.close()

    def test_other_window_keeps_focus_and_tabs_while_queued_lookup_runs(self):
        page=self.prepare(True)
        page.locator('#cases').fill(json.dumps([{'organization':ROW['orgName'],'ein':'12-3456789'}]))
        holder=self.context.new_page();holder.goto(c.NY_CONNECTOR_ORIGIN+'/holder')
        holder.evaluate("""() => {window.granted=false;window.addEventListener('message',e=>{if(e.data?.id==='aaaaaaaaaaaaaaaaaaaa'&&e.data.direction==='response'&&e.data.ok)window.granted=true;});window.postMessage({channel:'cc-ny-staging-v1',direction:'request',action:'acquire',id:'aaaaaaaaaaaaaaaaaaaa',lookup_id:'bbbbbbbbbbbbbbbbbbbb'},location.origin);} """)
        holder.wait_for_function('window.granted',timeout=15000)
        origin=self.worker.evaluate("async()=> (await chrome.tabs.query({url:'https://staging.compliance-express.com/connector/validation.html'}))[0].windowId")
        with patch.object(c,'public_profile_for_ein',return_value={}):
            page.locator('#start').click();page.wait_for_function("document.querySelector('#progress').textContent.includes('queue')",timeout=10000)
            other=self.worker.evaluate("async()=>{const w=await chrome.windows.create({url:'https://staging.compliance-express.com/unrelated-control',focused:true});return {id:w.id,tabs:w.tabs.map(t=>t.id)};}")
            holder.close()
            page.wait_for_function("document.querySelector('#progress').textContent==='Completed 1 of 1.'",timeout=30000)
        evidence=self.worker.evaluate("async()=>({created:testCreatedOptions,lastFocused:(await chrome.windows.getLastFocused()).id,windows:await chrome.windows.getAll({populate:true})})")
        self.assertEqual(evidence['created'][-1]['windowId'],origin)
        self.assertEqual(evidence['lastFocused'],other['id'])
        untouched=next(w for w in evidence['windows'] if w['id']==other['id'])
        self.assertEqual([t['id'] for t in untouched['tabs']],other['tabs'])
        self.worker.evaluate('(id)=>chrome.windows.remove(id)',other['id']);page.close()

if __name__=='__main__':
    suite=unittest.TestSuite(DedicatedWindow(name) for name in ['test_completed_background_cases_and_credentials_not_in_output','test_verification_failure_stops_new_background_cases','test_other_window_keeps_focus_and_tabs_while_queued_lookup_runs'])
    sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
