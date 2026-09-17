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
    def test_extra_pages_do_not_invalidate_completed_first_page(self):
        for count in (2,3,4,20):
            pages=Pages(count);selected,org=self.choose(pages)
            self.assertIsNone(selected);self.assertEqual(pages.current,1);self.assertFalse(org.ok_search_incomplete)
            self.assertEqual(pages.waits,[])
    def test_later_pages_are_outside_approved_search_policy(self):
        pages=Pages(3);selected,org=self.choose(pages,target=3)
        self.assertIsNone(selected);self.assertEqual(pages.current,1)
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
    def test_all_incomplete_first_pages_never_become_not_registered(self):
        result,calls=self.run_variants();self.assertEqual(result.status,'Unable to Confirm');self.assertEqual(len(calls),4)
    def test_complete_targeted_search_cannot_hide_other_unfinished_queries(self):
        result,calls=self.run_variants(complete_query='responders')
        self.assertEqual(result.status,'Unable to Confirm');self.assertEqual(len(result.queries_attempted),4)
        self.assertEqual([c[1] for c in calls],[1,1,1,1]);self.assertEqual(len({c[2] for c in calls}),1)
    def test_outage_does_not_reuse_an_earlier_negative(self):
        # Curly apostrophes now retain the same possessive token as ASCII input.
        result,_=self.run_variants(complete_query='responders',error_query='childrens')
        self.assertEqual(result.status,'Site Not Reachable')

class ReviewedNameTimingTests(unittest.TestCase):
    def run_plan(self, count, seconds, positive=False):
        now=[0.0];calls=[]
        queries=['Example Relief']+[f'Confirmed Previous Name {i}' for i in range(1,count)]
        module=SimpleNamespace(OK_SEARCH_URL='https://www.sos.ok.gov/corp/charityInquiryFind.aspx',
            SearchResult=lambda **kw:SimpleNamespace(**kw),STATUS_NOT_FOUND='Not Registered')
        def search(page,org,module):
            calls.append((org.organization_name,org.ok_search_deadline,org.ok_search_page_limit))
            now[0]+=seconds
            return SimpleNamespace(organization_name=org.organization_name,
                status='Current' if positive else 'Not Registered',success=True,
                matched_registry_name='',raw_status_text='',source_note='',error='')
        with patch.object(cc.time,'perf_counter',side_effect=lambda:now[0]), \
             patch.object(cc,'build_search_queries',return_value=['Example Relief']), \
             patch.object(cc,'reviewed_queries_first',return_value=queries), \
             patch.object(cc,'organization_match_target_variants',return_value=['Example Relief']), \
             patch.object(cc,'search_ok_precise',side_effect=search), \
             patch.object(cc,'public_status',lambda r:r.status):
            result=cc.search_ok_with_variants(None,cc.checker.Organization('Example Relief','123456789'),module)
        return result,calls,queries
    def test_short_plan_retains_existing_deadline_and_first_page_policy(self):
        result,calls,_=self.run_plan(4,6)
        self.assertEqual(result.status,'Not Registered')
        self.assertEqual({row[1] for row in calls},{72.0})
        self.assertEqual({row[2] for row in calls},{1})
    def test_long_reviewed_plan_completes_without_dropping_queries(self):
        result,calls,queries=self.run_plan(14,6)
        self.assertEqual(result.status,'Not Registered')
        self.assertEqual([row[0] for row in calls],queries)
        self.assertEqual(result.queries_attempted,queries)
        self.assertIn(queries[-1],result.source_attempts[0])
    def test_extended_budget_is_bounded_and_incomplete_is_not_negative(self):
        result,calls,_=self.run_plan(40,10)
        self.assertNotEqual(result.status,'Not Registered')
        self.assertLess(len(calls),40)
        self.assertLessEqual(max(row[1] for row in calls),100.0)
    def test_positive_still_returns_without_waiting_for_unused_names(self):
        result,calls,_=self.run_plan(14,6,positive=True)
        self.assertEqual(result.status,'Current');self.assertEqual(len(calls),1)

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
