"""MA primary-status precedence and MI slow-source recovery, without network."""
import copy,json,sys,time,unittest
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
import run_mi_name_fallback_guardrails as mi

class Today(date):
 @classmethod
 def today(cls):return cls(2026,9,14)

class Massachusetts(unittest.TestCase):
 def final(self,status,*,empty=False,a2=False,period='',account='067606',observed_account=None,filing_status='Submitted',name='College of William & Mary',ein='54-6001718',visible_status=''):
  org=c.checker.Organization(name,ein);r=c.checker.StateResult(name,ein,'MA','Current','https://masscharities.my.site.com/FilingSearch/s/')
  r.matched_registry_name=name;r.matched_registry_identifier=account;r.success=True
  page=Mock();page.get_by_role.return_value.all_inner_texts.return_value=[]
  page.locator.return_value.inner_text.return_value='AG Account Number '+account+(' Charity Status: '+visible_status if visible_status else '')
  completed={'record':{'ago_account':observed_account or account,'registry_status':status},'filings':{account:{'empty':empty,'only_schedule_a2':a2}}}
  annual={'period_end':period,'filing_status':filing_status,'ago_account':account} if period else {}
  with patch.object(c,'date',Today),patch.object(c,'public_profile_for_ein',return_value={}),patch.object(c,'ma_read_legacy_form_pc',return_value=annual),patch.object(c.urllib.request,'urlopen',side_effect=AssertionError('Unexpected network')):
   evidence=c.ma_read_latest_form_pc(page,r,'AG Account Number '+account+(' Charity Status: '+visible_status if visible_status else ''),completed)
   c.annotate_ma_visible_form_pc_due(r,evidence)
   return c.response_data_for_lookup(r,'',org,name,ein,'MA',time.perf_counter())
 def test_primary_pending_controls_all_filing_conditions_and_retains_identity(self):
  for status in ['Pending','In-Progress','In Progress','in-progress']:
   for filing in [{'empty':True},{'a2':True},{},{'period':'12/31/2023'},{'period':'12/31/2025'}]:
    with self.subTest(status=status,filing=filing):
     r=self.final(status,visible_status=status,**filing)
     self.assertEqual(r['status'],'Pending');self.assertEqual(r['status_reason'],'MA_PRIMARY_REGISTRATION_PENDING')
     self.assertEqual(r['ein'],'54-6001718');self.assertEqual(r['matched_registry_identifier'],'067606')
     self.assertEqual(r['matched_registry_name'],'College of William & Mary');self.assertTrue(r['success'])
     self.assertFalse(r.get('computed_due_date'));self.assertIn(status,r['comments']);self.assertIn('Review state communications',r['comments'])
 def test_network_only_pending_follows_public_filings(self):
  for primary in ['Pending','In-Progress','In Progress','in-progress']:
   for filing,expected in [({'empty':True},'Delinquent'),({'a2':True},'Delinquent'),({},'Unable to Confirm'),({'period':'12/31/2023'},'Delinquent'),({'period':'12/31/2024'},'Upcoming Filing'),({'period':'12/31/2025'},'Current')]:
    with self.subTest(primary=primary,filing=filing):
     r=self.final(primary,**filing);self.assertEqual(r['status'],expected)
     self.assertNotIn('registration as '+primary,r['comments'])
     self.assertEqual(r['ma_filing_evidence'].get('noncontrolling_network_status'),primary)
 def test_pending_in_hidden_html_is_not_visible_status(self):
  page=Mock();page.locator.return_value.inner_text.return_value='AG Account Number 067606 Annual Filings and Documents'
  completed={'record':{'ago_account':'067606','registry_status':'In-Progress'},'filings':{'067606':{'empty':True}}}
  r=c.checker.StateResult('College of William & Mary','546001718','MA','Current','')
  evidence=c.ma_read_latest_form_pc(page,r,'AG Account Number 067606 <script>Charity Status: Pending</script>',completed)
  self.assertTrue(evidence['empty_history_confirmed']);self.assertFalse(evidence.get('registration_pending'))
 def test_education_forward_activity_is_noncontrolling(self):
  for filing in [{'empty':True},{'a2':True}]:
   r=self.final('Not Doing Business in Mass',account='084432',name='Education Forward DC',ein='81-1823628',**filing)
   self.assertEqual(r['status'],'Delinquent');self.assertTrue(r['success']);self.assertEqual(r['matched_registry_identifier'],'084432')
   self.assertIn('infers Delinquent',r['comments']);self.assertFalse(r.get('computed_due_date'))
 def test_activity_retains_submitted_date_calculation(self):
  for period,status in [('12/31/2023','Delinquent'),('12/31/2024','Upcoming Filing'),('12/31/2025','Current')]:
   with self.subTest(period=period):self.assertEqual(self.final('Not Doing Business in Mass',period=period)['status'],status)
 def test_incomplete_history_and_pending_document_are_not_primary_pending(self):
  for primary in ['', 'Registered','Not Doing Business in Mass']:
   for period,filing_status in [('', 'Submitted'),('12/31/2024','Pending')]:
    with self.subTest(primary=primary,period=period):
     self.assertEqual(self.final(primary,period=period,filing_status=filing_status)['status'],'Unable to Confirm')
 def test_wrong_account_cannot_supply_pending_or_empty_history(self):
  for status in ['Pending','In-Progress','Not Doing Business in Mass']:
   self.assertEqual(self.final(status,empty=True,observed_account='999999')['status'],'Unable to Confirm')
 def test_unapproved_primary_statuses_are_not_reclassified(self):
  for primary in ['Suspended','Revoked','Closed','Withdrawn','Exempt','Unknown status']:
   self.assertEqual(self.final(primary,empty=True)['status'],'Needs Review')

class Michigan(mi.MichiganNameTests):
 def test_slow_name_response_fits_michigan_even_with_shared_59_second_setting(self):
  with patch.object(c,'LOOKUP_SOFT_MAX_SECONDS',59):
   for millis in [13000,24000,34000]:
    with self.subTest(millis=millis):
     r,_,_=self.flow([self.correct],navigation_ms=millis)
     self.assertTrue(r.success);self.assertEqual(r.matched_registry_name,"America's Charities")
 def test_slow_response_cannot_outrun_final_deadline(self):
  r,_,_=self.flow([self.correct],navigation_ms=20000,lookup_deadline=18,clock=lambda:0)
  self.assertFalse(r.success);self.assertNotEqual(c.public_status(r),'Not Registered')
 def test_retry_resumes_completed_empty_queries_and_opens_new_session(self):
  progress={'identity':(self.org.organization_name,c.canonical_ein_digits(self.org.ein))}
  variants=["America's Charities",'Americas Charities']
  first,_,_=self.flow([],text='0 record(s) found',variants=variants,navigation_ms=iter([1000,40000]),progress=progress)
  self.assertFalse(first.success);self.assertEqual(progress['completed_empty_name_queries'],["America's Charities"])
  second,_,module=self.flow([],text='0 record(s) found',variants=variants,navigation_ms=1000,progress=progress)
  self.assertTrue(second.success);self.assertEqual(c.public_status(second),'Not Registered')
  self.assertEqual(second.queries_attempted,['Americas Charities']);module.open_search_form.assert_called_once()
 def test_other_organization_progress_cannot_skip_search(self):
  progress={'identity':('Unrelated','123456789'),'completed_empty_name_queries':["America's Charities"]}
  r,_,_=self.flow([self.correct],progress=progress)
  self.assertTrue(r.success);self.assertEqual(r.queries_attempted,["America's Charities"])
  self.assertEqual(progress['completed_empty_name_queries'],["America's Charities"])
 def test_incomplete_or_nonempty_response_is_never_remembered_as_empty(self):
  for options in [{'missing_frame':True},{'text':'Please try again later'},{}]:
   progress={'identity':(self.org.organization_name,c.canonical_ein_digits(self.org.ein))}
   self.flow([self.wrong],progress=progress,**options)
   self.assertNotIn('completed_empty_name_queries',progress)

class Recovery(unittest.TestCase):
 def lookup(self,results,state='MI',ein='27-3067797'):
  with patch.object(c,'SINGLE_STATE_SEMANTIC_RETRY_STATES',{'MI','CO'}),patch.object(c,'SINGLE_STATE_SEMANTIC_RETRY_ATTEMPTS',2),patch.object(c,'SINGLE_STATE_SEMANTIC_RETRY_DELAY_SECONDS',1),patch.object(c,'run_state_lookup',side_effect=copy.deepcopy(results)) as run,patch.object(c.time,'sleep') as sleep:
   r=c.run_single_state_lookup_reliably('Classical 98.1',ein,state)
  return r,run,sleep
 def test_ein_timeout_gets_one_outer_retry_and_keeps_original_evidence(self):
  failed={'status':'Unable to Verify','reason_code':'MI_EIN_TRANSPORT_TIMEOUT','success':False,'source_attempts':['EIN timed out'],'error':''}
  success={'status':'Not Registered','reason_code':'MI_COMPLETED_EIN_AND_NAME_SEARCH','success':True}
  r,run,sleep=self.lookup([failed,success])
  self.assertEqual(run.call_count,2);self.assertEqual(r['status'],'Not Registered');self.assertEqual(r['semantic_attempts'],2)
  self.assertEqual(r['mi_attempt_history'][0]['source_attempts'],['EIN timed out']);self.assertEqual(len(r['mi_attempt_history']),2)
  self.assertGreaterEqual(sleep.call_args.args[0],2);self.assertLess(sleep.call_args.args[0],5)
 def test_persistent_transport_timeout_is_bounded_and_inconclusive(self):
  failure={'status':'Unable to Verify','reason_code':'MI_EIN_TRANSPORT_TIMEOUT','success':False}
  r,run,_=self.lookup([failure,failure]);self.assertEqual(run.call_count,2);self.assertFalse(r['success']);self.assertEqual(r['status'],'Unable to Verify')
 def test_name_budget_failure_gets_recovery(self):
  failure={'status':'Unable to Verify','reason_code':'MI_NAME_SEARCH_INCOMPLETE','source_note':'The name-search time budget ended','success':False}
  r,run,_=self.lookup([failure,{'status':'Current','success':True}]);self.assertEqual(run.call_count,2);self.assertEqual(r['status'],'Current')
 def test_completed_and_unreadable_results_are_not_retried(self):
  for result in [{'status':'Not Registered','reason_code':'MI_COMPLETED_EIN_AND_NAME_SEARCH','success':True},{'status':'Pending','success':True},{'status':'Unable to Verify','reason_code':'STATE_RESPONSE_UNREADABLE','success':False},{'status':'Unable to Verify','reason_code':'MI_NAME_SEARCH_INCOMPLETE','source_note':'Unrecognized results page','success':False}]:
   with self.subTest(result=result):
    r,run,sleep=self.lookup([result]);self.assertEqual(run.call_count,1);sleep.assert_not_called()
 def test_other_state_retry_behavior_is_unchanged(self):
  r,run,sleep=self.lookup([{'status':'Site Not Reachable'},{'status':'Current'}],state='CO')
  self.assertEqual(run.call_count,2);sleep.assert_called_once_with(1);self.assertNotIn('mi_attempt_history',r)
 def test_progress_is_private_to_one_check_and_shared_only_with_its_retry(self):
  seen=[]
  def lookup(name,ein,state,**kwargs):
   progress=kwargs['mi_progress'];seen.append(progress)
   if progress.get('attempted'):return {'status':'Current','success':True}
   progress['attempted']=True
   return {'status':'Site Not Reachable','reason_code':'MI_NAME_SEARCH_INCOMPLETE','error':'timeout','success':False}
  with patch.object(c,'run_state_lookup',side_effect=lookup),patch.object(c,'SINGLE_STATE_SEMANTIC_RETRY_STATES',{'MI'}),patch.object(c,'SINGLE_STATE_SEMANTIC_RETRY_ATTEMPTS',2),patch.object(c.time,'sleep'):
   for _ in range(2):self.assertEqual(c.run_single_state_lookup_reliably('Example','12-3456789','MI')['status'],'Current')
  self.assertIs(seen[0],seen[1]);self.assertIs(seen[2],seen[3]);self.assertIsNot(seen[0],seen[2])
 def test_mi_batch_uses_same_recovery_without_abandoned_worker(self):
  with patch.object(c,'run_single_state_lookup_reliably',return_value={'status':'Current'}) as run,patch.object(c,'ThreadPoolExecutor',side_effect=AssertionError('No abandoned MI worker')):
   r=c.run_state_lookup_for_batch('Control','12-3456789','MI',False)
  run.assert_called_once_with('Control','12-3456789','MI');self.assertEqual(r['status'],'Current')
 def test_mi_fanout_can_enclose_both_attempts(self):
  response=MagicMock();response.__enter__.return_value=response;response.read.return_value=json.dumps({'results':[{'status':'Current'}]}).encode()
  with patch.object(c,'BATCH_FANOUT_API_URLS',['https://example.org/api/check']),patch.object(c.urllib.request,'urlopen',return_value=response) as request:
   for state,timeout in [('MI',230),('AK',115),('CO',c.BATCH_FANOUT_STATE_TIMEOUT_SECONDS)]:
    c.run_fanout_state_lookup_for_batch('Control','12-3456789',state);self.assertEqual(request.call_args.kwargs['timeout'],timeout)

class EinTiming(unittest.TestCase):
 def test_real_master_retry_reuses_only_completed_ein_no_results(self):
  for completed in [True,False]:
   ein_result=c.checker.StateResult('Example Relief','12-3456789','MI','Not Registered' if completed else 'Unable to Verify','https://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx')
   ein_result.success=completed;ein_result.raw_status_text='No results found' if completed else 'EIN timed out'
   ein_result.reason_code='NO_CANDIDATES_AFTER_COMPLETED_SEARCH' if completed else 'MI_EIN_TRANSPORT_TIMEOUT'
   failed=c.checker.StateResult('Example Relief','12-3456789','MI','Unable to Verify','')
   failed.success=False;failed.reason_code='MI_NAME_SEARCH_INCOMPLETE';failed.error='name search timeout'
   success=c.checker.StateResult('Example Relief','12-3456789','MI','Not Registered','')
   success.success=True;success.reason_code='MI_COMPLETED_EIN_AND_NAME_SEARCH'
   with ExitStack() as stack:
    for key,value in {'SINGLE_STATE_SEMANTIC_RETRY_STATES':{'MI'},'SINGLE_STATE_SEMANTIC_RETRY_ATTEMPTS':2,'CAPTURE_EVIDENCE_SCREENSHOTS':False,'CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT':False,'MI_CONFIRM_NO_RESULTS_FRAME':False,'MI_ENABLE_NAME_FALLBACK':True}.items():stack.enter_context(patch.object(c,key,value))
    stack.enter_context(patch.object(c.checker,'sync_playwright',return_value=MagicMock()))
    stack.enter_context(patch.object(c,'configure_browser_context'))
    stack.enter_context(patch.object(c,'registry_page_body',return_value=''))
    stack.enter_context(patch.object(c,'public_profile_for_ein',return_value={}))
    stack.enter_context(patch.object(c.time,'sleep'))
    stack.enter_context(patch.object(c,'response_data_for_lookup',side_effect=lambda r,*a:{'status':r.status,'success':r.success,'reason_code':r.reason_code,'error':r.error}))
    probe=stack.enter_context(patch.object(c,'search_mi_http_completion_probe',return_value=ein_result))
    names=stack.enter_context(patch.object(c,'search_mi_name_fallback',side_effect=[failed,success]))
    result=c.run_single_state_lookup_reliably('Example Relief','12-3456789','MI')
   self.assertEqual(probe.call_count,1 if completed else 2)
   self.assertEqual(names.call_count,2 if completed else 0)
   self.assertEqual(result['status'],'Not Registered' if completed else 'Unable to Verify')
 def probe(self,search_seconds,*,spent=0):
  clock=[float(spent)];timeouts=[]
  session=Mock()
  def request(url,**kwargs):
   delay=search_seconds if 'frmDefault' in url else .5
   timeouts.append(kwargs['timeout']);clock[0]+=min(delay,kwargs['timeout'])
   if delay>kwargs['timeout']:raise TimeoutError('Operation timed out')
   return SimpleNamespace(text='No results found' if 'frmDefault' in url else '<html>Search</html>',raise_for_status=lambda:None)
  session.get.side_effect=request;session.post.side_effect=request
  with patch.object(c,'curl_requests',SimpleNamespace(Session=Mock(return_value=session))),patch.object(c,'LOOKUP_SOFT_MAX_SECONDS',59),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c.time,'perf_counter',side_effect=lambda:clock[0]),patch.object(c.time,'sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
   r=c.search_mi_http_completion_probe(c.checker.Organization('Control','12-3456789'),lookup_deadline=c.MI_LOOKUP_MAX_SECONDS)
  return r,clock[0],timeouts
 def test_slow_twenty_second_ein_completes_without_retry(self):
  r,elapsed,timeouts=self.probe(20)
  self.assertTrue(r.success);self.assertEqual(r.source_attempts,[]);self.assertLess(elapsed,25);self.assertEqual(timeouts[-1],35)
 def test_setup_time_is_charged_and_name_time_reserved(self):
  r,elapsed,_=self.probe(40,spent=20)
  self.assertFalse(r.success);self.assertLessEqual(elapsed,55);self.assertGreaterEqual(c.MI_LOOKUP_MAX_SECONDS-elapsed,45)
 def test_no_remaining_source_budget_is_a_retryable_timeout(self):
  r,_,_=self.probe(20,spent=70)
  self.assertFalse(r.success);self.assertEqual(r.reason_code,'MI_EIN_TRANSPORT_TIMEOUT')

if __name__=='__main__':unittest.main()
