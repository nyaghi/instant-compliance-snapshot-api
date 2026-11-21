"""Classify failed source access without changing search plans or identity decisions.

Only structured failure codes and error-channel transport signals are evidence.
PORTAL_ERROR alone is not evidence: existing adapters also use it for parsing and
identity uncertainty. No network requests, clock changes or retry timers here.
"""
import re

_UNRESOLVED = {'Site Not Reachable', 'Unable to Confirm', 'Unable to Verify',
               'Needs Review', 'Unknown', 'Runner Timeout'}
_DEADLINES = {'OR_SOURCE_TIME_LIMIT', 'WI_SOURCE_ALLOWANCE_EXHAUSTED',
              'RI_LOOKUP_TIMEOUT', 'NY_CONNECTOR_REGISTRY_NV_LOOKUP_TIMEOUT'}
_INITIAL_SOURCE_ERRORS = {state + '_INITIAL_SOURCE_UNREACHABLE' for state in
                          {'SC', 'AK', 'AR', 'HI', 'ME', 'MI', 'OH', 'VA', 'WV', 'WI'}}
_SOURCE_ERRORS = _INITIAL_SOURCE_ERRORS | {
    'SC_INITIAL_SOURCE_UNREACHABLE',
    'NH_DATASET_UNAVAILABLE', 'AR_SOURCE_MAINTENANCE',
    'OR_SOURCE_UNREACHABLE', 'OR_SOURCE_ACCESS_REFUSED',
    'DC_LICENSE_SOURCE_UNREACHABLE', 'WI_SOURCE_UNREACHABLE',
    'ME_SOURCE_APPLICATION_ERROR', 'FL_CERTIFICATE_ERROR',
    'NY_CONNECTOR_REGISTRY_NM_HTTP_ERROR', 'NY_CONNECTOR_REGISTRY_NM_SOURCE_ERROR',
    'NY_CONNECTOR_REGISTRY_NV_STARTUP_UNREACHABLE',
    'NY_CONNECTOR_REGISTRY_NV_FORM_LOAD_TIMEOUT',
    'NY_CONNECTOR_REGISTRY_NV_SEARCH_RESPONSE_TIMEOUT',
    'NY_CONNECTOR_SEARCH_NETWORK_ERROR', 'NY_CONNECTOR_SEARCH_RESPONSE_TIMEOUT',
    'NY_CONNECTOR_IL_RESPONSE_TIMEOUT',
}
_RATE_LIMITS = {'NY_CONNECTOR_NC_RATE_LIMITED',
                'NY_CONNECTOR_REGISTRY_TN_RATE_LIMITED', 'NY_CONNECTOR_RATE_LIMITED'}
# These describe our connector, a record interpretation, or missing evidence;
# they do not prove the registry is unavailable.
_NOT_SOURCE = re.compile(
    r'VERIFICATION|VERIFY_|CAPTCHA|IDENTITY|PARSER|FISCAL|SNAPSHOT|CAPTURE|'
    r'QUEUE|RELAY|INVALID_SEQUENCE|UPDATE_REQUIRED|CONNECTOR_UNAVAILABLE|'
    r'AL_READER|AL_IMAGE|INPUT_BINDING|RESULT_COUNT_MISMATCH|DETAIL|FOLLOWUP')
_HTTP = re.compile(r'\b(?:HTTP(?:Error)?(?:\s+Error)?[\s:=]+|status(?:\s+code)?[\s:=]+)(403|404|408|429|5\d\d)\b', re.I)
_NETWORK = re.compile(
    r'net::ERR_(?:CONNECTION_[A-Z_]+|NAME_NOT_RESOLVED|TIMED_OUT|INTERNET_DISCONNECTED)|'
    r'\b(?:ConnectionRefusedError|ConnectionResetError|ConnectTimeout|ReadTimeout|'
    r'NameResolutionError|RemoteDisconnected)\b|'
    r'\b(?:connection (?:refused|reset)|name resolution failed|read timed out|'
    r'connect(?:ion)? timed out|operation timed out|urlopen error timed out)|'
    r'Page\.goto: Timeout|Navigation timeout|curl: \(28\)', re.I)
_DEADLINE_TEXT = re.compile(
    r'\b(?:source|registry|lookup)\b.{0,100}\b(?:allowance exhausted|budget expired|'
    r'exhausted its source time limit|reached its (?:source |lookup )?time limit)\b', re.I)


def classify(data):
    """Return an availability fact, or None; never turn uncertainty into absence."""
    if not isinstance(data, dict) or data.get('success') is not False:
        return None
    if data.get('status') not in _UNRESOLVED:
        return None
    if (data.get('confirmation_required') or data.get('_worker_identity_review')
            or (data.get('identity_review') or {}).get('candidates')):
        return None
    codes = [str(data.get(k) or '') for k in ('status_reason', 'reason_code', 'runner_reason_code')]
    if any(_NOT_SOURCE.search(code) for code in codes):
        return None
    for code in codes:
        if code in _DEADLINES:
            return {'kind': 'deadline_exhausted', 'signal': code, 'terminal': True}
        if code in _RATE_LIMITS:
            return {'kind': 'rate_limited', 'signal': code, 'terminal': False}
        if code in _SOURCE_ERRORS:
            return {'kind': 'source_error', 'signal': code,
                    'terminal': code in _INITIAL_SOURCE_ERRORS}
    # Generic errors on a selected record do not prove source unavailability.
    # Explicit adapter source failures above remain valid even with an export ID.
    if data.get('matched_registry_name') or data.get('matched_registry_identifier'):
        return None
    # Restrict free-text inspection to adapter errors, never comments, names,
    # arbitrary source HTML, or prior attempt history.
    error = str(data.get('error') or '')
    raw = str(data.get('raw_status_text') or '')
    if re.search(r'\b(?:parser|parse|selector|verification|captcha|queue|snapshot|capture|internal batch)\b', error + ' ' + raw, re.I):
        return None
    if _DEADLINE_TEXT.search(error + ' ' + raw):
        return {'kind': 'deadline_exhausted', 'signal': 'SOURCE_DEADLINE_EXHAUSTED', 'terminal': True}
    http = _HTTP.search(error) or _HTTP.search(raw)
    if http:
        code = int(http[1])
        return {'kind': 'rate_limited' if code == 429 else 'source_error',
                'signal': 'HTTP_' + str(code), 'terminal': False}
    if _NETWORK.search(error) or _NETWORK.search(raw):
        return {'kind': 'transport_error', 'signal': 'SOURCE_TRANSPORT_ERROR', 'terminal': False}
    if data.get('state') == 'CT' and 'Connecticut registry returned its application error page' in error:
        return {'kind': 'source_error', 'signal': 'CT_APPLICATION_ERROR_PAGE', 'terminal': False}
    if ('RUNNER_TIMEOUT' in codes and data.get('status') == 'Site Not Reachable'
            and raw in {'Connecticut direct registry lookup could not be completed',
                        'Maryland registry search did not complete'}):
        return {'kind': 'deadline_exhausted', 'signal': 'SOURCE_DEADLINE_EXHAUSTED', 'terminal': True}
    return None


def apply(data):
    fact = classify(data)
    if fact is None:
        return data
    prior = (data.get('source_availability') or {}).get('prior_status', data['status'])
    data['source_availability'] = {'schema': 1, **fact, 'prior_status': prior}
    data['status'] = 'Site Not Reachable'
    explanation = {
        'deadline_exhausted': 'The registry lookup did not complete within its allowed source time. CharityClarity stopped waiting.',
        'rate_limited': 'The registry temporarily limited requests, and this check could not be completed.',
        'source_error': 'The registry returned an error or its search could not be opened.',
        'transport_error': 'The registry connection failed or did not respond in time.',
    }[fact['kind']]
    if data.get('status_reason') == 'AR_SOURCE_MAINTENANCE':
        explanation = 'Arkansas reports scheduled registry maintenance. CharityClarity stopped searching.'
    elif data.get('status_reason') == 'NH_DATASET_UNAVAILABLE':
        explanation = 'The verified New Hampshire registry download is unavailable or needs refresh.'
    # Do not claim the entire site is down, nor publish raw exception payloads.
    data['comments'] = explanation + ' No registration status was established. Retry this state later.'
    return data
