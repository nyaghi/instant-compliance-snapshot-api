"""Same master engine, isolated task lifetime. No state-specific logic lives here."""
import os
from pathlib import Path
import sys
import json
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FloridaTrace:
    """Lab-only passive timing. Never record headers, cookies or query strings."""
    def __init__(self, sink=None):
        self.started = time.monotonic()
        self.events = []
        self.sink = Path(sink) if sink else None

    def record(self, event, **details):
        if len(self.events) < 512 or event.startswith('attempt'):
            self.events.append({'seconds': round(time.monotonic()-self.started, 3),
                                'event': event, **details})
            if self.sink is not None:
                try:
                    temp=self.sink.with_suffix('.partial')
                    temp.write_text(json.dumps(self.events[-64:]),encoding='utf-8')
                    temp.replace(self.sink)
                except Exception:
                    pass  # Passive trace persistence cannot affect the lookup.

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
                # Fixed public classification labels only; preserve the exact
                # result object and never inspect registry text or identity.
                status = getattr(result, 'status', '')
                safe_status = status if status in {'Current', 'Upcoming Filing', 'Delinquent',
                    'Not Registered', 'Not registered', 'Delinquent/Non-compliant', 'Not Found', 'Site Not Reachable', 'Unable to Confirm',
                    'Unable to Verify', 'Unknown', 'Suspended', 'Revoked',
                    'Closed / Withdrawn / Canceled'} else 'other'
                self.record('attempt_return', result_status=safe_status)
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


@contextmanager
def observe_fl_headers(master, trace):
    """Observe the existing FL HTTPS request through header receipt, without I/O.

    Chromium's ERR_FAILED hides whether the verified forwarder ever received
    headers. This isolated-process observer preserves exact requests, timeout,
    response object and exceptions. It never reads a body or logs form data.
    """
    if trace is None or not master.APP_VERSION.endswith('-performance-lab'):
        yield
        return
    director = master.urllib.request.OpenerDirector
    original = director.open
    def observed(opener, request, *args, **kwargs):
        url = request.full_url if hasattr(request, 'full_url') else request
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'csapp.fdacs.gov'
                or parsed.path not in {'/CSPublicApp/CheckACharity/CheckACharity.aspx',
                                       '/CSPublicApp/BusinessSearch/BusinessSearch.aspx'}):
            return original(opener, request, *args, **kwargs)
        number = len(trace.events)
        details = {'host': parsed.hostname, 'path': parsed.path,
                   'method': request.get_method() if hasattr(request, 'get_method') else 'GET',
                   'request_id': number}
        trace.record('verified_open', **details)
        try:
            response = original(opener, request, *args, **kwargs)
        except Exception as exc:
            trace.record('verified_open_error', exception_type=type(exc).__name__, **details)
            raise
        trace.record('verified_headers', status=response.status, **details)
        return response
    director.open = observed
    try:
        yield
    finally:
        director.open = original


def browser_trace_route(url):
    """Public NY route classes only; never identifiers, query strings or tokens."""
    try:
        parsed=urlsplit(url)
        if parsed.scheme!='https':return None
        if parsed.hostname=='charities-search.ag.ny.gov':
            if parsed.path=='/RegistrySearch':return 'navigation'
            if parsed.path.endswith(('.js','.css')):return 'static_asset'
        if parsed.hostname=='charities-search-api.ag.ny.gov':
            return {'/api/recaptcha/verify':'verification','/api/FileNet/RegistrySearch':'search',
                    '/api/FileNet/RegistryDetail':'details'}.get(parsed.path)
    except Exception:pass
    return None


@contextmanager
def observe_browser_transport(master,state,sink=None):
    """Passive listeners in this isolated child; no body reads or extra requests."""
    if state!='NY' or not master.APP_VERSION.endswith('-performance-lab'):
        yield None;return
    from playwright.sync_api import BrowserContext
    trace=FloridaTrace(Path(sink).with_suffix('').with_suffix('.browser.json') if sink else None)
    original=BrowserContext.new_page
    attached=[]
    def record(event,request,status=None):
        try:
            route=browser_trace_route(request.url)
            if route:
                details={'route':route,'request_id':id(request)}
                if isinstance(status,int):details['status']=status
                if event == 'browser_failed':
                    failure = request.failure
                    if failure in {'net::ERR_FAILED', 'net::ERR_ABORTED', 'net::ERR_TIMED_OUT',
                            'net::ERR_CONNECTION_RESET', 'net::ERR_CONNECTION_CLOSED',
                            'net::ERR_NAME_NOT_RESOLVED', 'net::ERR_HTTP2_PROTOCOL_ERROR',
                            'net::ERR_BLOCKED_BY_CLIENT', 'net::ERR_INTERNET_DISCONNECTED'}:
                        details['failure'] = failure
                trace.record(event,**details)
        except Exception:pass
    def new_page(context,*args,**kwargs):
        page=original(context,*args,**kwargs)
        for event,callback in [('request',lambda r:record('browser_start',r)),
                ('response',lambda r:record('browser_headers',r.request,r.status)),
                ('requestfinished',lambda r:record('browser_complete',r)),
                ('requestfailed',lambda r:record('browser_failed',r))]:
            try:page.on(event,callback);attached.append((page,event,callback))
            except Exception:pass
        return page
    BrowserContext.new_page=new_page
    try:yield trace
    finally:
        BrowserContext.new_page=original
        for page,event,callback in attached:
            try:page.remove_listener(event,callback)
            except Exception:pass


def transport_route(state, url):
    """A fixed label, never a URL, query, registry ID or session value."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https': return None
        if state == 'ME' and parsed.hostname == 'www.pfr.maine.gov':
            return {'/almsonline/almsquery/searchcompany.aspx': 'search',
                    '/almsonline/almsquery/searchresults.aspx': 'results',
                    '/almsonline/almsquery/showdetail.aspx': 'details'}.get(parsed.path.casefold())
        if state == 'MI' and parsed.hostname == 'www.ag.state.mi.us':
            return {'/CharitableTrust/frmDisclaimer.aspx': 'disclaimer',
                    '/CharitableTrust/frmDefault.aspx': 'search',
                    '/CharitableTrust/frmSearchResults.aspx': 'results'}.get(parsed.path)
        if state == 'NJ' and parsed.hostname == 'charportal.dca.njoag.gov':
            for prefix, label in [('/Charity-Registration/CHR-Public-Search-Page/', 'search'),
                                  ('/_services/portal/GetListViewConfiguration/', 'configuration'),
                                  ('/_layout/tokenhtml', 'verification'),
                                  ('/_services/entity-grid-data', 'query'),
                                  ('/retrieveRegistration/', 'registration'),
                                  ('/CHR-Public-Details-Page/', 'details')]:
                if parsed.path.startswith(prefix): return label
    except Exception:
        pass
    return None


@contextmanager
def observe_transport(master, state, sink=None):
    """Observe the existing request/stream calls in one isolated lab child.

    This neither changes requests nor reads responses ahead of the master.
    The trace survives a killed task, identifying which source step stalled.
    """
    if state == 'WI':
        with observe_wi_transport(master, sink) as trace:
            yield trace
        return
    client = getattr(master, 'curl_requests', None)
    if (state not in {'MI', 'NJ', 'ME'} or client is None
            or not master.APP_VERSION.endswith('-performance-lab')):
        yield None
        return
    trace = FloridaTrace(Path(sink).with_suffix('').with_suffix('.transport.json') if sink else None)
    original = client.Session

    class ObservedSession(original):
        def request(self, method, url, *args, **kwargs):
            route = transport_route(state, url)
            if not route: return super().request(method, url, *args, **kwargs)
            number = len(trace.events)
            trace.record('http_start', route=route, method=method, request_id=number)
            try:
                response = super().request(method, url, *args, **kwargs)
            except Exception as exc:
                trace.record('http_exception', route=route, request_id=number,
                             exception_type=type(exc).__name__)
                raise
            trace.record('http_headers' if kwargs.get('stream') else 'http_complete',
                         route=route, request_id=number, status=response.status_code)
            if kwargs.get('stream'):
                original_iter = response.iter_content
                def observed_iter(*args, **kwargs):
                    try:
                        yield from original_iter(*args, **kwargs)
                    except Exception as exc:
                        trace.record('http_body_exception', route=route, request_id=number,
                                     exception_type=type(exc).__name__)
                        raise
                    else:
                        trace.record('http_complete', route=route, request_id=number)
                response.iter_content = observed_iter
            return response

    client.Session = ObservedSession
    try:
        yield trace
    finally:
        client.Session = original


def wi_transport_route(url):
    """Fixed public route labels only, including the existing reader fallback."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme != 'https': return None
        if parsed.hostname == 'r.jina.ai':
            nested = urlsplit(parsed.path.lstrip('/'))
            if nested.hostname == 'apps.dfi.wi.gov': return 'reader'
        if parsed.hostname == 'apps.dfi.wi.gov':
            if parsed.path.endswith('/OrganizationCredentialSearch.aspx'): return 'search'
            if parsed.path.endswith('/OrgCredentialSearchResults.aspx'): return 'results'
            if parsed.path.startswith('/ice/berg/Registration/'): return 'details'
    except Exception: pass
    return None


@contextmanager
def observe_wi_transport(master, sink=None):
    """Observe the original urllib request/read without extra reads or requests."""
    if not master.APP_VERSION.endswith('-performance-lab'):
        yield None
        return
    trace = FloridaTrace(Path(sink).with_suffix('').with_suffix('.transport.json') if sink else None)
    director = master.urllib.request.OpenerDirector
    original = director.open
    def observed(opener, request, *args, **kwargs):
        route = wi_transport_route(request.full_url if hasattr(request, 'full_url') else request)
        if not route: return original(opener, request, *args, **kwargs)
        number = len(trace.events)
        trace.record('http_start', route=route, request_id=number,
                     method=request.get_method() if hasattr(request, 'get_method') else 'GET')
        try:
            response = original(opener, request, *args, **kwargs)
        except Exception as exc:
            trace.record('http_exception', route=route, request_id=number, exception_type=type(exc).__name__)
            raise
        trace.record('http_headers', route=route, request_id=number, status=getattr(response, 'status', None))
        try:
            read = response.read
            def observed_read(*args, **kwargs):
                try: content = read(*args, **kwargs)
                except Exception as exc:
                    trace.record('http_body_exception', route=route, request_id=number, exception_type=type(exc).__name__)
                    raise
                trace.record('http_complete', route=route, request_id=number)
                return content
            response.read = observed_read
        except Exception:
            pass  # An unpatchable response keeps the original read untouched.
        return response
    director.open = observed
    try: yield trace
    finally: director.open = original


def execute(master, job, source_finished=None, trace_path=None):
    if job['version'] != master.APP_VERSION:
        raise ValueError('Master version mismatch')
    p = job['payload']
    if job['state'] == '@sales_identity':
        from deployment.lab_capacity import sales_identity_seconds
        return master.sales_identity_evidence(p['organization_name'], p['ein'],
                                              budget_seconds=sales_identity_seconds(job['version']))
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
    identity = job.get('sales_identity')
    if identity is not None:
        if p.get('mode') != 'sales' or p.get('alternate_names'):
            raise ValueError('Automatic Sales identity cannot override reviewed input')
        aliases = master.sales_names_from_evidence(p['ein'], identity)
        p = {**p, 'alternate_names': aliases}
    organizations = master.normalize_organization_requests(p, privileged=False)
    if len(organizations) != 1: raise ValueError('Exactly one organization required')
    trace = FloridaTrace(trace_path) if job['state'] == 'FL' else None
    original = master.search_fl if trace else None
    if trace: master.search_fl = trace.wrap(original)
    mode_context = getattr(master, 'LAB_LOOKUP_MODE_CONTEXT', None)
    mode_token = mode_context.set(p.get('mode', 'standard')) if mode_context is not None else None
    with observe_fl_headers(master, trace), observe_transport(master, job['state'], trace_path) as transport_trace, observe_browser_transport(master, job['state'], trace_path) as browser_trace:
        try:
            results = (master.run_sales_lookups_with_source_evidence(organizations, [job['state']], identity)
                       if identity is not None else master.run_state_lookups_parallel(organizations, [job['state']]))
        finally:
            if trace: master.search_fl = original
            if mode_context is not None: mode_context.reset(mode_token)
    if len(results) != 1: raise ValueError('Unexpected result count')
    if transport_trace: results[0]['lab_transport_trace'] = transport_trace.events
    if browser_trace: results[0]['lab_browser_trace'] = browser_trace.events
    if trace: results[0]['lab_fl_trace'] = trace.events
    if identity is not None:
        results[0] = master.sales_result_with_identity(results[0], identity)
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
    result = execute(master, job, progress, Path(output).with_suffix('.trace.json'))
    result['lab_task_metrics'] = {'import_seconds': import_seconds, 'import_cpu_seconds': import_cpu,
        'execution_seconds': time.monotonic()-execution_started, 'execution_cpu_seconds': time.process_time()-cpu_started}
    result['lab_task_metrics']['engine_preloaded'] = warmed is not None
    result['lab_task_metrics']['pooled_browser_used'] = bool(getattr(master.launch_lookup_browser, 'lab_reused', False))
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


def warm_ready_main(job, output, log_path, ready, supervisor_pid, env):
    """Readiness only: imports/static public tables, no organization or lookup."""
    warmed = prepare_forked_child(log_path, ready, env)
    if set(job) != {'version'} or warmed.master.APP_VERSION != job['version']:
        raise ValueError('Invalid warm readiness request')
    path=Path(output);temp=path.with_suffix('.partial')
    temp.write_text(json.dumps({'version':job['version'],
        'template_pid':warmed.PRELOAD_PID,'ready':True}),encoding='utf-8')
    temp.replace(path)


def main():
    run_job(json.load(sys.stdin),sys.argv[1])


if __name__ == '__main__': main()
