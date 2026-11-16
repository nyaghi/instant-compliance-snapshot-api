import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as c

class ConnectorLimit(unittest.TestCase):
 def record(self,state):
  row=getattr(self,'roster_row',{})
  return dict(state=state,organization_name=row.get('name','Example Relief'),ein=row.get('ein','123456789'),purpose='registration',connector_version='0.6.135',issued=1,expires=1000,completed=[],source_snapshots=[])
 def prepare(self,state):
  r=self.record(state)
  advance=c.final_four_connector_advance if state=='NM' else c.ny_connector_advance
  with patch.object(c.time,'time',return_value=100),patch.object(c,'trial_identity',return_value={'origin':'local'}),patch.object(c,'licensed_charity_names',return_value=([r['organization_name']],[])):
   first=advance(r);q=first['query'];self.assertEqual(q.get('ein'),c.canonical_ein_digits(r['ein']))
   rows={'query':q,'complete':True,'total':0,'rows':[]} if state=='NM' else {'rows':[]} if state=='IL' else []
   r['completed'].append({'query':q,'evidence':rows}if state=='NM'else{'query':q,'rows':rows})
   second=advance(r);self.assertEqual(second['phase'],'search');self.assertTrue(second['query'].get('name')or second['query'].get('orgName'))
  return r,dict(reason='NY_CONNECTOR_EIN_LIGHT_NAME_LIMIT',query_id=r['pending']['query_id'])
 def test_bound_empty_ein_replays_to_negative_without_fabricating_reply(self):
  for state in ['IL','NY','NM']:
   with self.subTest(state=state):
    r,p=self.prepare(state);original=copy.deepcopy(r['completed'])
    with patch.object(c.time,'time',return_value=120),patch.object(c,'trial_identity',return_value={'origin':'local'}):result=c.ein_light_connector_result(r,p)
    self.assertEqual(result['phase'],'complete');self.assertIn(result['result']['status'],['Not Registered','Not Registered / Non-Compliant']);self.assertEqual(r['completed'],original)
 def test_no_ein_proof_wrong_query_early_deadline_and_real_failure_cannot_be_negative(self):
  for state in ['IL','NY','NM']:
   for change in ['no-proof','wrong-id','early','source-error']:
    r,p=self.prepare(state)
    if change=='no-proof':r['completed']=[]
    if change=='wrong-id':p['query_id']='other'
    if change=='source-error':p['reason']='NY_CONNECTOR_SEARCH_HTTP_ERROR'
    with patch.object(c.time,'time',return_value=119 if change=='early' else 120):self.assertIsNone(c.ein_light_connector_result(r,p))
 def test_seventy_saved_organizations_on_all_three_connector_paths(self):
  from testing.test_ein_light_name_policy import ROSTER
  for row in ROSTER:
   self.roster_row=row
   for state in ['IL','NY','NM']:
    with self.subTest(state=state,name=row['name']),patch.object(c,'known_names_for_ein',return_value=row.get('aliases',[])),patch.object(c,'licensed_charity_names',return_value=([row['name']],[])):
     r,p=self.prepare(state)
     with patch.object(c.time,'time',return_value=120),patch.object(c,'trial_identity',return_value={'origin':'local'}):result=c.ein_light_connector_result(r,p)
     self.assertIn(result['result']['status'],['Not Registered','Not Registered / Non-Compliant'])
 def test_possible_record_never_converted_to_negative_by_cutoff(self):
  r,p=self.prepare('NY');r['completed'][0]['rows']=[{'orgID':'01-02-03','orgName':'Example Relief','ein':'malformed'}]
  with patch.object(c.time,'time',return_value=120):result=c.ein_light_connector_result(r,p)
  self.assertNotEqual(result['result']['status'],'Not Registered')

if __name__=='__main__':unittest.main()
