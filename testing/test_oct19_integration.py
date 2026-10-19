"""Join actual packaged collector outputs to signed master; compare exact FZ."""
import copy,importlib.util,json,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];P=ROOT.parent
sys.path.insert(0,str(ROOT))
import registry_snapshot_server as c
from testing import run_final_four_continuation_guardrails as signed
COHORT=json.loads((ROOT/'testing/fixtures/oct19-cohort.json').read_text())[:30]
RECEIPT={}

class Integration(unittest.TestCase):
    def test_actual_packaged_collector_outputs_complete_thirty_signed_positive_workflows(self):
        outputs=json.loads((P/'nc-collector-outputs.json').read_text())
        passed=[]
        for out in outputs:
            with self.subTest(organization=out['name'],order=out['evidence']['rows'][0]['Status']):
                t=signed.ContinuationControls('test_all_four_complete_through_signed_master_replay');t.setUp()
                try:
                    t.orgs['NC']=c.checker.Organization(out['name'],out['ein'])
                    source=next(x for x in out['evidence']['rows'] if x['License'])
                    with patch.object(c,'licensed_charity_names',return_value=([out['name']],[])):
                        code,res=t.start('NC')
                        for _ in range(15):
                            if res.get('phase')!='search':break
                            q=res['query']
                            if q['operation']=='search':
                                evidence={**copy.deepcopy(out['evidence']),'query':q,'search_mode':q.get('search_mode','STARTS_WITH')}
                            elif q['operation']=='detail':
                                self.assertEqual(q['identifier'],'SL123456')
                                fields={'Name':out['name'],'Registration #':source['License'],'Status':source['Status'],'Expiration Date':source['Expiration Date'],'Extension End Date':'','Last Application Date':'7/1/2026','Street':'14200 Park Meadow Dr Ste 330s','City':'Chantilly','State':'VA','Zip':'20151-4210','profile_url':source['profile_url']}
                                evidence={'query':q,'complete':True,'fields':fields}
                            elif q['operation']=='filings':
                                evidence={'query':q,'complete':True,'url':q['url'],'rows':[{'type':'Renewal Charity','date':'7/1/2026'}]}
                            else:self.fail(q)
                            code,res=t.advance(res,evidence=evidence)
                    self.assertEqual(code,200);self.assertEqual(res['phase'],'complete')
                    self.assertEqual(res['result']['status'],'Current',res)
                    self.assertEqual(res['result']['matched_registry_identifier'],'SL123456')
                    passed.append(out['ein'])
                finally:t.doCleanups()
        self.assertEqual(len(passed),60)
        RECEIPT['NC-collector-signed']={'distinct_organizations':len(set(passed)),'orders':len(passed)}

    def test_thirty_org_all_other_state_external_adapters_identical_to_exact_fz(self):
        spec=importlib.util.spec_from_file_location('oct19_unchanged_fz',P.parent/'cogency-demo-20261019/weekly-data-worktree/registry_snapshot_server.py')
        b=importlib.util.module_from_spec(spec);sys.modules[spec.name]=b;spec.loader.exec_module(b)
        states=['AK','AL','AR','CA','CO','CT','DC','FL','GA','HI','IL','KS','KY','LA','MA','MD','ME','MI','MN','MS','NC','ND','NH','NJ','NM','NV','NY','OH','OK','PA','RI','SC','TN','VA','WA','WI','WV']
        comparisons=0
        for org in COHORT:
            for state in states:
                for status,raw in [('Current','Active'),('Revoked','Revoked'),('Not Registered','No records found')]:
                    with self.subTest(organization=org['name'],state=state,status=status):
                        ext=SimpleNamespace(status=status,raw_status_text=raw,success=True,organization_name=org['name'],source_url='https://source.test/',matched_registry_name=org['registry_name'],matched_registry_identifier='retained-control')
                        old=b.copy_external_result(b.checker.Organization(org['name'],org['ein']),state,copy.deepcopy(ext))
                        new=c.copy_external_result(c.checker.Organization(org['name'],org['ein']),state,copy.deepcopy(ext))
                        self.assertEqual(vars(new),vars(old));comparisons+=1
        RECEIPT['other-state-adapters']={'distinct_organizations':30,'states':len(states),'comparisons':comparisons,'limitation':'Modeled external evidence through actual adapters, not live retrieval or broad accuracy.'}

if __name__=='__main__':
    r=unittest.TextTestRunner(verbosity=2).run(unittest.TestLoader().loadTestsFromModule(sys.modules[__name__]))
    (P/'integration-receipt.json').write_text(json.dumps({**RECEIPT,'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors)},indent=2),encoding='utf-8')
    sys.exit(not r.wasSuccessful())
