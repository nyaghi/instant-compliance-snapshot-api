"""One bounded initial transport-recovery sequence per staging state lookup.

Only explicit entry requests use this scope. A responding source permanently
disarms it, leaving search, identity, detail and capture recovery unchanged.
HTTP denials/errors retain their existing alternate-transport recovery too.
No request timeout, search plan, clock, network operation or thread is added.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import time
import urllib.error

STATES = frozenset({'AK', 'AR', 'HI', 'ME', 'MI', 'OH', 'VA', 'WV', 'WI'})
CURRENT = ContextVar('cc_initial_source_access', default=None)


class InitialSourceStopped(BaseException):
    """Private control flow, caught by run() before leaving the lookup boundary.

    BaseException deliberately escapes legacy ``except Exception`` recovery
    loops. Their finally blocks still close browsers and release owned locks.
    It must never represent cancellation, parser failure or an identity result.
    """
    def __init__(self, scope):
        self.scope = scope


class Scope:
    def __init__(self, state):
        self.state = state
        self.opened = False
        self.preserve_recovery = False
        self.failures = []
        self.semantic_attempt = 1


def transport_failure(exc):
    # An HTTP response is not a failed connection. Preserve verification and
    # alternative-access paths, including an HTTPError wrapping a timeout word.
    if isinstance(exc, urllib.error.HTTPError):
        return False
    if isinstance(exc, (TypeError, ValueError, AssertionError)):
        return False
    cause = getattr(exc, 'reason', None)
    if isinstance(exc, TimeoutError) or isinstance(cause, TimeoutError):
        return True
    from deployment.source_availability import classify
    fact = classify({'success': False, 'status': 'Site Not Reachable',
                     'error': str(exc)})
    return bool(fact and fact['kind'] == 'transport_error')


def _failure(scope, exc, seconds):
    if not transport_failure(exc):
        scope.preserve_recovery = True
        return
    scope.failures.append({'kind': 'initial_transport_failure', 'seconds': round(seconds, 3)})
    if len(scope.failures) >= 2:
        raise InitialSourceStopped(scope) from None


def mark_semantic_attempt(state, number):
    scope = CURRENT.get()
    if scope is not None and scope.state == state:
        scope.semantic_attempt = number


def preflight(state, reachable, note, seconds):
    scope = CURRENT.get()
    if scope is None or scope.state != state or scope.opened or scope.preserve_recovery:
        return
    if reachable:
        scope.opened = True
    else:
        _failure(scope, OSError(note), seconds)


@contextmanager
def attempt(state):
    scope = CURRENT.get()
    if scope is None or scope.state != state or scope.opened or scope.preserve_recovery:
        yield
        return
    started = time.monotonic()
    try:
        yield
    except Exception as exc:
        _failure(scope, exc, time.monotonic() - started)
        raise
    else:
        scope.opened = True


def call(state, operation, *args, **kwargs):
    with attempt(state):
        return operation(*args, **kwargs)


class _InitialPage:
    def __init__(self, state, wrapped):
        self._state, self._wrapped = state, wrapped

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def goto(self, *args, **kwargs):
        return call(self._state, self._wrapped.goto, *args, **kwargs)


def page(state, wrapped):
    scope = CURRENT.get()
    return (_InitialPage(state, wrapped) if scope is not None and scope.state == state
            and not scope.opened and not scope.preserve_recovery else wrapped)


def run(master, operation, organization_name, ein, state):
    if state not in STATES or not master.trial_identity():
        return operation(organization_name, ein, state)
    # Nested calls for the same check retain the original access history.
    if CURRENT.get() is not None:
        return operation(organization_name, ein, state)
    scope = Scope(state)
    token = CURRENT.set(scope)
    started = time.perf_counter()
    try:
        return operation(organization_name, ein, state)
    except InitialSourceStopped as stopped:
        if stopped.scope is not scope:
            raise
        org = master.checker.Organization(organization_name, ein)
        source_url = master.NAME_SEARCH_PREFLIGHT_URLS.get(state, '')
        source_url = {'AK': master.checker.AK_SEARCH_URL,
                      'HI': 'https://charity.ehawaii.gov/charity/new-search.html',
                      'MI': 'https://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx',
                      'OH': 'https://charitableregistration.ohioago.gov/Charities/ResearchCharities',
                      'VA': master.VA_EVOKE_PUBLIC_PORTAL_URL,
                      'WI': master.WI_SEARCH_URL}.get(state, source_url)
        result = master.checker.StateResult(organization_name, ein, state,
                                           'Site Not Reachable', source_url)
        result.reason_code = state + '_INITIAL_SOURCE_UNREACHABLE'
        result.success = False
        result.raw_status_text = 'Initial registry access failed after two bounded transport attempts.'
        result.source_note = ('The registry did not respond during initial access and its bounded recovery. '
                              'CharityClarity stopped without inferring a registration status.')
        data = master.response_data_for_lookup(result, '', org, organization_name,
                                               ein, state, started)
        data['initial_source_access'] = {'schema': 1, 'transport_failures': scope.failures,
                                        'completed_source_response': False}
        data['semantic_attempts'] = scope.semantic_attempt
        from deployment.source_availability import apply
        return apply(data)
    finally:
        CURRENT.reset(token)
