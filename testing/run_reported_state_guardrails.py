"""Behavior tests for the September reported issues; no runtime lookup script."""
import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class ReportedStateTests(unittest.TestCase):
    def test_corporate_descriptions_generalize_without_erasing_identity(self):
        for suffix in ('a California nonprofit religious corporation', 'a New York nonprofit religious corporation',
                       'an Oklahoma nonprofit charitable corporation', 'a Delaware non-profit public benefit corporation'):
            with self.subTest(suffix=suffix):
                self.assertTrue(cc.registry_name_is_safe_for_org('Example Relief, '+suffix, 'Example Relief'))
                self.assertFalse(cc.registry_name_is_safe_for_org('Different Relief, '+suffix, 'Example Relief'))
                self.assertFalse(cc.registry_name_is_safe_for_org('Example Relief Texas Chapter, '+suffix, 'Example Relief'))
        for name in ('Example Relief California', 'Example Relief, New York Chapter', 'Example Relief Corporation of Oklahoma'):
            self.assertEqual(cc.legal_name_without_corporate_description(name), name)

    def test_conflicting_ein_overrides_exact_name_and_alias(self):
        for name in ('Example Relief', 'Example Relief, a California nonprofit religious corporation'):
            self.assertEqual(cc.score_candidate('Example Relief', '123456789', {'name':name,'ein':'987654321'})['reason'], 'REJECT_DIFFERENT_EIN')
        self.assertEqual(cc.score_candidate('Example Relief', '123456789', {'name':'Renamed Relief','ein':'123456789'})['decision'], 'accepted')

    def test_nh_c_uses_due_date_without_claiming_good_standing(self):
        org=cc.checker.Organization('Example Relief', '123456789')
        for code, due, expected in [('C',date(2020,1,1),'Delinquent'), ('C',date(2090,1,1),'Current'),
                                    ('S',date(2090,1,1),'Suspended'),('X',date(2090,1,1),'Delinquent'),
                                    ('G',date(2090,1,1),'Current'),('C',None,'Needs Review')]:
            row={'registry_id':'1234','registry_name':'Example Relief','registry_words':{'example','relief'},
                 'body':'Example Relief 1 Main Street','status_code':code,'due_date':due,'due_raw':str(due or '')}
            with patch.object(cc,'nh_live_pdf_records',return_value=([row],'September 02, 2026')):
                result=cc.search_nh_live_pdf(org)
                self.assertEqual(result.status,expected)
                if code=='C': self.assertNotIn('Good Standing',result.raw_status_text)

    def test_nh_pdf_retains_reported_record(self):
        result=cc.search_nh_live_pdf(cc.checker.Organization('Focus on the Family','953188150'))
        self.assertEqual(result.matched_registry_identifier,'11711')
        self.assertEqual(result.status,'Delinquent')
        self.assertIn('2/15/2017',result.raw_status_text)

    def test_md_extension_calendar_is_not_six_months_added_to_base(self):
        self.assertEqual(cc.md_automatic_extension_due_date(date(2026,6,30)),date(2027,5,15))
        self.assertEqual(cc.md_automatic_extension_due_date(date(2026,12,31)),date(2027,11,15))

    def nd(self, rows, detail=None, http=200):
        page=Mock()
        response=Mock(status=http)
        response.json.return_value={'template':[],'rows':rows}
        pending=Mock();pending.value=response
        context=Mock();context.__enter__=Mock(return_value=pending);context.__exit__=Mock(return_value=False)
        page.expect_response.return_value=context
        detail_response=Mock(status=200)
        detail_response.json.return_value=detail or {'DRAWER_DETAIL_LIST':[{'LABEL':'Status','VALUE':'Active'}]}
        detail_context=Mock();detail_context.__enter__=Mock(return_value=SimpleNamespace(value=detail_response));detail_context.__exit__=Mock(return_value=False)
        if rows and all(isinstance(r,dict) and r.get('TITLE') for r in rows.values()):
            page.expect_response.side_effect=[context,detail_context]
        return cc.search_nd_completed(page,cc.checker.Organization('Example Relief','123456789')),page

    def test_nd_completed_empty_result_is_negative(self):
        r,p=self.nd({})
        self.assertEqual(r.status,cc.checker.STATUS_NOT_REGISTERED)
        self.assertTrue(r.success)

    def test_nd_selects_matching_row_not_first(self):
        r,p=self.nd({'1':{'ID':1,'TITLE':['Other Relief'],'STATUS':'Active'},
                     '2':{'ID':2,'TITLE':['Example Relief'],'STATUS':'Active','RECORD_NUM':'0004022'}})
        self.assertEqual(r.matched_registry_identifier,'0004022')
        p.get_by_text.assert_called_once_with('Example Relief',exact=True)

    def test_nd_incomplete_and_failed_responses_are_not_negative(self):
        for rows,code in ((None,200),({'1':{'ID':1}},200),({},500)):
            r,p=self.nd(rows,http=code)
            self.assertNotEqual(r.status,cc.checker.STATUS_NOT_REGISTERED)
            self.assertFalse(r.success)

    def test_nd_explicit_inactive_is_retained(self):
        r,p=self.nd({'1':{'ID':1,'TITLE':['Example Relief'],'STATUS':'Inactive - Involuntary'}},
                    {'DRAWER_DETAIL_LIST':[{'LABEL':'Status','VALUE':'Inactive - Involuntary'}]})
        self.assertEqual(r.raw_status_text,'Inactive - Involuntary')
        self.assertEqual(cc.public_status(r),'Closed / Withdrawn / Canceled')
        self.assertEqual(cc.true_status_from_body(r,''),'Closed / Withdrawn / Canceled')

    def test_ma_fully_failed_direct_queries_are_not_completed_negative(self):
        org=cc.checker.Organization('Example Relief','123456789')
        with patch.object(cc,'me_fast_direct_search_rows',side_effect=ValueError('incomplete page')):
            self.assertIsNone(cc.me_fast_direct_confirmation_result(org))

    def test_me_partial_query_failure_is_not_completed_negative(self):
        org=cc.checker.Organization('Example Relief','123456789')
        with patch.object(cc,'me_fast_direct_query_variants',return_value=['Example Relief','Example']), \
             patch.object(cc,'me_fast_direct_search_rows',side_effect=[([],Mock()),ValueError('incomplete page')]):
            self.assertIsNone(cc.me_fast_direct_confirmation_result(org))

if __name__=='__main__': unittest.main(verbosity=2)
