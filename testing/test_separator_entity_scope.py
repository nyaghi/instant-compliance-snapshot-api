"""Source identity scope and signed NC recovery controls; no live I/O."""
import sys,time,unittest,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class ScopeControls(unittest.TestCase):
 def setUp(self):
  self.name="GIGI'S PLAYHOUSE - DENVER, LLC";self.ein='853874604';self.parent="GiGi's Playhouse, Inc."
  for key,value in [('APP_VERSION','2026.09.26.5-staging'),('NY_CONNECTOR_SIGNING_KEY','test-only-'*8)]:
   p=patch.object(c,key,value);p.start();self.addCleanup(p.stop)
  p=patch.object(c,'log_event');p.start();self.addCleanup(p.stop)
  self.email='reviewer@example.test';self.device='test-device';self.origin='https://staging.example'
  t=c.REVIEWED_NAME_CONTEXT.set({self.ein:(self.name,'Denver Chapter')});self.addCleanup(c.REVIEWED_NAME_CONTEXT.reset,t)
 def test_specific_parent_brand_is_possible_not_accepted(self):
  for name,parent in [(self.name,self.parent),('River Learning Network - Portland, LLC','River Learning Network, Inc.'),('Community Support Alliance - Denver Branch','Community Support Alliance, Inc.')]:
   with self.subTest(name=name):
    s=c.score_candidate(name,self.ein,{'name':parent});self.assertEqual(s['decision'],'possible');self.assertEqual(s['reason'],'REVIEW_SEPARATOR_ENTITY_SCOPE')
    self.assertFalse(c.registry_name_is_safe_against_targets(parent,c.organization_match_target_variants(name,self.ein),name,self.ein))
 def test_sibling_chapter_and_generic_words_cannot_be_identity_candidates(self):
  for name in ["GiGi's Playhouse - Fargo, LLC","GiGi's Playhouse Charleston LLC",'Foundation']:
   self.assertEqual(c.score_candidate(self.name,self.ein,{'name':name})['decision'],'rejected')
  r=c.scope_identity_review_result(c.checker.Organization('Foundation - North Branch',self.ein),'AR',[{'name':'Foundation'}],True,'https://registry.example')
  self.assertFalse(hasattr(r,'_cc_identity_review'))
 def test_scope_declared_by_reviewed_chapter_name_is_preserved(self):
  self.assertTrue(c.separator_entity_scope_gap("GIGI'S PLAYHOUSE - DENVER",self.parent,self.ein))
 def test_matching_and_conflicting_eins_keep_priority(self):
  self.assertEqual(c.score_candidate(self.name,self.ein,{'name':self.parent,'ein':self.ein})['reason'],'MATCH_EIN_EXACT')
  self.assertEqual(c.score_candidate(self.name,self.ein,{'name':self.parent,'ein':'200058563'})['reason'],'REJECT_DIFFERENT_EIN')
 def test_complete_legal_names_aliases_suffixes_and_acronyms_preserved(self):
  token=c.REVIEWED_NAME_CONTEXT.set({})
  try:
   for name,candidate in [(self.name,self.name),('Service Year Exchange, Inc. \u2014 Service Year Alliance','Service Year Exchange, Inc.'),("Children's Literacy Foundation, Inc.","Children's Literacy Foundation")]:
    with self.subTest(name=name):self.assertEqual(c.score_candidate(name,self.ein,{'name':candidate})['decision'],'accepted')
   self.assertEqual(c.score_candidate('River Animal Sanctuary DBA Home for Life',self.ein,{'name':'River Animal Sanctuary'})['decision'],'possible')
  finally:c.REVIEWED_NAME_CONTEXT.reset(token)
 def test_explicit_reviewed_complete_alias_remains_authorized(self):
  t=c.REVIEWED_NAME_CONTEXT.set({self.ein:(self.parent,)} )
  try:self.assertEqual(c.score_candidate(self.name,self.ein,{'name':self.parent})['reason'],'MATCH_REVIEWED_ALTERNATE_NAME')
  finally:c.REVIEWED_NAME_CONTEXT.reset(t)
 def test_distinctive_extension_override_no_longer_erases_branch(self):
  self.assertTrue(c.distinctive_entity_extension_mismatch_against_targets(self.name,self.parent,c.organization_match_target_variants(self.name,self.ein)))
 def test_arkansas_parent_requires_review(self):
  self.assertEqual(c.ar_candidate_identity({'name':self.parent},self.name,c.organization_match_target_variants(self.name,self.ein),self.ein),'unconfirmed_scope')
 def test_south_carolina_parent_requires_filing_ein(self):
  self.assertTrue(c.sc_related_entity_requires_ein(self.name,self.parent,self.ein))
 def test_nevada_unavailable_address_cannot_confirm_scope(self):
  row=dict(name=self.parent,identifier='NV20201738686',ein='',location='',street='',postal_code='',region='')
  with patch.object(c,'reconciled_registry_address',return_value={'decision':'unavailable'}),patch.object(c,'licensed_charity_foreign_ein',return_value={}):
   self.assertEqual(c.licensed_charity_identity(c.checker.Organization(self.name,self.ein),row,'NV',time.monotonic()+10),'possible')
 def test_numbered_pending_nc_source_keeps_identifier_and_status(self):
  row=c.nc_charity_record_evidence({'CSL Legal Name':'Example Pending Charity','CSL Type':'In-Process','Status':'In-Process','License':'EX001234','Expiration Date':'','profile_url':'https://www.sosnc.gov/online_services/search/charities_profile/12345'})
  self.assertEqual(row['identifier'],'EX001234');self.assertEqual(row['status'],'Pending');self.assertIsNone(row['expiration'])
 def review(self,state='NC',complete=False,status='Pending'):
  data=dict(organization_name=self.name,ein=self.ein,state=state,status='Needs Review',success=False,comments='Identity unconfirmed',reviewed_alternate_names=[self.name,'Denver Chapter'])
  row=dict(name=self.parent,identifier='SOURCE123',ein='',location='',url='https://registry.example/record',raw_status='In-Process',status=status,expiration=None,initial=None,_identity_outcome='possible')
  c.attach_identity_review(data,dict(records=[row],search_complete=complete,freshness='Source freshness retained.'))
  return data
 def decide(self,data,action):
  return c.resolve_identity_review(dict(token=data['identity_review']['token'],candidate_id=data['identity_review']['candidates'][0]['id'],ein=data['ein'],state=data['state'],action=action),self.email,self.device)
 def test_source_status_retained_on_accept_reject_and_undo(self):
  for state,status in [('AR','Closed / Withdrawn / Canceled'),('ND','Closed / Withdrawn / Canceled'),('KS','Closed / Withdrawn / Canceled'),('SC','Upcoming Filing')]:
   with self.subTest(state=state):
    data=self.review(state,True,status);self.assertEqual(self.decide(data,'accept')['status'],status)
    rejected=self.decide(data,'reject');self.assertEqual(rejected['status'],'Not Registered');self.assertIn('Source freshness retained',rejected['comments'])
    self.assertEqual(self.decide(rejected,'clear')['status'],'Needs Review')
 def retry(self,data,**extra):
  payload=dict(action='start',state='NC',mode='standard',organization_name=self.name,ein=self.ein,email=self.email,admin_passcode='test',device_id=self.device,identity_review_token=data['identity_review']['token']);payload.update(extra)
  with patch.object(c,'trial_identity',return_value={'origin':self.origin,'permanent_staging':True}),patch.object(c,'is_verified_internal_passcode',return_value=True),patch.object(c,'final_four_connector_advance',side_effect=lambda r:{'phase':'search','query':{'state':'NC','operation':'search','name':'Pending Search'},'query_id':'qid','observed_context':c.USER_IDENTITY_CONTEXT.get(),'observed_names':c.known_names_for_ein(self.ein)}):
   return c.final_four_connector_request(payload,self.origin)
 def test_nc_retry_uses_signed_exclusions_history_and_names(self):
  rejected=self.decide(self.review(),'reject');code,r=self.retry(rejected,alternate_names=['untrusted new name'])
  self.assertEqual(code,200);self.assertEqual(r['observed_context']['rejected'],['SOURCE123']);self.assertEqual(r['observed_names'],[self.name,'Denver Chapter'])
  self.assertEqual(len(r['observed_context']['history']),1);self.assertEqual(c.USER_IDENTITY_CONTEXT.get(),{})
 def test_nc_retry_refuses_cross_org_state_mode_session_and_tampering(self):
  rejected=self.decide(self.review(),'reject')
  for extra in [{'ein':'123456789'},{'organization_name':'Another Branch'},{'state':'NV'},{'mode':'invalid'},{'device_id':'other-device'},{'identity_review_token':rejected['identity_review']['token'][:-1]+'x'}]:
   with self.subTest(extra=extra):self.assertNotEqual(self.retry(rejected,**extra)[0],200)
 def test_nc_retry_requires_incomplete_rejected_snapshot(self):
  self.assertNotEqual(self.retry(self.review())[0],200)
  self.assertNotEqual(self.retry(self.decide(self.review(complete=True),'reject'))[0],200)
 def test_signed_rejection_prevents_readmission(self):
  t=c.USER_IDENTITY_CONTEXT.set({'ein':self.ein,'state':'NC','rejected':['SOURCE123']})
  try:
   row=dict(name=self.parent,identifier='SOURCE123',ein='')
   self.assertEqual(c.licensed_charity_identity(c.checker.Organization(self.name,self.ein),row,'NC',time.monotonic()+5),'rejected')
  finally:c.USER_IDENTITY_CONTEXT.reset(t)
 def test_repeated_failed_retry_preserves_reject_and_incompleteness(self):
  rejected=self.decide(self.review(),'reject');prior=c.identity_review_unpack(rejected['identity_review']['token'],self.email,self.device)
  record={'state':'NC','identity_retry_review':prior,'identity_context':{'history':prior['history'],'rejected':['SOURCE123']}}
  data=c.preserve_nc_identity_retry(dict(status='Unable to Confirm',success=False,comments='Still incomplete'),record)
  self.assertFalse(data['identity_review']['search_complete']);self.assertEqual(data['identity_review']['candidates'][0]['decision'],'reject')

class StatePathControls(unittest.TestCase):
 setUp=ScopeControls.setUp
 def test_ar_full_collector_retains_specific_parent_for_review(self):
  from unittest.mock import MagicMock
  from urllib.parse import urlencode
  page=MagicMock();query=[''];page.url=c.AR_SEARCH_URL
  page.locator.return_value.fill.side_effect=lambda value:query.__setitem__(0,value)
  page.get_by_role.return_value.click.side_effect=lambda **kw:setattr(page,'url',c.AR_SEARCH_URL+'?'+urlencode({'name':query[0]}))
  parent=dict(name=self.parent,type='Charity Registration',status='Close',registration_date='2017-07-20')
  def is_brand():return query[0].strip().upper() in {'GIGI',"GIGI'S PLAYHOUSE",'GIGI PLAYHOUSE','GIGIS PLAYHOUSE'}
  with patch.object(c,'ar_wait_for_search_form',return_value=True),patch.object(c,'safe_wait_for_network_idle'),patch.object(c,'registry_page_body',side_effect=lambda p:'Registration Date Back to Search Form' if is_brand() else 'No Results Found Back to Search Form'),patch.object(c,'ar_result_rows',side_effect=lambda p,o:[parent] if is_brand() else []):
   r=c.search_ar_precise(page,c.checker.Organization(self.name,self.ein))
  self.assertEqual(r.status,'Needs Review');self.assertFalse(r.success);self.assertEqual(r._cc_identity_review['records'][0]['status'],'Closed / Withdrawn / Canceled')
 def test_sc_parent_review_conflicting_ein_exclusion_and_matching_ein_acceptance(self):
  from types import SimpleNamespace
  class Response:
   def __init__(self,text):self.text=text
   def raise_for_status(self):pass
  class Session:
   headers={}
   def get(self,*a,**k):return Response('Search')
   def post(self,url,data,**k):
    if data.get('ctl00$MainContent$Hidden_CharityID'):return Response('Status Registered Public Id P44840 Due Date 11/15/2026')
    if data.get('ctl00$MainContent$txt_CharitySearchName')=='GIGI':return Response('<a href="javascript:CharityInfo(44840)">GiGi\'s Playhouse, Inc.</a>')
    return Response('No results found')
  for filing,expected in [('', 'Needs Review'),('200058563','Not Registered'),(self.ein,'Upcoming Filing')]:
   with self.subTest(filing=filing),patch.object(c,'curl_requests',SimpleNamespace(Session=lambda **kw:Session())),patch.object(c,'build_search_queries',return_value=[self.name,'GIGI','Remaining Full Name']),patch.object(c,'sc_extract_hidden_fields',side_effect=lambda html:{}),patch.object(c,'sc_detail_filing_ein',return_value=filing):
    r=c.sc_official_detail_lookup(c.checker.Organization(self.name,self.ein));self.assertEqual(c.public_status(r),expected,repr(r))
    if filing==self.ein:self.assertEqual(r.identity_anchor,'EIN')
    if not filing:self.assertEqual(r._cc_identity_review['records'][0]['identifier'],'P44840')
 def test_ks_verified_snapshot_ein_priority_and_review_without_ein(self):
  from types import SimpleNamespace
  for observed,expected in [('', 'Needs Review'),('12','Needs Review'),('200058563','Not Registered'),(self.ein,'Closed / Withdrawn / Canceled')]:
   ext=SimpleNamespace(status='Closed / Withdrawn / Canceled',contact_number='23-006055',expiration_date='')
   record=SimpleNamespace(contact_number='23-006055',name=self.parent,ein=observed)
   module=SimpleNamespace(STATUS_NOT_REGISTERED='Not Registered',search_ks_snapshot=lambda *a:ext,load_live_records=lambda:([record],None,None))
   result=c.checker.StateResult(self.name,self.ein,'KS','Closed / Withdrawn / Canceled','https://registry.example',success=True,matched_registry_name=self.parent,matched_registry_identifier='23-006055',raw_status_text='Withdrawn')
   with self.subTest(ein=observed),patch.object(c,'weekly_asset',return_value=Path('validated')),patch.object(c,'load_ks_weekly_checker',return_value=module),patch.object(c,'copy_external_result',return_value=result):
    r=c._search_snapshot_or_embedded_state_once(c.checker.Organization(self.name,self.ein),'KS');self.assertEqual(r.status,expected)
    if not observed:self.assertIn('weekly',r.source_note)
 def test_nd_full_collector_prefers_real_child_over_parent_and_reviews_parent_only(self):
  from unittest.mock import MagicMock
  from types import SimpleNamespace
  class Pending:
   def __init__(self,page):self.page=page
   def __enter__(self):return self
   def __exit__(self,*a):pass
   @property
   def value(self):return SimpleNamespace(status=200,json=self.page.response)
  for has_child,expected in [(False,'Needs Review'),(True,'Active')]:
   page=MagicMock();kind=['search']
   parent={'ID':'parent','RECORD_NUM':'0004015387','TITLE':[self.parent],'STATUS':'Inactive - Voluntary'}
   child={'ID':'child','RECORD_NUM':'CHILD123','TITLE':[self.name],'STATUS':'Active'}
   page.expect_response.side_effect=lambda *a,**k:Pending(page)
   page.locator.return_value.click.side_effect=lambda **kw:kind.__setitem__(0,'search')
   page.get_by_role.return_value.filter.return_value.get_by_role.return_value.click.side_effect=lambda **kw:kind.__setitem__(0,'detail')
   page.response=lambda:({'rows':{'parent':parent,**({'child':child} if has_child else {})},'template':[]} if kind[0]=='search' else {'DRAWER_DETAIL_LIST':[{'LABEL':'Status','VALUE':'Active' if has_child else 'Inactive - Voluntary'}]})
   with self.subTest(child=has_child),patch.object(c,'nd_search_queries',return_value=['GIGI']):
    r=c.search_nd_completed(page,c.checker.Organization(self.name,self.ein));self.assertEqual(r.status,expected)
    if has_child:self.assertEqual(r.matched_registry_identifier,'CHILD123')
    else:self.assertEqual(r._cc_identity_review['records'][0]['identifier'],'0004015387')
if __name__=='__main__':unittest.main()
