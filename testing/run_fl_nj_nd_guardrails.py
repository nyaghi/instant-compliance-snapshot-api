"""Completion, bounded recovery and duplicate-name selection regression tests."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class RecoveryTests(unittest.TestCase):
    def retry(self,state,first,second):
        with patch.object(c,'run_state_lookup',side_effect=[first,second]) as lookup, patch.object(c.time,'sleep'):
            result=c.run_single_state_lookup_reliably('Example Relief','123456789',state)
        self.assertEqual(lookup.call_count,2)
        self.assertEqual(result['status'],second['status'])
    def test_nj_incomplete_search_recovers(self):
        self.retry('NJ',{'status':'Unable to Verify','reason_code':'NJ_INCOMPLETE_EIN_SEARCH'},{'status':'Upcoming Filing'})
    def test_fl_incomplete_search_recovers(self):
        self.retry('FL',{'status':'Unable to Confirm','reason_code':'FL_INCOMPLETE_SEARCH'},{'status':'Suspended'})
    def test_nj_recovery_is_bounded(self):
        with patch.object(c,'run_state_lookup',return_value={'status':'Unable to Verify','reason_code':'NJ_INCOMPLETE_EIN_SEARCH'}) as lookup, patch.object(c.time,'sleep'):
            result=c.run_single_state_lookup_reliably('Example Relief','123456789','NJ')
        self.assertEqual(lookup.call_count,c.SINGLE_STATE_SEMANTIC_RETRY_ATTEMPTS)
        self.assertEqual(result['status'],'Unable to Verify')
    def test_unrelated_inconclusive_not_retried(self):
        with patch.object(c,'run_state_lookup',return_value={'status':'Unable to Verify','reason_code':'IDENTITY_CONFLICT'}) as lookup:
            c.run_single_state_lookup_reliably('Example Relief','123456789','NJ')
        self.assertEqual(lookup.call_count,1)
    def test_completed_fl_negative_preserved(self):
        with patch.object(c,'run_state_lookup',return_value={'status':'Not Registered','source_note':'Completed explicit no-record response'}) as lookup:
            result=c.run_single_state_lookup_reliably('Example Relief','123456789','FL')
        self.assertEqual(lookup.call_count,1);self.assertEqual(result['status'],'Not Registered')
    def test_fl_loading_is_not_negative(self):
        page=MagicMock();response=Mock(status=200)
        page.expect_navigation.return_value.__enter__.return_value.value=response
        page.evaluate.return_value=[]
        with patch.object(c,'high_signal_search_phrases',return_value=['Example Relief']), patch.object(c,'organization_name_variants',return_value=[]), patch.object(c.checker,'find_visible_input',return_value=page), patch.object(c,'readable_page_text',return_value='Loading results...'), patch.object(c.time,'sleep'):
            result=c.search_fl(page,SimpleNamespace(organization_name='Example Relief',ein='123456789'))
        self.assertFalse(result.success);self.assertEqual(result.reason_code,'FL_INCOMPLETE_SEARCH')
        self.assertEqual(result.status,'Unable to Confirm')
    def test_nd_click_uses_selected_record_number(self):
        page=MagicMock()
        old={'ID':11,'RECORD_NUM':'0004010011','TITLE':['Example Relief'],'STATUS':'Inactive - Involuntary'}
        active={'ID':22,'RECORD_NUM':'0004010022','TITLE':['Example Relief'],'STATUS':'Active'}
        responses=[]
        for data in [{'rows':{'11':old,'22':active},'template':[]},{'DRAWER_DETAIL_LIST':[{'LABEL':'Status','VALUE':'Active'}]}]:
            response=Mock(status=200);response.json.return_value=data
            pending=MagicMock();pending.__enter__.return_value.value=response;responses.append(pending)
        page.expect_response.side_effect=responses
        result=c.search_nd_completed(page,SimpleNamespace(organization_name='Example Relief',ein='123456789'))
        self.assertTrue(result.success);self.assertEqual(result.matched_registry_identifier,'0004010022')
        page.get_by_role.assert_any_call('cell',name='0004010022',exact=True)
        page.get_by_text.assert_not_called()

if __name__=='__main__':unittest.main()
