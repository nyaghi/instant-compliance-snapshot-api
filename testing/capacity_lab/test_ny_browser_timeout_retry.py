"""The real Playwright exception must enter NY's existing bounded retry policy."""
import unittest
from unittest.mock import Mock,patch
import registry_snapshot_server as c
from testing.run_ny_retrieval_guardrails import ROW,DETAIL,response,AsOfDate

class NewYorkBrowserTimeout(unittest.TestCase):
    def invoke(self,answers):
        org=c.checker.Organization('Example National Foundation','123456789')
        with patch.object(c,'ny_browser_registry_response',side_effect=answers) as transport,patch.object(c.time,'sleep'),patch.object(c,'date',AsOfDate):
            r=c.search_ny_direct(org,browser_page=Mock())
        return r,transport

    def test_actual_browser_timeout_is_not_python_timeout(self):
        self.assertNotIsInstance(c.checker.PlaywrightTimeoutError('timeout'),TimeoutError)

    def test_browser_detail_timeout_retries_same_record_once(self):
        r,t=self.invoke([response([ROW]),c.checker.PlaywrightTimeoutError('detail timeout'),response(DETAIL)])
        self.assertTrue(r.success);self.assertEqual(c.public_status(r),'Current')
        self.assertEqual(t.call_count,3)
        self.assertEqual(t.call_args_list[1].args[1:3],t.call_args_list[2].args[1:3])
        self.assertTrue(any('retrying transient' in a for a in r.source_attempts))

    def test_persistent_timeout_never_becomes_negative(self):
        r,t=self.invoke([response([ROW]),c.checker.PlaywrightTimeoutError('timeout'),c.checker.PlaywrightTimeoutError('timeout')])
        self.assertFalse(r.success);self.assertNotEqual(c.public_status(r),'Not Registered');self.assertEqual(t.call_count,3)

    def test_one_retry_is_shared_between_search_and_detail(self):
        r,t=self.invoke([c.checker.PlaywrightTimeoutError('search'),response([ROW]),c.checker.PlaywrightTimeoutError('detail')])
        self.assertFalse(r.success);self.assertEqual(t.call_count,3)

    def test_wrong_detail_identity_is_never_retried(self):
        r,t=self.invoke([response([ROW]),response({**DETAIL,'ein':'987654321'})])
        self.assertFalse(r.success);self.assertEqual(t.call_count,2)

    def test_no_retry_without_remaining_lookup_budget(self):
        clock=[0.0]
        def slow(*args):clock[0]=34;raise c.checker.PlaywrightTimeoutError('slow')
        with patch.object(c.time,'perf_counter',side_effect=lambda:clock[0]):r,t=self.invoke(slow)
        self.assertFalse(r.success);self.assertEqual(t.call_count,1)

if __name__=='__main__':unittest.main(verbosity=2)
