import sys,unittest,time
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
class MaineBudgetTests(unittest.TestCase):
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
 def test_lock_contention_is_not_negative(self):
  lock=Mock();lock.acquire.return_value=False
  with patch.object(c,'ME_LOOKUP_LOCK',lock):r=c.search_me_serialized(Mock(),self.org)
  self.assertEqual(c.public_status(r),'Site Not Reachable');lock.release.assert_not_called()
  self.assertGreater(lock.acquire.call_args.kwargs['timeout'],70)
if __name__=='__main__':unittest.main()
