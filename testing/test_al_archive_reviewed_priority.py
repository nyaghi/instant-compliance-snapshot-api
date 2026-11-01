import copy,json,time,unittest
from pathlib import Path
from unittest.mock import patch
from deployment import state_snapshots as s

class ALArchivePriority(unittest.TestCase):
 def setUp(self):
  self.f=json.loads((Path(__file__).parent/'fixtures/al-large-grid.json').read_text())
  self.target=next(r for r in self.f['rows']if r[1]=='AL22-314')
  self.query={'state':'AL','operation':'search','name':'RONALD MCDONALD HOUSE'}
  self.text='Business Lookup Search Records: 1 to 40 of 40 '+' '.join(' '.join(r)for r in self.f['rows'])
  self.record={'state':'AL','ein':'431160478','organization_name':'RONALD MCDONALD HOUSE CHARITIES OF ST. LOUIS','alternate_names':[],'issued':time.time()-1}
  self.result={'state':'AL','ein':'431160478','matched_registry_name':self.target[0],'matched_registry_identifier':'AL22-314','status':'Delinquent'}
 def archive(self,record,rows,*,payload_edit=None,evidence_edit=None,text=None):
  evidence={'state':'AL','query':self.query,'complete':True,'verification_pending':False,'total':40,'headers':self.f['headers'],'rows':rows}
  if evidence_edit:evidence.update(evidence_edit)
  payload={'query_id':'local-retained-query','state_snapshot':{'query':self.query,'source_url':self.f['source_url'],'captured_at':time.time(),'public_text':self.text if text is None else text,'image':'modeled-original-image'}}
  if payload_edit:payload['state_snapshot'].update(payload_edit)
  calls=[]
  def retain(asset,**binding):
   self.assertEqual(binding['ein'],record['ein']);self.assertEqual(binding['state'],'AL')
   calls.append(asset)
   return {**asset,'url':'/state-snapshots/'+str(len(calls)).zfill(64)+'.pdf','ein':record['ein'],'state':'AL'}
  with patch.object(s,'STORE',object()),patch.object(s,'archive',side_effect=retain):s._connector_archive(record,payload,self.query,evidence)
  return calls
 def test_selected_beyond_reference_cap_and_first_rows(self):
  for index in range(30):
   with self.subTest(index=index):
    rows=[r for r in self.f['rows']if r[1]!='AL22-314'];rows.insert(index,self.target);record=copy.deepcopy(self.record);calls=self.archive(record,rows)
    self.assertEqual(len(calls),12);ref=s.matching_reference(self.result,record['source_snapshots']);self.assertIsNotNone(ref);self.assertEqual(ref['identifier'],'AL22-314')
    self.assertIsNone(s.matching_reference({**self.result,'ein':'000000000'},record['source_snapshots']))
    self.assertIsNone(s.matching_reference({**self.result,'matched_registry_identifier':'AL99-000000'},record['source_snapshots']))
 def test_exact_reviewed_alias_can_prioritize_without_accepting_identity(self):
  record={**copy.deepcopy(self.record),'organization_name':'Unrelated supplied label','alternate_names':[self.target[0]]};self.archive(record,self.f['rows']);self.assertIsNotNone(s.matching_reference(self.result,record['source_snapshots']))
  self.assertIsNone(s.matching_reference({**self.result,'matched_registry_identifier':'AL99-000000'},record['source_snapshots']))
 def test_unreviewed_target_never_becomes_selected_from_another_reference(self):
  record={**copy.deepcopy(self.record),'organization_name':'Unrelated supplied label'};self.archive(record,self.f['rows']);self.assertIsNone(s.matching_reference(self.result,record['source_snapshots']))
 def test_stale_or_wrong_query_snapshot_rejected(self):
  for change in [{'query':{**self.query,'name':'wrong query'}},{'captured_at':self.record['issued']-61},{'source_url':'https://example.com/wrong'}]:
   with self.subTest(change=change):
    record=copy.deepcopy(self.record);self.assertEqual(self.archive(record,self.f['rows'],payload_edit=change),[]);self.assertFalse(record.get('source_snapshots'))
 def test_incomplete_grid_does_not_gain_priority(self):
  for change in [{'complete':False},{'verification_pending':True},{'total':41}]:
   with self.subTest(change=change):
    record=copy.deepcopy(self.record);self.archive(record,self.f['rows'],evidence_edit=change);self.assertIsNone(s.matching_reference(self.result,record.get('source_snapshots',[])))
 def test_target_name_and_credential_must_be_in_bound_original_text(self):
  for text in [self.text.replace('AL22-314','AL22-999'),self.text.replace(self.target[0],'Different Organization')]:
   record=copy.deepcopy(self.record);self.archive(record,self.f['rows'],text=text);self.assertIsNone(s.matching_reference(self.result,record.get('source_snapshots',[])))

if __name__=='__main__':unittest.main()
