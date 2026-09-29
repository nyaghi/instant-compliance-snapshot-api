"""Complete zero queries can avoid duplicate browser work; nothing else can."""
import ast,json,os,subprocess,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import registry_snapshot_server as m
URL='https://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx'
RESULT='https://www.ag.state.mi.us/CharitableTrust/frmSearchResults.aspx'
FORM='<html><input type="hidden" name="__VIEWSTATE" value="test"><input id="ctl00_MainContent_txtName"><input id="ctl00_MainContent_txtEIN"><input id="ctl00_MainContent_btnTextSearch"></html>'
def body(q='Example Relief',count='0'):
 return f'<html>Results for the following input: Organization Type: Charity or Public Safety Organization Name Includes: {q} (All words); {count} record(s) found No records found for your search criteria</html>'
class Names(unittest.TestCase):
 def setUp(self):
  self.org=SimpleNamespace(organization_name='Example Relief',ein='123456789')
 def response(self,source,url):
  r=MagicMock();r.status_code=200;r.url=url;r.history=[];r.iter_content.return_value=[source.encode()];return r
 def run_source(self,source,queries=None,form=FORM):
  s=MagicMock();s.request.side_effect=[self.response(form,URL),self.response(source,RESULT)]
  with patch.object(m,'mi_name_fallback_queries',return_value=queries or ['Example Relief']):
   found=m.mi_name_http_empty_queries(s,self.org,{},time.perf_counter()+30)
  return found,s
 def test_completed_echoed_zero_only_and_same_query_fields(self):
  found,s=self.run_source(body());self.assertEqual(found,['Example Relief'])
  fields=s.request.call_args_list[1].kwargs['data']
  self.assertEqual(fields['ctl00$MainContent$txtName'],'Example Relief');self.assertEqual(fields['ctl00$MainContent$txtEIN'],'')
  self.assertEqual(fields['ctl00$MainContent$ddlName2'],'All words')
  for c in s.request.call_args_list:self.assertTrue(c.kwargs['verify']);self.assertLessEqual(c.kwargs['timeout'],4 if c.args[0]=='GET' else 18)
 def test_slow_complete_body_can_finish_without_resetting_total_deadline(self):
  for elapsed,want in [(14,['Example Relief']),(24,[])]:
   clock=[100.0];s=MagicMock()
   def request(method,*args,**kwargs):
    if method=='GET':return self.response(FORM,URL)
    self.assertEqual(kwargs['timeout'],18.0)
    clock[0]+=elapsed
    return self.response(body(),RESULT)
   s.request.side_effect=request
   with patch.object(m.time,'monotonic',side_effect=lambda:clock[0]),patch.object(m.time,'perf_counter',return_value=100.0),patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):
    self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},130.0),want)
 def test_request_allowance_cannot_extend_remaining_lookup_budget(self):
  with patch.object(m.time,'monotonic',return_value=100.0),patch.object(m.time,'perf_counter',return_value=100.0):
   found,s=self.run_source(body())
  self.assertEqual(found,['Example Relief'])
  session=MagicMock();session.request.return_value=self.response(FORM,URL)
  with patch.object(m.time,'monotonic',return_value=100.0),patch.object(m.time,'perf_counter',return_value=100.0),patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):
   m.mi_name_http_empty_queries(session,self.org,{},103.0)
  self.assertTrue(all(c.kwargs['timeout']<=3 for c in session.request.call_args_list))
 def test_partial_wrong_query_positive_ambiguous_blocked_do_not_complete(self):
  for source in [body()[:-7],body('Another Relief'),body(count='1'),body()+body(),body().replace('0 record(s)','0 record'),body().replace('All words','Any word'),body().replace('No records found for your search criteria',''),body().replace('</html>',' CAPTCHA</html>'),body().replace('</html>',' EIN: 98-7654321</html>')]:
   with self.subTest(source=source):self.assertEqual(self.run_source(source)[0],[])
 def test_incomplete_form_does_not_submit(self):
  found,s=self.run_source(body(),form='<html>Unavailable</html>');self.assertEqual(found,[]);self.assertEqual(s.request.call_count,1)
 def test_failed_transport_cannot_be_a_negative(self):
  for exc in [TimeoutError(),m.ssl.SSLCertVerificationError(),ValueError('bad response')]:
   s=MagicMock();s.request.side_effect=exc
   with patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},time.perf_counter()+30),[])
 def test_bad_status_redirect_or_oversize_cannot_complete(self):
  for kind in ['status','redirect','history','oversize']:
   first=self.response(FORM,URL);second=self.response(body(),RESULT)
   if kind=='status':second.status_code=500
   if kind=='redirect':second.url='https://example.com/'
   if kind=='history':second.history=[SimpleNamespace(url='http://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx')]
   if kind=='oversize':second.iter_content.return_value=[b'x'*1_000_001]
   s=MagicMock();s.request.side_effect=[first,second]
   with patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},time.perf_counter()+30),[])
   self.assertTrue(second.close.called)
 def test_expired_budget_sends_no_requests(self):
  s=MagicMock()
  with patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},time.perf_counter()-1),[])
  s.request.assert_not_called()
 def test_distinct_alias_is_probed_but_positive_stays_for_browser_confirmation(self):
  s=MagicMock();s.request.side_effect=[self.response(FORM,URL),self.response(body(),RESULT),self.response(FORM,URL),self.response(body('Community Help','1'),RESULT)]
  with patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief','The Example Relief','Community Help']):
   self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},time.perf_counter()+30),['Example Relief'])
  self.assertEqual(s.request.call_count,4)
 def test_all_words_zero_covers_only_narrower_joined_query(self):
  for old,query in [('Example Relief','Example-Relief'),('Example Relief Fund','The Example-Relief Fund'),('EXAMPLE RELIEF','example-relief')]:
   self.assertTrue(m.mi_completed_query_covers(old,query))
  for old,query in [('Example-Relief','Example Relief'),('Example Relief','Different Relief'),('Example Relief Inc.','Example Relief'),('','Example Relief')]:
   self.assertFalse(m.mi_completed_query_covers(old,query))
 def test_completed_zero_does_not_issue_generated_hyphen_queries(self):
  found,s=self.run_source(body(),queries=['Example Relief','Example-Relief','The Example-Relief'])
  self.assertEqual(found,['Example Relief']);self.assertEqual(s.request.call_count,2)
 def test_distinct_alias_zero_is_completed_without_restarting_browser(self):
  s=MagicMock();s.request.side_effect=[self.response(FORM,URL),self.response(body(),RESULT),self.response(FORM,URL),self.response(body('Community Help'),RESULT)]
  with patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief','Community Help']):
   self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},time.perf_counter()+30),['Example Relief','Community Help'])
  self.assertEqual(s.request.call_count,4)
 def test_joined_query_coverage_requires_lab_opt_in_and_same_identity(self):
  for enabled,identity,skip in [(True,('Example Relief','123456789'),True),(False,('Example Relief','123456789'),False),(True,('Other','123456789'),False)]:
   page=MagicMock();page._cc_mi_lookup_deadline=time.perf_counter()+30
   page._cc_mi_search_progress={'identity':identity,'completed_empty_name_queries':['Example Relief']}
   module=MagicMock();module.MI_SEARCH_URL=URL;module.open_search_form.return_value=False
   with patch.object(m,'mi_http_names_enabled',return_value=enabled),patch.object(m,'state_extension_module',return_value=module),patch.object(m,'patch_mi_module_for_fast_lookups'),patch.object(m,'mi_action_timeout',side_effect=TimeoutError()),patch.object(m,'mi_name_fallback_queries',return_value=['Example-Relief']):
    result=m.search_mi_name_fallback(page,self.org)
   self.assertEqual(result.success,skip)
   self.assertEqual(module.open_search_form.called,not skip)
 def test_completed_progress_uses_existing_negative_rule_without_browser(self):
  page=MagicMock();page._cc_mi_search_progress={'identity':('Example Relief','123456789'),'completed_empty_name_queries':['Example Relief']}
  page._cc_mi_lookup_deadline=time.perf_counter()+30
  module=MagicMock();module.MI_SEARCH_URL=URL
  with patch.object(m,'state_extension_module',return_value=module),patch.object(m,'patch_mi_module_for_fast_lookups'),patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief','The Example Relief']):
   result=m.search_mi_name_fallback(page,self.org)
  self.assertTrue(result.success);self.assertEqual(m.public_status(result),'Not Registered');module.open_search_form.assert_not_called()
 def test_wrong_identity_progress_cannot_skip_the_browser(self):
  page=MagicMock();page._cc_mi_search_progress={'identity':('Other','999999999'),'completed_empty_name_queries':['Example Relief']};page._cc_mi_lookup_deadline=time.perf_counter()+30
  module=MagicMock();module.MI_SEARCH_URL=URL;module.open_search_form.return_value=False
  with patch.object(m,'state_extension_module',return_value=module),patch.object(m,'patch_mi_module_for_fast_lookups'),patch.object(m,'mi_action_timeout',side_effect=TimeoutError()),patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief']):result=m.search_mi_name_fallback(page,self.org)
  self.assertFalse(result.success);self.assertNotEqual(result.status,'Not Registered');module.open_search_form.assert_called()
 def test_exact_lab_opt_in_and_evidence_mode(self):
  for version,origin,flag,want in [('v-performance-lab','https://instant-compliance-snapshot-api-hn4v.onrender.com','1',True),('v','https://instant-compliance-snapshot-api-hn4v.onrender.com','1',False),('v-performance-lab','https://staging.compliance-express.com','1',False),('v-performance-lab','https://instant-compliance-snapshot-api-hn4v.onrender.com','0',False)]:
   with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':origin,'CE_LAB_MI_NAME_HTTP':flag}),patch.object(m,'CAPTURE_EVIDENCE_SCREENSHOTS',False),patch.object(m,'CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT',False):self.assertEqual(m.mi_http_names_enabled(self.org),want)
  self.org.evidence_mode=True;self.assertFalse(m.mi_http_names_enabled(self.org))
 def test_ein_probe_reuses_its_session_only_after_completed_empty_ein(self):
  session=MagicMock();response=MagicMock();response.text='0 record(s) found No records found'
  session.get.return_value=response;session.post.return_value=response
  with patch.object(m.curl_requests,'Session',return_value=session),patch.object(m,'mi_http_names_enabled',return_value=True),patch.object(m,'mi_name_http_empty_queries',return_value=['Example Relief']) as names:
   result=m.search_mi_http_completion_probe(self.org,time.perf_counter()+100)
  self.assertTrue(result.success);self.assertEqual(result._cc_mi_completed_empty_names,['Example Relief']);self.assertEqual(names.call_args.args[0],session);session.close.assert_called_once()
 def test_ein_positive_never_runs_the_name_probe(self):
  session=MagicMock();response=MagicMock();response.text='1 record(s) found Results for the following input: No interpretable detail'
  session.get.return_value=response;session.post.return_value=response
  with patch.object(m.curl_requests,'Session',return_value=session),patch.object(m,'mi_http_names_enabled',return_value=True),patch.object(m,'mi_name_http_empty_queries') as names:
   m.search_mi_http_completion_probe(self.org,time.perf_counter()+100)
  names.assert_not_called();session.close.assert_called_once()
 def test_query_plan_and_entire_remaining_master_unchanged(self):
  from testing.capacity_lab.parsing_scope import strip_mi_name_transport
  root=Path(m.__file__).parent;old=ast.parse(subprocess.check_output(['git','show','e57e4c7:registry_snapshot_server.py'],cwd=root).decode())
  new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_mi_name_transport(new)
  self.assertEqual(ast.dump(old),ast.dump(new))
if __name__=='__main__':unittest.main()
