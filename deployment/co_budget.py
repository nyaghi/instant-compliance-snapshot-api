"""One Colorado lookup allowance, shared across its existing EIN/name attempts."""
from contextvars import ContextVar
import time
STOP=ContextVar('co_lookup_stop',default=float('inf'))


def run(function, *args):
    """Own one allowance across every semantic attempt and source fallback."""
    from .state_snapshots import DEADLINE
    started=time.monotonic()
    stop=min(STOP.get(),started+60,DEADLINE.get()-5)
    token=STOP.set(stop)
    deadline=DEADLINE.set(min(DEADLINE.get(),stop+5))
    try:
        result=function(*args)
        result['co_budget_metrics']={'allowance_seconds':60,'elapsed_seconds':round(time.monotonic()-started,2)}
        return result
    finally:
        STOP.reset(token);DEADLINE.reset(deadline)


def timeout(cap_ms):
    remaining=STOP.get()-time.monotonic()
    if remaining<=0:raise TimeoutError('Colorado lookup allowance exhausted; no negative conclusion')
    return max(1,int(min(cap_ms,remaining*1000)))
