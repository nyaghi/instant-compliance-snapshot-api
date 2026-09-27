"""Passive timing preserves requests, lazy streams, failures and all other code."""
import ast,json,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from deployment.queue_engine import observe_transport,transport_route
from deployment.queue_worker import log_failure_trace

URL='https://charportal.dca.njoag.gov/_layout/tokenhtml?secret=private'

class TransportTrace(unittest.TestCase):
    def fixture(self,version='test-performance-lab',error=None,body_error=None):
        seen=[]
        def chunks(*a,**kw):
            seen.append(('read',a,kw));yield b'private'
            if body_error:raise body_error
            yield b'complete'
        response=SimpleNamespace(status_code=200,iter_content=chunks)
        class Session:
            def __init__(self,*a,**kw):seen.append(('init',a,kw))
            def request(self,*a,**kw):
                seen.append(('request',a,kw))
                if error:raise error
                return response
        master=SimpleNamespace(APP_VERSION=version,curl_requests=SimpleNamespace(Session=Session))
        return master,Session,response,seen

    def test_exact_arguments_and_same_response_without_reading_body(self):
        master,original,response,seen=self.fixture()
        with observe_transport(master,'NJ') as trace:
            session=master.curl_requests.Session(impersonate='chrome')
            actual=session.request('GET',URL,timeout=4,stream=True,headers={'secret':'private'},verify=True)
            self.assertIs(actual,response);self.assertEqual(len(seen),2)
            self.assertEqual(seen[-1],('request',('GET',URL),dict(timeout=4,stream=True,headers={'secret':'private'},verify=True)))
            self.assertEqual(list(actual.iter_content(7)),[b'private',b'complete'])
            self.assertEqual(seen[-1],('read',(7,),{}))
        self.assertIs(master.curl_requests.Session,original)
        self.assertNotIn('private',json.dumps(trace.events));self.assertNotIn('secret',json.dumps(trace.events))
        self.assertEqual([r['event'] for r in trace.events],['http_start','http_headers','http_complete'])

    def test_nonstream_response_untouched(self):
        master,original,response,seen=self.fixture();iterator=response.iter_content
        with observe_transport(master,'MI') as trace:
            actual=master.curl_requests.Session().request('POST','https://www.ag.state.mi.us/CharitableTrust/frmDisclaimer.aspx',data={'private':'private'})
        self.assertIs(actual,response);self.assertIs(response.iter_content,iterator)
        self.assertEqual(trace.events[-1]['event'],'http_complete')

    def test_transport_exception_preserved_and_factory_restored(self):
        error=TimeoutError('private');master,original,_,_=self.fixture(error=error)
        with self.assertRaises(TimeoutError) as caught:
            with observe_transport(master,'NJ') as trace:master.curl_requests.Session().request('GET',URL)
        self.assertIs(caught.exception,error);self.assertIs(master.curl_requests.Session,original)
        self.assertEqual(trace.events[-1]['event'],'http_exception');self.assertNotIn('private',str(trace.events))

    def test_body_exception_preserved_at_same_point(self):
        error=TimeoutError('private');master,_,_,_=self.fixture(body_error=error)
        with observe_transport(master,'NJ') as trace:
            stream=master.curl_requests.Session().request('GET',URL,stream=True).iter_content()
            self.assertEqual(next(stream),b'private')
            with self.assertRaises(TimeoutError) as caught:next(stream)
        self.assertIs(caught.exception,error);self.assertEqual(trace.events[-1]['event'],'http_body_exception')

    def test_other_states_and_nonlab_are_untouched(self):
        for state,version in [('FL','v-performance-lab'),('NJ','production'),('MI','staging')]:
            master,original,_,_=self.fixture(version)
            with observe_transport(master,state) as trace:self.assertIsNone(trace);self.assertIs(master.curl_requests.Session,original)

    def test_unknown_routes_not_observed(self):
        master,_,_,_=self.fixture()
        with observe_transport(master,'NJ') as trace:master.curl_requests.Session().request('GET','https://example.com/private')
        self.assertEqual(trace.events,[])
        self.assertIsNone(transport_route('MI','http://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx'))

    def test_trace_persists_incomplete_request_and_redacts_failure_log(self):
        master,_,_,_=self.fixture(error=TimeoutError('secret'))
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'result.json';sink=output.with_suffix('.trace.json')
            with self.assertRaises(TimeoutError):
                with observe_transport(master,'NJ',sink):master.curl_requests.Session().request('GET',URL)
            rows=json.loads(output.with_suffix('.transport.json').read_text());self.assertEqual(len(rows),2)
            rows.append({'event':'http_start','route':'query','body':'secret','url':URL,'headers':{'private':'secret'}})
            output.with_suffix('.transport.json').write_text(json.dumps(rows))
            with patch('builtins.print') as emit:log_failure_trace({'output':output,'job':{'state':'NJ','id':'fixture'}},'TASK_TIME_LIMIT')
            text=emit.call_args.args[0];self.assertIn('query',text);self.assertNotIn('secret',text);self.assertNotIn('private',text)

    def test_failed_trace_writing_does_not_change_request(self):
        master,_,response,_=self.fixture()
        with tempfile.TemporaryDirectory() as folder:
            with observe_transport(master,'NJ',Path(folder)/'absent'/'trace.json') as trace:
                self.assertIs(master.curl_requests.Session().request('GET',URL),response)
        self.assertEqual(len(trace.events),2)

    def test_entire_master_and_queue_unchanged_and_adapter_only_adds_diagnostics(self):
        from testing.capacity_lab.parsing_scope import strip_transport_trace_engine,strip_transport_trace_worker,strip_transport_budget_and_redundancy
        root=Path(__file__).resolve().parents[2]
        for path,strip in [('deployment/queue_engine.py',strip_transport_trace_engine),('deployment/queue_worker.py',strip_transport_trace_worker),('registry_snapshot_server.py',strip_transport_budget_and_redundancy),('deployment/durable_queue.py',None)]:
            old=ast.parse(subprocess.check_output(['git','show','3f1779f:'+path],cwd=root).decode())
            new=ast.parse((root/path).read_text(encoding='utf-8'))
            if path == 'deployment/durable_queue.py':
                from testing.capacity_lab.tail_scope import strip_tail_latency
                strip_tail_latency(new)
            if strip:strip(new)
            self.assertEqual(ast.dump(old),ast.dump(new),path)

if __name__=='__main__':unittest.main()
