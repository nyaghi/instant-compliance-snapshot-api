"""Michigan transport recovery controls; synthetic responses, no registry traffic."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class Tests(unittest.TestCase):
 def probe(self, outcomes, elapsed=16, setup_elapsed=0):
  clock=[0.0]; sessions=[]; timeouts=[]
  def factory(**kw):
   session=Mock(); sessions.append(session)
   def response(text):return SimpleNamespace(text=text,raise_for_status=lambda:None)
   def request(url,**kw):
    timeout=kw['timeout'];timeouts.append(timeout)
    if 'frmDisclaimer' in url:
     clock[0]+=min(setup_elapsed,timeout)
     if setup_elapsed>=timeout:raise TimeoutError('Operation timed out')
     return response('<html>Search</html>')
    value=outcomes[min(len(sessions)-1,len(outcomes)-1)]
    if isinstance(value,Exception):
     clock[0]+=min(elapsed,timeout);raise value
    return response(value)
   session.get.side_effect=request;session.post.side_effect=request
   return session
  with patch.object(c,'curl_requests',SimpleNamespace(Session=factory)),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c.time,'sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
   result=c.search_mi_http_completion_probe(c.checker.Organization('Example Relief','123456789'))
  for session in sessions:session.close.assert_called_once()
  return result,sessions,clock[0],timeouts
 def test_third_attempt_recovers_completed_no_record(self):
  r,s,t,_=self.probe([TimeoutError('curl: (28) Operation timed out'),TimeoutError('Operation timed out'),'No results found'])
  self.assertEqual(c.public_status(r),'Not Registered');self.assertTrue(r.success);self.assertEqual(len(s),3);self.assertEqual(len(r.source_attempts),2);self.assertLessEqual(t,68)
 def test_current_pending_and_no_record_need_no_recovery(self):
  for text,expected in [('No results found','Not Registered'),('1 record(s) found<br>12345<br>Example Relief<br>12/31/2027','Current'),('1 record(s) found<br>12345<br>Example Relief<br>12/31/2026 Registration Pending','Pending')]:
   with self.subTest(expected=expected):
    r,s,_,_=self.probe([text]);self.assertEqual(c.public_status(r),expected);self.assertEqual(len(s),1)
 def test_persistent_timeout_is_inconclusive_and_explained(self):
  r,s,t,_=self.probe([TimeoutError('Operation timed out')],elapsed=24)
  self.assertEqual(len(s),3);self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success);self.assertEqual(r.reason_code,'MI_EIN_TRANSPORT_TIMEOUT');self.assertLessEqual(t,68)
  self.assertIn('timed out',c.comments_for_result_base(r,'',r.status));self.assertIn('does not establish',r.source_note)
 def test_budget_accounts_for_setup_requests(self):
  r,s,t,timeouts=self.probe([TimeoutError('Operation timed out')],setup_elapsed=9)
  self.assertLessEqual(t,68);self.assertLessEqual(len(s),3);self.assertTrue(all(0<v<=24 for v in timeouts));self.assertNotEqual(c.public_status(r),'Not Registered')
 def test_non_timeout_does_not_get_extra_attempt(self):
  r,s,_,_=self.probe([ValueError('HTTP 403')]);self.assertEqual(len(s),2);self.assertEqual(r.reason_code,'STATE_RESPONSE_UNREADABLE');self.assertFalse(r.success)
 def test_uninterpretable_response_is_not_retried_or_negative(self):
  r,s,_,_=self.probe(['<html>Incomplete search page</html>']);self.assertEqual(len(s),1);self.assertEqual(r.status,'Unable to Verify')
 def test_maintenance_is_not_negative(self):
  r,s,_,_=self.probe(['temporarily unavailable']);self.assertEqual(r.reason_code,'PORTAL_ERROR');self.assertFalse(r.success);self.assertEqual(len(s),1)

if __name__=='__main__':unittest.main()
