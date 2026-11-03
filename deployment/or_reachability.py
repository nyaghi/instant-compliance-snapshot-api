"""Bound Oregon source access within one isolated task; no cross-run outage cache."""
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

SOURCE = 'https://justice.oregon.gov/Charities'
PROBE_SECONDS = 16.0
TASK_SECONDS = 75.0
REASONS = {'OR_SOURCE_UNREACHABLE', 'OR_SOURCE_ACCESS_REFUSED', 'OR_SOURCE_TIME_LIMIT'}


def task_allowance(job):
    allowance = job['run_seconds']
    return min(allowance, TASK_SECONDS) if job.get('state') == 'OR' else allowance


def unavailable_result(payload, version, reason, attempts=(), elapsed=0):
    assert reason in REASONS
    if reason == 'OR_SOURCE_TIME_LIMIT':
        explanation = 'Oregon reached its available public-registry time limit (at most 75 seconds). The check was stopped instead of restarting its waits.'
    elif reason == 'OR_SOURCE_ACCESS_REFUSED':
        explanation = 'Oregon did not provide the requested public-registry page during this check.'
    else:
        explanation = ('Oregon\'s public-registry page could not be reached after two short connection attempts.'
                       if len(attempts) == 2 else 'Oregon\'s public-registry page could not be reached within the available connection time.')
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
    """GET the actual page headers, never HEAD or an unrelated health endpoint."""
    opener = opener or urllib.request.urlopen
    clock = clock or time.monotonic
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != 'justice.oregon.gov'
            or parsed.path not in {'/Charities', '/Charities/Charity/details'}):
        raise ValueError('Unapproved Oregon reachability destination')
    start = clock()
    stop = min(start+PROBE_SECONDS, deadline-1)
    attempts = []
    for number in (1, 2):
        remaining = stop-clock()
        if remaining <= 0:
            break
        attempt = {'attempt': number}
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'ComplianceExpressRegistrySnapshot/1.0'})
            with opener(request, timeout=min(8.0, remaining)) as response:
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
            attempts.append(attempt)
    return False, 'OR_SOURCE_UNREACHABLE', attempts, clock()-start
