"""Isolated performance service entry point; all state checks use the master.

This deployment-only boundary supplies private lab authentication, local static
assets and telemetry. It is not a state adapter or a replacement status engine.
It must never be used to start the staging or production services.
"""
import base64
import hmac
import io
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
import time
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
LAB_ORIGIN = 'https://instant-compliance-snapshot-api-hn4v.onrender.com'
LAB_SERVICE_ID = 'srv-d8u0hsu7r5hc73aqfsg0'
DISABLED_CONNECTIONS = (
    'CE_SINGLE_STATE_OVERFLOW_API_URL', 'CE_SINGLE_STATE_OVERFLOW_API_URLS',
    'CE_BATCH_FANOUT_API_URL', 'CE_BATCH_FANOUT_API_URLS',
    'CE_WI_SIDECAR_URL', 'CE_NM_STATUS_SIDECAR_URL',
    'CE_GA_SIDECAR_URL', 'CE_LEAD_LOG_WEBHOOK_URL',
)


def validate_environment(env):
    if env.get('PUBLIC_BASE_URL') != LAB_ORIGIN:
        raise RuntimeError('Performance entry point requires its isolated lab origin')
    if env.get('RENDER_SERVICE_ID', LAB_SERVICE_ID) != LAB_SERVICE_ID:
        raise RuntimeError('Performance entry point refuses another Render service')
    if not env.get('CE_APP_VERSION', '').endswith('-performance-lab'):
        raise RuntimeError('Performance version label required')
    if len(env.get('CE_LAB_ACCESS_KEY', '')) < 40:
        raise RuntimeError('A separate strong lab access key is required')
    if env.get('CE_STAGING_ACCESS_REQUIRED') != '1' or env.get('CE_PUBLIC_SINGLE_STATE_ONLY') != '1':
        raise RuntimeError('Private single-state access boundary required')
    if env.get('CE_BATCH_FANOUT_SINGLE_STATE_LOOKUPS') != '0':
        raise RuntimeError('Lab fanout must be disabled for the baseline')
    for key in DISABLED_CONNECTIONS:
        if env.get(key) != '':
            raise RuntimeError('Connection must be explicitly disabled: ' + key)


def valid_authorization(header, key):
    if header.startswith('Bearer '):
        candidate = header[7:]
    elif header.startswith('Basic '):
        try:
            user, candidate = base64.b64decode(header[6:], validate=True).decode().split(':', 1)
        except (ValueError, UnicodeError):
            return False
        if user != 'lab':
            return False
    else:
        return False
    return hmac.compare_digest(candidate.encode(), key.encode())


def blocked_app_host(host):
    host = str(host).lower().rstrip('.')
    return (host == 'compliance-express.com' or host.endswith('.compliance-express.com')
            or host.endswith('.onrender.com') or host.endswith('.trycloudflare.com'))


def install_http_egress_guard():
    # A second defense against accidentally reusing an application helper.
    # State registries and public IRS sources retain their existing paths.
    def audit(event, args):
        if event == 'socket.getaddrinfo' and blocked_app_host(args[0]):
            raise PermissionError('Performance lab cannot call an application environment')
    sys.addaudithook(audit)


def lab_asset(path):
    path = unquote(urlparse(path).path)
    if path in ('/', '/registry-snapshot', '/registry-snapshot/'):
        path = '/index.html'
    root = (ROOT / 'web-staging').resolve()
    file = (root / path.lstrip('/')).resolve()
    if not file.is_relative_to(root) or file.suffix.lower() not in {'.html', '.js', '.css', '.png', '.ico', '.svg', '.jpg'}:
        return None
    if not file.is_file():
        return None
    data = file.read_bytes()
    if file.suffix.lower() in {'.html', '.js', '.css'}:
        text = data.decode('utf-8')
        for origin in ('https://instant-compliance-snapshot-api-staging-8dnk.onrender.com',
                       'https://instant-compliance-snapshot-api-staging.onrender.com',
                       'https://staging.compliance-express.com'):
            text = text.replace(origin, LAB_ORIGIN)
        if file.name == 'index.html':
            text = text.replace('<title>', '<title>Performance Lab — ', 1)
            text = text.replace('<body', '<body data-performance-lab="true"', 1)
            marker = '<div style="padding:10px;background:#fff3cd;color:#533f03;text-align:center">Isolated performance lab. Capacity is under evaluation. New York browser validation is not enabled.</div>'
            import re
            text = re.sub(r'(<body\b[^>]*>)', lambda m: m.group(1) + marker, text, count=1)
        data = text.encode('utf-8')
    return data, mimetypes.guess_type(file)[0] or 'application/octet-stream'


def build_handler(master, key, capacity=None):
    lock = threading.Lock()
    telemetry = {'started_epoch': time.time(), 'active_requests': 0, 'peak_requests': 0, 'completed_requests': 0}

    class LabHandler(master.RegistrySnapshotHandler):
        def _send_json(self, status_code, payload, extra_headers=None):
            from deployment.lab_capacity import REQUEST_TIMING
            timing = REQUEST_TIMING.get()
            headers = dict(extra_headers or {})
            if timing is not None:
                queue = timing.get('queue_seconds', 0)
                elapsed = time.monotonic() - timing['started']
                headers['Server-Timing'] = f'queue;dur={queue*1000:.2f}, execution;dur={max(0, elapsed-queue)*1000:.2f}'
                headers['X-CC-Lab-Version'] = master.APP_VERSION
            return super()._send_json(status_code, payload, headers)

        def authorized(self):
            if valid_authorization(self.headers.get('Authorization', ''), key):
                return True
            self._send_json(401, {'error': 'Private performance lab access required.'},
                            {'WWW-Authenticate': 'Basic realm="CharityClarity performance lab"', 'Cache-Control': 'no-store'})
            return False

        def _send_healthz(self, include_body=True):
            data = {'ok': True, 'app_version': master.APP_VERSION, 'environment': 'performance-lab',
                    'supported_states': master.SUPPORTED_STATES, 'private_access': True,
                    'ny_browser_validation_enabled': False, 'shared_helpers_enabled': False,
                    'downloadable_data': {s: master.downloadable_data_info(s) for s in ('KS','KY','LA','NH','OR')}}
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            if include_body: self.wfile.write(body)

        def _get(self, include_body):
            if self.path in ('/health', '/healthz'):
                return self._send_healthz(include_body)
            if not self.authorized(): return
            if self.path == '/api/lab/metrics':
                with lock: data = dict(telemetry)
                data['app_version'] = master.APP_VERSION
                data['instance'] = os.environ.get('RENDER_INSTANCE_ID', 'local')
                if capacity is not None: data['capacity'] = capacity.snapshot()
                try:
                    import resource
                    data['process_peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                except ImportError: pass
                return self._send_json(200, data, {'Cache-Control':'no-store'})
            asset = lab_asset(self.path)
            if asset:
                body, kind = asset
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                if include_body: self.wfile.write(body)
                return
            # Evidence can trigger work in the master, so it stays private too.
            return super().do_GET() if include_body else super().do_HEAD()

        def do_GET(self): return self._get(True)
        def do_HEAD(self): return self._get(False)

        def do_POST(self):
            if not self.authorized(): return
            if self.path == '/api/ny-connector':
                return self._send_json(503, {'error':'An isolated New York browser collector has not been configured in this lab.'})
            from deployment.lab_capacity import REQUEST_GROUP, REQUEST_TIMING
            group = 'lab:other'
            if self.path in ('/api/check', '/api/discover-names'):
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 131072: raise ValueError('Invalid request size')
                    raw = self.rfile.read(length)
                    payload = json.loads(raw)
                    if not isinstance(payload, dict): raise ValueError('Object required')
                    import re
                    ein = re.sub(r'\D', '', str(payload.get('ein', '')))
                    group = 'lab:' + ein if len(ein) == 9 else 'lab:invalid'
                    self.rfile = io.BytesIO(raw)
                except (ValueError, TypeError):
                    return self._send_json(400, {'error': 'Invalid lab request body.'})
            group_token = REQUEST_GROUP.set(group)
            timing_token = REQUEST_TIMING.set({'started': time.monotonic()})
            with lock:
                telemetry['active_requests'] += 1
                telemetry['peak_requests'] = max(telemetry['peak_requests'], telemetry['active_requests'])
            try:
                return super().do_POST()
            finally:
                REQUEST_TIMING.reset(timing_token)
                REQUEST_GROUP.reset(group_token)
                with lock:
                    telemetry['active_requests'] -= 1
                    telemetry['completed_requests'] += 1
    return LabHandler


def main():
    validate_environment(os.environ)
    install_http_egress_guard()
    import registry_snapshot_server as master
    # Private lab credential, distinct from the existing staging access code.
    master.ADMIN_PASSCODE = os.environ['CE_LAB_ACCESS_KEY']
    capacity = None
    if os.environ.get('CE_LAB_FAIR_CAPACITY') == '1':
        from deployment.lab_capacity import install
        capacity = install(master, int(os.environ['CE_MAX_BROWSER_LOOKUPS']))
    master.RegistrySnapshotHandler = build_handler(master, master.ADMIN_PASSCODE, capacity)
    master.main()


if __name__ == '__main__':
    main()
