"""Observers preserve original sockets, requests, exceptions and privacy."""
import ast,json,socket,ssl,subprocess,threading,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock,patch
from deployment.queue_engine import FloridaTrace,observe_fl_connection,attach_ny_network_diagnostics
from testing.capacity_lab.network_diagnostic_scope import strip_network_diagnostics

class NetworkDiagnostics(unittest.TestCase):
    def test_fl_original_sockets_arguments_and_tls_context_unchanged(self):
        trace=FloridaTrace();tcp=object();tls=object();context=ssl.create_default_context()
        with patch.object(socket,'create_connection',return_value=tcp) as connect,patch.object(ssl.SSLContext,'wrap_socket',return_value=tls) as wrap:
            with observe_fl_connection(trace):
                self.assertIs(socket.create_connection(('csapp.fdacs.gov',443),timeout=4),tcp)
                self.assertIs(context.wrap_socket(tcp,server_hostname='csapp.fdacs.gov'),tls)
            self.assertIs(socket.create_connection,connect);self.assertIs(ssl.SSLContext.wrap_socket,wrap)
            connect.assert_called_once_with(('csapp.fdacs.gov',443),timeout=4)
            wrap.assert_called_once_with(context,tcp,server_hostname='csapp.fdacs.gov')
        self.assertEqual([x['event'] for x in trace.events],['fl_tcp_start','fl_tcp_complete','fl_tls_start','fl_tls_complete'])
        self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
    def test_fl_failures_same_exception_no_private_message_and_restoration(self):
        for phase in ['tcp','tls']:
            trace=FloridaTrace();error=TimeoutError('private secret');context=ssl.create_default_context()
            with patch.object(socket,'create_connection',side_effect=error) as connect,patch.object(ssl.SSLContext,'wrap_socket',side_effect=error) as wrap:
                with self.assertRaises(TimeoutError) as caught:
                    with observe_fl_connection(trace):
                        if phase=='tcp':socket.create_connection(('csapp.fdacs.gov',443),timeout=4)
                        else:context.wrap_socket(object(),server_hostname='csapp.fdacs.gov')
                self.assertIs(caught.exception,error);self.assertIs(socket.create_connection,connect);self.assertIs(ssl.SSLContext.wrap_socket,wrap)
            self.assertEqual(trace.events[-1]['event'],'fl_'+phase+'_error');self.assertNotIn('private',json.dumps(trace.events))
    def test_fl_other_hosts_and_broken_sink_do_not_change_execution(self):
        for host,trace in [('example.com',FloridaTrace()),('csapp.fdacs.gov',Mock())]:
            if isinstance(trace,Mock):trace.record.side_effect=ValueError('broken sink')
            value=object()
            with patch.object(socket,'create_connection',return_value=value) as connect:
                with observe_fl_connection(trace):self.assertIs(socket.create_connection((host,443),timeout=3),value)
            connect.assert_called_once_with((host,443),timeout=3)
            if isinstance(trace,FloridaTrace):self.assertEqual(trace.events,[])
    def test_ny_network_status_and_cors_only_never_reads_body_or_logs_credentials(self):
        context=Mock();page=object();session=context.new_cdp_session.return_value;callbacks={}
        session.on.side_effect=lambda name,callback:callbacks.__setitem__(name,callback)
        trace=FloridaTrace();self.assertIs(attach_ny_network_diagnostics(context,page,trace),session)
        callbacks['Network.requestWillBeSent']({'requestId':'private-id','request':{'url':'https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch?token=private','headers':{'secret':'private'}}})
        callbacks['Network.responseReceivedExtraInfo']({'requestId':'private-id','statusCode':429,'headers':{'secret':'private'}})
        callbacks['Network.loadingFailed']({'requestId':'private-id','errorText':'private','corsErrorStatus':{'corsError':'MissingAllowOriginHeader','failedParameter':'private'}})
        self.assertEqual(trace.events[0]['status'],429)
        self.assertEqual(trace.events[1]['cors_error'],'MissingAllowOriginHeader')
        self.assertNotIn('private',json.dumps(trace.events));session.send.assert_called_once_with('Network.enable')
    def test_ny_diagnostic_attach_and_callback_failures_are_nonfatal(self):
        context=Mock();context.new_cdp_session.side_effect=RuntimeError('unsupported')
        self.assertIsNone(attach_ny_network_diagnostics(context,object(),FloridaTrace()))
        context=Mock();session=context.new_cdp_session.return_value;session.send.side_effect=RuntimeError('closed')
        self.assertIsNone(attach_ny_network_diagnostics(context,object(),FloridaTrace()));session.detach.assert_called_once()
    def test_ny_unrelated_network_responses_and_arbitrary_labels_not_recorded(self):
        context=Mock();callbacks={};context.new_cdp_session.return_value.on.side_effect=lambda name,cb:callbacks.__setitem__(name,cb)
        trace=FloridaTrace();attach_ny_network_diagnostics(context,object(),trace)
        callbacks['Network.requestWillBeSent']({'requestId':'1','request':{'url':'https://example.com/private'}})
        callbacks['Network.responseReceivedExtraInfo']({'requestId':'1','statusCode':200})
        callbacks['Network.loadingFailed']({'requestId':'1','errorText':'secret'})
        self.assertEqual(trace.events,[])
    def test_exact_runtime_scope(self):
        root=Path(__file__).resolve().parents[2]
        old=ast.parse(subprocess.check_output(['git','show','5d85732:deployment/queue_engine.py'],cwd=root).decode())
        new=ast.parse((root/'deployment/queue_engine.py').read_text());strip_network_diagnostics(new)
        self.assertEqual(ast.dump(old),ast.dump(new))
        from testing.capacity_lab.loaded_timing_scope import assert_loaded_scope
        for path in ['deployment/durable_queue.py','deployment/queue_schema.sql']:
            assert_loaded_scope(root,'5d85732',path)
        subprocess.run(['git','diff','--exit-code','5d85732','--','registry_snapshot_server.py','deployment/queue_worker.py','deployment/lab_capacity.py','deployment/performance_lab.py'],cwd=root,check=True,stdout=subprocess.DEVNULL)
    def test_real_cors_rejection_exposes_http_429_without_body_reads(self):
        from playwright.sync_api import sync_playwright
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(429 if self.path.startswith('/reject') else 200)
                self.send_header('Content-Type','text/html');self.end_headers()
                self.wfile.write(b'<p>private fixture body</p>')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                try:
                    context=browser.new_context();page=context.new_page();trace=FloridaTrace()
                    port=server.server_port;target=f'http://localhost:{port}/reject?private=secret'
                    page.goto(f'http://127.0.0.1:{port}/')
                    with patch('deployment.queue_engine.browser_trace_route',side_effect=lambda url:'search' if url==target else None):
                        session=attach_ny_network_diagnostics(context,page,trace)
                        self.assertIsNotNone(session)
                        page.evaluate('(url) => fetch(url).catch(() => null)',target)
                        page.wait_for_timeout(100)
                        session.detach()
                    self.assertTrue(any(e.get('status')==429 for e in trace.events),trace.events)
                    self.assertTrue(any(e.get('cors_error')=='MissingAllowOriginHeader' for e in trace.events),trace.events)
                    self.assertNotIn('private',json.dumps(trace.events))
                finally:browser.close()
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
