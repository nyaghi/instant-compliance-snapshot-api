"""MD display fields: live source fixtures, record boundaries, and final comments."""
import copy,json,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
W=Path(__file__).resolve().parents[1];sys.path.insert(0,str(W))
import registry_snapshot_server as c
import run_md_duplicate_guardrails as duplicates
FIXTURES=W/'testing/fixtures/md-display'

class MarylandDisplay(unittest.TestCase):
 def setUp(self):
  self.body=(FIXTURES/'26-0537053.json').read_text(encoding='utf-8')
  self.org=c.checker.Organization('Air Force Academy Foundation','26-0537053')
  self.result=c.checker.StateResult(self.org.organization_name,self.org.ein,'MD','Delinquent','https://onestop.md.gov/list_views/62f3e1797f7e3200016a3dab')
  self.result.raw_status_text='Delinquent';self.result.success=True
  self.result.source_note='Maryland detail page was reached from the public registry search.'
  self.profile=patch.object(c,'public_profile_for_ein',return_value={});self.profile.start();self.addCleanup(self.profile.stop)
 def entry(self,**kwargs):
  e=duplicates.entry(**kwargs)
  e['view_data']['content_element_data']['charity_id']=f'<p>Charity ID: <var>{e["id"]}</var></p>'
  return e
 def test_real_registry_primary_names_and_ids(self):
  for p in FIXTURES.glob('*.json'):
   body=p.read_text(encoding='utf-8');entry=json.loads(body)['entries'][0]
   name=entry['f_aedd5545-808f-4725-9b1d-5fa61e994a75']
   org=SimpleNamespace(organization_name='User supplied alternate name',ein=p.stem)
   result=c.checker.StateResult(org.organization_name,org.ein,'MD','Current','')
   original=copy.deepcopy(vars(result));c.md_registry_match_from_entries(result,body,org)
   self.assertEqual(result.matched_registry_name,name)
   self.assertRegex(result.matched_registry_identifier,r'^\d+$')
   self.assertEqual({k:v for k,v in vars(result).items() if not k.startswith('matched_registry_')},{k:v for k,v in original.items() if not k.startswith('matched_registry_')})
 def test_exact_report_comment_replaces_dba_markup_without_changing_status(self):
  cases=[('26-0537053','Air Force Academy Foundation','19680','Delinquent'),('20-8084828','Center For A New American Security, Inc.','21756','Pending')]
  for ein,name,identifier,status in cases:
   body=(FIXTURES/(ein+'.json')).read_text(encoding='utf-8')
   org=c.checker.Organization(name,ein);r=c.checker.StateResult(name,ein,'MD',status,'');r.success=True;r.raw_status_text=status
   with patch.object(c,'md_registry_match_from_entries'):
    before=c.response_data_for_lookup(copy.deepcopy(r),body,org,name,ein,'MD',time.perf_counter())
   after=c.response_data_for_lookup(r,body,org,name,ein,'MD',time.perf_counter())
   self.assertIn('\\u003c',before['matched_registry_name'])
   self.assertEqual(after['status'],before['status']);self.assertEqual(after['status'],status)
   for field in ['computed_due_date','last_year_on_record','next_required_period','fiscal_year_end','success','error','raw_status_text','source_note']:
    self.assertEqual(after.get(field),before.get(field),field)
   self.assertIn(f'Registry match: {name} (ID: {identifier}).',after['comments'])
   self.assertNotIn('\\u003c',after['comments']);self.assertNotIn('<var>',after['comments'])
 def test_wrong_ein_cannot_supply_a_name_even_if_name_is_exact(self):
  for ein in ['99-9999999','', '123']:
   r=copy.deepcopy(self.result);org=SimpleNamespace(organization_name=self.org.organization_name,ein=ein)
   c.md_registry_match_from_entries(r,self.body,org);self.assertFalse(r.matched_registry_name)
  body=json.loads(self.body);fields=body['entries'][0]['view_data']['content_element_data']
  for key,value in fields.items():
   if 'Charity EIN:' in value:fields[key]=value.replace('26-0537053','99-9999999')
  c.md_registry_match_from_entries(self.result,json.dumps(body),self.org);self.assertFalse(self.result.matched_registry_name)
 def test_duplicate_selection_uses_existing_rules_in_both_orders(self):
  active=self.entry(identifier='19680',name=self.org.organization_name,status='Current',ein=self.org.ein)
  closed=self.entry(identifier='99999',name=self.org.organization_name,status='Closed',ein=self.org.ein)
  for rows in [[active,closed],[closed,active]]:
   result=copy.deepcopy(self.result);c.md_registry_match_from_entries(result,json.dumps({'entries':rows}),self.org)
   self.assertEqual(result.matched_registry_identifier,'19680');self.assertEqual(result.status,'Delinquent')
 def test_missing_or_malformed_primary_field_does_not_use_dba_or_input(self):
  for name in [None,'','<p>Wrong</p>',r'Name\u003cvar\u003e',{'name':'wrong'}]:
   payload=json.loads(self.body);payload['entries'][0]['f_aedd5545-808f-4725-9b1d-5fa61e994a75']=name
   r=copy.deepcopy(self.result);c.md_registry_match_from_entries(r,json.dumps(payload),self.org);self.assertFalse(r.matched_registry_name)
 def test_malformed_empty_and_non_entries_bodies_preserve_existing_behavior(self):
  for body in ['','not json','{"entries": []}','{"entries": null}','{"entries": [null]}','{"entries": {}}','{"other": 1}']:
   r=copy.deepcopy(self.result);before=copy.deepcopy(vars(r));c.md_registry_match_from_entries(r,body,self.org);self.assertEqual(vars(r),before)
 def test_other_states_and_conflicting_identifiers_are_untouched(self):
  for state in ['CO','MA','MI','NY','WI','MD']:
   r=copy.deepcopy(self.result);r.state=state;r.matched_registry_identifier='123456';before=copy.deepcopy(vars(r))
   c.md_registry_match_from_entries(r,self.body,self.org);self.assertEqual(vars(r),before)
 def test_negative_and_error_results_do_not_gain_match_fields(self):
  for status in ['Not Registered','Site Not Reachable','Unable to Confirm','Needs Review']:
   r=copy.deepcopy(self.result);r.status=status;r.raw_status_text=status
   with patch.object(c,'md_registry_match_from_entries') as display:
    c.response_data_for_lookup(r,'',self.org,self.org.organization_name,self.org.ein,'MD',time.perf_counter())
   display.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
