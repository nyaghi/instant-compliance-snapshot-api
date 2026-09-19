"""September 19 reported failures and adverse identity controls; no network."""
import sys,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class Controls(unittest.TestCase):
 def context(self,names,ein='123456789'):
  token=c.REVIEWED_NAME_CONTEXT.set({ein:names});self.addCleanup(c.REVIEWED_NAME_CONTEXT.reset,token)
 def test_ar_complete_alias_beats_word_count_gate(self):
  for original,names,row in [
   ('NAF — National Academy Foundation',['NAF','National Academy Foundation'],'National Academy Foundation'),
   ('PEN American Center, Inc. — PEN America',['PEN AMERICA CENTER INC','PEN AMERICA'],'Pen America Center'),
   ('TWLOHA, Inc. — To Write Love on Her Arms',['TWLOHA, INC.','To Write Love on Her Arms'],'TWLOHA, Inc')]:
   with self.subTest(original=original):
    self.context(names);targets=c.organization_match_target_variants(original,'123456789')
    self.assertEqual(c.ar_candidate_identity({'name':row},original,targets,'123456789'),'accept')
    self.assertEqual(c.ar_candidate_identity({'name':row,'ein':'987654321'},original,targets,'123456789'),'reject')
 def test_ar_near_names_scope_and_location_stay_rejected(self):
  for original,names,row in [
   ('NAF — National Academy Foundation',['NAF','National Academy Foundation'],'NAFSA'),
   ('PEN American Center, Inc. — PEN America',['PEN AMERICA CENTER INC'],'Open America LLC'),
   ('TWLOHA, Inc. — To Write Love on Her Arms',['TWLOHA, INC.'],'TWLOHA Boston Chapter'),
   ('Young Womens Christian Association of the United States',['Young Womens Christian Association of the United States'],'Young Womens Christian Association'),
   ('Beth Israel Deaconess Hospital - Milton',['Beth Israel Deaconess Hospital'],'Beth Israel Deaconess Hospital - Plymouth')]:
   with self.subTest(row=row):
    self.context(names);targets=c.organization_match_target_variants(original,'123456789')
    self.assertNotEqual(c.ar_candidate_identity({'name':row},original,targets,'123456789'),'accept')
 def test_ar_suffix_light_query_for_complete_alias(self):
  self.context(['TWLOHA, INC.','To Write Love on Her Arms'])
  org=c.checker.Organization('TWLOHA, Inc. — To Write Love on Her Arms','123456789')
  queries,_=c.ar_reviewed_search_plan(org,[])
  self.assertIn('TWLOHA',[q.upper() for q in queries]);self.assertLess([q.upper() for q in queries].index('TWLOHA'),3)
 def test_ms_wv_primary_literal_prefix_before_unrelated_programs(self):
  self.context(['NAACP Legal Defense and Educational Fund Inc','Earl Warren Legal Training Program','LDF','NAACP Legal Defense and Education Fund Inc'])
  for state in ['MS','WV']:
   queries=(c.ms_name_search_plan if state=='MS' else c.wv_preferred_query_variants)('NAACP Legal Defense & Educational Fund, Inc.','123456789')
   self.assertIn('NAACP Legal Defense',queries);self.assertLess(queries.index('NAACP Legal Defense'),queries.index('Earl Warren Legal Training Program'))
   self.assertFalse(c.registry_name_is_safe_for_org('NAACP Foundation','NAACP Legal Defense & Educational Fund Inc','123456789'))
 def test_short_typed_name_requires_complete_identity(self):
  self.context(['NAF','National Academy Foundation'])
  self.assertEqual(c.structured_registry_name('NAF','NAF — National Academy Foundation','123456789'),'NAF')
  for value in ['ABC','DBA','NA','NAFSA Search','Status']:
   self.assertEqual(c.structured_registry_name(value,'NAF — National Academy Foundation','123456789'),c.useful_registry_name(value))
  self.assertEqual(c.useful_registry_name('NAF'),'')
 def test_ma_primary_wins_alias_in_both_orders(self):
  self.context(['PEN AMERICAN CENTER, INC.','PEN NEW ENGLAND','PEN AMERICA'])
  options=[{'value':'main','label':'PEN AMERICAN CENTER, INC.'},{'value':'old','label':'PEN NEW ENGLAND'}]
  for name in ['PEN American Center, Inc.','PEN American Center, Inc. — PEN America']:
   for order in [options,options[::-1]]:
    self.assertEqual(c.ma_selection_candidate(c.checker.Organization(name,'123456789'),order)['value'],'main')
 def test_ma_equal_primary_duplicate_stays_ambiguous(self):
  self.context(['Example Foundation'])
  options=[{'value':'1','label':'Example Foundation'},{'value':'2','label':'Example Foundation, Inc.'}]
  self.assertIsNone(c.ma_selection_candidate(c.checker.Organization('Example Foundation','123456789'),options))
 def test_ma_unreviewed_dash_location_cannot_be_dropped(self):
  org=c.checker.Organization('Beth Israel Deaconess Hospital - Milton','123456789')
  self.context(['Beth Israel Deaconess Hospital','Beth Israel Deaconess Hospital - Plymouth'])
  self.assertIsNone(c.ma_selection_candidate(org,[{'value':'1','label':'Beth Israel Deaconess Hospital'},{'value':'2','label':'Beth Israel Deaconess Hospital - Plymouth'}]))
 def test_ma_unrelated_alias_tie_stays_ambiguous(self):
  self.context(['Old Aid','Older Aid'])
  self.assertIsNone(c.ma_selection_candidate(c.checker.Organization('New Aid','123456789'),[{'value':'1','label':'Old Aid'},{'value':'2','label':'Older Aid'}]))
 def test_me_literal_primary_query_first(self):
  self.context(['The Tides Foundation','Tides Foundation'])
  queries=c.me_fast_direct_query_variants(c.checker.Organization('Tides Foundation','123456789'))
  self.assertTrue('Tides Foundation'.casefold().startswith(queries[0].casefold()),queries)
 def test_me_inactive_does_not_stop_before_equivalent_active(self):
  self.context(['The Tides Foundation','Tides Foundation'])
  inactive=dict(name='THE TIDES FOUNDATION',status='FAILED TO RENEW',number='old',location='San Francisco, CA')
  active=dict(name='TIDES FOUNDATION',status='ACTIVE',number='new',location='San Francisco, CA')
  session=Mock();session.search.side_effect=[([inactive],session),([active],session)]
  with patch.object(c,'MaineRegistrySession',return_value=session),patch.object(c,'me_fast_direct_query_variants',return_value=['The Tides Foundation','Tides']),patch.object(c,'registry_address_evidence',return_value={'decision':'consistent'}),patch.object(c,'me_result_from_search',side_effect=lambda org,row,*a:row):
   result=c.me_fast_direct_confirmation_result(c.checker.Organization('Tides Foundation','123456789'))
  self.assertEqual(result['number'],'new');self.assertEqual(session.search.call_count,2)
 def test_me_unrelated_active_does_not_replace_inactive(self):
  self.context(['The Tides Foundation'])
  old=dict(name='Tides Foundation',status='FAILED TO RENEW',number='old',location='San Francisco, CA')
  wrong=dict(name='Tides Foundation Boston Chapter',status='ACTIVE',number='wrong',location='Boston, MA')
  session=Mock();session.search.side_effect=[([old],session),([wrong],session)]
  with patch.object(c,'MaineRegistrySession',return_value=session),patch.object(c,'me_fast_direct_query_variants',return_value=['Tides Foundation','Tides']),patch.object(c,'registry_address_evidence',return_value={'decision':'consistent'}),patch.object(c,'me_result_from_search',side_effect=lambda org,row,*a:row):
   result=c.me_fast_direct_confirmation_result(c.checker.Organization('Tides Foundation','123456789'))
  self.assertEqual(result['number'],'old')
 def test_or_incomplete_info_retries_same_record(self):
  org=c.checker.Organization('Example Foundation','123456789');result=c.checker.StateResult(org.organization_name,org.ein,'OR','Delinquent','')
  row=['42','67','','','123456789'];response=Mock(url='https://justice.oregon.gov/Charities/Charity/details?charityID=42')
  response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=b'<table id="info">loading</table>'
  with patch.object(c,'or_snapshot_row_for_ein',return_value=row),patch.object(c.urllib.request,'urlopen',return_value=response) as request,patch.object(c,'or_live_period_evidence',return_value={}):
   actual=c.or_confirm_snapshot_delinquency(org,result)
  self.assertEqual(request.call_count,2);self.assertEqual(actual.status,'Unable to Confirm');self.assertEqual(request.call_args_list[0].args[0].full_url,request.call_args_list[1].args[0].full_url)
 def test_short_wv_name_survives_response_and_comment_cleanup(self):
  self.context(['NAF','National Academy Foundation'])
  org=c.checker.Organization('NAF — National Academy Foundation','123456789')
  r=c.checker.StateResult(org.organization_name,org.ein,'WV','Current','')
  r.matched_registry_name='NAF';r.matched_registry_identifier='short-id'
  c.fill_registry_match_from_text(r,'',org);c.normalize_registry_match_fields(r,org)
  self.assertEqual(r.matched_registry_name,'NAF')
  self.assertIn('Registry match: NAF',c.append_registry_match_comment(r,'Registered','Current'))
 def test_ms_incomplete_search_explains_actual_reason(self):
  r=c.checker.StateResult('Example Charity','123456789','MS','Unable to Verify','')
  r.reason_code='MS_REVIEWED_SEARCH_INCOMPLETE';r.raw_status_text='Mississippi reviewed-name search incomplete'
  self.assertIn('did not complete searches',c.comments_for_result(r,'','Unable to Verify'))
 def test_ms_complete_reviewed_alias_is_not_a_truncated_prefix(self):
  name='TWLOHA, Inc. — To Write Love on Her Arms'
  self.assertFalse(c.ms_registry_name_is_safe('TWLOHA, Inc.',name,'123456789'))
  self.context(['TWLOHA, Inc.','To Write Love on Her Arms'])
  self.assertTrue(c.ms_registry_name_is_safe('TWLOHA, Inc.',name,'123456789'))
  for candidate in ['TWLOHA Boston Chapter','To Write Love','TWLOHA Community Foundation']:
   self.assertFalse(c.ms_registry_name_is_safe(candidate,name,'123456789'),candidate)
  self.assertFalse(c.ms_registry_name_is_safe('TWLOHA, Inc.',name,'987654321'))
 def test_ms_reviewed_name_does_not_drop_location(self):
  self.context(['Beth Israel Deaconess Hospital','Beth Israel Deaconess Hospital - Plymouth'])
  for candidate in ['Beth Israel Deaconess Hospital','Beth Israel Deaconess Hospital - Plymouth']:
   self.assertFalse(c.ms_registry_name_is_safe(candidate,'Beth Israel Deaconess Hospital - Milton','123456789'))
 def test_alias_context_does_not_leak_to_another_ein(self):
  self.context(['NAF','National Academy Foundation'])
  self.assertEqual(c.structured_registry_name('NAF','Example Charity','987654321'),'')
  self.assertEqual(c.ar_candidate_identity({'name':'National Academy Foundation'},'Example Charity',['Example Charity'],'987654321'),'reject')
 def test_wv_short_record_requires_detail_corroboration_and_rejects_conflict(self):
  self.context(['NAF','National Academy Foundation'])
  for dba,address,accepted in [('National Academy Foundation','unknown',True),('Unrelated Foundation','corroborated',True),('Unrelated Foundation','unknown',False),('National Academy Foundation','conflict',False)]:
   with self.subTest(dba=dba,address=address):
    page=Mock();selected=[];row=Mock();cells=[Mock() for _ in range(5)]
    for cell,value in zip(cells,['12300','NAF','Address','Charity','Active']):cell.inner_text.return_value=value
    cell_list=Mock();cell_list.count.return_value=5;cell_list.nth.side_effect=cells.__getitem__
    link=Mock();link.first.click.side_effect=lambda *a,**k:selected.append(True)
    row.locator.side_effect=lambda selector:cell_list if selector=='td' else link
    rows=Mock();rows.count.return_value=1;rows.nth.return_value=row
    page.locator.side_effect=lambda selector:rows if selector=='tr' else Mock()
    detail=f'Organization Name\nNAF\nExpiration Date\n03/07/2027\nContact Name\nControl\nStatus\nActive\nStreet Address\n169 Madison Avenue New York NY\nCounty\nNew York\nDBA\n{dba}\nTax Information\nExempt'
    with patch.object(c,'registry_page_body',side_effect=lambda _:detail if selected else 'Search results'),patch.object(c,'safe_wait_for_network_idle'),patch.object(c,'wv_preferred_query_variants',return_value=['NAF']),patch.object(c,'registry_address_evidence',return_value={'decision':address}):
     result=c.search_wv_precise(page,c.checker.Organization('NAF — National Academy Foundation','123456789'))
    self.assertTrue(selected)
    self.assertEqual(result.status=='Needs Review',not accepted)
    if not accepted:self.assertEqual(result.reason_code,'WV_SHORT_NAME_IDENTITY_UNCONFIRMED')

if __name__=='__main__':unittest.main()
