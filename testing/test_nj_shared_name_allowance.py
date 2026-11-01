"""A name plan shares one original allowance; late answers cannot become evidence."""
import time,unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock,MagicMock,patch
import registry_snapshot_server as c
from deployment.state_snapshots import DEADLINE

class SharedNameAllowance(unittest.TestCase):
    def setUp(self):
        self.org=c.checker.Organization('Christian Research Institute Inc.','226063412')
        self.clock=[100.0]
        for item in [patch.object(c,'trial_identity',return_value={'origin':'local'}),
                     patch.object(c.time,'monotonic',side_effect=lambda:self.clock[0]),
                     patch.object(c,'nj_same_lookup_zero_queries',return_value={self.org.ein})]:
            item.start();self.addCleanup(item.stop)
        token=c.LAB_LOOKUP_MODE_CONTEXT.set('standard');self.addCleanup(c.LAB_LOOKUP_MODE_CONTEXT.reset,token)
        token=DEADLINE.set(1000);self.addCleanup(DEADLINE.reset,token)
    def source(self,status='Not Registered'):
        r=c.checker.StateResult(self.org.organization_name,self.org.ein,'NJ',status,'https://state')
        r.success=status!='Unable to Confirm';return r
    def test_each_nested_call_gets_only_the_remaining_shared_allowance(self):
        caps=[]
        def query(*args,**kwargs):
            caps.append(c.nj_query_timeout_ms(60000));self.clock[0]+=11
            return self.source()
        with patch.object(c,'nj_name_fallback_queries',return_value=['First full name','Second name','Third name','Fourth name']),patch.object(c,'search_nj_direct',side_effect=query)as source:
            r=c.search_nj_with_name_fallback(None,self.org)
        self.assertEqual(caps,[32000,21000,10000]);self.assertEqual(source.call_count,3)
        self.assertEqual(r.reason_code,'NJ_NAME_PLAN_INCOMPLETE');self.assertFalse(r.success)
        self.assertEqual(c.NJ_NAME_QUERY_DEADLINE.get(),float('inf'))
    def test_parent_deadline_and_late_positive_are_enforced_without_extending_either(self):
        token=DEADLINE.set(106)
        try:
            def delayed(*args,**kwargs):
                self.assertEqual(c.nj_query_timeout_ms(30000),5000);self.clock[0]=105.01
                return self.source('Current')
            with patch.object(c,'nj_name_fallback_queries',return_value=['Christian Research Institute']),patch.object(c,'search_nj_direct',side_effect=delayed):
                r=c.search_nj_with_name_fallback(None,self.org)
            self.assertEqual(r.reason_code,'NJ_NAME_PLAN_INCOMPLETE');self.assertFalse(r.success)
            self.assertEqual(DEADLINE.get(),106)
        finally:DEADLINE.reset(token)
    def test_context_is_restored_after_source_error_and_unbound_body_uses_legacy_reader(self):
        with patch.object(c,'search_nj_direct',side_effect=ValueError('modeled malformed source')):
            with self.assertRaises(ValueError):c.nj_bounded_name_query(None,self.org,self.org,102)
        self.assertEqual(c.NJ_NAME_QUERY_DEADLINE.get(),float('inf'))
        page=Mock()
        with patch.object(c,'registry_page_body',return_value='original body')as reader:
            self.assertEqual(c.nj_query_page_body(page),'original body');reader.assert_called_once_with(page)
        self.assertEqual(c.nj_query_timeout_ms(1500),1500)
    def test_completed_empty_plan_remains_negative_but_unfinished_plan_does_not(self):
        with patch.object(c,'nj_name_fallback_queries',return_value=['Full name','Alias']),patch.object(c,'search_nj_direct',side_effect=lambda *a,**k:self.source()):
            r=c.search_nj_with_name_fallback(None,self.org)
        self.assertTrue(r.success);self.assertEqual(c.public_status(r),'Not Registered')
        token=c.NJ_NAME_QUERY_DEADLINE.set(100.0001)
        try:
            self.assertEqual(c.nj_query_timeout_ms(3000),1)
            self.clock[0]=101
            with self.assertRaises(TimeoutError):c.nj_query_timeout_ms(3000)
        finally:c.NJ_NAME_QUERY_DEADLINE.reset(token)
    def test_thirty_retained_plans_keep_all_literal_terms_and_prioritize_reviewed_names(self):
        for index in range(30):
            org=c.checker.Organization('Example Relief '+str(index),'123456789')
            names=['Example','RELIEF','Old reviewed name '+str(index),org.organization_name,'Example Relief Foundation']
            with patch.object(c,'known_names_for_ein',return_value=[names[2]]),patch.object(c,'build_search_queries',return_value=names):
                ranked=c.nj_name_fallback_queries(org)
                self.assertCountEqual(ranked,names);self.assertEqual(ranked[:2],[names[2],org.organization_name])
                token=c.LAB_LOOKUP_MODE_CONTEXT.set('sales')
                try:self.assertEqual(c.nj_name_fallback_queries(org),names)
                finally:c.LAB_LOOKUP_MODE_CONTEXT.reset(token)
    def test_outer_pipeline_does_not_restart_detail_after_incomplete_or_review(self):
        for reason in ['NJ_NAME_PLAN_INCOMPLETE','NJ_INCOMPLETE_QUERY_RESPONSE','NJ_INCOMPLETE_EIN_SEARCH','NJ_UNNUMBERED_EXEMPTION_REVIEW']:
            result=self.source('Unable to Confirm');result.reason_code=reason
            with ExitStack()as stack:
                for name,value in [('search_nj_public_details',None),('search_nj_with_name_fallback',result),
                                   ('launch_lookup_browser',MagicMock()),('registry_page_body','Retained public source'),
                                   ('CAPTURE_EVIDENCE_SCREENSHOTS',False),('CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT',False)]:
                    if isinstance(value,bool):stack.enter_context(patch.object(c,name,value))
                    else:stack.enter_context(patch.object(c,name,return_value=value))
                stack.enter_context(patch.object(c.checker,'sync_playwright',MagicMock()))
                detail=stack.enter_context(patch.object(c,'nj_detail_body',side_effect=AssertionError('No second detail acquisition')))
                stack.enter_context(patch.object(c,'response_data_for_lookup',side_effect=lambda r,*a,**k:r))
                output=c._run_state_lookup_source(self.org.organization_name,self.org.ein,'NJ')
                self.assertIs(output,result);detail.assert_not_called()

if __name__=='__main__':unittest.main()
