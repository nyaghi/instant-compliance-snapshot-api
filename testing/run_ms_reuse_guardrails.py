"""Mississippi reused-page searches must never accept a previous Kendo grid."""
import unittest
import os
from pathlib import Path
from playwright.sync_api import sync_playwright


CONTENT = Path(os.environ.get("CC_CONNECTOR_CONTENT", Path(__file__).resolve().parents[1] /
                              "browser-connector/registry-content.js")).read_text(encoding="utf-8")
URL = "https://charities.sos.ms.gov/online/portal/ch/page/charities-search/Portal.aspx"
HTML = """<!doctype html><html><body>
<input id="ContentPlaceHolder1_PortalPageControl1_ctl10_IFSearchControl1_EntityNameTextBox">
<input id="SearchButton" type="button" value="Search">
<div id="kendoSearchResults" style="display:none"><table role="grid"><tbody></tbody></table>
<span class="k-pager-info">No Matches Found.</span></div>
<script>
window.responses = {
  'Mercy Corps': [{name:'Mercy Corps',id:'100000143',status:'Current - Registered'}],
  'National Parks Traveler': [], 'National Park Traveler': []
};
window.searchCount = 0;
document.querySelector('#SearchButton').onclick = () => {
  const name=document.querySelector('#ContentPlaceHolder1_PortalPageControl1_ctl10_IFSearchControl1_EntityNameTextBox').value;
  window.searchCount++;
  if(name==='ERROR')return; // The public AJAX error callback leaves the prior grid alone.
  setTimeout(() => {
    const rows=window.responses[name];
    const grid=document.querySelector('#kendoSearchResults');
    grid.style.display='block';
    grid.querySelector('tbody').innerHTML=rows.map(r=>`<tr role="row"><td role="gridcell">${r.name}</td><td role="gridcell">${r.id}</td><td role="gridcell">${r.status}</td><td role="gridcell"><a class="k-grid-Details">Details</a></td></tr>`).join('');
    grid.querySelector('.k-pager-info').textContent=rows.length?`1 - ${rows.length} of ${rows.length} items`:'No Matches Found.';
  },180);
};
</script></body></html>"""


class MississippiReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw=sync_playwright().start()
        cls.browser=cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page=self.browser.new_page()
        self.page.route(URL,lambda route:route.fulfill(body=HTML,content_type='text/html'))
        self.page.add_init_script("""
window.chrome={runtime:{id:'fixture-extension',onMessage:{addListener(fn){window.registryListener=fn}}}};
window.sendRegistry=(name,reuse,budgetMs=1200)=>new Promise(resolve=>
  window.registryListener({action:'registry-ms',query:{state:'MS',operation:'search',name},
    requireFreshGrid:reuse,budgetMs},{id:'fixture-extension'},resolve));
""")
        self.page.goto(URL)
        self.page.add_script_tag(content=CONTENT)

    def tearDown(self):
        self.page.close()

    def search(self,name,reuse=True,budget=1200):
        return self.page.evaluate("([name,reuse,budget])=>sendRegistry(name,reuse,budget)",[name,reuse,budget])

    def test_stale_positive_to_empty_and_back(self):
        first=self.search('Mercy Corps',False)
        self.assertTrue(first['ok'],first)
        self.assertEqual(first['evidence']['rows'][0]['identifier'],'100000143')
        missing=self.search('National Parks Traveler')
        self.assertTrue(missing['ok'])
        self.assertEqual(missing['evidence']['total'],0)
        again=self.search('Mercy Corps')
        self.assertEqual(again['evidence']['rows'][0]['identifier'],'100000143')

    def test_same_empty_grid_requires_a_new_render(self):
        first=self.search('National Parks Traveler',False)
        self.assertTrue(first['ok'],first)
        self.assertTrue(self.search('National Park Traveler')['ok'])
        self.assertEqual(self.page.evaluate('window.searchCount'),2)

    def test_failed_request_never_reuses_old_negative(self):
        first=self.search('National Parks Traveler',False)
        self.assertTrue(first['ok'],first)
        failed=self.search('ERROR',True,400)
        self.assertFalse(failed['ok'])
        self.assertEqual(failed['reason'],'NY_CONNECTOR_INCOMPLETE')


if __name__=='__main__':
    unittest.main()
