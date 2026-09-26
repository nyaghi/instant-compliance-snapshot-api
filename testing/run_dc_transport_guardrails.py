"""Bounded DC timeout recovery without changing RI transport or source truth."""
import sys, time, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc
from run_dc_ri_guardrails import LicenseControls

class TransportControls(unittest.TestCase):
    def test_dc_two_timeouts_can_recover_on_third_read_with_existing_deadline(self):
        deadline=time.monotonic()+75
        with patch.object(cc,'identity_fetch',side_effect=[TimeoutError('read'),TimeoutError('read'),b'{"features":[]}']) as fetch,patch.object(cc.time,'sleep') as sleep,patch.object(cc,'log_event') as log:
            self.assertEqual(cc.registry_json_request(cc.DC_LICENSE_API,deadline),{'features':[]})
            self.assertEqual([c.kwargs['request_timeout'] for c in fetch.call_args_list],[15,20,25])
            self.assertTrue(all(c.args[1]==deadline for c in fetch.call_args_list))
            self.assertEqual(sleep.call_count,2)
            self.assertIn('recovered on attempt 3',log.call_args.args[0])
    def test_ri_retains_exactly_one_retry(self):
        with patch.object(cc,'identity_fetch',side_effect=TimeoutError('read')) as fetch:
            with self.assertRaises(TimeoutError):cc.registry_json_request(cc.RI_PUBLIC_SEARCH_API,time.monotonic()+75)
            self.assertEqual(fetch.call_count,2)
            self.assertTrue(all(c.kwargs['request_timeout']==15 for c in fetch.call_args_list))
    def test_dc_failed_reads_are_bounded_and_never_negative(self):
        with patch.object(cc,'identity_fetch',side_effect=TimeoutError('read')) as fetch,patch.object(cc.time,'sleep'),patch.object(cc,'log_event'),patch.object(cc,'log_error'):
            r=cc.search_dc(cc.checker.Organization('Zearn','37-1665745'))
            self.assertEqual(fetch.call_count,3)
            self.assertEqual(r.status,'Unable to Confirm')
    def test_dc_does_not_retry_block_or_malformed_response(self):
        for error in [urllib.error.HTTPError(cc.DC_LICENSE_API,403,'Forbidden',{},None),ValueError('invalid JSON')]:
            with patch.object(cc,'identity_fetch',side_effect=error) as fetch,patch.object(cc,'log_event'):
                with self.assertRaises(type(error)):cc.registry_json_request(cc.DC_LICENSE_API,time.monotonic()+75)
                self.assertEqual(fetch.call_count,1)
    def test_dc_insufficient_remaining_budget_does_not_start_another_read(self):
        with patch.object(cc,'identity_fetch',side_effect=TimeoutError('read')) as fetch,patch.object(cc,'log_event'):
            with self.assertRaises(TimeoutError):cc.registry_json_request(cc.DC_LICENSE_API,time.monotonic()+5)
            self.assertEqual(fetch.call_count,1)

if __name__=='__main__':unittest.main()
