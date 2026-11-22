import pathlib,json,time,sys,unittest
from unittest.mock import patch
import registry_snapshot_server as cc
from deployment import source_availability as av

class MississippiHostError(unittest.TestCase):
    def test_70_records_and_adjacent_reasons(self):
        cases=json.loads((pathlib.Path(__file__).parent/'fixtures/gate55/LOCAL-70.json').read_text())
        self.assertEqual(len({o['ein'] for o in cases}),70)
        for org in cases:
            for state,reason,expected in [('MS','NY_CONNECTOR_REGISTRY_MS_HOST_ERROR','Site Not Reachable'),('MS','NY_CONNECTOR_TAB_READY_TIMEOUT','Unable to Confirm'),('MS','NY_CONNECTOR_MS_VERIFICATION_PENDING','Unable to Confirm'),('NC','NY_CONNECTOR_REGISTRY_MS_HOST_ERROR','Unable to Confirm')]:
                record=dict(state=state,organization_name=org['name'],ein=org['ein'],issued=time.time(),completed=[],pending={},alternate_names=[])
                with self.subTest(ein=org['ein'],state=state,reason=reason), patch.object(cc,'response_data_for_lookup',side_effect=lambda result,*args:dict(status=result.status,state=state,success=result.success,status_reason=result.status_reason)):
                    result=av.apply(cc.final_four_connector_failure(record,reason))
                    self.assertEqual(result['status'],expected)
                    self.assertEqual('520' in result['comments'],expected=='Site Not Reachable')
                    self.assertFalse(result['success'])

