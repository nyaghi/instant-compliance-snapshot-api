"""Passive, bounded staging diagnostics. Never log arguments, tokens or page bodies.

Resource IDs are process-local; events from different processes must not be
treated as sharing a resource. Durations are nested, not additive.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from collections.abc import Mapping
import math
import json
import os
import threading
import time
from urllib.parse import urlsplit

ACTIVE = ContextVar('workflow_observation', default=None)
SINK = ContextVar('workflow_observation_sink', default=None)
PARENT = ContextVar('workflow_observation_parent', default=None)
_lock = threading.RLock()
_resources = {}


class Observation:
    def __init__(self, run_id, state, deadline=float('inf'), cap=1200):
        self.run_id, self.state, self.deadline = run_id, state, deadline
        self.cap = cap
        # Playwright callbacks run in a different greenlet Context. Bind this
        # run's journal now so callbacks cannot silently lose the failure log.
        self.sink = SINK.get()
        self.tail = []
        self.started = time.perf_counter()
        self.epoch = time.time()
        self.events, self.failures, self.pending = [], [], {}
        self.sequence = self.dropped = self.failures_dropped = 0
        self.resources = {}

    def remaining(self, deadline=None):
        value = self.deadline if deadline is None else deadline
        return round(value-time.monotonic(), 6) if isinstance(value,(int,float)) and math.isfinite(value) else None

    def emit(self, stage, outcome, **fields):
        # Diagnostic failure must never change the wrapped operation.
        try:
            self.sequence += 1
            event = dict(seq=self.sequence, at_seconds=round(time.perf_counter()-self.started,6),
                         stage=stage, outcome=outcome, parent=PARENT.get(),
                         deadline_remaining_seconds=self.remaining(), **fields)
            # Validate before retention, not only when the journal is written.
            # A diagnostic object must never poison the worker's result JSON.
            try:
                json.dumps(event, allow_nan=False)
            except (TypeError, ValueError, OverflowError):
                event = dict(seq=self.sequence,
                             at_seconds=round(time.perf_counter()-self.started,6),
                             stage='observer.invalid_event', outcome='rejected',
                             error_type='NonJSONDiagnostic')
            if len(self.events)<self.cap:self.events.append(event)
            else:self.dropped += 1
            self.tail.append(event)
            if len(self.tail)>120:self.tail.pop(0)
            sink=self.sink
            if sink is not None:sink.write(self.run_id,self.state,event)
            if event['outcome'] in ('exception','ownership_conflict','rejected'):
                if len(self.failures)>=100:self.failures.pop(0);self.failures_dropped+=1
                self.failures.append(event)
            return self.sequence
        except Exception:return None

    def resource(self, value, owner=None):
        if value is None:return None
        # Hold references for this trace to prevent id reuse; bounded by cap.
        ident=id(value)
        if ident not in self.resources and len(self.resources)<self.cap:
            self.resources[ident]=value
        if ident not in self.resources:return None
        with _lock:
            entry=_resources.get(ident)
            if entry is None:
                entry=dict(owner=owner, users={})
                _resources[ident]=entry
            elif owner and entry['owner'] is None:entry['owner']=owner
            return ident,entry

    def export(self):
        return dict(schema=1, run_id=self.run_id, state=self.state, process_id=os.getpid(),
                    clock='process monotonic; epoch is for approximate cross-process alignment',
                    started_epoch_seconds=self.epoch, durations='nested; do not sum parents and children',
                    events=list(self.events), terminal_events=list(self.tail), failures=list(self.failures), pending=list(self.pending.values()),
                    dropped_events=self.dropped, dropped_failures=self.failures_dropped,
                    coverage_complete=False)

    def release(self):
        with _lock:
            for ident in self.resources:
                entry=_resources.get(ident)
                if entry and entry['owner'] in (None,self.run_id) and not entry['users']:_resources.pop(ident,None)
        self.resources.clear()


class Journal:
    def __init__(self,path):
        self.fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
        self.bytes=0;self.rotations=0;self.lock=threading.Lock()
    def write(self,run_id,state,event):
        try:
            with self.lock:
                raw=(json.dumps(dict(run_id=run_id,state=state,journal_rotations=self.rotations,event=event),separators=(',',':'))+'\n').encode()
                if self.bytes+len(raw)>1_000_000:
                    os.ftruncate(self.fd,0);self.bytes=0;self.rotations+=1
                self.bytes+=os.write(self.fd,raw)
        except Exception:pass
    def close(self):
        try:os.close(self.fd)
        except Exception:pass


@contextmanager
def observation_sink(path):
    try:sink=Journal(path)
    except Exception:sink=None
    token=SINK.set(sink)
    try:yield
    finally:
        SINK.reset(token)
        if sink:sink.close()


def recover_failed_trace(record,error):
    if not error:return
    try:
        path=record['output'].with_suffix('.workflow.ndjson')
        if not path.is_file() or path.stat().st_size>1_000_000:return
        rows=[]
        for line in path.read_text(encoding='utf-8').splitlines()[-48:]:
            try:rows.append(json.loads(line))
            except ValueError:pass
        print(json.dumps(dict(type='workflow_terminal_trace',job_id=str(record['job'].get('id','')),
          state=record['job'].get('state'),error=error,tail=rows)),flush=True)
    except Exception:pass


def trace_return(stage,value):
    trace=ACTIVE.get()
    if trace:trace.emit(stage,'branch_return', return_kind='none' if value is None else type(value).__name__)
    return value


def workflow_call(stage, function, scope, *args, **kwargs):
    trace=ACTIVE.get()
    if trace is None:return function(*args,**kwargs)
    receiver=getattr(function,'__self__',None)
    # In-memory dictionary/context reads are not workflow operations. Recording
    # every get exhausts the bounded trace before the source/capture steps.
    if getattr(function,'__name__','')=='get' and isinstance(receiver,(Mapping,ContextVar)):
        return function(*args,**kwargs)
    started=time.perf_counter()
    entry=trace.resource(receiver)
    resource_id=None
    if entry:
        resource_id,resource=entry
        with _lock:
            peers=[dict(run_id=k[0],thread_id=k[1],count=v) for k,v in resource['users'].items()]
            own=(trace.run_id,threading.get_ident())
            conflict=resource['owner'] is not None and resource['owner']!=trace.run_id
            resource['users'][own]=resource['users'].get(own,0)+1
        trace.emit(stage,'ownership_conflict' if conflict else 'resource_observed',
                   resource_id=resource_id,owner_run_id=resource['owner'],active_peers=peers)
    allowance=scope.get('stop') if isinstance(scope,dict) else None
    timeout=kwargs.get('timeout')
    seq=trace.emit(stage,'started',resource_id=resource_id,
                   allowance_remaining_seconds=trace.remaining(allowance) if allowance is not None else None,
                   requested_timeout_seconds=timeout/(1 if stage=='source.http' or getattr(function,'__name__','')=='acquire' else 1000) if isinstance(timeout,(int,float)) else None)
    trace.pending[seq]=dict(seq=seq,stage=stage,resource_id=resource_id)
    parent=PARENT.set(seq)
    try:
        result=function(*args,**kwargs)
        if stage=='source.http':
            status=getattr(result,'status_code',None) or getattr(result,'status',None)
            trace.emit(stage,'response',http_status=status if isinstance(status,int) else None)
        if getattr(function,'__name__','') in ('new_page','new_context','launch','launch_lookup_browser'):
            trace.resource(result,owner=trace.run_id)
        trace.emit(stage,'returned',duration_seconds=round(time.perf_counter()-started,6),resource_id=resource_id,
                   allowance_remaining_seconds=trace.remaining(allowance) if allowance is not None else None)
        return result
    except BaseException as exc:
        # Exception text may contain source bodies, credentials or URLs: type only.
        trace.emit(stage,'exception',duration_seconds=round(time.perf_counter()-started,6),
                   resource_id=resource_id,error_type=type(exc).__name__,
                   allowance_remaining_seconds=trace.remaining(allowance) if allowance is not None else None)
        raise
    finally:
        PARENT.reset(parent);trace.pending.pop(seq,None)
        if entry:
            with _lock:
                count=resource['users'].get(own,1)-1
                if count:resource['users'][own]=count
                else:resource['users'].pop(own,None)


def workflow_stage(stage):
    def decorate(function):
        @wraps(function)
        def wrapped(*args,**kwargs):
            return workflow_call(stage,function,{},*args,**kwargs)
        return wrapped
    return decorate


def archive_stage(function):
    @wraps(function)
    def wrapped(queue,result,job,*args,**kwargs):
        if not isinstance(result,dict) or not isinstance(job,dict):return function(queue,result,job,*args,**kwargs)
        trace=Observation((result.get('workflow_observation') or {}).get('run_id','archive-'+str(job.get('id','unknown'))),job.get('state','unknown'))
        token=ACTIVE.set(trace)
        try:
            trace.emit('archive.queue_handoff','received',job_id=str(job.get('id','')),
                       workflow_id=str(job.get('workflow_id','')),attempt=job.get('attempt'),
                       submitted_epoch_seconds=job.get('submitted'),claimed_epoch_seconds=job.get('claimed'),
                       run_allowance_seconds=job.get('run_seconds'))
            output=workflow_call('archive.persist',function,{},queue,result,job,*args,**kwargs)
            if isinstance(output,dict):
                trace.emit('archive.link','available' if output.get('evidence_url') else 'unavailable',
                           evidence_capture=output.get('evidence_capture'))
                output['archive_observation']=trace.export()
            return output
        finally:trace.release();ACTIVE.reset(token)
    return wrapped


def observe_context(context,trace):
    """Existing network lifecycle only. No routing, body reads, polling or waits."""
    if not trace:return
    trace.resource(context,owner=trace.run_id)
    pending={}
    def request(req):
        try:
            if len(pending)>=200:
                trace.emit('source.network','rejected',guard='observer_pending_limit');return
            seq=trace.emit('source.network','started',host=urlsplit(req.url).hostname,
                           resource_type=req.resource_type,context_id=id(context))
            pending[req]=(seq,time.perf_counter())
            trace.pending[seq]=dict(seq=seq,stage='source.network',context_id=id(context))
        except Exception:trace.emit('source.network.observer','exception',error_type='ObserverError')
    def response(resp):
        try:
            item=pending.get(resp.request)
            if item:trace.emit('source.network','response',request_seq=item[0],http_status=resp.status,
                               response_headers_seconds=round(time.perf_counter()-item[1],6),context_id=id(context))
        except Exception:trace.emit('source.network.observer','exception',error_type='ObserverError')
    def ended(req,failed=False):
        try:
            item=pending.pop(req,None)
            if item:
                trace.pending.pop(item[0],None)
                trace.emit('source.network','exception' if failed else 'finished',request_seq=item[0],
                           duration_seconds=round(time.perf_counter()-item[1],6),context_id=id(context),
                           error_type='RequestFailed' if failed else None)
        except Exception:trace.emit('source.network.observer','exception',error_type='ObserverError')
    def page_created(page):
        trace.resource(page,owner=trace.run_id)
        trace.emit('browser.page','created',page_id=id(page),context_id=id(context))
        for event in ('domcontentloaded','load','close','crash'):
            page.on(event,lambda *args,event=event:trace.emit('browser.page',event,page_id=id(page),context_id=id(context)))
    try:
        context.on('request',request);context.on('response',response)
        context.on('requestfinished',ended);context.on('requestfailed',lambda req:ended(req,True))
        context.on('page',page_created)
    except Exception:trace.emit('source.network.observer','exception',error_type='ListenerRegistrationError')
