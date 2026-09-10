"""Michigan name-search regression: wrong first rows and incomplete searches."""
import sys, unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

def link(name, number, status='', expiration='12/31/2026'):
    item=Mock();item.get_attribute.return_value='javascript:btnOrgName'+number
    item.inner_text.return_value=name
    row=item.locator.return_value
    row.inner_text.return_value=f'{number} {name} Chantilly VA {expiration}'
    row.evaluate.return_value={'status':status}
    return item

def frame_for(items):
    frame=Mock();frame.locator.return_value.count.return_value=len(items)
    frame.locator.return_value.nth.side_effect=items.__getitem__
    return frame

class MichiganNameTests(unittest.TestCase):
    def setUp(self):
        self.org=c.checker.Organization("America's Charities",'54-1517707')
        self.correct=link("America's Charities",'9927')
        self.wrong=link("America's Best Charities",'10158')

    def flow(self,items,*,text='2 record(s) found',open_error=None,missing_frame=False,clock=None,variants=None,lookup_deadline=None,navigation_ms=None):
        page=Mock();page.expect_navigation.return_value=nullcontext()
        if navigation_ms is not None:
            def navigation(**kwargs):
                if kwargs['timeout'] < navigation_ms:raise TimeoutError('results arrive after navigation cutoff')
                return nullcontext()
            page.expect_navigation.side_effect=navigation
        if lookup_deadline is not None:page._cc_mi_lookup_deadline=lookup_deadline
        frame=frame_for(items)
        module=SimpleNamespace(open_search_form=Mock(return_value=True,side_effect=open_error),
            find_results_frame=Mock(return_value=None if missing_frame else frame),
            body_text=Mock(return_value=text),normalize_name=c.normalized_match_name,
            click_result_link=Mock(),find_detail_frame=Mock(return_value=None),
            MI_SEARCH_URL="https://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx",wait_for_search_form=Mock(return_value=True))
        with patch.object(c,'state_extension_module',return_value=module), \
             patch.object(c,'patch_mi_module_for_fast_lookups') as initialize, \
             patch.object(c,'organization_name_variants',return_value=variants if variants is not None else ['America Charities',"America's Charities",'Americas Charities','America s Charities']), \
             (patch.object(c.time,'perf_counter',side_effect=clock) if clock else nullcontext()):
            result=c.search_mi_name_fallback(page,self.org)
        initialize.assert_called_once_with(module)
        return result,page,module

    def test_correct_row_found_after_unrelated_first_row_in_both_orders(self):
        for items in ([self.wrong,self.correct],[self.correct,self.wrong]):
            r,page,_=self.flow(items)
            self.assertEqual(r.status,'Upcoming Filing');self.assertEqual(r.matched_registry_identifier,'9927')
            self.assertEqual(r.matched_registry_name,"America's Charities")
            self.assertEqual(r.queries_attempted,["America's Charities"])

    def test_six_result_reproduction(self):
        items=[self.wrong,self.correct,link('American Lebanese Syrian Associated Charities, Inc.','3799'),
               link('American Legion Charities, Inc.','52972'),link('Charities Aid Foundation America','29809'),
               link('Thoroughbred Charities of America, Inc.','59990')]
        r,_,_=self.flow(items,text='6 record(s) found')
        self.assertEqual(r.matched_registry_identifier,'9927')

    def test_exact_identity_active_tie_and_unrelated_active_record(self):
        closed=link("America's Charities",'1001','Closed');active=link("America's Charities",'1002','Active')
        unrelated=link("America's Best Charities",'3','Active')
        for items in ([unrelated,closed,active],[active,closed,unrelated]):
            r,_,_=self.flow(items);self.assertEqual(r.matched_registry_identifier,'1002')

    def test_no_completed_match_is_negative_only_after_all_queries(self):
        r,_,_=self.flow([],text='0 record(s) found')
        self.assertEqual(c.public_status(r),'Not Registered');self.assertTrue(r.success)
        self.assertEqual(r.queries_attempted,["America's Charities",'America Charities','Americas Charities']);self.assertEqual(len(r.source_attempts),4)
        self.assertEqual(r.reason_code,'MI_COMPLETED_EIN_AND_NAME_SEARCH')

    def test_unrelated_results_do_not_get_matched(self):
        r,_,_=self.flow([self.wrong],text='1 record(s) found')
        self.assertEqual(c.public_status(r),'Not Registered');self.assertFalse(r.matched_registry_name)

    def test_form_timeout_is_inconclusive(self):
        r,_,_=self.flow([],open_error=TimeoutError('form unavailable'))
        self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)
        self.assertIn('form unavailable',r.error)

    def test_missing_results_frame_is_inconclusive(self):
        r,_,_=self.flow([],missing_frame=True)
        self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)

    def test_unrecognized_results_are_not_a_completed_negative(self):
        r,_,_=self.flow([],text='Please try again later')
        self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)
        self.assertEqual(r.source_attempts,[])

    def test_punctuation_variant_is_safe_but_unrelated_name_is_not(self):
        r,_,_=self.flow([self.wrong,link('Americas Charities','9927')])
        self.assertEqual(r.matched_registry_identifier,'9927')

    def test_budget_exhaustion_is_not_a_negative(self):
        r,_,_=self.flow([],clock=iter([0,75]).__next__)
        self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)
        self.assertEqual(r.queries_attempted,[])

    def test_selected_row_does_not_borrow_another_rows_expiration(self):
        self.correct.locator.return_value.inner_text.return_value="9927 America's Charities"
        r,_,_=self.flow([self.correct,self.wrong],text="2 record(s) found America's Charities America's Best Charities 12/31/2027")
        self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)

    def test_browser_actions_use_remaining_budget(self):
        page=SimpleNamespace(_cc_mi_name_deadline=24)
        with patch.object(c.time,'perf_counter',return_value=23):self.assertEqual(c.mi_action_timeout(page,8000),1000)
        with patch.object(c.time,'perf_counter',return_value=24):
            with self.assertRaises(TimeoutError):c.mi_action_timeout(page,8000)

    def test_actual_one_word_legal_name_is_searched(self):
        self.org=c.checker.Organization('Earthjustice','94-1730465')
        r,_,_=self.flow([],text='0 record(s) found',variants=['Earthjustice','The Earthjustice','Earthjustice Inc'])
        self.assertEqual(c.public_status(r),'Not Registered');self.assertTrue(r.success)
        self.assertEqual(r.queries_attempted,['Earthjustice'])
        self.assertEqual(r.reason_code,'MI_COMPLETED_EIN_AND_NAME_SEARCH')

    def test_one_word_fragment_of_a_longer_name_is_not_searched(self):
        self.org=c.checker.Organization('Junior Achievement USA','84-1267604')
        r,_,_=self.flow([],text='0 record(s) found',variants=['Achievement','Junior Achievement USA'])
        self.assertEqual(r.queries_attempted,['Junior Achievement USA'])

    def test_completed_empty_query_skips_only_word_supersets(self):
        self.org=c.checker.Organization('Junior Achievement USA','84-1267604')
        r,page,module=self.flow([],text='0 record(s) found',variants=['The Junior Achievement USA','Junior Achievement USA','Junior Achievement USA Inc','Junior Achievement USA, Inc'])
        self.assertEqual(r.queries_attempted,['Junior Achievement USA','Junior Achievement USA, Inc'])
        self.assertTrue(r.success)
        self.assertTrue(any('Skipped redundant' in x for x in r.source_attempts))
        module.open_search_form.assert_called_once()
        module.wait_for_search_form.assert_called_once()

    def test_candidate_rows_do_not_justify_skipping_another_query(self):
        self.org=c.checker.Organization('Junior Achievement USA','84-1267604')
        r,_,_=self.flow([self.wrong],variants=['Junior Achievement USA','The Junior Achievement USA'])
        self.assertEqual(r.queries_attempted,['Junior Achievement USA','The Junior Achievement USA'])

    def test_incomplete_query_never_allows_a_completed_negative(self):
        self.org=c.checker.Organization('Junior Achievement USA','84-1267604')
        r,_,_=self.flow([],missing_frame=True,variants=['Junior Achievement USA','The Junior Achievement USA'])
        self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)
        self.assertEqual(r.source_attempts,[])

    def test_name_allowance_cannot_extend_existing_state_budget(self):
        r,_,_=self.flow([],clock=iter([0,6]).__next__,lookup_deadline=5)
        self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)
        self.assertEqual(r.queries_attempted,[])

    def test_nine_second_results_response_completes_within_state_budget(self):
        r,_,_=self.flow([self.correct],navigation_ms=9000)
        self.assertEqual(r.status,'Upcoming Filing');self.assertTrue(r.success)

    def test_navigation_cannot_overrun_remaining_state_budget(self):
        r,_,_=self.flow([self.correct],navigation_ms=9000,lookup_deadline=8,clock=lambda:0)
        self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)

if __name__=='__main__':unittest.main()
