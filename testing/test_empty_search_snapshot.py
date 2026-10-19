"""Completed empty collector receipt must not be mistaken for its request name."""
import ast,base64,copy,json,subprocess,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from deployment import state_snapshots as s
from testing.test_state_snapshots import Snapshots,image,COHORT
source=subprocess.check_output(['git','show','2a64d831aa5fee3f52ad3127389cd292357ab796:deployment/state_snapshots.py'],cwd=ROOT,text=True,encoding='utf-8')
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='connector_archive');scope=dict(s.__dict__);exec(compile(ast.Module(body=[node],type_ignores=[]),'<GD-archive>','exec'),scope)
class Empty(Snapshots):
 def inputs(self,org,state='TN',**changes):
  record=dict(state=state,ein=org['ein'],organization_name=org['name'],issued=time.time());query=dict(state=state,operation='search',name=org['name'])
  evidence=dict(query=query,state=state,complete=True,total=0,rows=[]);evidence.update(changes)
  incoming=dict(query=query,source_url='https://'+sorted(s.OFFICIAL_HOSTS[state])[0]+'/public-search',public_text='No Records Available\nNo items to display',captured_at=time.time(),image=base64.b64encode(image('LOCAL EMPTY SOURCE FIXTURE','No Records Available')).decode())
  return record,dict(query_id='local-empty',state_snapshot=incoming),query,evidence
 def test_thirty_complete_empty_receipts_reproduce_GD_gap_and_keep_actual_capture(self):
  scope['STORE']=self.store
  for org in COHORT:
   record,payload,query,evidence=self.inputs(org);old=copy.deepcopy(record);scope['connector_archive'](old,payload,query,evidence);self.assertFalse(old.get('source_snapshots'))
   s.connector_archive(record,payload,query,evidence);self.assertEqual(record['source_snapshots'][0]['identifier'],'@completed-search')
   result=dict(state='TN',ein=org['ein'],status='Not Registered',success=True);linked=s.attach_links(result,record['source_snapshots']);self.assertTrue(linked['evidence_url'])
   _,pdf=s.saved_pdf(linked['evidence_url'].split('/')[-1][:-4],self.store);self.assertTrue(pdf.startswith(b'%PDF'))
 def test_thirty_contexts_incomplete_or_unbound_empty_never_offer_evidence(self):
  for org in COHORT:
   for bad in ['incomplete','unknown-total','nonempty','missing-source-empty','changed-query','wrong-host','captcha']:
    record,payload,query,evidence=self.inputs(org)
    if bad=='incomplete':evidence['complete']=False
    if bad=='unknown-total':evidence.pop('total')
    if bad=='nonempty':evidence['rows']=[{'name':'UNRELATED','identifier':'OTHER'}]
    if bad=='missing-source-empty':payload['state_snapshot']['public_text']='Search form'
    if bad=='changed-query':payload['state_snapshot']['query']={**query,'name':'OTHER'}
    if bad=='wrong-host':payload['state_snapshot']['source_url']='https://example.com/search'
    if bad=='captcha':payload['state_snapshot']['public_text']='Verify you are human'
    s.connector_archive(record,payload,query,evidence);self.assertFalse(record.get('source_snapshots'),(org['ein'],bad))
 def test_thirty_positive_contexts_across_other_states_keep_selected_evidence(self):
  scope['STORE']=self.store
  for org in COHORT:
   for state in ['NV','NC','GA','MS','IL','AL']:
    record,payload,query,evidence=self.inputs(org,state);evidence.update(total=1,rows=[dict(name=org['name'],identifier='REG123')]);payload['state_snapshot']['public_text']=org['name']+' REG123 Current'
    old=copy.deepcopy(record);scope['connector_archive'](old,payload,query,evidence);s.connector_archive(record,payload,query,evidence)
    result={**self.result(org,'REG123',state)}
    self.assertEqual(s.matching_reference(result,old['source_snapshots'])['identifier'],s.matching_reference(result,record['source_snapshots'])['identifier'])
if __name__=='__main__':
 suite=unittest.TestSuite(Empty(n) for n in ['test_thirty_complete_empty_receipts_reproduce_GD_gap_and_keep_actual_capture','test_thirty_contexts_incomplete_or_unbound_empty_never_offer_evidence','test_thirty_positive_contexts_across_other_states_keep_selected_evidence'])
 result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
