"""Fresh-query completion, stale-result rejection and isolated form reuse."""
import ast
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch
import registry_snapshot_server as m

URL = 'https://charportal.dca.njoag.gov/Charity-Registration/CHR-Public-Search-Page/'
API = 'https://charportal.dca.njoag.gov/_services/entity-grid-data.json/test-grid'


def response_body(rows):
    return {'Records': [{'Attributes': [{'Name': k, 'DisplayValue': v} for k, v in row.items()]} for row in rows],
            'ItemCount': len(rows), 'MoreRecords': False, 'PageNumber': 1}


ROW = {'name': 'Example Relief', 'accountnumber': 'CH12345', 'crsm_federalein': '123456789',
       'crsm_filestanding': 'Compliant', 'crsm_mailingcity': 'NEW YORK'}


class NewJerseyQueryCompletionTests(unittest.TestCase):
    def test_response_must_be_complete_and_bound_to_unfiltered_submitted_query(self):
        request = Mock(url=API, method='POST', post_data_json={'search': '123456789', 'page': 1})
        response = request.response.return_value
        response.url = API; response.status = 200; response.headers = {'content-type': 'application/json'}
        response.json.return_value = response_body([ROW])
        self.assertEqual(m.nj_completed_query_rows(request, '123456789'), [tuple(ROW.values())])
        self.assertIsNone(m.nj_completed_query_rows(request, 'different'))
        for field, value in [('filter', 'active only'), ('page', 2), ('search', '')]:
            with patch.object(request, 'post_data_json', {'search': '123456789', 'page': 1, field: value}):
                self.assertIsNone(m.nj_completed_query_rows(request, '123456789'))
        for data in ({}, {'Records': []}, {**response_body([]), 'ItemCount': 1},
                     {**response_body([]), 'MoreRecords': True}, response_body([{'name': 'Unbound'}])):
            response.json.return_value = data
            self.assertIsNone(m.nj_completed_query_rows(request, '123456789'))
        response.json.return_value = response_body([])
        self.assertEqual(m.nj_completed_query_rows(request, '123456789'), [])
        response.url = 'https://other.example/'
        self.assertIsNone(m.nj_completed_query_rows(request, '123456789'))
        response.url = API; response.status = 503
        self.assertIsNone(m.nj_completed_query_rows(request, '123456789'))

    def test_browser_reuses_form_but_waits_for_new_response_and_new_grid(self):
        # Starts with a stale no-record result, then a delayed nonempty response.
        html = '''<input placeholder="Search"><div class="public-search-grid">No records to show</div>
        <script>document.querySelector('input').onkeydown = async e => {
          if(e.key !== 'Enter') return;
          const query=e.target.value;
          const r=await fetch('/_services/entity-grid-data.json/test-grid',{
            method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({search:query,page:1})});
          const b=await r.json();
          setTimeout(()=>document.querySelector('.public-search-grid').innerHTML=
            b.Records.length ? b.Records.map(r=>'<div role="row">'+r.Attributes.map(a=>a.DisplayValue).join(' ')+'</div>').join('') : 'No records to show',150);
        };</script>'''
        with m.checker.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(); requests = []
                def route(r):
                    if r.request.url == URL:
                        requests.append('document'); r.fulfill(status=200,content_type='text/html',body=html)
                    elif r.request.url == API:
                        query=r.request.post_data_json['search']; requests.append(query)
                        r.fulfill(status=200,content_type='application/json',body=json.dumps(response_body([ROW] if query=='123456789' else [])))
                    else:r.abort()
                page.route('**/*',route)
                found = m.nj_search_body(page, '123456789')
                self.assertIn('Example Relief', found)
                self.assertNotIn('No records', found)
                self.assertIn('No records', m.nj_search_body(page, '000000000'))
                self.assertEqual(requests, ['document', '123456789', '000000000'])
                self.assertIn('Example Relief', m.nj_search_body(page, '123456789'))
                self.assertEqual(requests.count('document'), 1)
                page.evaluate('''() => {
                  const d=document.createElement('div');d.setAttribute('role','dialog');
                  d.innerHTML='<iframe id="modalIframe"></iframe><button title="Close">Close</button>';
                  d.querySelector('button').onclick=()=>d.remove();document.body.append(d);
                }''')
                self.assertIn('No records', m.nj_search_body(page, '000000000'))
                self.assertEqual(requests.count('document'), 1)
            finally:browser.close()

    def test_unfinished_query_cannot_use_stale_negative_or_positive(self):
        # Accelerate the clock, not the external deadline or production code.
        for stale in ('No records to show', 'Example Relief 123456789 Compliant'):
            page=Mock(url=URL, _cc_nj_search_ready=True)
            page.locator.return_value.first.is_visible.return_value=True
            page.locator.return_value.is_visible.return_value=False
            page.locator.return_value.inner_text.return_value=stale
            clock=[0.0]
            page.wait_for_timeout.side_effect=lambda ms:clock.__setitem__(0,clock[0]+ms/1000)
            with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]):
                self.assertIsNone(m.nj_search_body(page,'123456789'))
            self.assertLess(clock[0],12.2)
            self.assertFalse(page._cc_nj_search_ready)
            self.assertEqual(page.remove_listener.call_count,2)
            with patch.object(m,'registry_page_body',side_effect=AssertionError('Stale evidence must not be read')):
                self.assertEqual(m.nj_detail_body(page,m.checker.Organization('Example Relief','123456789')),'')
        with patch.object(m,'nj_search_body',return_value=None):
            r=m.search_nj_direct(Mock(),m.checker.Organization('Example Relief','123456789'))
            self.assertFalse(r.success)
            self.assertNotEqual(m.public_status(r),'Not Registered')

    def test_only_query_acquisition_changes_not_matching_rules_or_other_states(self):
        from testing.capacity_lab.parsing_scope import strip_nj_query_optimization
        old=ast.parse(subprocess.check_output(['git','show','a3376d2:registry_snapshot_server.py'],cwd=Path(m.__file__).parent).decode())
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        strip_nj_query_optimization(new)
        self.assertEqual(ast.dump(new),ast.dump(old))

    def test_unfinished_name_fallback_cannot_revert_to_prior_ein_negative(self):
        org=m.checker.Organization('Example Relief','123456789')
        negative=m.checker.StateResult(org.organization_name,org.ein,'NJ','Not Registered',URL)
        negative.success=True
        with patch.object(m,'nj_search_body',return_value=None):
            pending=m.search_nj_direct(Mock(),org)
        with patch.object(m,'search_nj_direct',side_effect=[negative,pending]), \
             patch.object(m,'build_search_queries',return_value=['Example Relief']):
            result=m.search_nj_with_name_fallback(Mock(),org)
        self.assertFalse(result.success)
        self.assertNotEqual(m.public_status(result),'Not Registered')


if __name__=='__main__':unittest.main()
