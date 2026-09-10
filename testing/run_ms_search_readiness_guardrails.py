"""Mississippi search readiness: real DOM timing and conservative failures."""
import sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

TABLE='<table><tr><th>Charity Name</th><th>Status</th></tr><tr><td>FoodCorps, Inc.</td><td>Closed - Expired</td></tr></table>'

class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw=c.checker.sync_playwright().start();cls.browser=cls.pw.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.pw.stop()
    def setUp(self):self.page=self.browser.new_page()
    def tearDown(self):self.page.close()
    def brief_wait(self):
        page=Mock(wraps=self.page)
        page.wait_for_function.side_effect=lambda script,**kw:self.page.wait_for_function(script,timeout=150)
        return c.ms_wait_for_search_results(page)
    def test_immediate_table_returns_without_fixed_delay(self):
        self.page.set_content(TABLE);started=time.perf_counter()
        table,empty,note=c.ms_wait_for_search_results(self.page)
        self.assertIn('FoodCorps',table.inner_text());self.assertFalse(empty);self.assertEqual(note,'')
        self.assertLess(time.perf_counter()-started,1)
    def test_delayed_results_cross_old_four_second_cutoff(self):
        self.page.set_content('<div>Please Wait .</div>')
        self.page.evaluate('(html) => setTimeout(() => document.body.innerHTML=html, 5200)',TABLE)
        table,empty,note=c.ms_wait_for_search_results(self.page)
        self.assertIn('FoodCorps',table.inner_text());self.assertFalse(empty);self.assertIn('became ready',note)
    def test_completed_empty_search_is_recognized(self):
        for text in ['No results found','No records found','No matching records','0 results']:
            with self.subTest(text=text):
                self.page.set_content(text);table,empty,_=c.ms_wait_for_search_results(self.page)
                self.assertIsNone(table);self.assertTrue(empty)
    def test_loading_overlay_blocks_old_table_and_no_rows_text(self):
        for html in [TABLE,'No results found']:
            with self.subTest(html=html):
                self.page.set_content(html+'<div>Please Wait .</div>')
                table,empty,note=self.brief_wait()
                self.assertIsNone(table);self.assertFalse(empty);self.assertIn('incomplete',note)
    def test_missing_body_stays_inconclusive(self):
        self.page.evaluate('document.body.remove()')
        table,empty,note=self.brief_wait()
        self.assertIsNone(table);self.assertFalse(empty);self.assertIn('incomplete',note)
    def test_failed_request_page_never_means_not_registered(self):
        self.page.set_content('Service unavailable. Search request failed.')
        table,empty,note=self.brief_wait()
        self.assertIsNone(table);self.assertFalse(empty);self.assertIn('incomplete',note)
    def test_existing_table_criteria_and_order_are_preserved(self):
        self.page.set_content('<table><tr><td>Charity Name</td></tr></table>'+TABLE)
        table,empty,_=c.ms_wait_for_search_results(self.page)
        self.assertEqual(table.inner_text(),self.page.locator('table').nth(1).inner_text());self.assertFalse(empty)

class BudgetAndWorkflowTests(unittest.TestCase):
    def test_admitted_search_has_eight_second_readiness_limit(self):
        page=Mock();page.wait_for_function.return_value.json_value.return_value={'no_rows':True}
        c.ms_wait_for_search_results(page)
        self.assertEqual(page.wait_for_function.call_args.kwargs['timeout'],8000)
    def test_readiness_exception_remains_inconclusive(self):
        page=Mock();page.wait_for_function.side_effect=RuntimeError('page closed')
        table,empty,note=c.ms_wait_for_search_results(page)
        self.assertIsNone(table);self.assertFalse(empty);self.assertIn('RuntimeError',note)
    def test_missing_results_do_not_become_negative_in_normal_ms_search(self):
        module=c.state_batch_modules(['MS'])[c.load_state_batch_bundle().STATE_TO_MODULE['MS']]
        org=module.Organization(organization_name='FoodCorps, Inc.');page=Mock()
        with patch.object(module,'find_visible_input',return_value=Mock()),patch.object(c,'safe_wait_for_network_idle'),patch.object(c,'ms_wait_for_search_results',return_value=(None,False,'incomplete')):
            result=c.search_ms_fast(page,org)
        self.assertEqual(result.status,'Unable to Verify');self.assertFalse(result.success)
        self.assertEqual(result.source_confidence,'incomplete_search')
    def test_existing_budget_stops_starting_more_variants(self):
        seen=[];clock=[100.0]
        def search(page,org,navigate=True):
            seen.append(org.organization_name);clock[0]+=33
            return SimpleNamespace(status='Not Registered',organization_name=org.organization_name,raw_status_text='No results found',source_note='',success=True)
        with patch.object(c.time,'perf_counter',side_effect=lambda:clock[0]),patch.object(c,'search_ms_fast',side_effect=search),patch.object(c,'copy_external_result',side_effect=lambda org,state,result:result):
            c.search_batch_browser_state(Mock(),c.checker.Organization('FoodCorps, Inc.','27-3990987'),'MS')
        self.assertEqual(len(seen),1)

if __name__=='__main__':unittest.main()
