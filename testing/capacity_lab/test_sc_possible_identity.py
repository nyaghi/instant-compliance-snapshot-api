"""A possible SC name cannot become a definitive status without EIN proof."""
import ast
import subprocess
from pathlib import Path
from unittest.mock import Mock,patch
import unittest
import registry_snapshot_server as c

class SouthCarolinaIdentityTests(unittest.TestCase):
 def run_lookup(self,candidate,proof,name='National Low Income Housing Coalition',aliases=()):
  org=c.checker.Organization(name,'521089824'); session=Mock()
  session.get.return_value.text='<form></form>'
  def post(url,data,**kwargs):
   return Mock(text=('Public Id P1234 Status Registered Due Date 11/15/2026' if 'ctl00$MainContent$Hidden_CharityID' in data else f'<a href="javascript:CharityInfo(1234)">{candidate}</a>'))
  session.post.side_effect=post
  token=c.REVIEWED_NAME_CONTEXT.set({'521089824':aliases})
  try:
   with patch.object(c,'curl_requests',Mock(Session=Mock(return_value=session))),patch.object(c,'build_search_queries',return_value=[name]),patch.object(c,'sc_detail_filing_ein',return_value=proof) as filing:
    result=c.sc_official_detail_lookup(org)
   return result,filing,org
  finally:c.REVIEWED_NAME_CONTEXT.reset(token)
 def test_local_similar_name_cannot_supply_national_status(self):
  for proof in ('','999999999'):
   with self.subTest(proof=proof):
    r,filing,_=self.run_lookup('SC Low Income Housing Coalition',proof)
    self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)
    self.assertFalse(r.matched_registry_identifier);filing.assert_called_once()
    with patch.object(c,'sc_official_detail_lookup',return_value=r),patch.object(c,'search_with_name_variants') as fallback:
     self.assertIs(c.search_sc_resilient(Mock(),c.checker.Organization('National Low Income Housing Coalition','521089824')),r)
     fallback.assert_not_called()
 def test_same_ein_filing_can_confirm_possible_name(self):
  r,filing,org=self.run_lookup('SC Low Income Housing Coalition','521089824')
  self.assertTrue(r.success);self.assertEqual(r.verified_registry_ein,org.ein)
  self.assertEqual(r.matched_registry_identifier,'P1234')
  trace=c.debug_trace_for_result(r,org,'SC',r.status)
  self.assertEqual(trace['identity_anchor'],'EIN');self.assertEqual(trace['accepted_candidate']['reason'],'MATCH_EIN_EXACT')
 def test_exact_name_does_not_fetch_an_unneeded_filing(self):
  r,filing,_=self.run_lookup('National Low Income Housing Coalition','')
  self.assertTrue(r.success);filing.assert_not_called()
 def test_reviewed_alias_does_not_fetch_an_unneeded_filing(self):
  alias='National Low Income Housing Coalition and Low Income Housing'
  r,filing,_=self.run_lookup(alias,'',aliases=(alias,))
  self.assertTrue(r.success);filing.assert_not_called()
 def test_only_sc_identity_and_its_diagnostics_changed(self):
  root=Path(__file__).resolve().parents[2]
  before=ast.parse(subprocess.check_output(['git','show','ed83811:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
  after=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
  from testing.capacity_lab.sc_identity_scope import restore_sc_identity_guard
  restore_sc_identity_guard(after)
  self.assertEqual(ast.dump(before),ast.dump(after))

if __name__=='__main__':unittest.main()
