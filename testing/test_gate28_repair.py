import ast,copy,json,re,time,unittest,subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import registry_snapshot_server as m
from deployment import gate28_repairs as g,state_snapshots as ss
F=Path(__file__).parent/'fixtures/gate28'

class Gate28(unittest.TestCase):
 def test_only_reviewed_server_functions_changed(self):
  root=Path(m.__file__).parent
  old=subprocess.check_output(['git','show','3b4d9a17e8f9e832a47647aa77a009041e5207a2:registry_snapshot_server.py'],cwd=root,text=True,encoding='utf-8')
  functions=lambda source:{n.name:ast.dump(n)for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
  a,b=functions(old),functions((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
  changed={k for k in a.keys()|b.keys()if a.get(k)!=b.get(k)}
  self.assertEqual(changed,{'il_ga_browser_lookup','final_four_browser_lookup','ri_charity_detail','search_bundled_extension_state','ms_name_search_plan','attach_identity_review','identity_review_state_status'})
 def org(self,name='Center for Biological Diversity Inc.',ein='27-3943866'):
  return m.checker.Organization(name,ein)
 def test_me_actual_alias_heading_and_negative_boundaries(self):
  text=(F/'ME-original-text.txt').read_text(encoding='utf-8');name='AMERICAN SOCIETY FOR THE PREVENTION OF CRUELTY TO ANIMALS, THE'
  self.assertTrue(ss.me_detail_name_bound(name,text,'CO1734'))
  for changed,identifier in [(text,'CO1735'),(text.replace('CO1734','CO1735'),'CO1734'),(text.replace('THE AMERICAN SOCIETY FOR THE PREVENTION OF CRUELTY TO ANIMALS','OTHER LEGAL NAME'),'CO1734'),(text+'\nLicense Number: CO9999','CO1734')]:
   self.assertFalse(ss.me_detail_name_bound(name,changed,identifier))
  for i in range(30):
   legal=f'Beacon Education Research {i}'
   body=f'CHARITABLE SOLICITATIONS\n{legal}\nCHARITABLE ORGANIZATION\nLicense Number:\nCO{i}'
   self.assertTrue(ss.me_detail_name_bound(legal,body,f'CO{i}'))
   self.assertFalse(ss.me_detail_name_bound(legal+' Affiliate',body,f'CO{i}'))
 def test_ga_internal_article_changes_one_redundant_probe_only(self):
  name='American Society for the Prevention of Cruelty to Animals';org=self.org(name,'131623829')
  with patch.object(m,'known_names_for_ein',return_value=[]):r,gen=m.licensed_charity_names(org,literal_name_priority=True)
  # The exact deployed plan includes a punctuation-equivalent fallback.
  gen += ['American-Society for the Prevention of Cruelty to Animals']
  actual=g.ga_article_queries(m,r,gen)
  self.assertEqual(actual[1],'American Society for Prevention of Cruelty to Animals')
  self.assertEqual(len(actual),len(r)+len(gen));self.assertTrue(all(x in actual for x in r))
  self.assertTrue('American Society For Prevention Of Cruelty To Animals'.casefold().startswith(m.ga_distinctive_covering_prefix(actual[1]).casefold()))
  for i in range(30):
   name=f'Beacon Research Institute {i}';self.assertEqual(g.ga_article_queries(m,[name],[name+' Society']),[name,name+' Society'])
 def test_ms_actual_plan_reaches_dash_space_preserves_alias_and_cap(self):
  org=self.org('Oxfam-America Inc.','237069110')
  with patch.object(m,'known_names_for_ein',side_effect=lambda ein: ['OXFAM-AMERICA, INC.'] if ein else []):plan=m.ms_name_search_plan(org.organization_name,org.ein)
  self.assertEqual(plan[:2],['Oxfam-America Inc.','Oxfam- America'])
  self.assertIn('OXFAM-AMERICA, INC.',plan)
  self.assertNotIn('Oxfam',plan)
  with patch.object(m,'registry_name_is_safe_for_org',return_value=False):self.assertFalse(m.ms_registry_name_is_safe('Oxfam America Action Fund, Inc.',org.organization_name,org.ein))
  for i in range(30):
   name=f'Beacon Research {i}';old=[name,name+' Inc.'];self.assertEqual(g.ms_dash_space_queries(name,old,[name]),old)
 def ri_payload(self,value=None):
  address=['2108 N Street, Suite N','Sacramento, California 95816','United States']
  data=[{'label':'Credential','value':['CO.9701768','Charitable Organization','Securities Regulation']},{'label':'Status','value':['ACTIVE']},{'label':'Expiration Date','value':['10/21/2027']}]
  return {'id':'C40286','name':'Details for ANIMAL LEGAL DEFENSE FUND','tiles':[{'steps':[{'name':'Summary','contents':[{'data':data}]},{'name':'Address','contents':[{'data':[{'label':'Business Address','value':address},{'label':'Business Address','value':address if value is None else value}]}]}]}]}
 def test_ri_real_duplicate_address_and_conflicting_fields(self):
  for i in range(30):
   payload=self.ri_payload()
   with patch.object(m,'registry_json_request',return_value=payload):r=m.ri_charity_detail({'id':'C40286','title':'ANIMAL LEGAL DEFENSE FUND'},time.monotonic()+5,{})
   self.assertEqual(r['status'],'Current');self.assertEqual(r['identifier'],'CO.9701768')
   self.assertEqual(r['location'],'Sacramento, CA')
  for label,value in [('Business Address',['Another City']),('Status',['EXPIRED']),('Expiration Date',['10/21/2025']),('Credential',['CO.9999','Charitable Organization'])]:
   payload=self.ri_payload();payload['tiles'][0]['steps'][0]['contents'][0]['data'].append({'label':label,'value':value})
   with patch.object(m,'registry_json_request',return_value=payload),self.assertRaisesRegex(ValueError,'conflicting'):m.ri_charity_detail({'id':'C40286','title':'ANIMAL LEGAL DEFENSE FUND'},time.monotonic()+5,{})
 def nv_records(self):
  empty=dict(name='DEFENDERS OF WILDLIFE',identifier='NV20201926364',ein='',raw_status='Expired',expiration=date(2021,10,31),_nv_complete_empty_history=True,match={'decision':'accepted'},address_evidence={})
  charity=dict(name='DEFENDERS OF WILDLIFE',identifier='NV20171822684',ein='',raw_status='Expired',status='Delinquent',expiration=date(2024,12,31),solicitation_statement_filed=date(2023,9,25),_identity_outcome='accepted',match={'decision':'accepted'},address_evidence={})
  return empty,charity
 def test_nv_historical_resolution_and_conflict_boundaries(self):
  e,c=self.nv_records();self.assertTrue(g.nv_historical_expired_empty(m,e,[c],'accepted'))
  for changes in [{'_nv_complete_empty_history':False},{'raw_status':'Active'},{'expiration':date(2030,1,1)},{'ein':'987654321'},{'address_evidence':{'decision':'conflict'}},{'match':{'decision':'possible'}}]:
   self.assertFalse(g.nv_historical_expired_empty(m,{**e,**changes},[c],'accepted'))
  for changes in [{'solicitation_statement_filed':date(2020,1,1)},{'expiration':date(2020,1,1)},{'name':'DEFENDERS OF WILDLIFE ACTION FUND'},{'_identity_outcome':'possible'},{'match':{'decision':'possible'}},{'address_evidence':{'decision':'different_ein'}},{'status':'Suspended'}]:
   self.assertFalse(g.nv_historical_expired_empty(m,e,[{**c,**changes}],'accepted'))
  self.assertFalse(g.nv_historical_expired_empty(m,e,[c],'possible'))
 def test_nv_full_two_record_lookup_selects_original_charity_and_retains_exclusion(self):
  from testing.run_final_four_source_guardrails import NV
  org=self.org('Defenders of Wildlife','530183181');calls=[]
  def provider(q):
   calls.append(q)
   if q['operation']=='search':
    return {'state':'NV','query':q,'complete':True,'verification_pending':False,'rows':[
     {'name':org.organization_name,'identifier':'NV20201926364','entity_type':'','entity_number':'E10000952020-6','raw_status':'Expired'},
     {'name':org.organization_name,'identifier':'NV20171822684','entity_type':'','entity_number':'E0595252017-0','raw_status':'Expired'}],'total':2}
   empty=q['identifier']=='NV20201926364'
   fields={**NV,'Entity Name':'DEFENDERS OF WILDLIFE','NV Business ID':q['identifier'],'Entity Type':'-','Entity Status':'Expired',
    'IRS Registered Name':'DEFENDERS OF WILDLIFE','Solicits Charitable Contribution?':'Yes','Formation Date in Nevada':'12/07/2017',
    'Annual Renewal Due Date/Expiration Date':'10/31/2021' if empty else '12/31/2024'}
   rows=[] if empty else [['09/25/2023','09/25/2023','20233653582','Charitable Solicitation Registration Statement','Online','4']]
   history={'identifier':q['identifier'],'name':fields['Entity Name'],'complete':True,'total':len(rows),'headers':['Filed Date','Effective Date','Filing Number','Filing Type','Source','No. of Pages'],'rows':rows}
   return {'query':q,'complete':True,'fields':fields,'filings':history,'source_url':'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=bc74951f-4315-4ae9-bd77-42587da4654c'}
  with patch.object(m,'trial_identity',return_value={'origin':'local'}),patch.object(m,'reconciled_registry_address',return_value={'decision':'unavailable'}),patch.object(m,'known_names_for_ein',return_value=[]):
   result=m.final_four_browser_lookup(org,'NV',provider)
  self.assertTrue(result.success);self.assertEqual(result.status,'Delinquent');self.assertEqual(result.matched_registry_identifier,'NV20171822684')
  self.assertIn('Historical terminal',str(result.rejected_candidates))
  self.assertEqual(sum(q['operation']=='detail' for q in calls),2)
 def or_result(self):
  r=m.checker.StateResult('Center for Biological Diversity Inc.','273943866','OR','Delinquent','https://justice.oregon.gov/Charities/Charity/details?charityID=48191')
  r.raw_status_text='Status: Registered | Fiscal Period End: 12/31/2024 | Next Due: 5/15/2026';r.success=True;r.computed_due_date='5/15/2026'
  return r
 def test_or_malformed_ein_original_candidate_status_and_transport(self):
  body=(F/'OR-original-detail.txt').read_text(encoding='utf-8');org=self.org();r=self.or_result()
  with patch.object(m,'known_names_for_ein',return_value=[org.organization_name]):r=g.or_malformed_review(m,org,r,'Center for Biological Diversity, Inc.',body,r.source_url)
  self.assertIsNotNone(r);self.assertEqual(r.status,'Needs Review');self.assertEqual(r.matched_registry_identifier,'46703')
  self.assertEqual(r._cc_identity_review['records'][0]['status'],'Delinquent')
  m.normalize_registry_match_fields(r,org)
  self.assertEqual(r.matched_registry_identifier,'46703')
  run=ss.CaptureRun(org.organization_name,org.ein,'OR')
  # Placeholder image bytes are test-only; the retained public text is the actual source.
  run.documents=[(r.source_url,b'test-original-pixels','image',body,time.time(),'original-test-source')]
  with patch.object(ss,'asset_for',return_value={'url':'/state-snapshots/'+'a'*64+'.pdf'}) as archive:
   data=run.finish({'state':'OR','ein':org.ein,'organization_name':org.organization_name,'status':'Needs Review','success':False,'_worker_identity_review':r._cc_identity_review})
  self.assertTrue(data.get('_worker_source_archives'));self.assertEqual(archive.call_args.kwargs['identifier'],'46703')
  self.assertEqual(archive.call_args.args[0],b'test-original-pixels')
  with patch.object(m,'NY_CONNECTOR_SIGNING_KEY','x'*40),patch.object(m,'trial_identity',return_value={'origin':'local'}):
   data={'state':'OR','ein':org.ein,'organization_name':org.organization_name,'status':'Needs Review','comments':r.source_note}
   m.attach_identity_review(data,r._cc_identity_review)
   self.assertIn('identity_review',data)
   rec=m.identity_review_unpack(data['identity_review']['token'],'','')
   self.assertEqual(rec['records'][0]['interpreted_status'],'Delinquent')
   self.assertEqual(m.identity_review_state_status('OR',rec['records'][0]),'Delinquent')
   payload=dict(token=data['identity_review']['token'],ein=org.ein,state='OR',candidate_id=data['identity_review']['candidates'][0]['id'])
   with patch.object(m,'run_state_lookup',side_effect=AssertionError('No new lookup is permitted for this signed decision')):
    accepted=m.resolve_identity_review({**payload,'action':'accept'},'','')
    self.assertEqual(accepted['status'],'Delinquent');self.assertEqual(accepted['matched_registry_identifier'],'46703')
    rejected=m.resolve_identity_review({**payload,'action':'reject'},'','')
    self.assertFalse(rejected['success']);self.assertNotEqual(rejected['status'],'Not Registered')
 def test_or_valid_conflicting_ein_never_enters_malformed_review(self):
  body=(F/'OR-original-detail.txt').read_text(encoding='utf-8');org=self.org()
  for changed,url in [(body.replace('73943866','123456789'),self.or_result().source_url),(body.replace('73943866','273943866'),self.or_result().source_url),(body,'https://example.com/Charities/Charity/details?charityID=48191'),(body.replace('Registration:','#Other:'),self.or_result().source_url)]:
   with patch.object(m,'known_names_for_ein',return_value=[]):self.assertIsNone(g.or_malformed_review(m,org,self.or_result(),'Center for Biological Diversity, Inc.',changed,url))
 def test_or_full_lookup_stops_at_malformed_record_without_extra_search(self):
  body=(F/'OR-original-detail.txt').read_text(encoding='utf-8');org=self.org();page=SimpleNamespace(url=self.or_result().source_url)
  module=SimpleNamespace(Organization=m.checker.Organization)
  with patch.object(m,'state_extension_module',return_value=module),patch.object(m,'search_or_completed',return_value=self.or_result()) as search,patch.object(m,'copy_external_result',side_effect=lambda org,st,r:r),patch.object(m,'registry_page_body',return_value=body),patch.object(m,'known_names_for_ein',return_value=[]):
   r=m.search_bundled_extension_state(page,org,'OR')
  self.assertEqual(search.call_count,1);self.assertEqual(r.reason_code,'OR_MALFORMED_EIN_IDENTITY_REVIEW')

if __name__=='__main__':unittest.main(verbosity=2)
