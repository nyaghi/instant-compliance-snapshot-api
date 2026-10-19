"""Local archive/link controls for retained TN detail versus later searches."""
import ast,base64,copy,json,subprocess,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment import state_snapshots as s
from testing.test_state_snapshots import Snapshots,image,COHORT
source=subprocess.check_output(['git','show','c511aede52579f0e82b953e113fd7165d918205f:deployment/state_snapshots.py'],cwd=ROOT,text=True,encoding='utf-8');node=next(x for x in ast.parse(source).body if isinstance(x,ast.FunctionDef) and x.name=='matching_reference');scope=dict(s.__dict__);exec(compile(ast.Module(body=[node],type_ignores=[]),'<GC-snapshot-selector>','exec'),scope);BASELINE=scope['matching_reference']
class References(Snapshots):
 def test_thirty_real_archive_continuations_keep_detail_after_later_search(self):
  for org in COHORT:
   record=dict(state='TN',ein=org['ein'],organization_name=org['name'],issued=time.time());url='https://tncab.tnsos.gov/portal/registered-charities-search'
   def capture(operation,label):
    query={'state':'TN','operation':operation,**({'identifier':'CO42115'} if operation=='detail' else {'name':org['name']})};raw=base64.b64encode(image(org['name'],label)).decode()
    incoming=dict(query=query,source_url=url,public_text=org['name']+' CO42115 Expired',captured_at=time.time(),image=raw)
    evidence={'fields':{'Name':org['name'],'CO Number':'CO42115'}} if operation=='detail' else {'rows':[{'name':org['name'],'identifier':'CO42115'}]}
    s.connector_archive(record,dict(query_id='local-'+label,state_snapshot=incoming),query,evidence);return record['source_snapshots'][-1]
   search=capture('search','first-search');detail=capture('detail','actual-detail');capture('search','later-search')
   result={**self.result(org,'CO42115','TN'),'status':'Delinquent'}
   self.assertNotEqual(BASELINE(result,[search,detail,{**search,'url':'/later-search'}])['url'],detail['url'])
   self.assertEqual(s.attach_links(result,record['source_snapshots'])['evidence_url'],detail['url'])
   for i in range(30):capture('search','extra-search-'+str(i))
   self.assertEqual(len(record['source_snapshots']),24);self.assertEqual(s.matching_reference(result,record['source_snapshots'])['url'],detail['url'])
 def test_thirty_contexts_all_other_states_keep_exact_old_selection(self):
  for org in COHORT:
   for state in s.OFFICIAL_HOSTS:
    if state=='TN':continue
    result=self.result(org,'REG123',state);common=dict(ein=s.digits(org['ein']),state=state,identifier='REG123',record_name=org['name'])
    refs=[{**common,'operation':'detail','url':'/older-detail'},{**common,'operation':'search','url':'/later-search'}]
    self.assertEqual(s.matching_reference(result,refs),BASELINE(result,refs),(org['ein'],state))
 def test_thirty_contexts_foreign_scope_and_credential_guards_and_legacy(self):
  for org in COHORT:
   result=self.result(org,'CO42115','TN');common=dict(ein=s.digits(org['ein']),state='TN',identifier='CO42115',record_name=org['name'])
   search={**common,'operation':'search','url':'/valid-search'}
   for change in [dict(ein='999999999'),dict(state='NC'),dict(identifier='CO99999'),dict(record_name='DIFFERENT ORGANIZATION')]:
    refs=[search,{**common,**change,'operation':'detail','url':'/wrong-detail'}];self.assertEqual(s.matching_reference(result,refs)['url'],'/valid-search')
   legacy=[{**common,'url':'/first'},{**common,'url':'/latest'}];self.assertEqual(s.matching_reference(result,legacy),BASELINE(result,legacy))
if __name__=='__main__':
 suite=unittest.TestSuite(References(name) for name in ['test_thirty_real_archive_continuations_keep_detail_after_later_search','test_thirty_contexts_all_other_states_keep_exact_old_selection','test_thirty_contexts_foreign_scope_and_credential_guards_and_legacy']);result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
