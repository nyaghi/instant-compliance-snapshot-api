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
<div class="k-pager-numbers"></div><span class="k-pager-info">No Matches Found.</span></div>
<div id="printDiv1" style="display:none"></div>
<script>
window.responses = {
  'Mercy Corps': [{name:'Mercy Corps',id:'100000143',status:'Current - Registered'}],
  'National Parks Traveler': [], 'National Park Traveler': [],
  'HORIZON': Array.from({length:17},(_,i)=>({name:'Horizon Record '+(i+1),id:String(100000100+i),status:'Current - Registered'})),
  'DUPLICATE': Array.from({length:17},(_,i)=>({name:'Duplicate '+(i+1),id:String(100000100+(i===10?0:i)),status:'Current - Registered'}))
};
window.searchCount = 0;
window.msObserver = null;
window.addEventListener('message',event=>{
  const m=event.data;
  if(m?.channel==='cc-final-four-ms-search-v1'&&m.kind==='arm'&&m.name==='HORIZON') {
    window.msObserver=m;
    window.postMessage({channel:m.channel,kind:'armed',id:m.id},location.origin);
  }
});
window.renderPage=(name,page)=>{
  const rows=window.responses[name], grid=document.querySelector('#kendoSearchResults');
  const shown=rows.slice((page-1)*10,page*10);
  grid.style.display='block';
  grid.querySelector('tbody').innerHTML=shown.map(r=>`<tr role="row"><td role="gridcell">${r.name}</td><td role="gridcell">${r.id}</td><td role="gridcell">${r.status}</td><td role="gridcell"><a class="k-grid-Details">Details</a></td></tr>`).join('');
  grid.querySelector('.k-pager-info').textContent=rows.length?`${(page-1)*10+1} - ${(page-1)*10+shown.length} of ${rows.length} items`:'No Matches Found.';
  grid.querySelector('.k-pager-numbers').innerHTML=rows.length>10?[1,2].map(n=>n===page?`<span class="k-state-selected">${n}</span>`:`<a class="k-link" data-page="${n}" href="#">${n}</a>`).join(''):'';
};
document.querySelector('#kendoSearchResults').onclick=e=>{
  const pager=e.target.closest('a.k-link[data-page]');
  if(pager){e.preventDefault();const name=document.querySelector('#ContentPlaceHolder1_PortalPageControl1_ctl10_IFSearchControl1_EntityNameTextBox').value;
    setTimeout(()=>window.renderPage(name,Number(pager.dataset.page)),80);return;}
  if(e.target.matches('a.k-grid-Details')){
    const tr=e.target.closest('tr'), cells=tr.querySelectorAll('td');
    const panel=document.querySelector('#printDiv1');panel.style.display='block';
    panel.innerHTML=`<font>${cells[0].textContent}</font><table><tr><td class="infoText">Filing Number:</td><td>${cells[1].textContent}</td></tr><tr><td class="infoText">Filing Status:</td><td>${cells[2].textContent}</td></tr></table>`;
  }
};
document.querySelector('#SearchButton').onclick = () => {
  const name=document.querySelector('#ContentPlaceHolder1_PortalPageControl1_ctl10_IFSearchControl1_EntityNameTextBox').value;
  window.searchCount++;
  if(name==='ERROR')return; // The public AJAX error callback leaves the prior grid alone.
  setTimeout(() => {
    window.renderPage(name,1);
    if(name==='HORIZON'&&window.msObserver){
      const m=window.msObserver;
      window.postMessage({channel:m.channel,kind:'success',id:m.id,
        identifiers:window.responses[name].map(row=>row.id)},location.origin);
    }
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
window.sendDetail=(id,budgetMs=1200)=>new Promise(resolve=>
  window.registryListener({action:'registry-ms',query:{state:'MS',operation:'detail',identifier:id},
    budgetMs},{id:'fixture-extension'},resolve));
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

    def test_paginated_search_collects_all_rows_and_revisits_detail_page(self):
        found=self.search('HORIZON',False,2500)
        self.assertTrue(found['ok'],found)
        self.assertEqual(found['evidence']['total'],17)
        self.assertEqual(len(found['evidence']['rows']),17)
        self.assertEqual(found['evidence']['rows'][-1]['identifier'],'100000116')
        last=self.page.evaluate("()=>sendDetail('100000116',2500)")
        self.assertTrue(last['ok'],last)
        self.assertEqual(last['evidence']['fields']['Filing Number'],'100000116')
        detail=self.page.evaluate("()=>sendDetail('100000100',2500)")
        self.assertTrue(detail['ok'],detail)
        self.assertEqual(detail['evidence']['fields']['Filing Number'],'100000100')

    def test_duplicate_across_pages_is_incomplete(self):
        found=self.search('DUPLICATE',False,2500)
        self.assertFalse(found['ok'],found)
        self.assertEqual(found['reason'],'NY_CONNECTOR_INCOMPLETE')


if __name__=='__main__':
    unittest.main()
