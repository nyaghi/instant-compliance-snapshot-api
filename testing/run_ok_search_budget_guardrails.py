"""Oklahoma bounded retrieval, page completion, and navigation readiness controls."""
import ast,re,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class Pages:
    def __init__(self,total):self.total=total;self.current=1;self.waits=[]
    def locator(self,selector):
        loc=Mock();loc.first=loc
        if selector=='a[href*="Page$"]':
            hrefs=[f"javascript:__doPostBack('grid','Page${i}')" for i in range(2,min(self.total,10)+1)]
            if self.total>10:hrefs.append("javascript:__doPostBack('grid','Page$Last')")
            loc.evaluate_all.return_value=hrefs
        elif selector.startswith('a[href*='):
            match=re.search(r'Page\$(\d+)',selector);target=int(match[1])
            loc.count.return_value=target<=self.total
            loc.click.side_effect=lambda **kw:setattr(self,'current',target)
        else:loc.inner_text.return_value=f'Page {self.current} records'
        return loc
    def wait_for_function(self,*args,**kwargs):self.waits.append((args,kwargs))

class RetrievalTests(unittest.TestCase):
    def org(self,limit=1):
        org=cc.checker.Organization('Example Relief','123456789');org.ok_search_page_limit=limit;return org
    def choose(self,pages,target=None,limit=1):
        org=self.org(limit)
        with patch.object(cc,'ok_choose_safe_result_row_on_page',side_effect=lambda p,o,m:('row','link','Example Relief','123') if p.current==target else None):
            selected=cc.ok_choose_safe_result_row(pages,org,None)
        return selected,org
    def test_first_page_match_does_not_page(self):
        pages=Pages(20);selected,org=self.choose(pages,1)
        self.assertEqual(selected[3],'123');self.assertEqual(pages.current,1);self.assertFalse(org.ok_search_incomplete)
    def test_large_phrase_set_preserves_incomplete_evidence(self):
        pages=Pages(20);selected,org=self.choose(pages)
        self.assertIsNone(selected);self.assertEqual(pages.current,1);self.assertTrue(org.ok_search_incomplete)
    def test_small_sets_keep_second_and_third_page_matches(self):
        for count in [2,3]:
            pages=Pages(count);selected,org=self.choose(pages,count)
            self.assertEqual(selected[3],'123');self.assertEqual(pages.current,count);self.assertFalse(org.ok_search_incomplete)
    def test_three_page_probe_is_a_completed_negative_only_at_end(self):
        for count,complete in [(3,True),(4,False)]:
            pages=Pages(count);selected,org=self.choose(pages,limit=3)
            self.assertIsNone(selected);self.assertEqual(pages.current,3);self.assertEqual(not org.ok_search_incomplete,complete)
    def test_pagination_waits_for_new_grid_content(self):
        pages=Pages(2);self.choose(pages)
        self.assertEqual(len(pages.waits),1)
        self.assertEqual(pages.waits[0][1]['arg'][1],'Page 1 records')
    def test_failed_pagination_stays_incomplete(self):
        pages=Pages(2);pages.wait_for_function=Mock(side_effect=TimeoutError('navigation stalled'))
        selected,org=self.choose(pages);self.assertIsNone(selected);self.assertTrue(org.ok_search_incomplete)
    def test_expired_budget_does_not_start_page_scan(self):
        org=self.org();org.ok_search_deadline=10
        with patch.object(cc.time,'perf_counter',return_value=11),patch.object(cc,'ok_choose_safe_result_row_on_page') as scan:
            with self.assertRaises(TimeoutError):cc.ok_choose_safe_result_row(Pages(2),org,None)
            scan.assert_not_called()
    def test_action_wait_is_clamped_to_remaining_budget(self):
        org=self.org();org.ok_search_deadline=11
        with patch.object(cc.time,'perf_counter',return_value=10):self.assertEqual(cc.ok_action_timeout(org,12000),1000)
        self.assertEqual(cc.ok_action_timeout(None,8000),8000)
    def run_variants(self,complete_query=None,error_query=None):
        calls=[]
        def search(page,org,module):
            calls.append((org.organization_name,org.ok_search_page_limit,org.ok_search_deadline))
            status='Site Not Reachable' if org.organization_name==error_query else 'Not Registered' if org.organization_name==complete_query else 'Unable to Confirm'
            return SimpleNamespace(organization_name=org.organization_name,status=status,success=status!='Site Not Reachable',matched_registry_name='',raw_status_text='No safely matching filing number link' if status=='Not Registered' else 'Incomplete search',source_note='')
        with patch.object(cc,'search_ok_precise',side_effect=search),patch.object(cc,'public_status',lambda r:r.status):
            result=cc.search_ok_with_variants(None,cc.checker.Organization('First Responders Children\u2019s Foundation','05-0536854'),SimpleNamespace())
        return result,calls
    def test_all_first_page_misses_never_become_not_registered(self):
        result,calls=self.run_variants();self.assertEqual(result.status,'Unable to Confirm');self.assertEqual(len(calls),4)
    def test_complete_targeted_search_can_supply_existing_negative_result(self):
        result,calls=self.run_variants(complete_query='responders')
        self.assertEqual(result.status,'Not Registered');self.assertEqual(len(result.queries_attempted),4)
        self.assertIn('responders',result.source_attempts[-1]);self.assertNotIn('children.',result.source_attempts[-1])
        self.assertEqual([c[1] for c in calls],[1,1,3,3]);self.assertEqual(len({c[2] for c in calls}),1)
    def test_outage_does_not_reuse_an_earlier_negative(self):
        result,_=self.run_variants(complete_query='responders',error_query='children')
        self.assertEqual(result.status,'Site Not Reachable')

class ReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse(Path(cc.__file__).read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='search_ok_precise')
        cls.predicate=next(n.args[0].value for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='wait_for_function' and n.args and isinstance(n.args[0],ast.Constant))
        cls.playwright=cc.checker.sync_playwright().start();cls.browser=cls.playwright.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.playwright.stop()
    def test_navigation_document_without_body_is_not_ready(self):
        page=self.browser.new_page()
        try:
            page.evaluate('document.body.remove()')
            self.assertFalse(page.evaluate(self.predicate))
        finally:page.close()
    def test_only_result_or_explicit_no_result_content_is_ready(self):
        page=self.browser.new_page()
        try:
            for html,expected in [('<p>Search by Name</p>',False),('<p>No records found</p>',True),('<div id="ctl00_DefaultContent_CharityNameSearch1_EntityGridView"><span id="record_lblName">Example Relief</span></div>',True)]:
                page.set_content(html);self.assertEqual(page.evaluate(self.predicate),expected)
        finally:page.close()

if __name__=='__main__':unittest.main()
