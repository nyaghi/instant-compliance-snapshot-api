"""WI diagnostics must preserve request/response identity and source failures."""
import ast, json, subprocess, tempfile, unittest, urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from deployment.queue_engine import observe_transport, wi_transport_route
from deployment.queue_worker import log_failure_trace

URL = 'https://apps.dfi.wi.gov/ice/berg/Registration/OrgCredentialSearchResults.aspx?FirmName=private'

class WisconsinTrace(unittest.TestCase):
    def master(self, version='test-performance-lab'):
        return SimpleNamespace(APP_VERSION=version, urllib=SimpleNamespace(request=urllib.request))

    def test_same_arguments_response_lazy_read_and_no_private_data(self):
        reads=[]
        response=SimpleNamespace(status=200,read=lambda *a,**kw: reads.append((a,kw)) or b'private-body')
        with patch.object(urllib.request.OpenerDirector,'open',return_value=response) as original:
            with observe_transport(self.master(),'WI') as trace:
                req=urllib.request.Request(URL);actual=urllib.request.build_opener().open(req,timeout=4)
                self.assertIs(actual,response);self.assertEqual(reads,[])
                self.assertIs(original.call_args.args[1],req);self.assertEqual(original.call_args.kwargs,{'timeout':4})
                self.assertEqual(actual.read(12),b'private-body');self.assertEqual(reads,[((12,),{})])
            self.assertIs(urllib.request.OpenerDirector.open,original)
        self.assertEqual([x['event'] for x in trace.events],['http_start','http_headers','http_complete'])
        self.assertNotIn('private',json.dumps(trace.events))

    def test_exception_is_identical_and_failure_trace_survives_task(self):
        error=TimeoutError('private')
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'result.json'
            with patch.object(urllib.request.OpenerDirector,'open',side_effect=error) as original:
                with self.assertRaises(TimeoutError) as caught:
                    with observe_transport(self.master(),'WI',out.with_suffix('.trace.json')):
                        urllib.request.build_opener().open(URL)
                self.assertIs(caught.exception,error);self.assertIs(urllib.request.OpenerDirector.open,original)
            with patch('builtins.print') as emit:log_failure_trace({'output':out,'job':{'state':'WI','id':'test'}},'TASK_TIME_LIMIT')
            saved=emit.call_args.args[0];self.assertIn('http_exception',saved);self.assertNotIn('private',saved)

    def test_body_error_and_unobserved_hosts_preserve_original(self):
        error=ValueError('private')
        def read(): raise error
        response=SimpleNamespace(status=200,read=read)
        with patch.object(urllib.request.OpenerDirector,'open',return_value=response):
            with observe_transport(self.master(),'WI') as trace:
                actual=urllib.request.build_opener().open('https://example.com/private')
                self.assertIs(actual.read,read);self.assertEqual(trace.events,[])
                actual=urllib.request.build_opener().open(URL)
                with self.assertRaises(ValueError) as caught:actual.read()
                self.assertIs(caught.exception,error)
        self.assertEqual(trace.events[-1]['event'],'http_body_exception')

    def test_production_and_staging_are_not_instrumented(self):
        for version in ['production','staging']:
            with observe_transport(self.master(version),'WI') as trace:self.assertIsNone(trace)
        self.assertIsNone(wi_transport_route('http://apps.dfi.wi.gov/private'))
        self.assertIsNone(wi_transport_route('https://r.jina.ai/http://example.com/private'))
        self.assertEqual(wi_transport_route('https://r.jina.ai/http://apps.dfi.wi.gov/ice/berg/Registration/test'),'reader')

    def test_every_other_worker_and_engine_operation_unchanged(self):
        from testing.capacity_lab.wi_trace_scope import strip_wi_trace_engine, strip_wi_trace_worker
        root=Path(__file__).resolve().parents[2]
        for path,strip in [('deployment/queue_engine.py',strip_wi_trace_engine),('deployment/queue_worker.py',strip_wi_trace_worker)]:
            old=ast.parse(subprocess.check_output(['git','show','45bddd3:'+path],cwd=root).decode())
            new=ast.parse((root/path).read_text());strip(new)
            self.assertEqual(ast.dump(old),ast.dump(new))

if __name__ == '__main__': unittest.main()
