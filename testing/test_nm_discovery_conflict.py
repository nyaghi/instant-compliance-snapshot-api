import copy,json,time,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as cc

FIXTURE=json.loads((Path(__file__).parent/'fixtures/fresh-five/NM-NAME-CONFLICT.json').read_text())
class NmDiscoveryConflict(unittest.TestCase):
 def source(self,name):
  return {'names':[cc.identity_new_source_candidate(name,'NM','Registered name','https://secure.nmdoj.gov/CharitySearch/CharityDetail.aspx?FEIN=13-1610451')],'complete':True}
 def test_actual_contradictory_heading_is_visible_but_not_preselected(self):
  result=self.source('The Franklin Institute');before=copy.deepcopy(result)
  with patch.dict(cc.PUBLIC_PROFILE_CACHE,{'131610451':{'organization':FIXTURE['profile']}}),patch.object(cc,'identity_fetch',return_value=json.dumps({'organizations':FIXTURE['candidates']}).encode()) as fetch:
   output=cc.identity_nm_name_review(result,'131610451',time.monotonic()+20)
  item=output['names'][0];self.assertFalse(item['verified']);self.assertEqual(item['identity_conflict']['candidate_ein'],'23-1370501')
  self.assertEqual(item['name'],'The Franklin Institute');self.assertEqual(result,before);fetch.assert_called_once()
 def test_seventy_healthy_legal_names_do_not_add_searches(self):
  roster=json.loads((Path(__file__).parent/'fixtures/fresh-five/LOCAL-70.json').read_text())
  for case in roster:
   with self.subTest(name=case['name']),patch.dict(cc.PUBLIC_PROFILE_CACHE,{case['ein']:{'organization':{'ein':case['ein'],'name':case['name'],'city':'City','state':'VA'}}}),patch.object(cc,'identity_fetch') as fetch:
    result=self.source(case['name']);self.assertEqual(cc.identity_nm_name_review(result,case['ein'],time.monotonic()+20),result)
    fetch.assert_not_called()
 def test_incomplete_corroboration_and_legitimate_names_are_retained(self):
  source=self.source('Distinct Former Name')
  with patch.dict(cc.PUBLIC_PROFILE_CACHE,{'131610451':{'organization':FIXTURE['profile']}}):
   for candidates in [[],[dict(name='Distinct Former Name',ein=131610451,city='Other',state='PA')],
                      [dict(name='Distinct Former Name',ein=231370501,city='Arlington',state='VA')],
                      [dict(name='Similar Former Name',ein=231370501,city='Other',state='PA')]]:
    with patch.object(cc,'identity_fetch',return_value=json.dumps({'organizations':candidates}).encode()):
     self.assertEqual(cc.identity_nm_name_review(source,'131610451',time.monotonic()+20),source)
   with patch.object(cc,'identity_fetch',side_effect=TimeoutError()):
    self.assertEqual(cc.identity_nm_name_review(source,'131610451',time.monotonic()+20),source)

if __name__=='__main__':unittest.main()
