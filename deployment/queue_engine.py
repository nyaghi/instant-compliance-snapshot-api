"""Same master engine, isolated task lifetime. No state-specific logic lives here."""
import os
from pathlib import Path
import sys
import json
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FloridaTrace:
    """Lab-only passive timing. Never record headers, cookies or query strings."""
    def __init__(self):
        self.started = time.monotonic()
        self.events = []

    def record(self, event, **details):
        if len(self.events) < 512 or event.startswith('attempt'):
            self.events.append({'seconds': round(time.monotonic()-self.started, 3),
                                'event': event, **details})

    def request(self, event, request, **details):
        try:
            if request.resource_type != 'document': return
            url = urlsplit(request.url)
            self.record(event, request_id=id(request), host=url.hostname, path=url.path,
                        method=request.method, resource_type=request.resource_type, **details)
        except Exception:
            pass  # Diagnostics must never change the registry lookup.

    def wrap(self, original):
        def observed(page, org):
            hooks = {
                'request': lambda r: self.request('request', r),
                'response': lambda r: self.request('response', r.request, status=r.status),
                'requestfinished': lambda r: self.request('requestfinished', r),
                'requestfailed': lambda r: self.request('requestfailed', r, failure=r.failure),
            }
            attached = []
            self.record('attempt_start')
            for event, callback in hooks.items():
                try: page.on(event, callback); attached.append((event, callback))
                except Exception: pass
            try:
                result = original(page, org)
                self.record('attempt_return')
                return result
            except Exception as exc:
                self.record('attempt_exception', exception_type=type(exc).__name__)
                raise
            finally:
                for event, callback in attached:
                    try: page.remove_listener(event, callback)
                    except Exception: pass
        return observed


class DiscoveryProgress:
    """Private child-to-supervisor evidence; never contains organization data.

    Only source functions which have returned can release permits. IRS remains
    held until tree cleanup because WA's alias review also uses IRS metadata.
    Missing/unwritable progress is conservative: keep all unreported permits.
    """
    def __init__(self, output, job):
        self.path = Path(output).with_suffix('.sources.json')
        self.job = job
        self.completed = set()
        self.lock = threading.Lock()

    def __call__(self, source):
        if source == 'IRS' or source not in self.job['resources']: return
        with self.lock:
            self.completed.add(source)
            payload = {'id': self.job['id'], 'token': self.job['token'],
                       'completed': sorted(self.completed)}
            try:
                temp = self.path.with_suffix('.partial')
                temp.write_text(json.dumps(payload), encoding='utf-8')
                temp.replace(self.path)
            except OSError:
                pass


def execute(master, job, source_finished=None):
    if job['version'] != master.APP_VERSION:
        raise ValueError('Master version mismatch')
    p = job['payload']
    if job['state'] == '@discovery':
        if source_finished is None:
            return master.discover_organization_names(p['organization_name'], p['ein'])
        # This master instance belongs to one isolated task process. Observe its
        # existing collectors; do not alter their input, deadlines or results.
        original = master.identity_source_result
        def observed(source, *args, **kwargs):
            try:
                return original(source, *args, **kwargs)
            finally:
                try: source_finished(source)
                except Exception: pass  # Observation cannot change registry evidence.
        master.identity_source_result = observed
        try:
            return master.discover_organization_names(p['organization_name'], p['ein'])
        finally:
            master.identity_source_result = original
    if job['state'] == 'NY' and os.environ.get('CE_LAB_NY_BROWSER') != '1':
        raise ValueError('Isolated NY collector not configured')
    if job['state'] not in master.SUPPORTED_STATES:
        raise ValueError('Unsupported state')
    organizations = master.normalize_organization_requests(p, privileged=False)
    if len(organizations) != 1: raise ValueError('Exactly one organization required')
    trace = FloridaTrace() if job['state'] == 'FL' else None
    original = master.search_fl if trace else None
    if trace: master.search_fl = trace.wrap(original)
    try:
        results = master.run_state_lookups_parallel(organizations, [job['state']])
    finally:
        if trace: master.search_fl = original
    if len(results) != 1: raise ValueError('Unexpected result count')
    if trace: results[0]['lab_fl_trace'] = trace.events
    return results[0]


def run_job(job, output, supervisor_pid=None, warmed=None):
    from deployment.performance_lab import validate_environment, install_http_egress_guard
    validate_environment(os.environ)
    install_http_egress_guard()
    if os.name != 'nt':
        import threading, time, signal
        parent = os.getppid()
        deadline = min(time.monotonic()+job['run_seconds'], job.get('_deadline_monotonic', float('inf')))
        def guard():
            while time.monotonic() < deadline and os.getppid() == parent:
                if supervisor_pid:
                    from deployment.queue_worker import process_running
                    if not process_running(supervisor_pid): break
                time.sleep(.25)
            os.killpg(os.getpgrp(), signal.SIGKILL)
        threading.Thread(target=guard, daemon=True).start()
    import time
    import_started, cpu_started = time.monotonic(), time.process_time()
    if warmed is None:
        import registry_snapshot_server as master
    else:
        master = warmed.master
    import_seconds, import_cpu = time.monotonic()-import_started, time.process_time()-cpu_started
    # The child has a private result file. Logs never mix into the result payload.
    execution_started, cpu_started = time.monotonic(), time.process_time()
    progress = DiscoveryProgress(output, job) if job['state'] == '@discovery' else None
    result = execute(master, job, progress)
    result['lab_task_metrics'] = {'import_seconds': import_seconds, 'import_cpu_seconds': import_cpu,
        'execution_seconds': time.monotonic()-execution_started, 'execution_cpu_seconds': time.process_time()-cpu_started}
    result['lab_task_metrics']['engine_preloaded'] = warmed is not None
    if warmed is not None:
        result['lab_task_metrics']['template_pid'] = warmed.PRELOAD_PID
        result['lab_task_metrics']['template_import_cpu_seconds'] = warmed.IMPORT_CPU_SECONDS
    if os.name != 'nt':
        import resource
        children = resource.getrusage(resource.RUSAGE_CHILDREN)
        result['lab_task_metrics'].update(child_cpu_seconds=children.ru_utime+children.ru_stime,
            self_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, child_peak_rss_kib=children.ru_maxrss)
    output = Path(output)
    temp = output.with_suffix('.partial')
    temp.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    temp.replace(output)
    # Discovery can leave deadline-exceeded executor threads alive. The parent
    # kills/reaps the process tree before accepting this saved result.


def prepare_forked_child(log_path, ready, env):
    """One isolated child of an organization-free, single-threaded template."""
    os.setsid()
    with open(log_path, 'ab', buffering=0) as log:
        os.dup2(log.fileno(),1); os.dup2(log.fileno(),2)
    os.environ.clear(); os.environ.update(env)
    from deployment import engine_preload as warmed
    if warmed.PRELOAD_PID != os.getppid():
        raise RuntimeError('Warm template was not preloaded by the forkserver')
    ready.send(os.getpid())
    if not ready.poll(8) or ready.recv() != 'accepted':
        raise RuntimeError('Supervisor did not accept isolated child')
    ready.close()
    return warmed


def forked_main(job, output, log_path, ready, supervisor_pid, env):
    warmed = prepare_forked_child(log_path, ready, env)
    run_job(job, output, supervisor_pid=supervisor_pid, warmed=warmed)


def main():
    run_job(json.load(sys.stdin),sys.argv[1])


if __name__ == '__main__': main()
