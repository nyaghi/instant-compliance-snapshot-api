"""Passive FL timing cannot alter I/O or expose names, headers or cookies."""
import ast,json,subprocess,unittest,urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from deployment.queue_engine import FloridaTrace,observe_fl_headers

class Headers(unittest.TestCase):
    def master(self,version='test-performance-lab'):
        return SimpleNamespace(APP_VERSION=version,urllib=SimpleNamespace(request=urllib.request))
    def test_same_request_response_timeout_and_no_body_read(self):
        response=SimpleNamespace(status=200,read=Mock())
        request=urllib.request.Request('https://csapp.fdacs.gov/CSPublicApp/BusinessSearch/BusinessSearch.aspx?private=value',data=b'private=form',headers={'Cookie':'private-cookie'})
        trace=FloridaTrace();opener=urllib.request.build_opener()
        with patch.object(urllib.request.OpenerDirector,'open',return_value=response) as call:
            with observe_fl_headers(self.master(),trace):self.assertIs(opener.open(request,timeout=4),response)
            call.assert_called_once_with(opener,request,timeout=4)
        response.read.assert_not_called()
        self.assertEqual([r['event'] for r in trace.events],['verified_open','verified_headers'])
        self.assertNotIn('private',json.dumps(trace.events))
    def test_exception_restored_without_message_leak(self):
        error=TimeoutError('private-secret');trace=FloridaTrace();opener=urllib.request.build_opener()
        with patch.object(urllib.request.OpenerDirector,'open',side_effect=error) as call:
            with self.assertRaises(TimeoutError) as caught:
                with observe_fl_headers(self.master(),trace):opener.open('https://csapp.fdacs.gov/CSPublicApp/CheckACharity/CheckACharity.aspx',timeout=12)
            self.assertIs(urllib.request.OpenerDirector.open,call)
        self.assertIs(caught.exception,error)
        self.assertEqual(trace.events[-1]['event'],'verified_open_error')
        self.assertNotIn('secret',json.dumps(trace.events))
    def test_other_host_nonlab_and_no_trace_unchanged(self):
        for version,trace,url in [('production',FloridaTrace(),'https://csapp.fdacs.gov/CSPublicApp/CheckACharity/CheckACharity.aspx'),('test-performance-lab',None,'https://example.com/'),('test-performance-lab',FloridaTrace(),'https://example.com/private')]:
            with patch.object(urllib.request.OpenerDirector,'open',return_value=SimpleNamespace(status=200)):
                with observe_fl_headers(self.master(version),trace):urllib.request.build_opener().open(url)
            if trace:self.assertEqual(trace.events,[])
    def test_runtime_scope_is_only_validator_and_passive_observer(self):
        root=Path(__file__).resolve().parents[2]
        for path in ['deployment/queue_worker.py','deployment/queue_schema.sql','deployment/performance_lab.py']:
            subprocess.run(['git','diff','--exit-code','f56a83d','--',path],cwd=root,check=True,stdout=subprocess.DEVNULL)
        old=ast.parse(subprocess.check_output(['git','show','f56a83d:deployment/durable_queue.py'],cwd=root).decode())
        new=ast.parse((root/'deployment/durable_queue.py').read_text())
        for tree in [old,new]:tree.body=[n for n in tree.body if getattr(n,'name','')!='normalize_submission']
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main()
