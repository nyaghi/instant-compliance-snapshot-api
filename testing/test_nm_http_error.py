import time,unittest
from unittest.mock import patch
import registry_snapshot_server as cc

class NmHttpFailure(unittest.TestCase):
 def test_scoped_status_mapping_and_negative_controls(self):
  for state in ['NM','NC','NV','AL','TN','MS']:
   for reason in ['NY_CONNECTOR_REGISTRY_NM_HTTP_ERROR','NY_CONNECTOR_TAB_READY_TIMEOUT','NY_CONNECTOR_REGISTRY_NM_SOURCE_ERROR','NY_CONNECTOR_NM_VERIFICATION_PENDING']:
    with self.subTest(state=state,reason=reason):
     r=dict(state=state,organization_name='Example Research',ein='123456789',issued=time.time(),completed=[],pending={},alternate_names=[])
     with patch.object(cc,'response_data_for_lookup',side_effect=lambda result,*args:dict(status=result.status,success=result.success)):
      out=cc.final_four_connector_failure(r,reason)
     expected=state=='NM' and reason=='NY_CONNECTOR_REGISTRY_NM_HTTP_ERROR'
     self.assertEqual(out['status'],'Site Not Reachable' if expected else 'Unable to Confirm')
     self.assertFalse(out['success'])
     self.assertEqual('HTTP server error' in out['comments'],expected)
 def test_real_response_renderer_retains_outage(self):
  r=dict(state='NM',organization_name='Example Research',ein='123456789',issued=time.time(),completed=[],pending={},alternate_names=[])
  with patch.object(cc,'reconciled_registry_address',return_value=''):
   out=cc.final_four_connector_failure(r,'NY_CONNECTOR_REGISTRY_NM_HTTP_ERROR')
  self.assertEqual(out['status'],'Site Not Reachable')
  self.assertFalse(out.get('evidence_url'))
  self.assertFalse(out.get('search_history_url'))
if __name__=='__main__':unittest.main()
