"""Real headless DOM regression: an AJAX result displayed after the old pause.

All browser requests are fulfilled locally. No regulator or user browser is used.
"""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import registry_snapshot_server as m

FORM='''<html><body><input id="charityname"><button id="search">Search</button><div id="results"></div>
<script>document.querySelector('#search').onclick=async()=>{
 const value=document.querySelector('#charityname').value;
 const response=await fetch('/Charities/Charity/Results',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'Name='+encodeURIComponent(value)+'&EIN='});
 const body=await response.text();setTimeout(()=>document.querySelector('#results').innerHTML=body,DELAY);
};</script></body></html>'''
RESULT='<table id="grid"><tbody><tr><td><a href="/Charities/Charity/Details/fixture">Example Relief</a></td></tr></tbody></table>'
DETAIL='''<html><body><div id="report">Report</div><table id="info"><tr><td>Status:</td><td>Registered</td></tr></table>
<div id="reports"><ul><li><a>2025</a></li></ul></div><div class="reportperiod">Fiscal Year Beginning 1/1/2025 and Ending 12/31/2025</div></body></html>'''


class OregonBrowser(unittest.TestCase):
    def run_case(self, guarded, delay, result=RESULT):
        module=m.state_extension_module('OR');org=module.Organization('Example Relief','123456789')
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                def route(r):
                    url=r.request.url
                    body=(result if url.endswith('/Charity/Results') else DETAIL if '/Details/' in url
                          else FORM.replace('DELAY',str(delay)))
                    r.fulfill(status=200,content_type='text/html',body=body)
                page.route('**/*',route)
                with patch.object(m,'APP_VERSION','fixture-performance-lab'),patch.dict(m.os.environ,
                    {'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com'}):
                    return m.search_or_completed(page,org,module) if guarded else module.search_or(page,org)
            finally:browser.close()

    def test_late_dom_reproduces_old_false_negative_and_guard_recovers_real_record(self):
        before=self.run_case(False,5500)
        self.assertEqual(before.status,m.state_extension_module('OR').STATUS_NOT_REGISTERED)
        after=self.run_case(True,5500)
        self.assertTrue(after.success,after.error)
        self.assertNotEqual(after.status,m.state_extension_module('OR').STATUS_NOT_REGISTERED)
        self.assertIn('12/31/2025',after.raw_status_text)

    def test_completed_empty_result_remains_a_valid_negative(self):
        result=self.run_case(True,0,'<div>No record found</div>')
        self.assertTrue(result.success);self.assertEqual(result.status,m.state_extension_module('OR').STATUS_NOT_REGISTERED)

    def test_dom_that_never_catches_up_is_incomplete_not_negative(self):
        result=self.run_case(True,15000)
        self.assertFalse(result.success);self.assertEqual(result.reason_code,'OR_INCOMPLETE_QUERY_RESPONSE')


if __name__=='__main__':unittest.main()
