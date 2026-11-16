"""Keep Connecticut requests inside one existing source lookup allowance."""
from contextvars import ContextVar
import time
import re
from urllib.parse import unquote, urlsplit

STOP = ContextVar('ct_lookup_stop', default=float('inf'))


class SourceUnavailable(RuntimeError):
    pass


def check_response(body):
    """ASP.NET can return its error-page redirect with HTTP 200."""
    redirect = re.search(r'\|pageRedirect\|\|([^|]+)\|', body or '', re.I)
    if redirect and urlsplit(unquote(redirect.group(1))).path.casefold() == '/errorpage.aspx':
        raise SourceUnavailable('Connecticut registry returned its application error page')


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
