"""Local capacity experiment, not imported by the application.

One coordinator owns admission across all supplied worker pools. Adapters receive
the unchanged state request and a cooperative deadline/cancellation control.
No URLs, credentials, registry implementations, or automatic retries live here.
The coordinator is intentionally in-memory: durable leases/HA are still required
before this design can be used by independently replicated production gateways.
"""
from __future__ import annotations

import copy
import math
import threading
import time
from collections import Counter, deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable


def ein_key(value):
    return ''.join(c for c in str(value) if c.isdigit())


class Stopped(Exception):
    pass


class Control:
    def __init__(self, deadline):
        self.deadline = deadline
        self.event = threading.Event()

    def checkpoint(self):
        if self.event.is_set() or time.monotonic() >= self.deadline:
            raise Stopped('Lookup canceled or deadline reached')

    def wait(self, seconds):
        self.checkpoint()
        self.event.wait(min(seconds, max(0, self.deadline - time.monotonic())))
        self.checkpoint()


@dataclass(frozen=True)
class Request:
    task_id: str
    payload: dict
    resource: str = 'browser'
    registry_key: str = ''


@dataclass
class Worker:
    name: str
    pool: str
    limits: dict[str, int]
    execute: Callable
    healthy: bool = True
    active: Counter = field(default_factory=Counter)
    last_dispatch: int = 0


@dataclass
class Job:
    request: Request
    future: Future
    control: Control
    enqueued: float


@dataclass
class Workflow:
    key: tuple[str, str]
    pending: deque
    running: dict = field(default_factory=dict)
    admitted: bool = False
    stopped: bool = False


class CapacityRouter:
    def __init__(self, workers, max_workflows=15, per_workflow=15, registry_limits=None, registry_intervals=None):
        if not workers or max_workflows < 1 or per_workflow < 1:
            raise ValueError('Positive capacity and workers are required')
        if len({w.name for w in workers}) != len(workers):
            raise ValueError('Worker names must be unique')
        if any(not w.limits or any(v < 1 for v in w.limits.values()) for w in workers):
            raise ValueError('Worker limits must be positive')
        self.workers = workers
        self.max_workflows, self.per_workflow = max_workflows, per_workflow
        self.registry_limits = registry_limits or {}
        self.registry_intervals = registry_intervals or {}
        if any(v < 1 for v in self.registry_limits.values()) or any(v < 0 for v in self.registry_intervals.values()):
            raise ValueError('Registry limits/intervals must be positive/nonnegative')
        self.registry_active = Counter()
        self.registry_ready = Counter()
        self.cv = threading.Condition(threading.RLock())
        self.flows = {}
        self.order = deque()
        self.trace = []
        self.sequence = 0
        self.closing = False
        self.executor = ThreadPoolExecutor(max_workers=sum(sum(w.limits.values()) for w in workers))
        self.thread = threading.Thread(target=self._pump, name='local-capacity-coordinator', daemon=True)
        self.thread.start()

    def submit(self, workspace, workflow_id, requests, deadline):
        key = (workspace, workflow_id)
        requests = list(requests)
        if not math.isfinite(deadline):
            raise ValueError('A finite deadline is required')
        if not workspace or not workflow_id or not requests:
            raise ValueError('Workspace, workflow ID, and requests are required')
        if len({r.task_id for r in requests}) != len(requests):
            raise ValueError('Duplicate task IDs within workflow')
        if len({ein_key(r.payload.get('ein')) for r in requests}) != 1:
            raise ValueError('One workflow must belong to exactly one organization EIN')
        for r in requests:
            if len(ein_key(r.payload.get('ein'))) != 9 or not r.payload.get('state'):
                raise ValueError('Every task must identify its EIN and state')
            if not any(w.limits.get(r.resource, 0) for w in self.workers):
                raise ValueError('No worker can execute the requested resource class')
        with self.cv:
            if self.closing or key in self.flows:
                raise ValueError('Router closed or workflow already exists')
            # Do not allow a caller to mutate an admitted identity or alias list.
            jobs = [Job(copy.deepcopy(r), Future(), Control(deadline), time.monotonic()) for r in requests]
            self.flows[key] = Workflow(key, deque(jobs))
            self.order.append(key)
            self.cv.notify_all()
            return {j.request.task_id: j.future for j in jobs}

    def _outcome(self, job, reason):
        p = job.request.payload
        return {'ein': p['ein'], 'state': p['state'], 'organization_name': p.get('organization_name', ''),
                'success': False, 'status': 'Unable to Confirm', 'status_reason': reason,
                'comments': 'The lookup did not complete with confirmed evidence. No negative registration conclusion was drawn.'}

    def _stop_job(self, job, reason):
        job.control.event.set()
        if not job.future.done():
            job.future.set_result(self._outcome(job, reason))

    def cancel(self, workspace, workflow_id):
        with self.cv:
            flow = self.flows.get((workspace, workflow_id))
            if flow is None:
                return False
            flow.stopped = True
            for job in list(flow.pending) + list(flow.running.values()):
                self._stop_job(job, 'WORKFLOW_CANCELED')
            flow.pending.clear()
            self.cv.notify_all()
            return True

    def set_health(self, worker_name, healthy):
        with self.cv:
            next(w for w in self.workers if w.name == worker_name).healthy = healthy
            self.cv.notify_all()

    def _available_worker(self, job):
        r = job.request
        if time.monotonic() < self.registry_ready[r.registry_key]:
            return None
        if r.registry_key in self.registry_limits:
            if self.registry_active[r.registry_key] >= self.registry_limits[r.registry_key]:
                return None
        candidates = [w for w in self.workers if w.healthy and w.active[r.resource] < w.limits.get(r.resource, 0)]
        if not candidates:
            return None
        return min(candidates, key=lambda w: (sum(w.active.values()) / sum(w.limits.values()), w.last_dispatch))

    def _record(self, event, flow, job=None, worker=None, **extra):
        self.trace.append({'event': event, 'at': time.monotonic(), 'workspace': flow.key[0],
                           'workflow': flow.key[1], 'task': job.request.task_id if job else None,
                           'worker': worker.name if worker else None, 'pool': worker.pool if worker else None,
                           'active_workflows': sum(f.admitted for f in self.flows.values()),
                           'active_tasks': sum(len(f.running) for f in self.flows.values()), **extra})

    def _pump(self):
        with self.cv:
            while True:
                now = time.monotonic()
                for flow in list(self.flows.values()):
                    retained = deque()
                    for job in flow.pending:
                        if now >= job.control.deadline:
                            self._stop_job(job, 'DEADLINE_EXCEEDED')
                        else:
                            retained.append(job)
                    flow.pending = retained
                    for job in flow.running.values():
                        if now >= job.control.deadline:
                            self._stop_job(job, 'DEADLINE_EXCEEDED')
                    if not flow.pending and not flow.running:
                        self._record('workflow_drained', flow)
                        del self.flows[flow.key]
                        self.order.remove(flow.key)
                if self.closing and not self.flows:
                    return
                admitted = sum(f.admitted for f in self.flows.values())
                for key in self.order:
                    flow = self.flows[key]
                    if not flow.admitted and admitted < self.max_workflows:
                        flow.admitted = True
                        admitted += 1
                        self._record('workflow_admitted', flow)
                dispatched = False
                last_dispatched = None
                # Round robin across workflows, one dispatch per workflow per pass.
                for key in list(self.order):
                    flow = self.flows[key]
                    if not flow.admitted or flow.stopped or len(flow.running) >= self.per_workflow:
                        continue
                    for job in flow.pending:
                        worker = self._available_worker(job)
                        if worker:
                            flow.pending.remove(job)
                            flow.running[job.request.task_id] = job
                            worker.active[job.request.resource] += 1
                            self.registry_active[job.request.registry_key] += 1
                            self.sequence += 1
                            worker.last_dispatch = self.sequence
                            self._record('dispatch', flow, job, worker, queue_seconds=now - job.enqueued,
                                         worker_active=dict(worker.active), workflow_active=len(flow.running))
                            self.executor.submit(self._execute, flow, job, worker)
                            dispatched = True
                            last_dispatched = key
                            break
                if last_dispatched is not None:
                    while self.order[0] != last_dispatched:
                        self.order.rotate(-1)
                    self.order.rotate(-1)
                if not dispatched:
                    self.cv.wait(.005)

    def _execute(self, flow, job, worker):
        try:
            job.control.checkpoint()
            result = worker.execute(copy.deepcopy(job.request.payload), job.control)
            job.control.checkpoint()
            if result.get('state') != job.request.payload['state'] or ein_key(result.get('ein')) != ein_key(job.request.payload['ein']):
                raise ValueError('Worker returned a different organization/state identity')
        except Stopped:
            result = self._outcome(job, 'DEADLINE_OR_CANCELLATION')
        except Exception:
            result = self._outcome(job, 'WORKER_RESPONSE_UNCONFIRMED')
        with self.cv:
            if not job.future.done():
                job.future.set_result(copy.deepcopy(result))
            # A client deadline never frees a slot while work is still running.
            worker.active[job.request.resource] -= 1
            self.registry_active[job.request.registry_key] -= 1
            self.registry_ready[job.request.registry_key] = time.monotonic() + self.registry_intervals.get(job.request.registry_key, 0)
            flow.running.pop(job.request.task_id)
            self._record('finished', flow, job, worker)
            self.cv.notify_all()

    def drain(self, timeout=10):
        end = time.monotonic() + timeout
        with self.cv:
            while self.flows:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Workers have not released capacity')
                self.cv.wait(min(.02, remaining))

    def close(self):
        with self.cv:
            self.closing = True
            for key in list(self.flows):
                self.cancel(*key)
            self.cv.notify_all()
        self.thread.join(timeout=10)
        if self.thread.is_alive():
            raise TimeoutError('Uncooperative worker remains active')
        self.executor.shutdown(wait=True)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
