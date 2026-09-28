"""Explicit source errors are not negatives; recovery has one fenced attempt."""
import ast,os,subprocess,unittest,time
from pathlib import Path
from unittest.mock import Mock,patch
import registry_snapshot_server as m
from deployment.durable_queue import source_application_retry
from testing.capacity_lab.test_durable_queue import DurableTests,payload,VERSION

ENV={'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com','CE_LAB_ME_APPLICATION_RECOVERY':'1'}
ERROR='<html><title>ALMS License Information : Error</title><p>An error has been encountered while processing your request. Please try again at a later time.</p></html>'

class SourceError(unittest.TestCase):
 def setUp(self):
  p=patch.dict(os.environ,ENV);p.start();self.addCleanup(p.stop)
  p=patch.object(m,'APP_VERSION','fixture-performance-lab');p.start();self.addCleanup(p.stop)
  t=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,t)
 def test_exact_official_error_has_distinct_type_and_zero_is_unchanged(self):
  with self.assertRaises(m.MainePublicApplicationError):m.me_parse_search_rows(ERROR)
  self.assertEqual(m.me_parse_search_rows('<html>0 records found</html>'),[])
  for body in ['<html>Loading</html>','<html>Access denied</html>','<html>Too many requests</html>','<html>Verify you are human</html>',ERROR.replace('ALMS License Information : Error','Different page')]:
   with self.assertRaises(ValueError) as caught:m.me_parse_search_rows(body)
   self.assertNotIsInstance(caught.exception,m.MainePublicApplicationError)
 def test_nonlab_standard_or_flag_off_preserves_original_exception(self):
  for version,host,mode,flag in [('fixture','https://staging.compliance-express.com','sales','1'),('fixture-performance-lab',ENV['PUBLIC_BASE_URL'],'standard','1'),('fixture-performance-lab',ENV['PUBLIC_BASE_URL'],'sales','0')]:
   with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':host,'CE_LAB_ME_APPLICATION_RECOVERY':flag}):
    t=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
    try:
     with self.assertRaises(ValueError) as caught:m.me_parse_search_rows(ERROR)
     self.assertNotIsInstance(caught.exception,m.MainePublicApplicationError)
    finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(t)
 def test_error_stops_name_variants_closes_session_and_preserves_attempt(self):
  org=m.checker.Organization('Example Relief','123456789');org._cc_me_progress={}
  session=Mock();session.search.side_effect=m.MainePublicApplicationError('official error')
  with patch.object(m,'MaineRegistrySession',return_value=session),patch.object(m,'me_browser_search_rows') as browser:
   result=m.me_fast_direct_confirmation_result(org,page=Mock())
  self.assertFalse(result.success);self.assertEqual(result.reason_code,'ME_SOURCE_APPLICATION_ERROR')
  self.assertEqual(session.search.call_count,1);session.close.assert_called_once();browser.assert_not_called()
  attempts=org._cc_me_progress['source_attempts'];self.assertEqual(len(attempts),1);self.assertFalse(attempts[0]['complete'])
 def test_no_nested_semantic_retry_or_sleep_after_application_error(self):
  result={'status':'Site Not Reachable','success':False,'reason_code':'ME_SOURCE_APPLICATION_ERROR'}
  with patch.object(m,'run_me_lookup_with_lane',return_value=result) as run,patch.object(m.time,'sleep') as sleep:
   actual=m.run_single_state_lookup_reliably('Example Relief','123456789','ME')
  run.assert_called_once();sleep.assert_not_called();self.assertEqual(actual['semantic_attempts'],1)
 def test_retry_requires_exact_signal_mode_scope_remaining_time_and_first_attempt(self):
  j={'source_version':VERSION,'mode':'sales','state':'ME','attempt':1,'stop_reason':None,'deadline':160}
  r={'status':'Site Not Reachable','success':False,'reason_code':'ME_SOURCE_APPLICATION_ERROR'}
  self.assertEqual(source_application_retry(j,r,None,100,'worker')['not_before'],108)
  for changes in [{'mode':'standard'},{'state':'CA'},{'attempt':2},{'stop_reason':'canceled'},{'deadline':123},{'source_version':'production'}]:
   self.assertIsNone(source_application_retry({**j,**changes},r,None,100,'worker'))
  for changes in [{'success':True},{'status':'Not Registered'},{'reason_code':'ME_SEARCH_INCOMPLETE'},{'reason_code':'RATE_LIMITED'},{'reason_code':'HUMAN_VERIFICATION'}]:
   self.assertIsNone(source_application_retry(j,{**r,**changes},None,100,'worker'))
  self.assertIsNone(source_application_retry(j,r,'WORKFLOW_DEADLINE',100,'worker'))
 def test_master_changes_are_confined_to_error_detection_and_recovery_exit(self):
  root=Path(m.__file__).parent;old=ast.parse(subprocess.check_output(['git','show','4b6afa0:registry_snapshot_server.py'],cwd=root).decode());new=ast.parse((root/'registry_snapshot_server.py').read_text())
  changed={'me_parse_search_rows','me_fast_direct_confirmation_result','run_single_state_lookup_reliably'}
  added={'MainePublicApplicationError','lab_me_application_recovery_enabled'}
  a=[x for x in old.body if getattr(x,'name','') not in changed]
  z=[x for x in new.body if getattr(x,'name','') not in changed|added]
  self.assertEqual(ast.dump(ast.Module(body=a,type_ignores=[])),ast.dump(ast.Module(body=z,type_ignores=[])))

@unittest.skipUnless(os.environ.get('CE_TEST_DATABASE_URL'),'Real lab Postgres required')
class RecoveryDB(unittest.TestCase):
 # Reuse fixture setup only; do not accidentally inherit every legacy test.
 setUp=DurableTests.setUp;tearDown=DurableTests.tearDown;worker=DurableTests.worker;submit=DurableTests.submit;second=DurableTests.second;finish=DurableTests.finish
 def configure(self):
  p=patch.dict(os.environ,ENV);p.start();self.addCleanup(p.stop)
 def source_error(self,j):
  return {'ein':j['payload']['ein'],'state':'ME','app_version':VERSION,'status':'Site Not Reachable','success':False,'reason_code':'ME_SOURCE_APPLICATION_ERROR','source_note':'Official public application error','source_attempts':[{'complete':False,'stage':'source application error'}]}
 def setup_job(self,mode='sales',other=True):
  self.configure();a=self.worker();b=self.worker() if other else None
  ident=self.submit(payload(states=['ME'],mode=mode));j=self.q.claim(a);self.assertIsNotNone(j)
  return ident,a,b,j
 def release_delay(self,job):
  with self.q.transaction() as (c,now):
   c.execute("UPDATE cc_lab_jobs SET result=jsonb_set(result,'{lab_source_retry,not_before}',to_jsonb(%s::double precision)) WHERE id=%s",(now-1,job))
 def test_delayed_different_worker_same_deadline_and_fresh_result(self):
  ident,a,b,j=self.setup_job();before=self.q.status('a',ident);failure=self.source_error(j)
  self.assertTrue(self.q.complete(a,j['id'],j['token'],failure))
  pending=self.q.status('a',ident);self.assertEqual(pending['completed'],0);self.assertEqual(pending['deadline'],before['deadline'])
  self.assertIsNone(self.q.claim(a));self.assertIsNone(self.q.claim(b))
  self.release_delay(j['id']);self.assertIsNone(self.q.claim(a));retry=self.q.claim(b);self.assertEqual(retry['id'],j['id']);self.assertEqual(retry['attempt'],2);self.assertNotEqual(retry['token'],j['token'])
  self.assertFalse(self.q.complete(a,j['id'],j['token'],failure))
  success={**failure,'status':'Current','success':True,'reason_code':'MATCH_NAME_EXACT','matched_registry_identifier':'CO123'}
  self.assertTrue(self.q.complete(b,j['id'],retry['token'],success));end=self.q.status('a',ident)
  self.assertEqual(end['completed'],1);self.assertEqual(end['deadline'],before['deadline'])
  r=end['jobs'][0]['result'];self.assertTrue(r['success']);self.assertTrue(r['lab_source_recovery']['recovered']);self.assertEqual(r['lab_source_recovery']['first_attempt']['reason_code'],'ME_SOURCE_APPLICATION_ERROR')
  with self.q.transaction() as (c,now):self.assertEqual(c.execute("SELECT count(*) AS n FROM cc_lab_events WHERE workflow_id=%s AND event='source_application_retry'",(ident,)).fetchone()['n'],1)
 def test_second_failure_finishes_conservatively_without_third_attempt(self):
  ident,a,b,j=self.setup_job();self.q.complete(a,j['id'],j['token'],self.source_error(j));self.release_delay(j['id']);retry=self.q.claim(b)
  self.q.complete(b,retry['id'],retry['token'],self.source_error(retry));r=self.q.status('a',ident)
  self.assertEqual(r['completed'],1);self.assertFalse(r['jobs'][0]['result']['success']);self.assertEqual(r['jobs'][0]['attempt'],2)
  self.assertIsNone(self.q.claim(a));self.assertIsNone(self.q.claim(b))
 def test_cancel_waiting_recovery_prevents_fresh_dispatch(self):
  ident,a,b,j=self.setup_job();self.q.complete(a,j['id'],j['token'],self.source_error(j));self.q.cancel('a',ident);self.release_delay(j['id'])
  self.assertIsNone(self.q.claim(b));r=self.q.status('a',ident);self.assertEqual(r['phase'],'canceled');self.assertEqual(r['jobs'][0]['error'],'WORKFLOW_CANCELED')
 def test_deadline_waiting_recovery_never_resets(self):
  ident,a,b,j=self.setup_job();self.q.complete(a,j['id'],j['token'],self.source_error(j))
  with self.q.transaction() as (c,now):c.execute('UPDATE cc_lab_workflows SET deadline=%s WHERE id=%s',(now-1,ident))
  self.assertIsNone(self.q.claim(b));r=self.q.status('a',ident);self.assertEqual(r['phase'],'expired');self.assertEqual(r['jobs'][0]['error'],'WORKFLOW_DEADLINE')
 def test_standard_no_other_worker_or_insufficient_time_never_requeues(self):
  for mode,other,remaining in [('standard',True,50),('sales',False,50),('sales',True,20)]:
   with self.subTest(mode=mode,other=other,remaining=remaining):
    # Separate fixture schema for the sole-worker case.
    if mode=='sales' and not other:
     with self.q.transaction() as (c,now):c.execute('UPDATE cc_lab_workers SET retired=true')
    ident,a,b,j=self.setup_job(mode,other)
    with self.q.transaction() as (c,now):c.execute('UPDATE cc_lab_workflows SET deadline=%s WHERE id=%s',(now+remaining,ident))
    self.q.complete(a,j['id'],j['token'],self.source_error(j));self.assertEqual(self.q.status('a',ident)['completed'],1)
 def test_wrong_identity_rolls_back_and_keeps_original_reservation(self):
  ident,a,b,j=self.setup_job();bad={**self.source_error(j),'ein':'987654321'}
  with self.assertRaises(ValueError):self.q.complete(a,j['id'],j['token'],bad)
  self.assertEqual(self.q.status('a',ident)['jobs'][0]['phase'],'running')
 def test_other_state_can_run_while_source_retry_waits(self):
  ident,a,b,j=self.setup_job();self.q.complete(a,j['id'],j['token'],self.source_error(j));other=self.submit(payload(ein='987654321',states=['CA'],mode='standard'))
  x=self.q.claim(a);self.assertEqual(x['state'],'CA');self.assertEqual(x['workflow_id'],other);self.finish(x)

if __name__=='__main__':unittest.main(verbosity=2)

