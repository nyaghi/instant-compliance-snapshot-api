"""Keep Connecticut requests inside one existing source lookup allowance."""
from contextvars import ContextVar
import time

STOP = ContextVar('ct_lookup_stop', default=float('inf'))


def run(function, organization, allowance):
    token = STOP.set(min(STOP.get(), time.perf_counter() + allowance))
    try:
        return function(organization)
    finally:
        STOP.reset(token)


def timeout(cap):
    remaining = STOP.get() - time.perf_counter()
    if remaining <= 0:
        raise TimeoutError('Connecticut source lookup allowance exhausted')
    return min(float(cap), remaining)
