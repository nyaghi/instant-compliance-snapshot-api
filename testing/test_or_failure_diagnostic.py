"""Use real local stalled sockets to distinguish TLS and HTTP-header waits."""
import http.client
import socket
import ssl
import threading
import unittest
import urllib.error
from contextlib import contextmanager
from deployment.or_reachability import failure_diagnostic

@contextmanager
def stalled_peer():
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
    port=listener.getsockname()[1];done=threading.Event()
    def serve():
        conn=None
        try:
            listener.settimeout(2);conn,_=listener.accept();done.wait(2)
        finally:
            if conn:conn.close()
    worker=threading.Thread(target=serve);worker.start()
    try:yield port
    finally:done.set();listener.close();worker.join(3)

class FailureDiagnosticTests(unittest.TestCase):
    def test_real_http_header_timeout(self):
        with stalled_peer() as port:
            c=http.client.HTTPConnection('127.0.0.1',port,timeout=.1)
            try:
                c.request('GET','/')
                try:c.getresponse()
                except TimeoutError as error:diagnostic=failure_diagnostic(error)
                else:self.fail('Expected a stalled header timeout')
            finally:c.close()
        self.assertEqual(diagnostic['failure_phase'],'http_response_headers')
        self.assertIn('http.client._read_status',diagnostic['network_frames'])

    def test_real_tls_timeout_wrapped_by_urllib(self):
        with stalled_peer() as port:
            raw=socket.create_connection(('127.0.0.1',port),timeout=.1)
            try:
                try:ssl.create_default_context().wrap_socket(raw,server_hostname='localhost')
                except TimeoutError as error:diagnostic=failure_diagnostic(urllib.error.URLError(error))
                else:self.fail('Expected TLS timeout')
            finally:raw.close()
        self.assertEqual(diagnostic['failure_phase'],'tls_handshake')

    def test_dns_error_is_not_tcp_error(self):
        self.assertEqual(failure_diagnostic(urllib.error.URLError(socket.gaierror(-2,'private-message')))['failure_phase'],'dns_resolution')

    def test_no_frames_means_unknown_and_no_messages(self):
        result=failure_diagnostic(TimeoutError('private-message https://example.invalid/?secret=abc'))
        self.assertEqual(result['failure_phase'],'unknown')
        self.assertNotIn('private-message',str(result));self.assertNotIn('secret',str(result))

    def test_cyclic_causes_are_bounded(self):
        error=TimeoutError();error.__cause__=error
        self.assertEqual(failure_diagnostic(error)['failure_phase'],'unknown')

if __name__=='__main__':unittest.main()
