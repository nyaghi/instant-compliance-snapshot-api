import sys,unittest,time
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
class MaineBudgetTests(unittest.TestCase):
 def test_query_limit_is_read_from_live_form(self):
  name='Example Organization With A Long Legal Name'
  for limit in [30,40]:
   body=f'<input name="ctl00$scCompanyName" maxlength="{limit}" />'
   self.assertEqual(c.me_query_for_form(name,body),name[:limit])
  self.assertEqual(c.me_query_for_form(name,'<input name="scCompanyName" />'),name)
 def test_missing_search_field_does_not_produce_negative(self):
  with self.assertRaises(ValueError):c.me_query_for_form('Example Charity','Loading')
 def test_direct_search_sends_live_field_length(self):
  session=object.__new__(c.MaineRegistrySession);session.deadline=time.perf_counter()+30
  session.url='https://www.pfr.maine.gov/ALMSOnline/ALMSQuery/SearchCompany.aspx'
  session.form_html='<input type="hidden" name="__VIEWSTATE" value="state" /><input name="scCompanyName" maxlength="30" />'
  session.session=Mock();session.session.post.return_value.text='0 records found'
  name='Example Organization With A Long Legal Name'
  session.search(name)
  self.assertEqual(session.session.post.call_args.kwargs['data']['ctl00$ctl00$mainContent$mainContent$scCompanyName'],name[:30])
  self.assertEqual(session.form_html,'')
  session.session.get.return_value.text='<input type="hidden" name="__VIEWSTATE" value="fresh" /><input name="scCompanyName" maxlength="30" />'
  session.session.get.return_value.url=session.url
  session.search('Another Charity')
  session.session.get.assert_called_once()
  self.assertEqual(session.session.post.call_args.kwargs['data']['__VIEWSTATE'],'fresh')
 def test_browser_waits_for_category_postback_before_entering_name(self):
  from contextlib import contextmanager
  events=[];page=Mock();reg=Mock();company=Mock();radio=Mock();button=Mock()
  reg.input_value.return_value='';reg.get_attribute.return_value="setTimeout('__doPostBack()',0)"
  reg.select_option.side_effect=lambda *a,**k:events.append('category changed')
  company.fill.side_effect=lambda value,**k:events.append('name entered')
  company.input_value.return_value='Example Charity'
  page.content.return_value='<input name="scCompanyName" maxlength="30" />0 records found'
  page.locator.side_effect=lambda selector:reg if 'scRegulator' in selector else company if 'scCompanyName' in selector else button if 'btnSearch' in selector else radio
  @contextmanager
  def navigation(**kwargs):
   yield
   events.append('navigation completed')
  page.expect_navigation.side_effect=navigation
  c.me_browser_search_rows(page,'Example Charity',time.perf_counter()+30)
  self.assertLess(events.index('category changed'),events.index('navigation completed'))
  self.assertLess(events.index('navigation completed'),events.index('name entered'))
 def setUp(self):
  self.org=c.checker.Organization('Example Charity','123456789')
 def run_flow(self,direct,browser=None):
  session=Mock();session.search.side_effect=direct
  with patch.object(c,'MaineRegistrySession',return_value=session),patch.object(c,'me_fast_direct_query_variants',return_value=['Example Charity','Example Charity Inc']),patch.object(c,'me_browser_search_rows',side_effect=browser) as fallback:
   result=c.me_fast_direct_confirmation_result(self.org,page=Mock())
  return result,session,fallback
 def test_completed_queries_not_repeated(self):
  r,s,b=self.run_flow([([],Mock()),TimeoutError('slow')],[([],Mock())])
  self.assertEqual(c.public_status(r),'Not Registered')
  self.assertEqual(b.call_count,1);self.assertEqual(b.call_args.args[1],'Example Charity Inc')
  self.assertTrue(s.close.called)
 def test_unresolved_query_never_negative(self):
  r,s,b=self.run_flow([([],Mock()),TimeoutError('slow')],[TimeoutError('slow')])
  self.assertIsNone(r)
 def test_complete_direct_search_skips_browser(self):
  r,s,b=self.run_flow([([],Mock()),([],Mock())])
  self.assertEqual(c.public_status(r),'Not Registered');b.assert_not_called()
 def test_wrong_organization_is_not_accepted(self):
  row={'name':'Unrelated Foundation','status':'ACTIVE','number':'123','href':'ShowDetail.aspx?id=1'}
  r,s,b=self.run_flow([([row],Mock()),([],Mock())])
  self.assertEqual(c.public_status(r),'Not Registered')
 def test_registered_match_retains_expiration(self):
  row={'name':'Example Charity','status':'ACTIVE','number':'123','href':'ShowDetail.aspx?id=1'}
  opener=Mock();opener.open.return_value.read.return_value=b'Status: ACTIVE Expiration Date: 12/31/2027'
  r,s,b=self.run_flow([([row],opener)])
  self.assertIn('12/31/2027',r.raw_status_text);self.assertEqual(r.matched_registry_name,'Example Charity');b.assert_not_called()
 def test_parser_requires_explicit_empty_result(self):
  self.assertEqual(c.me_parse_search_rows('<p>0 records found</p>'),[])
  for body in ['Loading','Human verification','<html>Server Error</html>']:
   with self.assertRaises(ValueError):c.me_parse_search_rows(body)
 def test_expired_budget_starts_no_transport(self):
  with patch.object(c,'MaineRegistrySession') as session:
   self.assertIsNone(c.me_fast_direct_confirmation_result(self.org,page=Mock(),deadline=time.perf_counter()-1));session.assert_not_called()
 def test_begins_with_removes_only_covered_queries(self):
  queries=c.me_fast_direct_query_variants(c.checker.Organization('Young Life','840385934'))
  self.assertIn('Young Life',queries);self.assertIn('Young-Life',queries)
  self.assertIn('The Young Life',queries)
  self.assertNotIn('Young Life Inc',queries)
 def test_maine_does_not_restart_entire_budget_on_failure(self):
  with patch.object(c,'run_state_lookup',return_value={'state':'ME','status':'Site Not Reachable'} ) as run:
   result=c.run_single_state_lookup_reliably('Example Charity','123456789','ME')
  self.assertEqual(run.call_count,1);self.assertEqual(result['semantic_attempts'],1)
 def test_reviewed_suffix_is_covered_by_maine_prefix(self):
  with patch.object(c,'known_names_for_ein',return_value=['Example Charity Foundation']):
   queries=c.me_fast_direct_query_variants(self.org)
  self.assertIn('Example Charity',queries)
  self.assertNotIn('Example Charity Foundation',queries)
 def test_care_of_contact_is_not_an_alias_search(self):
  with patch.object(c,'known_names_for_ein',return_value=['Example Charity C/O Corporate Agent Inc']):
   queries=c.me_fast_direct_query_variants(self.org)
  self.assertIn('Example Charity',queries)
  self.assertFalse(any('corporate agent' in x.lower() for x in queries))
 def test_distinct_reviewed_former_name_is_retained(self):
  with patch.object(c,'known_names_for_ein',return_value=['Historic Support Trust']):
   queries=c.me_fast_direct_query_variants(self.org)
  self.assertIn('Historic Support Trust',queries)
 def test_contact_text_that_is_independently_reviewed_is_preserved(self):
  with patch.object(c,'known_names_for_ein',return_value=['Example Charity C/O Corporate Agent Inc','Corporate Agent Inc']):
   queries=c.me_fast_direct_query_variants(self.org)
  self.assertTrue(any('corporate agent' in x.lower() and not x.lower().startswith('example') for x in queries))
 def test_punctuation_with_different_search_prefix_is_retained(self):
  queries=c.me_fast_direct_query_variants(c.checker.Organization('Young Life','840385934'))
  self.assertIn('Young Life',queries);self.assertIn('Young-Life',queries)
 def test_lock_contention_is_not_negative(self):
  lock=Mock();lock.acquire.return_value=False
  with patch.object(c,'ME_LOOKUP_LOCK',lock):r=c.search_me_serialized(Mock(),self.org)
  self.assertEqual(c.public_status(r),'Site Not Reachable');lock.release.assert_not_called()
  self.assertGreater(lock.acquire.call_args.kwargs['timeout'],70)
if __name__=='__main__':unittest.main()
