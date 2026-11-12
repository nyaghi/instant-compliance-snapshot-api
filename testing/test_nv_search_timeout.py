import time, unittest
from unittest.mock import patch
import registry_snapshot_server as cc

class NevadaSearchTimeout(unittest.TestCase):
    def record(self,state='NV',operation='search',completed=None):
        return dict(state=state,organization_name='Example Research',ein='123456789',issued=time.time(),
                    completed=completed or [],pending={'query':{'state':state,'operation':operation,'name':'Example'}},alternate_names=[])
    def test_only_nv_search_timeouts_map_to_unreachable(self):
        for state in ['NV','NC','TN','NM','AL','MS']:
            for operation in ['search','detail']:
                for reason in ['NY_CONNECTOR_REGISTRY_NV_SEARCH_RESPONSE_TIMEOUT','NY_CONNECTOR_REGISTRY_NV_COLUMNS_CHANGED','NY_CONNECTOR_REGISTRY_NV_SEARCH_NOT_STARTED','NY_CONNECTOR_REGISTRY_NV_RESPONSE_INCOMPLETE']:
                    with self.subTest(state=state,operation=operation,reason=reason):
                        with patch.object(cc,'response_data_for_lookup',side_effect=lambda result,*args:dict(status=result.status,success=result.success)):
                            out=cc.final_four_connector_failure(self.record(state,operation),reason)
                        expected=state=='NV' and operation=='search' and reason.endswith('SEARCH_RESPONSE_TIMEOUT')
                        self.assertEqual(out['status'],'Site Not Reachable' if expected else 'Unable to Confirm')
                        self.assertFalse(out['success'])
    def test_total_lookup_timeout_includes_later_search_and_detail(self):
        for operation in ['search','detail']:
            for state in ['NV','TN','NC']:
                with patch.object(cc,'response_data_for_lookup',side_effect=lambda result,*args:dict(status=result.status,success=result.success)):
                    out=cc.final_four_connector_failure(self.record(state,operation),'NY_CONNECTOR_REGISTRY_NV_LOOKUP_TIMEOUT')
                self.assertEqual(out['status'],'Site Not Reachable' if state=='NV' else 'Unable to Confirm')
                self.assertFalse(out['success'])
    def test_actual_renderer_and_partial_history_preserve_failed_check(self):
        completed=[{'query':{'state':'NV','operation':'search','name':'Example Research'}}]
        with patch.object(cc,'reconciled_registry_address',return_value=''):
            out=cc.final_four_connector_failure(self.record(completed=completed),'NY_CONNECTOR_REGISTRY_NV_SEARCH_RESPONSE_TIMEOUT')
        self.assertEqual(out['status'],'Site Not Reachable')
        self.assertFalse(out.get('success'))
        self.assertFalse(out.get('evidence_url'))
        self.assertIn('stopped waiting',out['comments'])
        self.assertEqual([q['completed'] for q in out['queries_attempted']],[True,False])
if __name__=='__main__':unittest.main()
