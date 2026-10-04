"""Deployment identities for the approved pool and the disposable 29.2 trial.

This module contains no state rules. The trial requires an immutable resource
manifest populated by provisioning; changing a public URL alone cannot enable
the performance paths or connect a trial worker to the approved queue.
"""
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse

APPROVED_ORIGIN = 'https://instant-compliance-snapshot-api-hn4v.onrender.com'
APPROVED_DATABASE = 'dpg-dar6utvavr4c7380ou60-a'
PROTECTED_SERVICES = frozenset({
    'srv-d8a38lnavr4c73d4ib30', 'srv-d82afqjrjlhs738j7or0',
    'srv-d8u0hsu7r5hc73aqfsg0', 'srv-dar7adgu01pc738fsmgg',
    'srv-d8tf2mjtqb8s73fhgcdg', 'srv-d7nsq85ckfvc73f8b2lg',
})
PROTECTED_ORIGINS = frozenset({
    APPROVED_ORIGIN, 'https://staging.compliance-express.com',
    'https://compliance-express.com', 'https://www.compliance-express.com',
    'https://instant-compliance-snapshot-api-staging-8dnk.onrender.com',
    'https://instant-compliance-snapshot-api-staging.onrender.com',
})
TRIAL_VERSION = '2026.09.29.2-performance-lab'
TRIAL_RELEASE_LABEL = '29.2CK'
TRIAL_DATABASE_NAME = 'cc_final_four_29_2'
MANIFEST = Path(__file__).with_name('final-four-resources.json')


def trial_sales_cutoff(payload, identity):
    """An explicit bounded cutoff study in the disposable lab only.

    Ordinary Sales retains 60 seconds, including the approved performance
    pool. This does not change matching, state budgets or source evidence.
    """
    if 'sales_cutoff_seconds' not in payload:
        return 60
    value = payload['sales_cutoff_seconds']
    if (not identity or payload.get('mode') != 'sales'
            or payload.get('kind', 'registration') != 'registration'
            or type(value) is not int or value not in (60, 70, 80, 90)):
        raise ValueError('Cutoff studies require isolated lab Sales and 60, 70, 80 or 90 seconds')
    return value


@lru_cache(maxsize=1)
def _manifest():
    try:
        if MANIFEST.stat().st_size > 16384:
            return None
        return json.loads(MANIFEST.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def trial_identity(env=None, manifest=None, now=None):
    """Return a fully isolated active identity, or fail closed with None."""
    env = os.environ if env is None else env
    if env.get('CE_FINAL_FOUR_TRIAL') != '1':
        return None
    data = _manifest() if manifest is None else manifest
    if not isinstance(data, dict):
        return None
    try:
        if data['version'] != TRIAL_VERSION or env.get('CE_APP_VERSION') != TRIAL_VERSION:
            return None
        origin, api, worker, database = (data[k] for k in ('origin', 'api', 'worker', 'database'))
        url = urlparse(origin)
        if (origin in PROTECTED_ORIGINS or url.scheme != 'https' or url.path or url.query
                or url.fragment or url.username or url.password or url.port
                or not (url.hostname or '').endswith('.onrender.com')):
            return None
        if env.get('PUBLIC_BASE_URL') != origin:
            return None
        if (api['name'] != 'charityclarity-final-four-29-2'
                or worker['name'] != 'charityclarity-final-four-29-2-worker'
                or api['id'] == worker['id']):
            return None
        for item in (api, worker):
            if item['id'] in PROTECTED_SERVICES or not re.fullmatch(r'srv-[a-z0-9]+', item['id']):
                return None
        role = worker if env.get('CE_LAB_ROLE') == 'worker' else api
        if env.get('RENDER_SERVICE_ID') != role['id'] or env.get('RENDER_SERVICE_NAME') != role['name']:
            return None
        if (database['host'] == APPROVED_DATABASE
                or not re.fullmatch(r'dpg-[a-z0-9]+-a', database['host'])
                or database['name'] != TRIAL_DATABASE_NAME):
            return None
        if env.get('CE_FINAL_FOUR_CHILD') == '1':
            # Only the already-validated supervisor supplies this marker.
            # A state process must not receive database or control-plane keys.
            if (env.get('CE_LAB_DURABLE_QUEUE') != '0' or env.get('CE_LAB_DATABASE_URL')
                    or env.get('CE_TEST_DATABASE_URL') or env.get('RENDER_API_KEY')):
                return None
        else:
            dsn = urlparse(env.get('CE_LAB_DATABASE_URL', ''))
            if (dsn.scheme not in ('postgres', 'postgresql')
                    or dsn.hostname not in (database['host'], database['host'] + '.oregon-postgres.render.com')
                    or dsn.path != '/' + TRIAL_DATABASE_NAME
                    or env.get('CE_LAB_DURABLE_QUEUE') != '1'):
                return None
        started, expires = float(data['activated_epoch']), float(data['expires_epoch'])
        clock = time.time() if now is None else now
        if not started <= clock < expires or not 0 < expires - started <= 120 * 3600:
            return None
        if not 0 < float(data['spending_cap_usd']) <= 80:
            return None
        return data
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def performance_origin_enabled(env=None):
    env = os.environ if env is None else env
    if env.get('CE_FINAL_FOUR_TRIAL') == '1':
        return trial_identity(env) is not None
    # Preserve the existing release's origin condition exactly.
    return env.get('PUBLIC_BASE_URL') == APPROVED_ORIGIN


def configured_lab_origin():
    if os.environ.get('CE_FINAL_FOUR_TRIAL') != '1':
        return APPROVED_ORIGIN
    identity = trial_identity()
    if identity is None:
        raise RuntimeError('29.2 requires an active isolated resource manifest')
    return identity['origin']
