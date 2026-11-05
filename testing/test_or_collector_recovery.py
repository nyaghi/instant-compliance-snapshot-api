"""Exercise the actual queue boundary, keeping status/evidence/deadline guards."""
import time, unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock,patch
from deployment import or_reachability as m, queue_engine as engine

class CollectorRecoveryTests(unittest.TestCase):
    def run_case(self, *, attempts=None, reason='OR_SOURCE_UNREACHABLE', result=None, remaining=43, reachable=False, state='OR'):
        attempts=attempts if attempts is not None else [{'error_type':'TimeoutError','failure_phase':'http_response_headers'}]*3
        result=result if result is not None else {'state':state,'status':'Upcoming Filing','success':True,'evidence_capture':'captured','_worker_source_archives':[{'bound_original':True}]}
        deadline=time.monotonic()+remaining
        def collect(*args):
            from deployment.state_snapshots import DEADLINE
            self.assertEqual(DEADLINE.get(),deadline)
            return [dict(result)]
        collector=Mock(side_effect=collect)
        master=SimpleNamespace(APP_VERSION='test',SUPPORTED_STATES={'OR','CA'},normalize_organization_requests=lambda *a,**k:[object()],or_snapshot_row_for_ein=lambda ein:['202'],run_state_lookups_parallel=collector)
        job={'state':state,'version':'test','_deadline_monotonic':deadline,'payload':{'organization_name':'Test','ein':'131930701','mode':'standard'}}
        with patch.object(m,'check',return_value=(reachable,reason,attempts,32)) as probe,patch.object(engine,'observe_fl_headers',return_value=nullcontext()),patch.object(engine,'observe_transport',return_value=nullcontext()),patch.object(engine,'observe_browser_transport',return_value=nullcontext()):
            value=engine.execute(master,job)
        self.assertEqual(job['_deadline_monotonic'],deadline)
        return value,collector,probe

    def test_stalled_preflight_then_original_capture_recovers_once(self):
        value,collector,_=self.run_case()
        self.assertEqual(collector.call_count,1)
        self.assertEqual(value['status'],'Upcoming Filing')
        self.assertTrue(value['or_reachability']['collector_recovery']['original_evidence_captured'])
        self.assertFalse(value['or_reachability']['collector_recovery']['deadline_extended'])

    def test_complete_outage_or_offline_only_result_cannot_become_success(self):
        for result in [dict(status='Upcoming Filing',success=True,evidence_capture='unavailable'),dict(status='Not Registered',success=True,evidence_capture='unavailable'),dict(status='Unable to Confirm',success=False,evidence_capture='unavailable')]:
            with self.subTest(status=result['status']):
                value,collector,_=self.run_case(result=result)
                self.assertEqual(collector.call_count,1)
                self.assertEqual(value['status'],'Site Not Reachable')
                self.assertFalse(value['success']);self.assertEqual(value['evidence_url'],'')

    def test_capture_flag_without_original_archive_is_not_recovery(self):
        value,_,_=self.run_case(result=dict(status='Current',success=True,evidence_capture='captured'))
        self.assertEqual(value['status'],'Site Not Reachable')

    def test_original_capture_does_not_override_collector_status_or_identity(self):
        value,_,_=self.run_case(result=dict(status='Review required',success=False,evidence_capture='captured',_worker_source_archives=[{'bound_original':True}],identity_review_required=True))
        self.assertEqual(value['status'],'Review required');self.assertTrue(value['identity_review_required']);self.assertFalse(value['success'])

    def test_setup_failure_denial_foreign_redirect_and_late_response_stay_terminal(self):
        cases=[('OR_SOURCE_UNREACHABLE',[{'error_type':'URLError','failure_phase':phase}]) for phase in ['dns_resolution','tcp_connect','tls_handshake']]
        cases += [('OR_SOURCE_ACCESS_REFUSED',[{'http_status':403}]),('OR_SOURCE_ACCESS_REFUSED',[{'http_status':200}]),('OR_SOURCE_UNREACHABLE',[{'error_type':'LateResponse'}]),('OR_SOURCE_UNREACHABLE',[]),('OR_SOURCE_UNREACHABLE',[{'http_status':503}])]
        for reason,attempts in cases:
            with self.subTest(reason=reason,attempts=attempts):
                _,collector,_=self.run_case(reason=reason,attempts=attempts)
                collector.assert_not_called()

    def test_existing_deadline_reserve_is_enforced(self):
        for remaining in [0,2,3]:
            _,collector,_=self.run_case(remaining=remaining)
            collector.assert_not_called()

    def test_saved_bare_response_timeout_supported_without_new_frames(self):
        _,collector,_=self.run_case(attempts=[{'error_type':'TimeoutError'}]*3)
        self.assertEqual(collector.call_count,1)

    def test_healthy_oregon_and_other_states_keep_normal_collector_path(self):
        value,collector,_=self.run_case(reachable=True)
        self.assertNotIn('collector_recovery',value['or_reachability']);self.assertEqual(collector.call_count,1)
        value,collector,probe=self.run_case(state='CA')
        probe.assert_not_called();self.assertNotIn('or_reachability',value);self.assertEqual(collector.call_count,1)

if __name__=='__main__':unittest.main()
