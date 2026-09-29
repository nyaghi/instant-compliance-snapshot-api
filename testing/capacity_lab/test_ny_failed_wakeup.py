"""Real browser failures wake the same bounded retry without accepting partial data."""
import ast,json,os,subprocess,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import registry_snapshot_server as m
from testing.capacity_lab.test_ny_response_body_deadline import BodyDeadline
from testing.run_ny_retrieval_guardrails import ROW,DETAIL,response,AsOfDate
from testing.capacity_lab.ny_failed_scope import strip_ny_failed_wakeup

class FailedBodyDeadline(BodyDeadline):
    def run_response(self,path,budget=.25,submit=None):
        deadline=time.perf_counter()+budget
        def remaining():
            value=int((deadline-time.perf_counter())*1000)
            if value<=0:raise TimeoutError('fixture budget')
            return value
        return m.ny_wait_for_completed_or_failed_response(self.page,lambda r:r.url.endswith(path),
            submit or (lambda:self.page.evaluate(f'void fetch({json.dumps(path)}).catch(()=>{{}})')),remaining)

    def test_failed_request_wakes_well_before_response_deadline(self):
        self.page.route('**/abort',lambda route:route.abort('failed'))
        started=time.perf_counter()
        with self.assertRaises(m.NYBrowserConnectionError):self.run_response('/abort',budget=5)
        self.assertLess(time.perf_counter()-started,.8)

    def test_unrelated_failed_request_does_not_poison_matching_response(self):
        self.page.route('**/abort-other',lambda route:route.abort('failed'))
        self.assertEqual(self.run_response('/fast?unrelated-failure',submit=lambda:self.page.evaluate("void fetch('/abort-other').catch(()=>{}); void fetch('/fast?unrelated-failure')")).status,200)

    def test_failed_body_after_headers_does_not_get_accepted(self):
        # The original slow-body fixture still proves headers alone cannot finish.
        with self.assertRaises(TimeoutError):self.run_response('/slow?partial',budget=.15)

class FailedWakeup(unittest.TestCase):
    def test_whole_master_scope_preserves_matching_status_and_deadlines(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','647fddb:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_ny_failed_wakeup(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_gate_only_explicit_lab_sales(self):
        settings={'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com','CE_LAB_NY_FAILED_REQUEST_WAKEUP':'1'}
        for mode,version,change,want in [('sales','v-performance-lab',{},True),('standard','v-performance-lab',{},False),('sales','staging',{},False),('sales','v-performance-lab',{'CE_LAB_NY_FAILED_REQUEST_WAKEUP':''},False),('sales','v-performance-lab',{'PUBLIC_BASE_URL':'https://staging.compliance-express.com'},False)]:
            with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{**settings,**change}):
                token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
                try:self.assertEqual(m.lab_ny_failed_request_wakeup(),want)
                finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_original_one_retry_shared_by_search_and_detail(self):
        error=m.NYBrowserConnectionError('failed');org=m.checker.Organization('Example National Foundation','123456789')
        for answers,success,calls in [([error,response([ROW]),response(DETAIL)],True,3),([response([ROW]),error,response(DETAIL)],True,3),([error,response([ROW]),error],False,3),([error,error],False,2)]:
            with patch.object(m,'ny_browser_registry_response',side_effect=answers) as transport,patch.object(m.time,'sleep'),patch.object(m,'date',AsOfDate):
                result=m.search_ny_direct(org,browser_page=Mock())
            self.assertEqual(result.success,success);self.assertEqual(transport.call_count,calls)
            if not success:self.assertNotEqual(m.public_status(result),'Not Registered')

    def test_verification_connection_failure_retains_transport_identity(self):
        page=Mock();page._cc_ny_search_url=None;page.get_by_role.return_value.is_enabled.return_value=False
        with patch.object(m,'ny_complete_browser_response',side_effect=m.NYBrowserConnectionError('failed')):
            with self.assertRaises(m.NYBrowserConnectionError):m.ny_browser_registry_response(page,'RegistrySearch',{'ein':'123456789'},12)

if __name__=='__main__':unittest.main(verbosity=2)
