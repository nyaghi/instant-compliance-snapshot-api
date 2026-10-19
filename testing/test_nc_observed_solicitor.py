"""Fresh actual source row + 30 retained identity contexts, modeled workflows."""
import ast,copy,json,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import registry_snapshot_server as c
from testing.test_oct19_integration import Integration
P=ROOT.parent
OBS=json.loads((ROOT/'testing/fixtures/oct19-nc-solicitor-source.json').read_text())
ACTUAL=OBS['fields']
RECEIPT={}

class SourceControls(unittest.TestCase):
    def test_observed_actual_solicitor_rejected_by_gb_and_validated_only_as_noncharity(self):
        source=subprocess.check_output(['git','show','2f00dda88288c40cfedd8017050f1cfd1835a1f2:registry_snapshot_server.py'],cwd=ROOT,text=True,encoding='utf-8')
        tree=ast.parse(source)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='nc_charity_record_evidence')
        namespace=dict(vars(c));exec(compile(ast.Module(body=[fn],type_ignores=[]),'exact-GB-function','exec'),namespace)
        with self.assertRaisesRegex(ValueError,'not an identified charity license'):
            namespace['nc_charity_record_evidence'](ACTUAL)
        row=c.nc_charity_record_evidence(ACTUAL)
        self.assertTrue(row['non_charity_scope'])
        self.assertEqual(row['identifier'],'SL101159')
        self.assertNotIn('status',row)
        query={'state':'NC','operation':'search','name':'WILLIAM'}
        payload={'state':'NC','query':query,'complete':True,'verification_pending':False,'total':1,'rows':[ACTUAL],'search_mode':'STARTS_WITH'}
        self.assertEqual(c.final_four_clean_evidence(payload,query),payload)
        self.assertEqual(c.final_four_search_evidence(payload,'NC',query),[])
        RECEIPT['fresh_source_row']={'source':OBS['source_url'],'identifier':row['identifier'],'GB_rejection_reproduced':True,'candidate_excludes_only_explicit_noncharity':True,'not_raw_installed_payload':True}

    def test_malformed_unknown_categories_and_dates_remain_rejected(self):
        count=0
        for key,value in [('License',''),('License','EX101159'),('License','SLx'),('CSL Type','Unknown'),('CSL Type','Solicitor Unknown'),('Expiration Date',''),('Expiration Date','not a date'),('Status',''),('profile_url','https://wrong.example/10559313')]:
            row={**ACTUAL,key:value}
            with self.subTest(field=key,value=value),self.assertRaises(ValueError):c.nc_charity_record_evidence(row)
            count+=1
        RECEIPT['adverse_guards']=count

    def test_thirty_retained_orgs_with_actual_solicitor_joined_to_packaged_signed_workflows(self):
        original=Path.read_text
        outputs=json.loads(original(ROOT/'testing/fixtures/oct19-nc-collector-outputs.json'))
        for i,out in enumerate(outputs):
            evidence=out['evidence'];evidence['rows'].insert(0 if i%2 else len(evidence['rows']),copy.deepcopy(ACTUAL));evidence['total']=len(evidence['rows'])
        serialized=json.dumps(outputs)
        def read(path,*args,**kwargs):
            return serialized if path==ROOT/'testing/fixtures/oct19-nc-collector-outputs.json' else original(path,*args,**kwargs)
        test=Integration('test_actual_packaged_collector_outputs_complete_thirty_signed_positive_workflows')
        with patch.object(Path,'read_text',read):
            try:test.test_actual_packaged_collector_outputs_complete_thirty_signed_positive_workflows()
            finally:test.doCleanups()
        RECEIPT['joined_workflows']={'distinct_retained_organizations':len({o['ein'] for o in outputs}),'source_order_workflows':len(outputs),'scope':'Actual packaged model outputs joined with observed official Solicitor row through actual signed master; not live searches'}

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SourceControls))
    (P/'nc-solicitor-local-receipt.json').write_text(json.dumps({**RECEIPT,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)},indent=2))
    sys.exit(not result.wasSuccessful())
