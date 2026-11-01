"""Actual signed responses + assembled frontend, with modeled port closure."""
import copy,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from deployment import performance_lab
from testing import test_nc_specific_fallback as nc_tests
ROOT=nc_tests.ROOT

class FreshTransportJoin(unittest.TestCase):
 def test_signed_response_reacquires_nc_before_specific_query(self):
  t=nc_tests.SpecificFallback();t.setUp();self.addCleanup(t.doCleanups)
  fixture=json.loads((ROOT/'testing/fixtures/nc-lobular-specific.json').read_text())
  out={'name':'Lobular Breast Cancer Alliance, Inc.','ein':'86-2260246','evidence':fixture['evidence']}
  with t.contexts(out['name']):
   import registry_snapshot_server as c
   t.t.orgs['NC']=c.checker.Organization(out['name'],out['ein'])
   _,start=t.start();_,narrow=t.source_fail(start)
   exchanges=[];request=t.t.request
   def capture(payload,**kw):
    code,response=request(payload,**kw);exchanges.append({'payload':payload,'response':response});return code,response
   with patch.object(t.t,'request',side_effect=capture):final,queries=t.complete(narrow,out)
  with patch.object(performance_lab,'trial_identity',return_value={'origin':'https://fixture-final-four.onrender.com'}),patch.object(performance_lab,'LAB_ORIGIN','https://fixture-final-four.onrender.com'):
   source=performance_lab.lab_asset('/ny-connector.js')[0].decode('utf-8')
  data={'start':start,'narrow':narrow,'exchanges':exchanges,'final':final}
  with tempfile.TemporaryDirectory(prefix='cc-nc-transport-')as folder:
   p=Path(folder);(p/'source.js').write_text(source,encoding='utf-8');(p/'responses.json').write_text(json.dumps(data),encoding='utf-8')
   node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
   result=subprocess.run([str(node),str(ROOT/'testing/nc_fresh_transport_join.cjs'),str(p)],capture_output=True,text=True,timeout=25)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   self.assertIn('baseline failed; candidate reacquired NC',result.stdout)

if __name__=='__main__':unittest.main()
