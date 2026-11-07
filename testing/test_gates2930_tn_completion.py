import ast,copy,json,subprocess,time,sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
W=Path(__file__).resolve().parents[1];sys.path.insert(0,str(W))
import registry_snapshot_server as m
source=subprocess.check_output(['git','show','8cb77cde889c34a50ca42dd37cd13a90eb8c94e8:registry_snapshot_server.py'],cwd=W,text=True,encoding='utf-8')
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name=='final_four_browser_lookup')
scope=dict(vars(m));exec(compile(ast.Module(body=[node],type_ignores=[]),'deployed-before-tn-replay-fix','exec'),scope);old=scope['final_four_browser_lookup']
COHORT=json.loads((W/'testing/fixtures/oct19-cohort.json').read_text())[:30]
class TNReplay(unittest.TestCase):
 def run_plan(self,org,status,possible,baseline):
  queries=[];completed={};selections=[];required=[org.organization_name];generated=['Optional '+str(i) for i in range(5)]
  row=dict(name=org.organization_name,identifier='CO123',ein='',aliases=[],status=status,raw_status=status,expiration=None,initial=None,url='https://tncab.tnsos.gov/portal/registered-charities-search')
  def select(org,rows,state,deadline):
   selections.append(status)
   return (None,'identity review')if possible else (rows[0],'')
  def final(org,state,rows,deadline,url):
   selected,review=select(org,rows,state,deadline)
   return NS(status='Needs Review'if review else selected['status'],success=not bool(review),source_note=review,matched_registry_identifier=''if review else selected['identifier'])
  def collect(q):
   key=json.dumps(q,sort_keys=True)
   if key not in completed:raise m.NYConnectorQueryNeeded(q)
   return completed[key]
  with patch.object(m,'licensed_charity_names',return_value=(required,generated)),patch.object(m,'known_names_for_ein',return_value=[]),patch.object(m,'tn_charity_detail_evidence',side_effect=lambda *a:copy.deepcopy(row)),patch.object(m,'select_licensed_charity',side_effect=select),patch.object(m,'final_four_license_result',side_effect=final):
   scope.update({k:getattr(m,k) for k in ['licensed_charity_names','known_names_for_ein','tn_charity_detail_evidence','select_licensed_charity','final_four_license_result']})
   for _ in range(20):
    try:
     result=(old if baseline else m.final_four_browser_lookup)(org,'TN',collect,time.monotonic()+20);break
    except m.NYConnectorQueryNeeded as request:
     q=request.params;queries.append(q)
     if q['operation']=='search':
      rows=[{'name':org.organization_name,'identifier':'CO123','city':'KANSAS CITY','region':'MO','aliases':[]}]if q['name']==org.organization_name else []
      payload=dict(query=q,state='TN',complete=True,verification_pending=False,total=len(rows),rows=rows)
     else:payload=dict(query=q,complete=True,fields={})
     completed[json.dumps(q,sort_keys=True)]=payload
   else:raise AssertionError('continuation failed to terminate')
  return vars(result),queries,len(selections)
 def test_thirty_organizations_keep_results_and_queries_reduce_futile_work(self):
  for item in COHORT:
   org=m.checker.Organization(item['name'],item['ein'])
   for status in ['Delinquent','Closed / Withdrawn / Canceled','Current','Upcoming Filing','Exempt']:
    for possible in [False,True]:
     with self.subTest(org=item['name'],status=status,possible=possible):
      a=self.run_plan(org,status,possible,True);b=self.run_plan(org,status,possible,False)
      self.assertEqual(a[:2],b[:2])
      if status in ['Delinquent','Closed / Withdrawn / Canceled']:
       self.assertEqual(b[2],1);self.assertGreater(a[2],b[2])
      else:self.assertEqual(a[2],b[2])
 def test_primary_requires_exact_full_ein_bound_office(self):
  org=m.checker.Organization('Children International','446005794')
  primary=dict(name=org.organization_name,identifier='CO2787',ein='',status='Upcoming Filing',raw_status='Active',expiration=m.date(2026,11,27),street='2000 E. RED BRIDGE RD.',region='MO',postal_code='64131',location='KANSAS CITY, MO')
  alias=dict(name='NEIGHBOR TO NATION',identifier='CO5019',ein='',status='Delinquent',raw_status='Expired',expiration=m.date(2021,12,31),street='PUBLIC OFFICE',region='VA',postal_code='22301',location='ALEXANDRIA, VA')
  office=dict(address_role='organization',ein=org.ein,street='2000 E. RED BRIDGE ROAD',state='MO',postal_code='64131',names=[org.organization_name])
  def identity(org,row,state,deadline):
   row['match']={'reason':'MATCH_NAME_EXACT'if row['identifier']=='CO2787'else'ALIAS_IDENTITY_UNCONFIRMED'}
   row['address_evidence']={'decision':'corroborated'if row['identifier']=='CO2787'else'unavailable'}
   return 'accepted'if row['identifier']=='CO2787'else'possible'
  for change,want in [({},True),({'ein':'999999999'},False),({'street':'999 OTHER ROAD'},False),({'state':'VA'},False),({'postal_code':'99999'},False),({'address_role':'agent'},False)]:
   with self.subTest(change=change),patch.object(m,'licensed_charity_identity',side_effect=identity),patch.object(m,'identity_source_result',return_value={'organization_records':[office|change]}):
    selected,review=m.select_licensed_charity(org,copy.deepcopy([primary,alias]),'TN',time.monotonic()+10)
    self.assertEqual(bool(selected),want,(selected,review))
    if want:self.assertEqual(selected['identifier'],'CO2787')
if __name__=='__main__':unittest.main(verbosity=2)

