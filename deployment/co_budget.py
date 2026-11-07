"""One Colorado lookup allowance, shared across its existing EIN/name attempts."""
from contextvars import ContextVar
import time
STOP=ContextVar('co_lookup_stop',default=float('inf'))


def timeout(cap_ms):
    remaining=STOP.get()-time.monotonic()
    if remaining<=0:raise TimeoutError('Colorado lookup allowance exhausted; no negative conclusion')
    return max(1,int(min(cap_ms,remaining*1000)))
