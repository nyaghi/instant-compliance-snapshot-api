"""Same request/response and bounded redacted evidence after task termination."""
import ast,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from deployment.queue_engine import observe_transport,transport_route
from deployment.queue_worker import log_failure_trace
from testing.capacity_lab.test_transport_trace import TransportTrace
from testing.capacity_lab.me_trace_scope import strip_me_transport_trace

class MaineTrace(unittest.TestCase):
    def test_same_post_and_response_no_body_read_or_secret_logging(self):
        f=TransportTrace();master,original,response,seen=f.fixture()
        url='https://www.pfr.maine.gov/ALMSOnline/ALMSQuery/SearchCompany.aspx?private=secret'
        with observe_transport(master,'ME') as trace:
            actual=master.curl_requests.Session().request('POST',url,data={'private':'secret'},timeout=15,verify=True)
        self.assertIs(actual,response);self.assertIs(master.curl_requests.Session,original)
        self.assertEqual(seen[-1],('request',('POST',url),{'data':{'private':'secret'},'timeout':15,'verify':True}))
        self.assertEqual([x['event'] for x in trace.events],['http_start','http_complete'])
        self.assertNotIn('private',json.dumps(trace.events));self.assertNotIn('secret',json.dumps(trace.events))
    def test_interrupted_request_remains_observable_after_cleanup(self):
        master,_,_,_=TransportTrace().fixture(error=TimeoutError('secret'))
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'result.json'
            with self.assertRaises(TimeoutError):
                with observe_transport(master,'ME',output.with_suffix('.trace.json')):
                    master.curl_requests.Session().request('GET','https://www.pfr.maine.gov/ALMSOnline/ALMSQuery/ShowDetail.aspx?token=secret')
            with patch('builtins.print') as emit:log_failure_trace({'output':output,'job':{'state':'ME','id':'fixture'}},'WORKFLOW_DEADLINE')
            text=emit.call_args.args[0];self.assertIn('http_exception',text);self.assertIn('details',text);self.assertNotIn('secret',text)
    def test_only_official_https_paths_observed(self):
        self.assertEqual(transport_route('ME','https://www.pfr.maine.gov/ALMSOnline/ALMSQuery/SearchResults.aspx'),'results')
        self.assertEqual(transport_route('ME','https://www.pfr.maine.gov/almsonline/almsquery/SearchCompany.aspx'),'search')
        for url in ['http://www.pfr.maine.gov/ALMSOnline/ALMSQuery/SearchResults.aspx','https://example.com/ALMSOnline/ALMSQuery/SearchResults.aspx']:
            self.assertIsNone(transport_route('ME',url))
    def test_entire_queue_engine_and_worker_unchanged_except_state_trace_opt_in(self):
        root=Path(__file__).resolve().parents[2]
        for f in ['deployment/queue_engine.py','deployment/queue_worker.py']:
            old=ast.parse(subprocess.check_output(['git','show','03a1467:'+f],cwd=root).decode())
            new=ast.parse((root/f).read_text());strip_me_transport_trace(new)
            self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main(verbosity=2)
