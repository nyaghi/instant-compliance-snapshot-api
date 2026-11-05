"""Bound Oregon source access within one isolated task; no cross-run outage cache."""
import re
import socket
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

SOURCE = 'https://justice.oregon.gov/Charities'
CONNECT_SECONDS = 8.0
# Retain the 8/16-second attempts and add one fresh 8-second transient recovery.
PROBE_SECONDS = CONNECT_SECONDS * 4
TASK_SECONDS = 75.0
REASONS = {'OR_SOURCE_UNREACHABLE', 'OR_SOURCE_ACCESS_REFUSED', 'OR_SOURCE_TIME_LIMIT'}


def failure_diagnostic(exc):
    """Classify retained exception frames; no I/O or exception-message logging.

    A timeout class alone cannot establish which network stage failed. Keep
    unknown when no standard-library frame establishes a stage. The diagnostic
    must never change the original bounded recovery result.
    """
    try:
        pending, seen, frames, kinds = [exc], set(), [], []
        dns_error = False
        while pending and len(seen) < 8:
            error = pending.pop()
            if not isinstance(error, BaseException) or id(error) in seen:
                continue
            seen.add(id(error)); kinds.append(type(error).__name__)
            dns_error = dns_error or isinstance(error, socket.gaierror)
            tb = error.__traceback__
            while tb is not None:
                module = tb.tb_frame.f_globals.get('__name__', '')
                if module in {'socket', 'ssl', 'http.client', 'urllib.request'}:
                    frames.append((module, tb.tb_frame.f_code.co_name))
                tb = tb.tb_next
            pending.extend([error.__cause__, error.__context__, getattr(error, 'reason', None)])
        if ('http.client', '_read_status') in frames:
            phase = 'http_response_headers'
        elif any(module == 'ssl' and name in {'do_handshake', '_create', 'wrap_socket'} for module, name in frames):
            phase = 'tls_handshake'
        elif dns_error:
            phase = 'dns_resolution'
        elif ('socket', 'create_connection') in frames:
            phase = 'tcp_connect'
        else:
            phase = 'unknown'
        return {'failure_phase': phase, 'exception_types': list(dict.fromkeys(kinds))[:8],
                'network_frames': [module+'.'+name for module, name in frames][-12:]}
    except Exception:
        return {'failure_phase': 'unknown'}


def task_allowance(job):
    allowance = job['run_seconds']
    return min(allowance, TASK_SECONDS) if job.get('state') == 'OR' else allowance


def collector_recovery_allowed(reason, attempts, deadline, *, clock=None):
    """One normal-collector opportunity for response stalls, within the old cap.

    DNS, connect, TLS, access denial, foreign redirects and elapsed deadlines
    remain terminal. A bare TimeoutError with missing frames covers the retained
    response-stage failures; urllib wraps request-setup timeouts in URLError.
    """
    clock = clock or time.monotonic
    return (reason == 'OR_SOURCE_UNREACHABLE' and bool(attempts)
            and clock()+3 < deadline
            and all(a.get('error_type') == 'TimeoutError'
                    and a.get('failure_phase', 'unknown') in {'unknown', 'http_response_headers'}
                    for a in attempts))


def unavailable_result(payload, version, reason, attempts=(), elapsed=0):
    assert reason in REASONS
    if reason == 'OR_SOURCE_TIME_LIMIT':
        explanation = 'Oregon reached its available public-registry time limit (at most 75 seconds). The check was stopped instead of restarting its waits.'
    elif reason == 'OR_SOURCE_ACCESS_REFUSED':
        explanation = 'Oregon did not provide the requested public-registry page during this check.'
    else:
        explanation = (f'Oregon\'s public-registry page could not be reached after {len(attempts)} bounded connection attempts.'
                       if attempts else 'Oregon\'s public-registry page could not be reached within the available connection time.')
    if attempts and attempts[-1].get('http_status'):
        explanation += ' The source returned HTTP '+str(attempts[-1]['http_status'])+'.'
    elif attempts and attempts[-1].get('error_type') in {'TimeoutError', 'LateResponse'}:
        explanation += ' The connection did not respond in time.'
    explanation += ' This describes access during this check, not the organization\'s registration status or a confirmed statewide outage. Retry Oregon when access is restored.'
    ein = re.sub(r'\D', '', str(payload.get('ein', '')))
    return {'organization_name': payload['organization_name'],
            'ein': ein[:2]+'-'+ein[2:] if len(ein) == 9 else ein,
            'state': 'OR', 'status': 'Site Not Reachable', 'success': False,
            'reason_code': reason, 'status_reason': reason, 'app_version': version,
            'comments': explanation, 'source_note': explanation, 'source_url': SOURCE,
            'error': '', 'evidence_url': '', 'search_history_url': '',
            'evidence_capture': 'unavailable', 'lookup_seconds': round(elapsed, 3),
            'or_reachability': {'attempts': list(attempts), 'probe_limit_seconds': PROBE_SECONDS,
                                'task_limit_seconds': TASK_SECONDS}}


def check(url=SOURCE, *, deadline=float('inf'), opener=None, clock=None):
    """Check source access; a slow detail alone must not suppress normal lookup.

    A transient detail failure uses the existing retries for the official search
    entrance. Success permits the unchanged collector, not a registration claim.
    """
    opener = opener or urllib.request.urlopen
    clock = clock or time.monotonic
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != 'justice.oregon.gov'
            or parsed.path not in {'/Charities', '/Charities/Charity/details'}):
        raise ValueError('Unapproved Oregon reachability destination')
    start = clock()
    stop = min(start+PROBE_SECONDS, deadline-1)
    attempts = []
    for number, allowance in enumerate((CONNECT_SECONDS, CONNECT_SECONDS * 2, CONNECT_SECONDS), 1):
        remaining = stop-clock()
        if remaining <= 0:
            break
        request_url = SOURCE if number > 1 and parsed.path == '/Charities/Charity/details' else url
        started = clock()
        attempt = {'attempt': number, 'target': 'search' if request_url == SOURCE else 'detail'}
        try:
            request = urllib.request.Request(request_url, headers={'User-Agent': 'ComplianceExpressRegistrySnapshot/1.0'})
            with opener(request, timeout=min(allowance, remaining)) as response:
                if clock() >= stop:
                    attempt['error_type'] = 'LateResponse'
                    attempts.append(attempt)
                    return False, 'OR_SOURCE_UNREACHABLE', attempts, clock()-start
                status = response.status
                destination = urlsplit(response.url)
                attempt['http_status'] = status
                if (destination.scheme != 'https' or destination.hostname != 'justice.oregon.gov'
                        or not 200 <= status < 300):
                    attempts.append(attempt)
                    return False, 'OR_SOURCE_ACCESS_REFUSED', attempts, clock()-start
                attempts.append(attempt)
                # No response-body wait: normal record parsing remains unchanged.
                return True, '', attempts, clock()-start
        except urllib.error.HTTPError as exc:
            attempt['http_status'] = exc.code
            attempts.append(attempt)
            if exc.code not in {408, 429, 500, 502, 503, 504}:
                return False, 'OR_SOURCE_ACCESS_REFUSED', attempts, clock()-start
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            attempt['error_type'] = type(exc).__name__
            attempt.update(failure_diagnostic(exc))
            attempts.append(attempt)
        finally:
            attempt['elapsed_seconds'] = round(clock()-started, 3)
    return False, 'OR_SOURCE_UNREACHABLE', attempts, clock()-start
