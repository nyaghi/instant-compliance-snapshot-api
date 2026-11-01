"""Retain the observed denied application without changing matching or standing."""
import ast,copy,json,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import registry_snapshot_server as c
import testing.test_oct19_integration as integration

ACTUAL=json.loads((ROOT/'testing/fixtures/nc-denied-exempt.json').read_text())

class DeniedExemptGuard(unittest.TestCase):
    def test_observed_category_is_retained_only_as_unsupported_identity_evidence(self):
        source=subprocess.check_output(['git','show','532608e662d7d9599d207210004a829b49f63864:registry_snapshot_server.py'],cwd=ROOT,text=True,encoding='utf-8')
        fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name=='nc_charity_record_evidence')
        scope=dict(vars(c));exec(compile(ast.Module(body=[fn],type_ignores=[]),'exact-MT-nc-parser','exec'),scope)
        with self.assertRaises(ValueError):scope['nc_charity_record_evidence'](ACTUAL)
        row=c.nc_charity_record_evidence(ACTUAL)
        self.assertTrue(row['unsupported_registration_scope'])
        self.assertEqual(row['identifier'],'NCAPP-'+ACTUAL['profile_url'].rsplit('/',1)[1])
        self.assertEqual(row['raw_status'],'Denied')
        self.assertEqual(row['status'],'Unable to Confirm')
        self.assertNotIn('unissued_application',row)
        self.assertNotIn('non_charity_scope',row)

    def test_existing_identity_date_and_category_rejections_remain(self):
        for change in [{'Expiration Date':'1/1/2027'},{'Extension End Date':'1/1/2027'},
                       {'profile_url':'https://wrong.example/123'}, {'CSL Legal Name':''},
                       {'CSL Type':'Unrecognized Exemption'}, {'Status':'Current Active'}]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                c.nc_charity_record_evidence({**ACTUAL,**change})

    def test_thirty_retained_identities_keep_signed_positive_workflows(self):
        original=Path.read_text
        outputs=json.loads(original(ROOT/'testing/fixtures/oct19-nc-collector-outputs.json'))
        for i,out in enumerate(outputs):
            evidence=out['evidence']
            evidence['rows'].insert(0 if i%2 else len(evidence['rows']),copy.deepcopy(ACTUAL))
            evidence['total']=len(evidence['rows'])
        serialized=json.dumps(outputs)
        def read(path,*args,**kwargs):
            return serialized if path==ROOT/'testing/fixtures/oct19-nc-collector-outputs.json' else original(path,*args,**kwargs)
        test=integration.Integration('test_actual_packaged_collector_outputs_complete_thirty_signed_positive_workflows')
        with patch.object(Path,'read_text',read):
            try:test.test_actual_packaged_collector_outputs_complete_thirty_signed_positive_workflows()
            finally:test.doCleanups()

if __name__=='__main__':unittest.main()
