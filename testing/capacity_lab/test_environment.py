"""Private lab boundary controls; uses loopback fixtures only."""
import base64
import importlib.util
import json
from pathlib import Path
import threading
import types
import unittest
import urllib.request
import concurrent.futures
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('performance_lab', ROOT/'deployment/performance_lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)
KEY = 'fixture-only-' + 'a'*48


class Base(BaseHTTPRequestHandler):
    calls = []
    def _send_json(self, code, body, extra_headers=None):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Length', str(len(data)))
        for k,v in (extra_headers or {}).items(): self.send_header(k,v)
        self.end_headers()
        self.wfile.write(data)
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        Base.calls.append(data)
        self._send_json(200, data)
    def do_GET(self): self._send_json(404, {'error':'fixture fallback'})
    do_HEAD = do_GET
    def log_message(self,*args): pass


class LabTests(unittest.TestCase):
    def test_http_queue_preserves_payloads_and_reports_wait_time(self):
        from deployment.lab_capacity import FairCapacity, AdmissionSemaphore, REQUEST_GROUP
        pool = FairCapacity(2)
        gate = AdmissionSemaphore(pool, 'registration')
        seen = []
        finished = []
        finish_lock = threading.Lock()
        all_released = threading.Event()
        class QueuedBase(Base):
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if not gate.acquire(timeout=3): return self._send_json(429, {'error': 'Capacity busy'})
                try:
                    seen.append((REQUEST_GROUP.get(), data))
                    time.sleep(.03)
                    self._send_json(200, data)
                finally:
                    gate.release()
                    with finish_lock:
                        finished.append(True)
                        if len(finished) == 10: all_released.set()
        master = types.SimpleNamespace(RegistrySnapshotHandler=QueuedBase, APP_VERSION='test-performance-lab')
        server = ThreadingHTTPServer(('127.0.0.1', 0), lab.build_handler(master, KEY, pool))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def check(i):
            payload = {'ein': f'{i+1:09}', 'organization_name': f'Fixture {i}', 'states': ['MA'],
                       'alternate_names': [f'Former Name {i}'], 'nested': {'address': 'Oakland, CA'}}
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/check',
                  data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer '+KEY})
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.load(r), payload)
                self.assertIn('queue;dur=', r.headers['Server-Timing'])
                self.assertEqual(r.headers['X-CC-Lab-Version'], 'test-performance-lab')
        try:
            with concurrent.futures.ThreadPoolExecutor(10) as executor:
                list(executor.map(check, range(10)))
            self.assertEqual(len(seen), 10)
            self.assertTrue(all(group == 'lab:'+data['ein'] for group, data in seen))
            self.assertEqual(pool.snapshot()['counts']['peak_active'], 2)
            self.assertGreater(pool.snapshot()['counts']['peak_waiters'], 1)
            # Reading the flushed HTTP body can precede the handler's finally.
            self.assertTrue(all_released.wait(2), 'Request handlers did not release capacity')
            self.assertEqual(pool.snapshot()['active'], 0)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def env(self):
        return {**dict.fromkeys(lab.DISABLED_CONNECTIONS,''), 'PUBLIC_BASE_URL':lab.LAB_ORIGIN,
                'CE_APP_VERSION':'test-performance-lab','CE_LAB_ACCESS_KEY':KEY,
                'CE_STAGING_ACCESS_REQUIRED':'1','CE_PUBLIC_SINGLE_STATE_ONLY':'1',
                'CE_BATCH_FANOUT_SINGLE_STATE_LOOKUPS':'0'}

    def test_only_lab_service_and_origin_allowed(self):
        lab.validate_environment(self.env())
        for key,value in [('PUBLIC_BASE_URL','https://staging.compliance-express.com'),
                          ('RENDER_SERVICE_ID','another-service'),('CE_APP_VERSION','test-staging')]:
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                lab.validate_environment({**self.env(),key:value})

    def test_helpers_and_fanout_cannot_leak_to_other_environments(self):
        for key in lab.DISABLED_CONNECTIONS:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                lab.validate_environment({**self.env(),key:'https://staging.compliance-express.com'})
        with self.assertRaises(RuntimeError):
            lab.validate_environment({**self.env(),'CE_BATCH_FANOUT_SINGLE_STATE_LOOKUPS':'1'})

    def test_strong_separate_credentials_and_access_gate_required(self):
        for key,value in [('CE_LAB_ACCESS_KEY','short'),('CE_STAGING_ACCESS_REQUIRED','0'),('CE_PUBLIC_SINGLE_STATE_ONLY','0')]:
            with self.subTest(key=key),self.assertRaises(RuntimeError):
                lab.validate_environment({**self.env(),key:value})

    def test_durable_database_and_worker_targets_are_explicit(self):
        env={**self.env(),'CE_LAB_DURABLE_QUEUE':'1',
             'CE_LAB_DATABASE_URL':'postgresql://fixture:fixture@dpg-dar6utvavr4c7380ou60-a/cc_performance_lab'}
        lab.validate_environment(env)
        for dsn in ('postgresql://fixture:fixture@production/cc_performance_lab',
                    'postgresql://fixture:fixture@dpg-dar6utvavr4c7380ou60-a/other_database'):
            with self.assertRaises(RuntimeError):lab.validate_environment({**env,'CE_LAB_DATABASE_URL':dsn})
        worker={**env,'CE_LAB_ROLE':'worker','CE_LAB_WORKER_SERVICE_ID':'fixture-worker',
                'RENDER_SERVICE_ID':'fixture-worker','RENDER_SERVICE_NAME':'charityclarity-performance-lab-worker-1'}
        lab.validate_environment(worker)
        for sid in ('srv-d8a38lnavr4c73d4ib30','srv-d82afqjrjlhs738j7or0'):
            with self.assertRaises(RuntimeError):lab.validate_environment({**worker,'CE_LAB_WORKER_SERVICE_ID':sid,'RENDER_SERVICE_ID':sid})

    def test_authorization_is_exact_and_malformed_input_rejected(self):
        self.assertTrue(lab.valid_authorization('Bearer '+KEY,KEY))
        self.assertTrue(lab.valid_authorization('Basic '+base64.b64encode(('lab:'+KEY).encode()).decode(),KEY))
        for value in ('', 'Bearer '+KEY+'x', 'Basic @@@', 'Basic '+base64.b64encode(('other:'+KEY).encode()).decode()):
            self.assertFalse(lab.valid_authorization(value,KEY))

    def test_application_hosts_blocked_registry_hosts_unchanged(self):
        for host in ['staging.compliance-express.com','compliance-express.com','anything.onrender.com','old.trycloudflare.com']:
            self.assertTrue(lab.blocked_app_host(host))
        for host in ['charitiesnys.com','www.elicense.ct.gov','127.0.0.1','apps.dfi.wi.gov']:
            self.assertFalse(lab.blocked_app_host(host))

    def test_private_assets_rewrite_all_frontend_backend_lanes(self):
        for asset in ['/','/sales-mode.js','/organization-identity.js','/ny-connector.js']:
            data,_=lab.lab_asset(asset)
            self.assertNotIn(b'staging.compliance-express.com',data)
            self.assertNotIn(b'instant-compliance-snapshot-api-staging',data)
        page=lab.lab_asset('/')[0]
        self.assertIn(b'Performance Lab',page)
        self.assertTrue(b'Math.min(15,' in page, 'Standard scheduler remains at 15 state slots')
        sales=lab.lab_asset('/sales-mode.js')[0]
        self.assertIn(b'const RUN_LIMIT_MS = 60000',sales)
        self.assertIn(b'const STATE_CONCURRENCY = 15',sales)

    def test_static_paths_cannot_read_secrets_or_extension_archives(self):
        for path in ['/../registry_snapshot_server.py','/%2e%2e/requirements.txt','/connector/charityclarity-ny-staging.zip']:
            self.assertIsNone(lab.lab_asset(path))

    def test_live_http_boundary_and_master_dispatch(self):
        master=types.SimpleNamespace(RegistrySnapshotHandler=Base, APP_VERSION='test-performance-lab',
              SUPPORTED_STATES=['CO','NY'],downloadable_data_info=lambda s:{'usable':True})
        server=ThreadingHTTPServer(('127.0.0.1',0),lab.build_handler(master,KEY))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        url=f'http://127.0.0.1:{server.server_port}'
        def request(path,payload=None,auth=None):
            req=urllib.request.Request(url+path,data=json.dumps(payload).encode() if payload is not None else None,
                                      headers={'Authorization':'Bearer '+auth} if auth else {})
            try:
                with urllib.request.urlopen(req,timeout=3) as r:return r.status,r.read()
            except urllib.error.HTTPError as e:
                code,body=e.code,e.read();e.close();return code,body
        try:
            for path in ['/','/api/lab/metrics','/evidence/CO/test.pdf','/admin/leads.csv']:
                self.assertEqual(request(path)[0],401)
            self.assertEqual(request('/api/check',{})[0],401)
            self.assertEqual(request('/api/discover-names',{})[0],401)
            self.assertEqual(request('/api/ny-connector',{},KEY)[0],503)
            self.assertEqual(request('/healthz')[0],200)
            payload={'ein':'123456789','organization_name':'Fixture','alternate_names':['Former Name'],'states':['CO']}
            code,body=request('/api/check',payload,KEY)
            self.assertEqual(code,200);self.assertEqual(json.loads(body),payload)
            self.assertEqual(Base.calls[-1],payload)
            data=json.loads(request('/api/lab/metrics',auth=KEY)[1])
            self.assertEqual(data['active_requests'],0)
            self.assertEqual(data['completed_requests'],1)
        finally:
            server.shutdown();server.server_close();worker.join()


if __name__=='__main__':unittest.main(verbosity=2)
