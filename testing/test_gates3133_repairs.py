import copy,json,sys,time,unittest
from pathlib import Path
from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import Mock,MagicMock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import registry_snapshot_server as m
from deployment import gates3133_repairs as g,short_alias_identity as identity,pa_detail_evidence as pa,co_budget
D=Path(__file__).parent/'fixtures/gates31-33'

class AsOf(date):
 @classmethod
 def today(cls):return cls(2026,11,7)

class Repairs(unittest.TestCase):
 def test_actual_al_complete_149_rows_and_scope(self):
  rows=[r for page in json.loads((D/'AL-AIR-149-ROWS.json').read_text()) for r in page['rows']]
  payload=dict(headers=['Name','License/Registration#','Status','Registration Type','Issued Date','Expiration Date','Address','City','State','Zip','Print'],rows=rows,total=149,complete=True,verification_pending=False)
  result=m.al_charity_search_evidence(payload)
  self.assertTrue(result);self.assertFalse(any(r['identifier']=='AL25-014CCV' for r in result))
  self.assertFalse(any('American Institutes' in r['name'] for r in result))
  for mutate in ['missing_page','duplicate_row','charity_conflict','changed_name','changed_category']:
   p=copy.deepcopy(payload)
   if mutate=='missing_page':p['rows'].pop()
   elif mutate=='duplicate_row':p['rows'][-1]=p['rows'][0]
   else:
    hits=[r for r in p['rows'] if r[1]=='AL25-014CCV']
    if mutate=='charity_conflict':
     for r in hits:r[3]='Charitable Organization'
    elif mutate=='changed_name':hits[1][0]='Different Company'
    else:hits[1][3]='Exempted Charity'
   with self.subTest(mutate=mutate),self.assertRaises(ValueError):m.al_charity_search_evidence(p)

 def test_co_restriction_three_paths_and_ordinary_records(self):
  org=m.checker.Organization('Teach for All Inc.','262122566')
  for raw,want in [('Expired - may not solicit as of 08/16/2026','Suspended'),('Not authorized to solicit','Suspended'),('Current',''),('Withdrawn','Closed / Withdrawn / Canceled')]:
   r=NS(state='CO',ein=org.ein,matched_registry_name='TEACH FOR ALL INC',raw_status_text=raw)
   with self.subTest(raw=raw):self.assertEqual(m.co_status_from_registry_evidence(r,org),want)
  page=MagicMock();page.locator.return_value.inner_text.return_value='Name: Teach for All Inc.\nStatus: Expired - may not solicit as of 08/16/2026'
  with patch.object(m.checker,'find_visible_input',return_value=Mock()),patch.object(m.checker,'safe_wait_for_network_idle'),patch.object(m.checker,'fast_sleep'):
   self.assertEqual(m.checker.search_co(page,org).status,'Suspended')

 def test_co_shared_budget_does_not_restart(self):
  with patch.object(co_budget.time,'monotonic',return_value=100):
   token=co_budget.STOP.set(105)
   try:
    self.assertEqual(co_budget.timeout(45000),5000)
    with patch.object(co_budget.time,'monotonic',return_value=105),self.assertRaises(TimeoutError):co_budget.timeout(1000)
   finally:co_budget.STOP.reset(token)

 def test_va_actual_extension_and_adverse_controls(self):
  reg=dict(expirationDate='2026-05-15',extensionDate='2026-11-15',status={'name':'Expired/Lapsed'},registrationType={'name':'Charity'},registrationNumber='674395',renewalStatus='Eligible')
  with patch.object(m,'date',AsOf):
   status,raw,identifier,due=m.va_evoke_status_from_entity_and_registrations({'status':'Unregistered'},[reg])
   r=m.checker.StateResult('Room to Read','912003533','VA',status,'');r.success=True;r.raw_status_text=raw;r.matched_registry_name='Room to Read';r.matched_registry_identifier=identifier
   self.assertEqual(m.true_status_from_body(r,raw),'Upcoming Filing')
   for change in [dict(state='MD'),dict(success=False),dict(matched_registry_identifier='999'),dict(raw_status_text=raw+' | Suspended'),dict(raw_status_text=raw.replace('11/15/2026','11/06/2026')),dict(raw_status_text=raw.replace('11/15/2026','malformed'))]:
    obj=copy.copy(r)
    for k,v in change.items():setattr(obj,k,v)
    with self.subTest(change=change):self.assertIsNone(g.va_effective_extension(obj,m.parse_due_date,AsOf.today()))

 def test_me_actual_primary_closed_beats_local_active_alias(self):
  rows=[dict(name='PROLITERACY WORLDWIDE',number='CO1948',location='SYRACUSE, NY 13210',profession='CHARITABLE ORGANIZATION',status='WITHDRAWN/TERMINATED BY LICENSEE'),dict(name='PROLITERACY WORLDWIDE',number='CO3911',location='*MULTIPLE LOCATIONS',profession='CHARITABLE ORGANIZATION',status='CANCELED'),dict(name='LITERACY VOLUNTEERS',number='CO16326',location='FARMINGTON, ME',profession='CHARITABLE ORGANIZATION',status='ACTIVE')]
  org=m.checker.Organization('ProLiteracy Worldwide','161607787');session=Mock(covered_source_query='')
  with patch.object(m,'organization_match_target_variants',return_value=['ProLiteracy Worldwide','Literacy Volunteers']),patch.object(m,'me_fast_direct_query_variants',return_value=['ProLiteracy','Literacy Volunteers']),patch.object(m,'MaineRegistrySession',return_value=session),patch.object(m,'me_search_with_prefix_coverage',side_effect=[(rows[:2],session),(rows[2:],session)]),patch.object(m,'registry_name_is_safe_for_org',return_value=True),patch.object(m,'registry_identity_preference',side_effect=lambda n,*a:3 if n=='PROLITERACY WORLDWIDE' else 2),patch.object(m,'reconciled_registry_address',side_effect=lambda ein,name,*a,**kw:dict(decision='conflict' if name=='LITERACY VOLUNTEERS' else 'corroborated')),patch.object(m,'me_result_from_search',side_effect=lambda org,row,*a:row):
   self.assertIn(m.me_fast_direct_confirmation_result(org)['number'],{'CO1948','CO3911'})

 def test_me_address_review_keeps_original_without_accepting(self):
  r=dict(state='ME',ein='161607787',status='Needs Review',success=False,status_reason='REGISTRY_ADDRESS_CONFLICT',matched_registry_name='Example',matched_registry_identifier='CO123',source_url='https://www.pfr.maine.gov/ALMSOnline/ALMSQuery/ShowDetail.aspx?DetailToken=ABC')
  candidate=dict(name='Example',identifier='CO123',status='Closed / Withdrawn / Canceled',url=r['source_url'],_identity_outcome='conflict')
  r['_worker_identity_review']={'records':[candidate]}
  visual=identity.visual_result(r)
  self.assertTrue(visual['success']);self.assertFalse(r['success']);self.assertEqual(r['status'],'Needs Review')
  for changed in [{'identifier':'CO999'},{'name':'Other'},{'url':'https://evil.example'},{'status':'Unable to Confirm'}]:
   bad=copy.deepcopy(r);bad['_worker_identity_review']['records'][0].update(changed)
   with self.subTest(changed=changed):self.assertFalse(identity.visual_result(bad)['success'])

 def test_ca_actual_name_variation_and_numbered_credential(self):
  self.assertEqual(g.ca_name_queries('Jackie Robinson Foundation Inc.'),['Jackie Robinson Foundation Inc.','Jackie Robinson Foundation'])
  data=json.loads((D/'CA-REGISTRATION-RESPONSES.json').read_text());entity=data[0]['entity'];regs=data[0]['registrations']
  standing,raw,identifier,_=m.checker.ca_evoke_status_from_record(entity,regs)
  self.assertEqual(identifier,'081772');self.assertIn('Delinquent',standing)
  org=m.checker.Organization('Jackie Robinson Foundation Inc.','132754715')
  self.assertEqual(m.ca_master_name_identity(org,dict(entity,fein='99-9999999')),'rejected')
  with patch.dict(m.PUBLIC_PROFILE_CACHE,{},clear=True),patch.object(m,'SALES_PROFILE_CONTEXT',NS(get=lambda:{})):
   self.assertEqual(m.ca_master_name_identity(org,entity),'possible')
  for name in ['Sjögren’s Foundation Inc.','National Cancer Research','A.B.C. Foundation, Inc.','The Children’s Place LLC','Campus']:
   queries=g.ca_name_queries(name);self.assertLessEqual(len(queries),2);self.assertEqual(queries[0],name)

 def test_ny_actual_legacy_row_transport_and_matching_guard(self):
  fixture=json.loads((D/'NY-LEARNING-RESPONSE.json').read_text());body=json.loads(fixture['body']) if isinstance(fixture.get('body'),str) else fixture.get('body',fixture)
  rows=[{k:str(r.get(k) or '') for k in ('orgID','orgName','ein')} for r in body['data']]
  q={'orgName':'Learning'}
  payload=dict(query=q,http_status=200,success=True,statusCode=200,rows=rows)
  self.assertEqual(len(m.ny_connector_clean_response(payload,q)),300)
  for bad_id in ['../escape','<script>','x'*33,'a\n']:
   with self.subTest(bad_id=bad_id),self.assertRaises(ValueError):m.ny_connector_clean_response(dict(payload,rows=[dict(rows[0],orgID=bad_id)]),q)
  legacy={'orgID':'200381DP','orgName':'LearningSpring School','ein':'010603628'}
  def search(query):return m.NYConnectorResponse([] if 'ein' in query else [legacy])
  result=m.search_ny_direct(m.checker.Organization('Learning Forward','310955962'),registry_search_provider=search,registry_detail_provider=lambda q:self.fail('Legacy unrelated row must not open detail'))
  self.assertEqual(m.public_status(result),'Not Registered')
  legacy['orgName']='Learning Forward';legacy['ein']='310955962'
  result=m.search_ny_direct(m.checker.Organization('Learning Forward','310955962'),registry_search_provider=search)
  self.assertNotEqual(m.public_status(result),'Not Registered')

 def test_pa_detail_requires_all_four_fields(self):
  row=['TEACH FOR ALL, INC.','','','101367','08/15/2027','26-2122566']
  fields=dict(EntityName=row[0],RegNum=row[3],Expdt=row[4],FederalID=row[5])
  self.assertTrue(pa.bound(fields,row))
  for key in fields:
   with self.subTest(key=key):self.assertFalse(pa.bound(dict(fields,**{key:'other'}),row))

 def test_ok_early_transport_recovery_same_live_action(self):
  page=Mock(url='https://www.sos.ok.gov/corp/charityDetail.aspx?id=1234567890')
  page.get_by_role.return_value.get_attribute.return_value="javascript:__doPostBack('ctl00$DefaultContent$grdFilingList$ctl02$lnkAction','')"
  page.locator.return_value.first.evaluate.return_value={'__VIEWSTATE':'fixture'}
  response=Mock(ok=True);response.body.return_value=b'%PDF-offline-fixture'
  page.request.post.side_effect=[RuntimeError('socket hang up'),response]
  with patch.object(m,'ok_certificate_expiration',return_value=(date(2027,5,12),'verified')),patch('deployment.ok_certificate_evidence.retain_certificate'):
   result=m.ok_fetch_registration_certificate(page,'12345670002 Renewal Registration May 12, 2026 5','Example')
  self.assertEqual(page.request.post.call_count,2);self.assertEqual(result.expiration,date(2027,5,12))

if __name__=='__main__':unittest.main(verbosity=2)
