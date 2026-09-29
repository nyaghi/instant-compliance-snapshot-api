"""Authenticated staging transport to the existing optimized master-worker pool.

No state interpretation lives here. The worker runs the same merged master;
the staging master retains access checks and signs its own identity reviews.
Production origins and service IDs cannot enable this route.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request

ORIGIN = 'https://instant-compliance-snapshot-api-hn4v.onrender.com'
STAGING = {
    'srv-d8a38lnavr4c73d4ib30': 'https://instant-compliance-snapshot-api-staging-8dnk.onrender.com',
    'srv-d82afqjrjlhs738j7or0': 'https://instant-compliance-snapshot-api-staging.onrender.com',
}


def enabled(master):
    return (master.APP_VERSION.endswith('-staging')
        and os.environ.get('CE_STAGING_WORKFLOW_ORIGIN') == ORIGIN
        and os.environ.get('PUBLIC_BASE_URL') == STAGING.get(os.environ.get('RENDER_SERVICE_ID'), 'disabled')
        and len(os.environ.get('CE_STAGING_WORKFLOW_KEY', '')) >= 40
        and len(master.NY_CONNECTOR_SIGNING_KEY) >= 32)


def call(path, payload=None, key=None):
    if not re.fullmatch(r'/api/lab/workflows(?:/[a-f0-9-]{36}(?:/(?:cancel|release-external))?)?', path):
        raise ValueError('Invalid workflow route')
    headers = {'Authorization': 'Bearer ' + os.environ['CE_STAGING_WORKFLOW_KEY'], 'Content-Type': 'application/json'}
    if key: headers['Idempotency-Key'] = key
    request = urllib.request.Request(ORIGIN + path, headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None)
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(4_000_001)
        if len(data) > 4_000_000: raise ValueError('Workflow response too large')
        return json.loads(data)


def pack(master, record):
    body = base64.urlsafe_b64encode(json.dumps(record, separators=(',', ':'), sort_keys=True).encode()).rstrip(b'=')
    signature = hmac.new(master.NY_CONNECTOR_SIGNING_KEY.encode(), b'cc-workflow-v1.' + body, hashlib.sha256).hexdigest()
    return body.decode() + '.' + signature


def unpack(master, token, owner):
    if not isinstance(token, str) or not 65 < len(token) < 2500: raise ValueError('Invalid workflow token')
    body, signature = token.rsplit('.', 1)
    expected = hmac.new(master.NY_CONNECTOR_SIGNING_KEY.encode(), b'cc-workflow-v1.' + body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected): raise ValueError('Invalid workflow token')
    record = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
    if (record['owner'] != owner or record['version'] != master.APP_VERSION
            or not record['issued'] <= time.time() < record['expires'] <= record['issued'] + 1500):
        raise ValueError('Workflow expired or belongs to another session')
    if not re.fullmatch(r'[a-f0-9-]{36}', record['id']): raise ValueError('Invalid workflow identity')
    return record


def prepare(master, payload, owner):
    name, ein = payload.get('organization_name'), payload.get('ein')
    aliases = payload.get('alternate_names', [])
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 300: raise ValueError('Organization name required')
    if not isinstance(ein, str) or not re.fullmatch(r'\d{2}-?\d{7}', ein): raise ValueError('Valid EIN required')
    if (not isinstance(aliases, list) or len(aliases) > 32
            or any(not isinstance(n, str) or not 1 <= len(n.strip()) <= 300 for n in aliases)):
        raise ValueError('Invalid alternate names')
    states = payload.get('states', [])
    if not isinstance(states, list) or not states or any(s not in master.SUPPORTED_STATES for s in states):
        raise ValueError('Select supported states')
    mode = payload.get('mode', 'standard')
    if mode not in ('sales', 'standard'): raise ValueError('Invalid mode')
    nonce = payload.get('request_id')
    if not isinstance(nonce, str) or not re.fullmatch(r'[a-f0-9-]{36}', nonce): raise ValueError('Invalid request ID')
    external = sorted(set(states) & {'IL', 'GA'})
    internal = sorted(set(states) - set(external))
    if not internal: raise ValueError('Use the browser connector for these states')
    request = {'organization_name': name.strip(), 'ein': ein, 'alternate_names': aliases,
        'states': internal, 'mode': mode, 'kind': 'registration',
        'state_concurrency': 20 if mode == 'sales' else 15, 'external_state_slots': len(external)}
    idempotency = hashlib.sha256(json.dumps([owner, nonce]).encode()).hexdigest()
    accepted = call('/api/lab/workflows', request, idempotency)
    now = int(time.time())
    record = {'id': accepted['id'], 'owner': owner, 'issued': now, 'expires': now + 1500,
        'version': master.APP_VERSION, 'ein': master.canonical_ein_digits(ein), 'name': name,
        'states': internal, 'mode': mode}
    return {'token': pack(master, record), 'external_states': external, 'state_concurrency': request['state_concurrency']}


def public_result(master, job, record):
    result = job.get('result')
    if not isinstance(result, dict):
        if job['phase'] != 'done': return None
        return {'ein': record['ein'], 'organization_name': record['name'], 'state': job['state'],
            'app_version': master.APP_VERSION, 'status': 'Unable to Confirm', 'success': False,
            'status_reason': 'SALES_TIME_LIMIT' if record['mode'] == 'sales' else 'WORKFLOW_INCOMPLETE',
            'comments': 'The state check did not complete within this run. Registration status remains unconfirmed.'}
    if (master.canonical_ein_digits(str(result.get('ein', ''))) != record['ein']
            or result.get('state') != job['state'] or job['state'] not in record['states']
            or result.get('app_version') != os.environ.get('CE_STAGING_WORKFLOW_VERSION')):
        raise ValueError('Worker result identity or release mismatch')
    data = {key: value for key, value in result.items() if not key.startswith(('lab_', '_worker_'))}
    data['execution_version'] = data['app_version']
    data['app_version'] = master.APP_VERSION
    context = result.get('_worker_identity_review')
    if context:
        master.attach_identity_review(data, context)
    return data


def handle(master, handler):
    if not enabled(master):
        handler._send_json(503, {'error': 'Optimized staging execution is not enabled.'}); return
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        if not 0 < length <= 32768: raise ValueError('Invalid workflow input size')
        payload = json.loads(handler.rfile.read(length))
        if not isinstance(payload, dict): raise ValueError('Object required')
        email = master.normalize_email(payload.get('email', ''))
        device = master.normalize_device_id(payload.get('device_id', ''))
        passcode = str(payload.get('admin_passcode', '')).strip()
        if master.staging_access_error(email, passcode) or not master.is_verified_internal_passcode(email, passcode):
            handler._send_json(403, {'error': 'Sign in with authorized Compliance Express access.'}); return
        owner = [email, device]
        action = payload.get('action')
        if action == 'start':
            if payload.get('consent') is not True: raise ValueError('Consent is required')
            data = prepare(master, payload, owner)
        else:
            record = unpack(master, payload.get('token'), owner)
            path = '/api/lab/workflows/' + record['id']
            if action == 'poll':
                status = call(path)
                if (status.get('source_version') != os.environ.get('CE_STAGING_WORKFLOW_VERSION')
                        or status.get('ein') != record['ein']): raise ValueError('Worker release mismatch')
                data = {key: status[key] for key in ('phase','completed','total','submitted','deadline','started','finished')}
                data['results'] = [r for job in status['jobs'] if job['state'] in record['states']
                                   and (r := public_result(master, job, record)) is not None]
            elif action in ('cancel', 'release-external'):
                call(path + '/' + action, {})
                data = {'ok': True}
            else: raise ValueError('Invalid workflow action')
        handler._send_json(200, data, {'Cache-Control': 'no-store'})
    except (ValueError, TypeError, KeyError, UnicodeError):
        handler._send_json(400, {'error': 'Invalid or expired workflow. Start a new check.'})
    except urllib.error.HTTPError as exc:
        handler._send_json(429 if exc.code == 429 else 503, {'error': 'State-check workers are temporarily unavailable. Retry this check.'})
    except Exception as exc:
        master.log_error('Optimized workflow failed: ' + type(exc).__name__)
        handler._send_json(503, {'error': 'State-check progress is temporarily unavailable. Retry this check.'})
