"""Recorded organization inputs; synthetic transport failures, no live queries."""
import ast, copy, json, subprocess, time, unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as c
from deployment.gate41_repairs import legal_core

ROOT = Path(__file__).resolve().parents[1]
ROSTER = json.loads((ROOT/'testing/fixtures/ms-bound-recovery/LOCAL-70.json').read_text())
ORIGIN = 'https://charityclarity-final-four-29-2.onrender.com'
BASE = 'a578abe39ec9d66db982945b055d732c83be8042'

def prior_request():
    source = subprocess.check_output(['git','show',BASE+':registry_snapshot_server.py'],cwd=ROOT).decode('utf-8')
    node = next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='final_four_connector_request')
    return compile(ast.Module(body=[node],type_ignores=[]),'<SB request>','exec')

class MSBoundRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.old = prior_request()

    def invoke(self, org, *, baseline=False, used=False, stale=False, seconds=120, reason='NY_CONNECTOR_INCOMPLETE'):
        name = org['name']
        query_name = name if legal_core(name) != name else name+', Inc.'
        record = {'state':'MS','protocol':'final-four-public-v1','origin':ORIGIN,
            'organization_name':name,'ein':org['ein'],'alternate_names':[],
            'completed':[],'expires':time.time()+seconds,'source_snapshots':[],
            'pending':{'query_id':'first','query':{'state':'MS','operation':'search','name':query_name}}}
        if used: record['ms_search_recovery']='Prior recovery'
        payload = {'action':'fail','email':'test@example.invalid','admin_passcode':'test-only',
            'device_id':'test-session','check_token':'test-only','query_id':'stale' if stale else 'first','reason':reason}
        next_response = {'phase':'search','query_id':'second',
            'query':{'state':'MS','operation':'search','name':legal_core(query_name)}}
        before = record['expires']
        mocks = dict(trial_identity=lambda:{'origin':ORIGIN},
            is_verified_internal_passcode=lambda *a:True, NY_CONNECTOR_SIGNING_KEY='x'*40,
            ny_connector_unpack=lambda *a:record, ny_connector_pack=lambda r:'continued',
            ein_light_connector_result=lambda *a:None, al_unread_image_retry=lambda *a:None,
            ms_duplicate_exempt_detail_fallback=lambda *a:None,
            final_four_connector_advance=lambda r:copy.deepcopy(next_response),
            final_four_connector_failure=lambda r,reason='':{'state':'MS','status':'Unable to Confirm','reason':reason})
        with ExitStack() as stack:
            for key,value in mocks.items(): stack.enter_context(patch.object(c,key,value,create=True))
            stack.enter_context(patch('deployment.search_history.failed_receipt'))
            stack.enter_context(patch('deployment.search_history.mark_issued'))
            if baseline:
                # Extracted previous function shares patched collaborators, not a live service.
                space = dict(c.__dict__); space.update({k:getattr(c,k) for k in mocks})
                exec(self.old,space)
                out = space['final_four_connector_request'](payload,ORIGIN)
            else: out = c.final_four_connector_request(payload,ORIGIN)
        self.assertEqual(record['expires'],before)
        return out,record

    def test_70_recorded_inputs_pair_old_and_new_recovery(self):
        results=[]
        for org in ROSTER:
            with self.subTest(ein=org['ein']):
                old,_ = self.invoke(org,baseline=True)
                new,record = self.invoke(org)
                self.assertEqual(old[0],200); self.assertEqual(new[0],200)
                self.assertNotIn('recovery',old[1])
                if len(legal_core(org['name']).split()) < 2:
                    self.assertEqual(old,new)
                    results.append({**org,'single_acronym_recovery_still_disallowed':True})
                    continue
                self.assertEqual(new[1]['recovery'],{'action':'fresh_browser','attempt':1,'reason':'NY_CONNECTOR_INCOMPLETE'})
                self.assertEqual(old[1]['query'],new[1]['query'])
                self.assertEqual(new[1]['query']['state'],'MS')
                self.assertEqual(record['completed'],[])
                results.append({**org,'same_query':True,'fresh_MS_transport':True,'deadline_not_reset':True})
        self.assertEqual(len(results),70)
        target = __import__('os').environ.get('CC_MS_70_REPORT')
        if target: Path(target).write_text(json.dumps({'passed':True,'cases':results,'scope':'70 distinct recorded org inputs with mocked transport failures; paired server continuation contracts, not live source searches.'},indent=2))

    def test_no_second_recovery_stale_query_or_unrelated_failure(self):
        for options in ({'used':True},{'stale':True},{'seconds':10},{'reason':'NY_CONNECTOR_INVALID_SEQUENCE'}):
            status,record = self.invoke(ROSTER[0],**options)
            self.assertEqual(status[1]['phase'],'complete')
            self.assertEqual(status[1]['result']['status'],'Unable to Confirm')
            self.assertNotIn('recovery',status[1])

if __name__ == '__main__': unittest.main()
