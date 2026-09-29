"""Loopback-only HTTP replay of saved state responses through candidate routing.

Registry durations are compressed 100x to keep this invisible and inexpensive.
Neither elapsed wall time nor scaled time is a live performance prediction.
"""
import argparse
import copy
import hashlib
import json
import random
import socket
import threading
import time
import urllib.request
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from router import CapacityRouter, Request, Worker


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load_cases(root):
    eligible = []
    for folder in sorted((root / 'outputs/overnight171-capacity-20260923/checks').iterdir()):
        rows = [json.loads(p.read_text(encoding='utf-8-sig')) for p in sorted(folder.glob('*.json'))]
        if len(rows) == 30 and all(isinstance(r.get('result'), dict) and r['result'].get('ein') and r['result'].get('state') for r in rows):
            eligible.append(rows)
    cases = random.Random(20260924).sample(eligible, 15)
    return cases


def run(root, out):
    cases = load_cases(root)
    fixtures = {}
    for rows in cases:
        for row in rows:
            key = f"{row['case_id']}:{row['state']}"
            fixtures[key] = row
    scale = 100
    tokens, requests_seen = {}, []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            item = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            key, payload = item['key'], item['payload']
            row = fixtures[key]
            # Fail closed on any loss/change of discovered names or identity.
            assert payload['ein'] == row['ein'] and payload['state'] == row['state']
            assert payload['alternate_names'] == row['alternate_names']
            assert payload['organization_name'] == row['submitted_name']
            with lock:
                control = tokens[item['token']]
                requests_seen.append(key)
            try:
                control.wait(max(.001, float(row.get('seconds', 0)) / scale))
                body = json.dumps(row['result'], ensure_ascii=False).encode()
                self.send_response(200)
            except Exception:
                body = b'{"error":"local replay canceled"}'
                self.send_response(409)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    servers = [ThreadingHTTPServer(('127.0.0.1', 0), Handler) for _ in range(2)]
    for s in servers:
        s.daemon_threads = True
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for t in threads:
        t.start()
    real_connect = socket.socket.connect

    def loopback_only(sock, address):
        if address[0] != '127.0.0.1':
            raise AssertionError('External network is prohibited in this experiment')
        return real_connect(sock, address)

    socket.socket.connect = loopback_only
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    summaries = []
    try:
        # Equal-total-capacity control separates routing from extra worker slots.
        for pools, slots_per_worker in ((1, 2), (2, 1), (2, 2)):
            workers = []
            for pool in range(pools):
                url = f'http://127.0.0.1:{servers[pool].server_port}/api/check'
                def execute(payload, control, url=url):
                    key = payload.pop('_fixture_key')
                    token = str(id(control))
                    with lock:
                        tokens[token] = control
                    try:
                        wire = json.dumps({'key': key, 'payload': payload, 'token': token}).encode()
                        req = urllib.request.Request(url, data=wire, headers={'Content-Type': 'application/json'})
                        with opener.open(req, timeout=10) as response:
                            return json.load(response)
                    finally:
                        with lock:
                            tokens.pop(token, None)
                workers.extend(Worker(f'pool-{pool}-worker-{i}', f'pool-{pool}', {'browser': slots_per_worker}, execute) for i in range(6))
            started = time.monotonic()
            with CapacityRouter(workers, max_workflows=15) as router:
                futures, expected = {}, {}
                for rows in cases:
                    jobs = []
                    for row in rows:
                        key = f"{row['case_id']}:{row['state']}"
                        payload = {'ein': row['ein'], 'state': row['state'], 'organization_name': row['submitted_name'],
                                   'alternate_names': copy.deepcopy(row['alternate_names']), '_fixture_key': key}
                        jobs.append(Request(key, payload))
                        expected[key] = row['result']
                    futures.update(router.submit('recorded-controls', rows[0]['case_id'], jobs, started + 90))
                results = {key: future.result(90) for key, future in futures.items()}
                router.drain(10)
                duration = time.monotonic() - started
                mismatches = [key for key in expected if digest(expected[key]) != digest(results[key])]
                dispatch = [e for e in router.trace if e['event'] == 'dispatch']
                assert not mismatches, mismatches
                assert len(dispatch) == len(expected) == 450
                assert all(e['worker_active']['browser'] <= slots_per_worker and e['active_workflows'] <= 15 for e in dispatch)
                summaries.append({'pools': pools, 'workers': 6 * pools, 'configured_slots': 6 * pools * slots_per_worker,
                                  'organizations': 15, 'recorded_responses': 450, 'changed_responses': len(mismatches),
                                  'wall_seconds': round(duration, 3), 'peak_active_tasks': max(e['active_tasks'] for e in dispatch),
                                  'requests_by_pool': dict(Counter(e['pool'] for e in dispatch)),
                                  'median_queue_seconds': sorted(e['queue_seconds'] for e in dispatch)[len(dispatch) // 2]})
                (out / f'replay-{pools}-pool-{slots_per_worker}-slots-trace.json').write_text(json.dumps(router.trace, indent=2), encoding='utf-8')
        assert len(requests_seen) == 1350
        report = {'kind': 'LOCAL RECORDED RESPONSE REPLAY, NOT LIVE VALIDATION',
                  'duration_compression': scale, 'network': '127.0.0.1 only; external socket connections rejected',
                  'source': 'Saved overnight171 check files, September 23-24. Their old failures are deliberately preserved.',
                  'coverage': '15 different organizations, 30 recorded non-NY states each; no FL or NY in these fixture files.',
                  'cases': [{'case_id': rows[0]['case_id'], 'ein': rows[0]['ein'], 'organization': rows[0]['organization']} for rows in cases],
                  'input_snapshot_sha256': digest(fixtures), 'runs': summaries,
                  'observed_local_replay_speedup': summaries[0]['wall_seconds'] / summaries[2]['wall_seconds']}
        (out / 'recorded-replay-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, indent=2))
    finally:
        socket.socket.connect = real_connect
        for s in servers:
            s.shutdown()
            s.server_close()
        for t in threads:
            t.join(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    run(args.root, args.out)
