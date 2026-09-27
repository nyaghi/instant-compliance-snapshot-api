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
    def run_case(self, guarded, delay, result=RESULT, transform=''):
        module=m.state_extension_module('OR');org=module.Organization('Example Relief','123456789')
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                def route(r):
                    url=r.request.url
                    form=FORM.replace('DELAY',str(delay)).replace(
                        "()=>document.querySelector('#results').innerHTML=body",
                        "()=>{document.querySelector('#results').innerHTML=body;"+transform+"}")
                    body=(result if url.endswith('/Charity/Results') else DETAIL if '/Details/' in url else form)
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

    def test_state_datatable_empty_row_controls_and_removed_scripts_are_not_records(self):
        source='''<div id="search-results">Search Results for "Example Relief"</div>
<table id="grid"><thead><tr><th>Name</th></tr></thead><tbody></tbody></table>
<script>/* State DataTables initialization */</script>'''
        transform='''document.querySelector('#results script').remove();
document.querySelector('#grid tbody').innerHTML='<tr><td class="dataTables_empty">No data available in table</td></tr>';
document.querySelector('#grid').insertAdjacentHTML('beforebegin','<div>Show 25 entries Filter:</div>');'''
        result=self.run_case(True,0,source,transform)
        self.assertTrue(result.success,result.error)
        self.assertEqual(result.status,m.state_extension_module('OR').STATUS_NOT_REGISTERED)

    def test_state_sorting_preserves_all_record_text_and_links(self):
        source=RESULT.replace('<tbody>','<tbody><tr><td><a href="/Charities/Charity/Details/other">Other Relief</a></td></tr>')
        transform="const rows=document.querySelector('#grid tbody');rows.appendChild(rows.firstElementChild);"
        result=self.run_case(True,0,source,transform)
        self.assertTrue(result.success,result.error)
        self.assertNotEqual(result.status,m.state_extension_module('OR').STATUS_NOT_REGISTERED)

    def test_missing_record_or_changed_link_is_not_a_completed_grid(self):
        result=self.run_case(True,0,RESULT,"document.querySelector('#grid a').setAttribute('href','/Charities/Charity/Details/wrong');")
        self.assertFalse(result.success);self.assertEqual(result.reason_code,'OR_INCOMPLETE_QUERY_RESPONSE')

    def test_stale_empty_grid_for_another_query_is_not_a_completed_search(self):
        source='<div id="search-results">Search Results for "Example Relief"</div><table id="grid"><tbody></tbody></table>'
        result=self.run_case(True,0,source,"document.querySelector('#search-results').textContent='Search Results for Other';")
        self.assertFalse(result.success);self.assertEqual(result.reason_code,'OR_INCOMPLETE_QUERY_RESPONSE')

    def test_client_side_pagination_exposes_every_received_record_before_parsing(self):
        others=''.join(f'<tr><td><a href="/Charities/Charity/Details/other{i}">A Relief {i}</a></td></tr>' for i in range(25))
        source=RESULT.replace('<tbody>','<tbody>'+others)
        transform='''const grid=document.querySelector('#grid');
const all=Array.from(grid.querySelectorAll('tbody tr'));
all.slice(25).forEach(row=>row.remove());
window.jQuery=()=>({DataTable:()=>({page:{len:n=>({draw:()=>{
 if(n===-1)all.forEach(row=>grid.querySelector('tbody').appendChild(row));
}})}})});
window.jQuery.fn={dataTable:{isDataTable:el=>el===grid}};'''
        result=self.run_case(True,0,source,transform)
        self.assertTrue(result.success,result.error)
        self.assertNotEqual(result.status,m.state_extension_module('OR').STATUS_NOT_REGISTERED)


if __name__=='__main__':unittest.main()
