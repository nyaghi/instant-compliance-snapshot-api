"""Actual overlength Arkansas spellings; unchanged identity and completion guards."""
import unittest
from unittest.mock import patch
import registry_snapshot_server as c
from testing.run_ar_completion_guardrails import ArkansasCompletionTests
NAME='Stonestreet-Rone Post No 1983 Veterans of Foreign Wars of the United States'
ALIASES=['1983 Stonestreet-rone Post']
class LongQueries(ArkansasCompletionTests):
 def test_actual_long_name_completes_only_explicit_empty_queries(self):
  r,qs=self.lookup(name=NAME,aliases=ALIASES)
  self.assertTrue(r.success);self.assertEqual(c.public_status(r),'Not Registered')
  self.assertTrue(all(len(q)<=50 for q in qs),qs)
  self.assertEqual(len(qs),len(set(qs)))
 def test_long_generated_prefix_never_becomes_identity(self):
  q='Stonestreet Rone Post No 1983 Veteran of Foreign'
  row={'name':q+' Relief Fund','status':'Current','type':'Charity'}
  r,qs=self.lookup({q:{'body':'Back to Search Form Registration Date','rows':[row]}},name=NAME,aliases=ALIASES)
  self.assertNotEqual(r.status,'Current');self.assertFalse(r.matched_registry_name)
 def test_incomplete_generated_prefix_still_blocks_negative(self):
  q='Stonestreet Rone Post No 1983 Veteran of Foreign'
  r,qs=self.lookup({q:{'body':'Back to Search Form Registration Date'}},name=NAME,aliases=ALIASES)
  self.assertIn(q,qs);self.assertFalse(r.success);self.assertEqual(r.status,'Unable to Verify')
if __name__=='__main__':unittest.main()
