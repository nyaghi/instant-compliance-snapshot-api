"""Lab supervisor for isolated master tasks and durable claims.

The supervisor, not a client HTTP timeout, owns task termination. Each task runs
in a process tree that is killed and reaped before its reservation is released.
Linux uses a private process group, Windows uses a kill-on-close Job Object.
No customer browser/profile is opened; master uses its own headless browsers.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def process_running(pid):
    if os.name == 'nt':
        import win32api, win32process, win32con, pywintypes
        try: handle = win32api.OpenProcess(win32con.PROCESS_QUERY_INFORMATION, False, pid)
        except pywintypes.error as exc:
            if exc.winerror == 87: return False
            raise
        try: return win32process.GetExitCodeProcess(handle) == win32con.STILL_ACTIVE
        finally: handle.Close()
    try: return Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()[0] not in ('Z','X')
    except FileNotFoundError: return False


def group_running(group):
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(') ',1)[1].split()
            if int(fields[2]) == group and fields[0] not in ('Z','X'): return True
        except (FileNotFoundError, ProcessLookupError): pass
    return False


class ProcessTree:
    def __init__(self, command, input_data, directory, env=None):
        self.log = (Path(directory)/'task.log').open('wb')
        self.handle = None
        if os.name == 'nt':
            # pywin32 is a lab-only Windows dependency. Suspended launch prevents
            # children escaping assignment to the kill-on-close Job Object.
            import win32api, win32con, win32job, win32process
            self.handle = win32job.CreateJobObject(None, '')
            limits = win32job.QueryInformationJobObject(self.handle, win32job.JobObjectExtendedLimitInformation)
            limits['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(self.handle, win32job.JobObjectExtendedLimitInformation, limits)
            # Input is a private bounded file opened by a small bootstrap, avoiding
            # inheritable pipe handles leaking to Chromium descendants.
            path = Path(directory)/'input.json'
            path.write_text(json.dumps(input_data), encoding='utf-8')
            bootstrap = "import sys,runpy;sys.stdin=open(sys.argv.pop(1),encoding='utf-8');sys.argv=sys.argv[1:];runpy.run_path(sys.argv[0],run_name='__main__')"
            args = [command[0], '-c', bootstrap, str(path), *command[1:]]
            startup = win32process.STARTUPINFO()
            hp, ht, pid, _ = win32process.CreateProcess(None, subprocess.list2cmdline(args), None, None, False,
                    win32con.CREATE_SUSPENDED | win32con.CREATE_NO_WINDOW, env, str(ROOT), startup)
            try:
                win32job.AssignProcessToJobObject(self.handle, hp)
                win32process.ResumeThread(ht)
            except BaseException:
                win32process.TerminateProcess(hp, 1)
                raise
            finally: ht.Close()
            self.process, self.pid = hp, pid
        else:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=self.log, stderr=self.log,
                                            cwd=ROOT, env=env, start_new_session=True)
            self.pid = self.process.pid
            self.process.stdin.write(json.dumps(input_data).encode())
            self.process.stdin.close()

    def poll(self):
        if os.name != 'nt': return self.process.poll()
        import win32process, win32con
        value = win32process.GetExitCodeProcess(self.process)
        return None if value == win32con.STILL_ACTIVE else value

    def stop(self):
        if self.log.closed: return
        if os.name == 'nt':
            import win32job, win32event
            win32job.TerminateJobObject(self.handle, 1)
            if win32event.WaitForSingleObject(self.process, 10000) != win32event.WAIT_OBJECT_0:
                raise RuntimeError('Task termination not confirmed')
            # Active-process accounting verifies descendants, not just the parent.
            end = time.monotonic()+10
            while win32job.QueryInformationJobObject(self.handle, win32job.JobObjectBasicAccountingInformation)['ActiveProcesses']:
                if time.monotonic() >= end: raise RuntimeError('Task descendants still alive')
                time.sleep(.05)
            self.process.Close(); self.handle.Close()
        else:
            try: os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            self.process.wait(timeout=10)
            end = time.monotonic()+10
            while group_running(self.pid):
                if time.monotonic() >= end: raise RuntimeError('Task descendants still alive')
                time.sleep(.05)
        self.log.close()


class ResourceAdmission:
    """Lab-only launch pacing; existing tasks always retain their reservations.

    Extra slots are usable only with cgroup CPU/memory evidence. Missing metrics
    retain the original eight-slot ceiling; they never imply unlimited capacity.
    """
    def __init__(self, root=Path('/sys/fs/cgroup'), clock=time.monotonic):
        self.root, self.clock = root, clock
        self.previous = None
        self.last_launch = float('-inf')
        self.snapshot = {}

    def limit(self, configured, used):
        now = self.clock()
        if now-self.last_launch < .25:
            self.snapshot['reason'] = 'launch_pacing'
            return used
        try:
            quota, period = (self.root/'cpu.max').read_text().split()
            cores = int(quota)/int(period)
            if cores <= 0: raise ValueError('Invalid CPU allocation')
            counters = dict(line.split() for line in (self.root/'cpu.stat').read_text().splitlines())
            cpu = int(counters['usage_usec'])/1_000_000
            memory = int((self.root/'memory.current').read_text())
            maximum = int((self.root/'memory.max').read_text())
            if not 0 <= memory <= maximum or maximum <= 0: raise ValueError('Invalid memory allocation')
            previous = self.previous
            # Keep a >=250 ms interval so short samples do not swing the gate.
            if previous is None or now-previous[0] >= .25:
                self.previous = (now,cpu)
            utilization = ((cpu-previous[1])/(now-previous[0])/cores
                if previous and now>previous[0] and cpu>=previous[1] else None)
            self.snapshot = {'cpu_fraction': utilization, 'memory_bytes':memory,
                'memory_limit_bytes':maximum,'configured_slots':configured,'reason':'available'}
            # Leave space for a new master process and its browser, if required.
            if memory + 384*1024*1024 > .85*maximum:
                self.snapshot['reason']='memory_headroom'
                return used
            if utilization is not None and utilization >= .85:
                self.snapshot['reason']='cpu_pressure'
                return used
            if utilization is None:
                self.snapshot['reason']='cpu_warmup'
                return min(configured,8)
            return configured
        except (OSError, ValueError, KeyError, ZeroDivisionError):
            self.snapshot={'reason':'metrics_unavailable','configured_slots':configured}
            return min(configured,8)

    def launched(self): self.last_launch=self.clock()


class AdmissionWindow:
    """Constant-size observations; never make scheduling decisions."""
    def __init__(self, now):
        self.started = self.last = now
        self.reason = 'starting'
        self.seconds = Counter()
        self.counts = Counter()
        self.had_work = False

    def observe(self, reason, now, had_work=False):
        self.seconds[self.reason] += max(0, now-self.last)
        self.last, self.reason = now, reason
        self.counts[reason] += 1
        self.had_work |= had_work

    def snapshot(self, now):
        seconds = self.seconds.copy()
        seconds[self.reason] += max(0, now-self.last)
        return {'window_seconds': max(0, now-self.started),
            'seconds_by_reason': dict(seconds), 'counts_by_reason': dict(self.counts)}

    def reset(self, now):
        self.started = self.last = now
        self.seconds.clear(); self.counts.clear(); self.had_work = False


class Supervisor:
    def __init__(self, queue, version, slots=8, command=None, env=None):
        self.queue, self.version, self.slots = queue, version, slots
        self.id = os.environ.get('RENDER_INSTANCE_ID', 'local')+'-'+uuid.uuid4().hex
        self.command = command or [sys.executable, str(ROOT/'deployment/queue_engine.py')]
        self.env = env
        settings=os.environ if env is None else env
        self.admission = ResourceAdmission() if settings.get('CE_LAB_RESOURCE_ADMISSION') == '1' else None
        self.stop_event = threading.Event()
        self.active = {}
        self.observations = AdmissionWindow(time.monotonic())
        self.queue.register_worker(self.id, version, slots)

    def stop(self): self.stop_event.set()

    def run(self):
        last_heartbeat = time.monotonic()
        next_heartbeat = 0
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now >= next_heartbeat:
                    try:
                        observed = self.observations.snapshot(now) if self.observations.had_work else None
                        self.observations.observe('heartbeat_transaction',now,bool(self.active))
                        allowed = self.queue.heartbeat(self.id, [(j, r['job']['token']) for j, r in self.active.items()],
                            observation=observed)
                        self.observations.reset(now)
                        last_heartbeat = time.monotonic()
                        for ident, r in self.active.items():
                            if ident not in allowed: r['stop_reason'] = 'LEASE_OR_WORKFLOW_STOP'
                    except Exception:
                        # Cannot renew => stop locally well before the 20s lease.
                        if time.monotonic()-last_heartbeat >= 8:
                            for r in self.active.values(): r['stop_reason'] = 'QUEUE_CONNECTION_LOST'
                    next_heartbeat = time.monotonic()+3
                for ident, r in list(self.active.items()):
                    if r.get('terminated'): continue
                    output_ready = r['output'].is_file()
                    exited = r['tree'].poll() is not None
                    if time.monotonic() >= r['deadline']: r['stop_reason'] = 'TASK_TIME_LIMIT'
                    if output_ready or exited or r.get('stop_reason'):
                        result, error = None, r.get('stop_reason')
                        if output_ready and not error:
                            try: result = json.loads(r['output'].read_text(encoding='utf-8'))
                            except (ValueError, OSError): error = 'INVALID_WORKER_OUTPUT'
                        if result is None and not error: error = 'WORKER_TASK_FAILED'
                        r['tree'].stop()  # Must succeed before releasing capacity.
                        try:
                            self.queue.complete(self.id, ident, r['job']['token'], result, error)
                        except ValueError:
                            self.queue.complete(self.id, ident, r['job']['token'], error='WORKER_RESULT_REJECTED')
                        except Exception:
                            # Persisted claim stays reserved. Recovery is retried.
                            r['terminated'] = True
                            r['result'], r['error'] = result, error
                            continue
                        r['temp'].cleanup()
                        del self.active[ident]
                # If result persistence failed, retry without touching dead handles.
                for ident, r in list(self.active.items()):
                    if r.get('terminated'):
                        try: self.queue.complete(self.id, ident, r['job']['token'], r['result'], r['error'])
                        except Exception: continue
                        r['temp'].cleanup(); del self.active[ident]
                used = sum(r['job']['weight'] for r in self.active.values())
                ceiling = self.admission.limit(self.slots,used) if self.admission else self.slots
                reason = ('physical_slots' if used >= self.slots else
                    (self.admission.snapshot.get('reason', 'available') if self.admission else 'available'))
                self.observations.observe(reason, time.monotonic(), bool(self.active))
                if used < ceiling and time.monotonic()-last_heartbeat < 8:
                    claim_started = time.monotonic()
                    self.observations.observe('claim_transaction', claim_started, bool(self.active))
                    try: job = self.queue.claim(self.id,slot_limit=ceiling,
                        admission_evidence=dict(self.admission.snapshot) if self.admission else None)
                    except Exception:
                        job = None
                        self.observations.observe('claim_error', time.monotonic(), bool(self.active))
                    else:
                        self.observations.observe('launch' if job else 'no_eligible_job', time.monotonic(), bool(self.active) or bool(job))
                    if job:
                        temp = tempfile.TemporaryDirectory(prefix='cc-lab-task-')
                        output = Path(temp.name)/'result.json'
                        try:
                            deadline = claim_started+job['run_seconds']
                            child_job = {**job, 'run_seconds': max(0, deadline-time.monotonic())}
                            child_env = dict(os.environ if self.env is None else self.env)
                            child_env.pop('CE_LAB_DATABASE_URL', None)
                            child_env.pop('CE_TEST_DATABASE_URL', None)
                            child_env.pop('RENDER_API_KEY', None)
                            child_env['CE_LAB_DURABLE_QUEUE'] = '0'
                            tree = ProcessTree([*self.command, str(output)], child_job, temp.name, child_env)
                            self.active[job['id']] = dict(job=job, tree=tree, temp=temp, output=output,
                                                        deadline=deadline)
                            if self.admission:self.admission.launched()
                        except Exception:
                            self.queue.complete(self.id, job['id'], job['token'], error='WORKER_START_FAILED')
                            temp.cleanup()
                        continue
                self.stop_event.wait(.1 if self.active else .5)
        finally:
            all_stopped = True
            for r in self.active.values():
                try:
                    if not r.get('terminated'): r['tree'].stop()
                    r['temp'].cleanup()
                except Exception: all_stopped = False
            if all_stopped:
                # Requeues only after actual local process-tree termination.
                self.queue.confirm_worker_stopped(self.id, 'Supervisor shutdown: all owned process trees terminated and reaped')


def main():
    from deployment.performance_lab import validate_environment
    from deployment.durable_queue import Queue
    validate_environment(os.environ)
    queue = Queue(os.environ['CE_LAB_DATABASE_URL'], ny_enabled=os.environ.get('CE_LAB_NY_BROWSER') == '1')
    supervisor = Supervisor(queue, os.environ['CE_APP_VERSION'], int(os.environ.get('CE_LAB_WORKER_SLOTS', '8')))
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, lambda *args: supervisor.stop())
    try: supervisor.run()
    finally: queue.close()


if __name__ == '__main__': main()
