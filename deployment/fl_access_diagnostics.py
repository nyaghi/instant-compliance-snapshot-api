"""Bounded passive FL access diagnostics; no request or decision changes."""
import re
import time
from contextlib import contextmanager
from deployment.workflow_observation import ACTIVE

_STACK_PHASES = {'getaddrinfo':'dns', 'create_connection':'tcp_connect',
                 'connect':'tcp_connect', 'do_handshake':'tls',
                 '_read_status':'response_headers', 'getresponse':'response_headers',
                 'read1':'response_body', 'read':'response_body', 'recv_into':'socket_read'}

def _failure(exc):
    code = re.search(r'net::ERR_[A-Z0-9_]+', str(exc))
    frames=[];tb=exc.__traceback__
    while tb is not None:
        name=tb.tb_frame.f_code.co_name
        if name in _STACK_PHASES:frames.append(name)
        tb=tb.tb_next
    cause=getattr(exc,'reason',None)
    if isinstance(cause,BaseException) and cause is not exc:
        tb=cause.__traceback__
        while tb is not None:
            name=tb.tb_frame.f_code.co_name
            if name in _STACK_PHASES:frames.append(name)
            tb=tb.tb_next
    # Prefer a specific protocol phase over a generic underlying socket read.
    phase=next((_STACK_PHASES[name] for name in reversed(frames)
                if _STACK_PHASES[name] not in {'socket_read','response_body'}),None)
    if phase is None and frames:phase=_STACK_PHASES[frames[-1]]
    return dict(error_type=type(exc).__name__,cause_type=type(cause).__name__ if isinstance(cause,BaseException) else None,
                network_error_code=code[0] if code else None,protocol_phase=phase,
                socket_errno=getattr(cause if isinstance(cause,BaseException) else exc,'errno',None)
                    if isinstance(getattr(cause if isinstance(cause,BaseException) else exc,'errno',None),int) else None,
                phase_frames=frames[-8:])

def _trace():
    try:
        trace=ACTIVE.get()
        return trace if trace is not None and trace.state=='FL' else None
    except Exception:return None

def _emit(trace,outcome,**fields):
    try:
        if trace is not None:
            count=getattr(trace,'_fl_access_event_count',0)
            if count>=96 and outcome!='exception':return
            trace._fl_access_event_count=count+1
            trace.emit('fl.access',outcome,**fields)
    except Exception:pass

def _elapsed(started):
    try:return round(time.perf_counter()-started,6)
    except Exception:return None

@contextmanager
def step(operation):
    trace=_trace()
    if trace is None:
        yield;return
    try:started=time.perf_counter()
    except Exception:
        yield;return
    _emit(trace,'started',operation=operation)
    try:yield
    except BaseException as exc:
        try:fields=_failure(exc)
        except Exception:fields={'error_type':type(exc).__name__}
        _emit(trace,'exception',operation=operation,duration_seconds=_elapsed(started),**fields)
        raise
    else:_emit(trace,'returned',operation=operation,duration_seconds=_elapsed(started))

def call(operation,function,*args,**kwargs):
    with step(operation):return function(*args,**kwargs)

def browser_failure_fields(request,failed):
    """Only fixed network codes and numeric timing; never URLs/headers/bodies."""
    import math
    fields={}
    if failed:
        code=re.search(r'net::ERR_[A-Z0-9_]+',str(request.failure or ''))
        if code:fields['network_error_code']=code[0]
    try:
        timing=request.timing
        allowed=('startTime','domainLookupStart','domainLookupEnd','connectStart',
                 'secureConnectionStart','connectEnd','requestStart','responseStart','responseEnd')
        fields['network_timing_ms']={k:timing[k] for k in allowed
            if type(timing.get(k)) in (float,int) and math.isfinite(timing[k])}
    except Exception:pass
    return fields
