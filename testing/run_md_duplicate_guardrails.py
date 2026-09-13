"""MD exact-EIN duplicates: retain nonclosed Not Current; preserve other rules."""
import copy,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
W=Path(__file__).resolve().parents[1];sys.path.insert(0,str(W));import registry_snapshot_server as c
EIN='04-2103881';NAME='Beth Israel Deaconess Medical Center, Inc.'
def entry(identifier,name,status,ein=EIN,year=''):
 return {'id':identifier,'f_aedd5545-808f-4725-9b1d-5fa61e994a75':name,'view_data':{'content_element_data':{
  'status':f'<p><strong>Registration Status:</strong> <var>{status}</var></p>',
  'ein':f'<p><strong>Charity EIN:</strong> <var>{ein}</var></p>',
  'year':f'<p><strong>Year Represented:</strong> <var>{year}</var></p>'}}}
class MarylandDuplicates(unittest.TestCase):
 def setUp(self):
  self.org=SimpleNamespace(organization_name=NAME,ein=EIN)
  self.open=entry('15364',NAME,'Not Current',year='2024');self.closed=entry('26587','Beth Israel Deaconess Medical Center','Closed')
  self.target=patch.object(c,'organization_match_target_variants',return_value=[NAME,'Beth Israel Deaconess Medical Center']);self.target.start();self.addCleanup(self.target.stop)
 def selected(self,rows):
  return json.loads(c.md_prefer_active_entry_body(json.dumps({'entries':rows,'total_count':len(rows)}),self.org))['entries']
 def test_nonclosed_exact_record_wins_both_orders(self):
  for rows in [[self.open,self.closed],[self.closed,self.open]]:
   with self.subTest(order=[r['id'] for r in rows]):self.assertEqual([r['id'] for r in self.selected(rows)],['15364'])
 def test_current_priority_is_unchanged(self):
  current=entry('current',NAME,'Current')
  for rows in [[self.open,self.closed,current],[current,self.closed,self.open]]:self.assertEqual(self.selected(rows)[0]['id'],'current')
 def test_wrong_ein_cannot_displace_closed(self):
  wrong=entry('wrong',NAME,'Not Current','99-9999999')
  self.assertEqual(self.selected([wrong,self.closed])[0]['id'],'26587')
 def test_weaker_name_cannot_displace_exact_closed(self):
  other=entry('other','Beth Israel Hospital Regional Foundation','Not Current')
  self.assertEqual(self.selected([other,self.closed])[0]['id'],'26587')
 def test_revoked_unknown_or_distinct_statuses_do_not_gain_new_priority(self):
  for status in ['Revoked','Pending','Unclear','Inactive']:
   first=entry('first',NAME,status)
   self.assertEqual(self.selected([first,self.open])[0]['id'],'first')
 def test_single_closed_record_is_preserved(self):
  self.assertEqual(self.selected([self.closed]),[self.closed])
 def test_nonexact_equal_scores_keep_existing_order(self):
  a=entry('a','Beth Israel Regional','Closed');b=entry('b','Beth Israel Regional','Not Current')
  with patch.object(c,'target_name_score',return_value=50):self.assertEqual(self.selected([a,b])[0]['id'],'a')
 def test_malformed_payload_is_unchanged(self):
  for body in ['not json','{"entries": null}']:
   self.assertEqual(c.md_prefer_active_entry_body(body,self.org),body)
if __name__=='__main__':unittest.main(verbosity=2)
