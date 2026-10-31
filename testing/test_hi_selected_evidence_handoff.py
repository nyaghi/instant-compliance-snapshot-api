"""Native local HI search-to-evidence regression; every request is intercepted."""
import dataclasses
import html
import unittest
from contextlib import ExitStack
from unittest.mock import patch
from playwright.sync_api import sync_playwright
import registry_snapshot_server as m

SEARCH='https://charity.ehawaii.gov/charity/new-search.html'

class HawaiiSelectedEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime=sync_playwright().start()
        cls.browser=cls.runtime.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.runtime.stop()
    def execute(self,registration='Exempt',ein='823980782',detail_ein=None,rows=True,incomplete=False,fn=None):
        name='ACOEL FOUNDATION' if ein=='823980782' else 'Retained Relief '+ein
        url='https://charity.ehawaii.gov/charity/'+ein+'/details.html'
        selected_ein=detail_ein if detail_ein is not None else ein
        detail='<html><body><h1>Hawaii Charity Detail</h1><dl>'+''.join('<dt>'+k+':</dt><dd>'+html.escape(v)+'</dd>' for k,v in [('Primary Name',name),('FEIN',selected_ein),('Registration Status','Active'),('Registration Type',registration)])+'</dl><h2>Documents</h2><p>Local fixture only</p></body></html>'
        search='<html><body><select id="nameFilter"><option>Contains...</option></select><input id="name"><input id="fein"><table id="searchOrgTable"><tbody>'+('<tr><td><a href="'+url+'">'+name+'</a></td><td>'+ein+'</td></tr>' if rows else '')+'</tbody></table>'+('' if rows else 'No records found')+'</body></html>'
        unexpected=[];ctx=self.browser.new_context()
        def route(rt):
            if rt.request.url in [SEARCH,url]:rt.fulfill(status=200,content_type='text/html',body=search if rt.request.url==SEARCH else detail)
            else:unexpected.append(rt.request.url);rt.abort()
        ctx.route('**/*',route);page=ctx.new_page()
        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(m.checker,'safe_wait_for_network_idle'))
                stack.enter_context(patch.object(m.time,'sleep'))
                stack.enter_context(patch.object(m,'build_search_queries',return_value=[]))
                stack.enter_context(patch.object(m,'organization_name_variants',return_value=[name]))
                stack.enter_context(patch.object(m,'organization_match_target_variants',return_value=[name]))
                stack.enter_context(patch.object(m,'registry_candidate_fields',return_value={'name':name,'status':'Active'}))
                submit=stack.enter_context(patch.object(m,'hi_submit_completed_search',side_effect=RuntimeError('fixture incomplete') if incomplete else None,return_value=[{'fein':ein}] if rows else []))
                filing=stack.enter_context(patch.object(m,'hi_public_filing_period',return_value={}))
                annotate=stack.enter_context(patch.object(m,'annotate_irs_based_state_period'))
                result=(fn or m.search_hi_precise)(page,m.checker.Organization(name,ein))
            self.assertEqual(unexpected,[])
            return result,filing.call_count,annotate.call_count,submit.call_count,detail,url
        finally:ctx.close()
    def test_exact_exempt_keeps_selected_url_without_filing_query(self):
        r,filing,annotate,queries,_,url=self.execute()
        self.assertTrue(r.success);self.assertEqual(r.source_url,url)
        self.assertEqual(r.matched_registry_identifier,'823980782')
        self.assertEqual(r.matched_registry_name,'ACOEL FOUNDATION')
        self.assertEqual(r.raw_status_text,'Registration Status: Active | Registration Type: Exempt')
        self.assertEqual((filing,annotate,queries),(0,0,1))
    def test_registered_keeps_existing_filing_path(self):
        r,filing,annotate,queries,_,url=self.execute(registration='Registered')
        self.assertTrue(r.success);self.assertEqual(r.source_url,url)
        self.assertEqual((filing,annotate,queries),(1,1,1))
    def test_wrong_or_missing_detail_ein_does_not_admit_url(self):
        for value in ['999999999','']:
            with self.subTest(value=value):
                r,filing,_,_,_,_=self.execute(detail_ein=value)
                self.assertEqual(r.source_url,SEARCH);self.assertEqual(filing,0)
    def test_completed_negative_and_incomplete_keep_search_url(self):
        r,filing,_,_,_,_=self.execute(rows=False)
        self.assertTrue(r.success);self.assertEqual(r.source_url,SEARCH)
        self.assertEqual(m.public_status(r),'Not Registered');self.assertEqual(filing,0)
        r,filing,_,_,_,_=self.execute(incomplete=True)
        self.assertFalse(r.success);self.assertEqual(r.reason_code,'HI_SEARCH_INCOMPLETE')
        self.assertEqual(r.source_url,SEARCH);self.assertEqual(filing,0)

if __name__=='__main__':unittest.main()
