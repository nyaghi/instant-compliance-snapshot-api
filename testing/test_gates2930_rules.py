import sys,json,time,copy,re,unittest
from pathlib import Path
from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import patch
W=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(W))
import registry_snapshot_server as m
from deployment import gates2930_repairs as g, state_snapshots as ss,ca_accepted_renewal as ca
D=Path(__file__).resolve().parent/'fixtures/gates29-30'

class Repairs(unittest.TestCase):
 def test_il_blank_good_standing(self):
  row=m.il_charity_detail_text('WORLD VISION INC\nCO Number: 01029200\nFEIN: 95-1922279\nStatus: Good Standing\nRegistration Date: 01/01/2000','01029200')
  self.assertEqual(row['status'],'Current')
 def test_il_evidence_join_and_wrong_id(self):
  selected=dict(name='PLAN INTERNATIONAL USA INC DBA CHILDREACH',identifier='01003858',ein='135661832',_identity_outcome='accepted')
  result=NS(state='IL',ein='135661832',matched_registry_identifier='01003858',matched_registry_name='PLAN INTERNATIONAL USA INC',success=True)
  proof=g.il_source_identity(result,selected,m.canonical_ein_digits);self.assertIsNotNone(proof)
  data=vars(result)|{'status':'Current','il_source_identity':proof}
  ref=dict(state='IL',ein='135661832',identifier='01003858',record_name=selected['name'],operation='detail',url='/state-snapshots/fixture.pdf',captured_at='2026-11-06')
  self.assertTrue(ss.matching_reference(data,[ref]))
  for change in ({'ein':'123456789'},{'identifier':'999'},{'record_name':'OTHER ORGANIZATION'}):
   with self.subTest(change=change):self.assertFalse(ss.matching_reference(data,[ref|change]))
  for change in ({'ein':'123456789'},{'_identity_outcome':'possible'},{'identifier':'999'}):
   with self.subTest(change=change):self.assertIsNone(g.il_source_identity(result,selected|change,m.canonical_ein_digits))
 def test_co_precedence(self):
  for text,expected in [('Expired - may not solicit as of 11/16/2024',True),('Expired – may not solicit',True),('Suspended - may not solicit',False),('Revoked; Expired - may not solicit',False),('May not solicit',False),('Current',False)]:
   with self.subTest(text=text):self.assertEqual(bool(g.co_expired_restriction(text)),expected)
 def test_sc_finish_limits(self):
  for stop,deadline,now,want in [(116,200,112,121),(116,117,112,116),(116,200,116,116),(116,200,110,121),(116,200,108,116),(116,114,112,116)]:
   with self.subTest(stop=stop,deadline=deadline,now=now):self.assertEqual(g.sc_finish_deadline(stop,deadline,now),want)
 def test_wi_keeps_budget_and_literals(self):
  original='Water.org Inc.';required=[original,'WaterPartners International']
  before=[*required,'Waterorg','Water','Water Partners','WaterOrg Inc']
  after=g.wi_literal_core_plan(original,required,before)
  self.assertIn('Water.org',after);self.assertEqual(len(before),len(after));self.assertTrue(set(required)<=set(after))
  for name in ['Example Foundation Inc.','St Jude Inc.','Example-Name Inc.',"Children's Foundation"]:
   with self.subTest(name=name):self.assertEqual(g.wi_literal_core_plan(name,[name],['other',name]),['other',name])
 def test_tn_plan_literal_and_budget(self):
  required=['PLAN INTERNATIONAL USA INC.', 'FOSTER PARENTS PLAN, INC.']
  before=['Plan International','Foster Parents','Foster Parents Plan']
  after=g.tn_possessive_plan(required,before)
  self.assertEqual(len(after),len(before))
  self.assertTrue(any(q.casefold() in "Foster Parents' Plan for Spanish Children, Inc.".casefold() for q in after))
  self.assertTrue(all(len(q.split())>=2 for q in after))
 def test_tn_prefix_not_acceptance(self):
  self.assertTrue(g.tn_historical_prefix(['Foster Parents Plan, Inc.'],"Foster Parents' Plan for Spanish Children, Inc."))
  for candidate in ['Foster Other Parents Plan','Parents Plan','Plan International School','Another Foundation']:
   self.assertFalse(g.tn_historical_prefix(['Foster Parents Plan, Inc.'],candidate))
 def test_tn_strict_primary(self):
  org=m.checker.Organization('Children International','446005794')
  primary={'name':'CHILDREN INTERNATIONAL','ein':'446005794'}
  alias={'name':'NEIGHBOR TO NATION','match':{'reason':'ALIAS_IDENTITY_UNCONFIRMED'}}
  check=lambda a,p,c:g.tn_primary_over_alias(org,a,p,c,m.normalized_match_name,m.registry_street_key,m.canonical_ein_digits)
  self.assertTrue(check([primary],[alias],[]))
  self.assertFalse(check([primary|{'ein':''}],[alias],[]))
  self.assertFalse(check([primary],[alias],[{}]))
  self.assertFalse(check([primary],[alias|{'name':'Children International Foundation'}],[]))
  self.assertFalse(check([primary,primary],[alias],[]))
 def test_ny_plausible_gets_detail_review(self):
  calls=[]
  def search(q):
   calls.append(q);return m.NYConnectorResponse([] if 'ein' in q else [{'orgID':'11-44-30','orgName':'WORLD VISION INTERNATIONAL','ein':None}])
  def detail(q):
   calls.append(q);return m.NYConnectorResponse({'orgID':'11-44-30','orgName':'WORLD VISION INTERNATIONAL','ein':None,'regStatute':'7A','documents':{'Annual Filing for Charitable Organizations':[]}})
  r=m.search_ny_direct(m.checker.Organization('World Vision','951922279'),registry_search_provider=search,registry_detail_provider=detail)
  self.assertEqual(r.status,'Needs Review',r.source_note)
  self.assertEqual(sum('orgID'in q for q in calls),1)
  self.assertEqual(r._cc_identity_review['records'][0]['identifier'],'11-44-30')
  self.assertEqual(r._cc_identity_review['records'][0]['status'],'Delinquent')
 def test_ny_different_ein_does_not_accept(self):
  def search(q):return m.NYConnectorResponse([{'orgID':'11-44-30','orgName':'WORLD VISION INTERNATIONAL','ein':'123456789'}])
  def detail(q):raise AssertionError('Unrelated EIN must not reach detail')
  r=m.search_ny_direct(m.checker.Organization('World Vision','951922279'),registry_search_provider=search,registry_detail_provider=detail)
  self.assertEqual(r.status,m.checker.STATUS_NOT_REGISTERED)
 def test_ny_original_detail_before_later_query_replaces_grid(self):
  calls=[];grid=[]
  row={'orgID':'11-44-30','orgName':'WORLD VISION INTERNATIONAL','ein':None}
  def search(q):
   calls.append(q);grid[:]=[row] if q.get('orgName')=='World Vision' else []
   return m.NYConnectorResponse(list(grid))
  def detail(q):
   self.assertTrue(any(r['orgID']==q['orgID'] for r in grid),'Detail lost its owning search grid')
   calls.append(q)
   return m.NYConnectorResponse(row|{'regStatute':'7A','documents':{'Annual Filing for Charitable Organizations':[]}})
  with patch.object(m,'known_names_for_ein',side_effect=lambda ein:['WORLD VISION, INC.'] if m.canonical_ein_digits(ein)=='951922279' else []):
   r=m.search_ny_direct(m.checker.Organization('World Vision','951922279'),registry_search_provider=search,registry_detail_provider=detail)
  self.assertEqual(r.status,'Needs Review',r.source_note)
  self.assertEqual(sum('orgID'in q for q in calls),1)
  self.assertTrue(any('orgName'in q for q in calls[calls.index({'orgID':'11-44-30'})+1:]))
 def ca_fixture(self):
  entity={'id':'5301538','entityName':'LUTHERAN WORLD RELIEF INC.','fein':'132574963','entityStatus':'Listed'}
  reg={'id':'1026699','registrationNumber':'078450','registrationType':'Charitable Organization','registrationStatus':'Registered','reportingStatus':'Current','currentExpirationDate':'2025-09-30','complianceStatus':[]}
  row={'id':'0JjR16KMjbKuZsx9OeyzC','relatedEntity':{'id':'5301538'},'relatedRegistration':{'id':'1026699'},'stateCharityRegistrationNumber':'078450','fein':'13-2574963','officialName':'LUTHERAN WORLD RELIEF INC.','isShortFiscalYear':'No','countOfOpenDeficiencies':0,'newReportingStatus':'Current','newRegistrationStatus':'Registered','formType':'Form RRF-1','status':'Accepted','registrationMethod':'Renewal','fullAccountingPeriodBeginning':'2024-10-01','fullAccountingPeriodEnding':'2025-09-30','recievedDate':'2026-09-01'}
  return entity,reg,row
 def test_ny_later_confirmed_identity_still_wins(self):
  loose={'orgID':'11-44-30','orgName':'WORLD VISION INTERNATIONAL','ein':None}
  exact={'orgID':'12-34-56','orgName':'WORLD VISION INC','ein':'951922279'}
  grid=[];calls=[]
  def search(q):
   grid[:]=[] if 'ein'in q else [loose if q['orgName']=='World Vision' else exact]
   return m.NYConnectorResponse(list(grid))
  def detail(q):
   self.assertEqual(grid[0]['orgID'],q['orgID']);calls.append(q)
   return m.NYConnectorResponse(grid[0]|{'regStatute':'EXEMPT','documents':{}})
  with patch.object(m,'known_names_for_ein',side_effect=lambda ein:['WORLD VISION, INC.'] if m.canonical_ein_digits(ein)=='951922279' else []):
   r=m.search_ny_direct(m.checker.Organization('World Vision','951922279'),registry_search_provider=search,registry_detail_provider=detail)
  self.assertEqual(r.status,'Exempt',r.source_note)
  self.assertEqual(r.matched_registry_identifier,'951922279')
  self.assertEqual(len(calls),2)
 def test_ca_bound_accepted_renewal(self):
  e,r,a=self.ca_fixture();self.assertIsNotNone(ca.accepted_period(m,e,r,[a],e['fein']))
  for change in [{'status':'Pending'},{'status':'Rejected'},{'fein':'123456789'},{'relatedRegistration':{'id':'wrong'}},{'officialName':'OTHER CHARITY'},{'fullAccountingPeriodBeginning':'2025-10-01'},{'countOfOpenDeficiencies':1},{'isShortFiscalYear':'Yes'}]:
   with self.subTest(change=change):self.assertIsNone(ca.accepted_period(m,e,r,[a|change],e['fein']))
 def test_ca_joined_status_preserved(self):
  e,reg,a=self.ca_fixture();org=m.checker.Organization(e['entityName'],e['fein'])
  r=m.checker.StateResult(org.organization_name,org.ein,'CA',m.checker.STATUS_DELINQUENT,'https://ca-rcf.evokeplatform.com/')
  r.success=True;r.raw_status_text='Current Expiration Date: 2025-09-30';r.matched_registry_name=e['entityName'];r.matched_registry_identifier='078450'
  with patch.object(m,'identity_fetch',return_value=json.dumps([a])):
   ca.reconcile(m,org,r,e,[reg])
  self.assertTrue(ca.preserves(r));self.assertEqual(r.computed_due_date,'2027-02-15')
  self.assertEqual(m.true_status_from_body(r,''),'Upcoming Filing')
  self.assertEqual(r._cc_ca_accepted_renewal['registration'],'078450')
 def test_ca_enforcement_untouched(self):
  e,reg,a=self.ca_fixture();org=m.checker.Organization(e['entityName'],e['fein'])
  r=m.checker.StateResult(org.organization_name,org.ein,'CA',m.checker.STATUS_DELINQUENT,'');r.success=True;r.matched_registry_identifier='078450'
  with patch.object(m,'identity_fetch',side_effect=AssertionError('No request for enforcement')):
   ca.reconcile(m,org,r,e,[reg|{'complianceStatus':['Enforcement']}])
  self.assertEqual(r.status,m.checker.STATUS_DELINQUENT)

if __name__=='__main__':unittest.main(verbosity=2)
