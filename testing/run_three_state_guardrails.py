"""Bounded retrieval recovery and alias-conflict controls; no live fixtures fetched."""
import io,json,sys,time,unittest,urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import registry_snapshot_server as c

class ThreeStateTests(unittest.TestCase):
 def test_former_name_label_fragments_are_not_candidates(self):
  for name in ["(the charitable organization's former name)","Inc. (The Charitable Organization's Former Name)","Inc.(it's former name)","Inc. (It's Former Name)","LLC (its former name)","(the organization’s former name)","(the Charitable Organizations former name)","(the charitable organization former name)"]:
   with self.subTest(name=name):self.assertIsNone(c.identity_candidate(name,'Example state','DBA','https://state.test'))
 def test_real_former_names_and_annotations_remain_candidates(self):
  for name in ["Example Endowment, Inc. (the charitable organization's former name)","First Responders Children's Foundation","F/K/A Example Endowment, Inc.","Former Name Foundation","The Organization's Former Name Foundation","ITS Foundation","YWCA of the USA, National Board"]:
   with self.subTest(name=name):self.assertEqual(c.identity_candidate(name,'Example state','DBA','https://state.test')['name'],name)
 def test_state_alias_lists_discard_label_only_fragments(self):
  result=c.identity_rows_names('WA',[{'FEINNumber':'123456789','EntityName':'Example Foundation','AKANames':"Example Endowment; Inc. (it's former name); (the charitable organization's former name)"}],'123456789','https://state.test')
  self.assertEqual([r['name'] for r in result['names']],['Example Foundation','Example Endowment'])
  self.assertEqual(len(result['rejected_name_fields']),2)
 def test_me_success_and_completed_empty_are_not_retried(self):
  for status in ['Current','Not Registered','Unable to Confirm']:
   with self.subTest(status=status),patch.object(c,'run_state_lookup',return_value={'state':'ME','status':status}) as run,patch.object(c.time,'sleep') as sleep:
    result=c.run_single_state_lookup_reliably('Example Charity','123456789','ME')
    self.assertEqual(result['status'],status);self.assertEqual(run.call_count,1);sleep.assert_not_called()
 def test_me_recovers_and_retains_first_failure(self):
  rows=[{'state':'ME','status':'Site Not Reachable','error':'incomplete'}, {'state':'ME','status':'Not Registered','success':True}]
  with patch.object(c,'run_state_lookup',side_effect=rows) as run,patch.object(c.time,'sleep') as sleep:
   result=c.run_single_state_lookup_reliably('Example Charity','123456789','ME')
  self.assertEqual(result['status'],'Not Registered');self.assertEqual(len(result['me_attempt_history']),2)
  self.assertEqual(result['me_attempt_history'][0]['error'],'incomplete');sleep.assert_called_once_with(8)
  self.assertFalse(c.fragile_batch_result_needs_confirmation(result))
 def test_me_repeated_incomplete_is_never_negative(self):
  with patch.object(c,'run_state_lookup',return_value={'state':'ME','status':'Site Not Reachable','success':False}) as run,patch.object(c.time,'sleep'):
   result=c.run_single_state_lookup_reliably('Example Charity','123456789','ME')
  self.assertEqual(run.call_count,2);self.assertEqual(result['status'],'Site Not Reachable')
 def test_me_batch_uses_same_recovery(self):
  with patch.object(c,'run_single_state_lookup_reliably',return_value={'status':'Current'}) as run:
   c.run_state_lookup_for_batch('Example','123456789','ME',True)
  run.assert_called_once_with('Example','123456789','ME')
 def test_unrelated_state_receives_no_me_retry(self):
  with patch.object(c,'run_state_lookup',return_value={'state':'NY','status':'Site Not Reachable'}) as run,patch.object(c.time,'sleep') as sleep:
   c.run_single_state_lookup_reliably('Example','123456789','NY')
  self.assertEqual(run.call_count,1);sleep.assert_not_called()
 def test_wi_one_transient_read_retry(self):
  operation=Mock(side_effect=[TimeoutError('temporary'),'valid evidence'])
  with patch.object(c.time,'sleep') as sleep:
   self.assertEqual(c.wi_identity_read(operation,time.monotonic()+20,'IRS return'),'valid evidence')
  self.assertEqual(operation.call_count,2);sleep.assert_called_once_with(.35)
 def test_wi_persistent_failure_stops(self):
  operation=Mock(side_effect=TimeoutError('temporary'))
  with patch.object(c.time,'sleep'),self.assertRaises(TimeoutError):c.wi_identity_read(operation,time.monotonic()+20,'financial values')
  self.assertEqual(operation.call_count,2)
 def test_wi_full_evidence_workflow_recovers_each_transient_read(self):
  import run_cogency_repair_guardrails as fixtures
  original=c.wi_identity_read
  for selected in ['IRS return','Wisconsin fiscal-year selection','Wisconsin financial values']:
   c.WI_FINANCIAL_IDENTITY_CACHE.clear();attempts=[]
   def injected(operation,deadline,stage,diagnostics=None):
    if stage!=selected:return original(operation,deadline,stage,diagnostics)
    def once():
     attempts.append(stage)
     if len(attempts)==1:raise TimeoutError('QA injected read failure')
     return operation()
    return original(once,deadline,stage,diagnostics)
   with self.subTest(stage=selected),patch.object(c,'wi_identity_read',side_effect=injected),patch.object(c.time,'sleep'):
    self.assertEqual(fixtures.RepairTests().financial().get('decision'),'corroborated')
   self.assertEqual(len(attempts),2)
 def test_wi_no_retry_of_identity_or_parsing_disagreement(self):
  for error in [ValueError('wrong EIN'),urllib.error.HTTPError('https://example.test',404,'absent',{},None)]:
   operation=Mock(side_effect=error)
   with self.subTest(error=error),self.assertRaises(type(error)):c.wi_identity_read(operation,time.monotonic()+20,'IRS return')
   self.assertEqual(operation.call_count,1)
 def test_wi_deadline_is_not_restarted(self):
  operation=Mock()
  with self.assertRaises(TimeoutError):c.wi_identity_read(operation,time.monotonic()-1,'IRS return')
  operation.assert_not_called()
 def test_wi_response_size_is_bounded(self):
  opener=Mock();opener.open.return_value=io.BytesIO(b'x'*2_000_001)
  with self.assertRaises(ValueError):c.wi_identity_page(opener,'https://example.test',time.monotonic()+20)
 def test_wi_exact_credential_financial_identity_does_not_depend_on_location_row(self):
  name='Florida Gulf Coast University Foundation Inc'
  detail='Name: '+name+' Credential Type: Charitable Organization Credential Number: 22812-800 Location: NEW YORK , NY Status: License is current (Active)'
  conflict={'decision':'conflict','registry_location':'NEW YORK , NY','ein_linked_location':'Fort Myers, FL'}
  for city in ['NEW YORK , NY','FORT MEYERS, FL']:
   candidate={'registry_name':name,'license_number':'22812-800','location':city,'detail_href':'CredSummaryDetails.aspx?chid=944852&h=847014605'}
   for financial in [{},{'decision':'corroborated','fiscal_year':'2025'}]:
    with self.subTest(city=city,financial=financial),patch.object(c,'registry_address_evidence',return_value=conflict),patch.object(c,'wi_minor_city_spelling_difference',return_value=city.startswith('FORT')),patch.object(c,'wi_financial_identity_evidence',return_value=financial) as read:
     result=c.wi_verify_candidate_identity(candidate,[name],name,'650403969',detail)
    read.assert_called_once();self.assertEqual(result['identity_conflict'],not bool(financial))
 def test_wi_other_primary_entity_cannot_use_financial_fallback(self):
  name='Example Hospital - Milton'
  detail='Name: Example Hospital - Needham Credential Type: Charitable Organization Credential Number: 123-800 Location: Boston, MA Status: License is current (Active)'
  candidate={'registry_name':name,'license_number':'123-800','location':'Boston, MA','detail_href':'CredSummaryDetails.aspx?chid=123'}
  with patch.object(c,'wi_financial_identity_evidence') as read:
   result=c.wi_verify_candidate_identity(candidate,[name],name,'123456789',detail)
  self.assertTrue(result is None or result.get('identity_conflict'));read.assert_not_called()
 def review(self,foreign=None,primary='Example Education Center',alias='National Institute of Experimental Medicine'):
  data={'names':[c.identity_candidate(primary,'WA','Registered name','https://state.test'),c.identity_candidate(alias,'WA','AKA / DBA','https://state.test')],'complete':True}
  candidate={'ein':987654321,'name':alias,'city':'Seattle','state':'WA',**(foreign or {})}
  with patch.dict(c.PUBLIC_PROFILE_CACHE,{'123456789':{'organization':{'ein':123456789,'name':primary,'city':'Chicago','state':'IL'}}}),patch.object(c,'identity_fetch',return_value=json.dumps({'organizations':[candidate]}).encode()):
   return c.identity_wa_alias_review(data,'123456789',time.monotonic()+20)
 def test_wa_conflict_visible_but_unverified(self):
  result=self.review();self.assertEqual(len(result['names']),2);self.assertTrue(result['names'][0]['verified'])
  self.assertFalse(result['names'][1]['verified']);self.assertIn('identity_conflict',result['names'][1])
 def test_wa_same_ein_or_location_is_not_quarantined(self):
  for foreign in [{'ein':123456789},{'city':'Chicago'},{'state':'IL'},{'city':''},{'ein':'invalid'}]:
   with self.subTest(foreign=foreign):self.assertTrue(self.review(foreign)['names'][1]['verified'])
 def test_wa_unrelated_search_result_is_not_evidence(self):
  self.assertTrue(self.review({'name':'National Institute of Experimental Medicine Wisconsin Chapter'})['names'][1]['verified'])
 def test_wa_shared_distinctive_name_is_preserved(self):
  self.assertTrue(self.review(primary='National Institute of Experimental Medicine Foundation')['names'][1]['verified'])
 def test_wa_unavailable_independent_source_preserves_name(self):
  data={'names':[c.identity_candidate('Example Center','WA','Registered name','https://state.test'),c.identity_candidate('Completely Different Former Name','WA','AKA / DBA','https://state.test')]}
  with patch.object(c,'identity_fetch',side_effect=TimeoutError('unavailable')):
   result=c.identity_wa_alias_review(data,'123456789',time.monotonic()+20)
  self.assertTrue(result['names'][1]['verified'])
 def test_wa_secondary_exact_ein_source_restores_alias(self):
  conflict=self.review()['names'][1];alias=conflict['name']
  def source(name,ein,deadline):
   names=[conflict] if name=='WA' else [c.identity_candidate(alias,'IRS via ProPublica','Form 990 filer legal name','https://irs.test')] if name=='IRS' else []
   return {'source':name,'names':names,'complete':True}
  with patch.object(c,'identity_source_result',side_effect=source):result=c.discover_organization_names('Example Center','123456789')
  row=next(n for n in result['names'] if n['name']==alias)
  self.assertTrue(row['verified']);self.assertNotIn('identity_conflict',row)
 def test_wa_close_foreign_name_is_only_a_review_candidate(self):
  self.assertTrue(c.identity_alias_foreign_name_matches('American Association of Clinical Endocrinology','American Association of Clinical Endocrinologists'))
  self.assertFalse(c.identity_alias_foreign_name_matches('Autism Research Institute','Organization for Autism Research'))
  self.assertFalse(c.identity_alias_foreign_name_matches('YWCA USA','YWCA Milwaukee'))

if __name__=='__main__':unittest.main(verbosity=2)
