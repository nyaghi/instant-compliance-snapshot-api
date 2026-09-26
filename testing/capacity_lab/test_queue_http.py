"""HTTP contract and authorization tests. No registry network traffic."""
import json
import io
import threading
import types
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import Mock
from testing.capacity_lab.test_environment import Base, KEY
from deployment.performance_lab import build_handler
from deployment.durable_queue import Conflict, QueueFull, NotFound


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.queue=Mock()
        self.queue.submit.return_value=('fixture-id',True)
        self.queue.status.return_value={'id':'fixture-id','phase':'queued','queue_position':2}
        master=types.SimpleNamespace(RegistrySnapshotHandler=Base,APP_VERSION='test-performance-lab',
            SUPPORTED_STATES=['CO','NY'],IDENTITY_STATES=['CO'],downloadable_data_info=lambda s:{'usable':True})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),build_handler(master,KEY,durable=self.queue))
        self.thread=threading.Thread(target=self.server.serve_forever);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def req(self,path,payload=None,auth=True,key='sample-request'):
        headers={'Idempotency-Key':key}
        if auth:headers['Authorization']='Bearer '+KEY
        req=urllib.request.Request(self.url+path,headers=headers,data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with urllib.request.urlopen(req,timeout=3) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:
            with e:return e.code,json.load(e)

    def test_acceptance_returns_saved_id_and_server_derived_scope(self):
        p={'organization_name':'Fixture','ein':'12-3456789','states':['CO'],'alternate_names':['Former Name']}
        code,data=self.req('/api/lab/workflows',p)
        self.assertEqual(code,202);self.assertEqual(data['id'],'fixture-id')
        args=self.queue.submit.call_args.args
        self.assertEqual(args[0],'private-performance-lab')
        self.assertEqual(args[2]['alternate_names'],['Former Name'])
        self.assertEqual(args[2]['ein'],'123456789')
        self.assertNotIn('admin_passcode',args[2])
        self.assertEqual(self.req('/api/lab/workflows/fixture-id')[1]['phase'],'queued')
        self.assertEqual(self.req('/api/lab/workflows/fixture-id/cancel',{})[0],202)

    def test_legacy_execution_paths_cannot_bypass_shared_queue(self):
        for path in ('/api/check','/api/discover-names','/api/ny-connector'):
            self.assertEqual(self.req(path,{})[0],409)
        self.assertEqual(self.req('/evidence/CO/test.pdf')[0],409)
        self.queue.submit.assert_not_called()

    def test_rejection_and_cancellation_consume_bounded_ignored_body(self):
        for path in ('/api/check','/api/discover-names','/api/ny-connector','/api/lab/workflows/id/cancel','/unknown'):
            handler=self.server.RequestHandlerClass.__new__(self.server.RequestHandlerClass)
            handler.path=path;handler.headers={'Content-Length':'2'}
            handler.authorized=lambda:True;handler.rfile=io.BytesIO(b'{}')
            observations=[]
            handler._send_json=lambda status,*args:observations.append((status,handler.rfile.tell()))
            handler.do_POST()
            self.assertEqual(observations,[(202 if path.endswith('/cancel') else 404 if path=='/unknown' else 409,2)])

    def test_ignored_body_size_limit_does_not_trigger_execution(self):
        for length in ('-1','32769','invalid'):
            handler=self.server.RequestHandlerClass.__new__(self.server.RequestHandlerClass)
            handler.path='/api/lab/workflows/id/cancel';handler.headers={'Content-Length':length}
            handler.authorized=lambda:True;handler.rfile=io.BytesIO(b'{}')
            handler._send_json=Mock();handler.do_POST()
            self.assertEqual(handler._send_json.call_args.args[0],400)
            self.assertEqual(handler.rfile.tell(),0)
        self.queue.cancel.assert_not_called()

    def test_private_access_and_client_scope_injection(self):
        for path,data in (('/api/lab/workflows',{}),('/api/lab/workflows/id',None),('/api/lab/workflows/id/cancel',{})):
            self.assertEqual(self.req(path,data,auth=False)[0],401)
        p={'organization_name':'Fixture','ein':'123456789','states':['CO'],'scope':'another-company'}
        self.assertEqual(self.req('/api/lab/workflows',p)[0],400)
        self.queue.submit.assert_not_called()

    def test_unauthorized_post_drains_only_bounded_body_before_denial(self):
        for length,consumed in [('2',2),('32769',0),('-1',0),('invalid',0)]:
            handler=self.server.RequestHandlerClass.__new__(self.server.RequestHandlerClass)
            handler.command='POST';handler.headers={'Content-Length':length}
            handler.connection=Mock();handler.connection.gettimeout.return_value=None
            handler.rfile=io.BytesIO(b'{}');observed=[]
            handler._send_json=lambda status,*args:observed.append((status,handler.rfile.tell()))
            self.assertFalse(handler.authorized())
            self.assertEqual(observed,[(401,consumed)])
            self.assertTrue(handler.close_connection)
            handler.connection.settimeout.assert_called_with(None)
            if consumed:self.assertTrue(0<handler.connection.settimeout.call_args_list[0].args[0]<=1)
        self.queue.submit.assert_not_called();self.queue.cancel.assert_not_called()

    def test_unauthorized_body_timeout_still_denies_without_execution(self):
        handler=self.server.RequestHandlerClass.__new__(self.server.RequestHandlerClass)
        handler.command='POST';handler.headers={'Content-Length':'2'}
        handler.connection=Mock();handler.connection.gettimeout.return_value=5
        handler.rfile=Mock();handler.rfile.read1.side_effect=TimeoutError()
        handler._send_json=Mock()
        self.assertFalse(handler.authorized())
        self.assertEqual(handler._send_json.call_args.args[0],401)
        handler.connection.settimeout.assert_called_with(5)
        self.queue.submit.assert_not_called();self.queue.cancel.assert_not_called()

    def test_errors_are_transport_outcomes_never_registry_negatives(self):
        p={'organization_name':'Fixture','ein':'123456789','states':['CO']}
        for error,code in ((Conflict('Different input'),409),(QueueFull('Busy'),429),(RuntimeError('secret'),503)):
            self.queue.submit.side_effect=error
            status,data=self.req('/api/lab/workflows',p)
            self.assertEqual(status,code)
            self.assertNotIn('Not Registered',json.dumps(data));self.assertNotIn('secret',json.dumps(data))
        self.queue.status.side_effect=NotFound()
        self.assertEqual(self.req('/api/lab/workflows/missing')[0],404)


if __name__=='__main__':unittest.main(verbosity=2)
