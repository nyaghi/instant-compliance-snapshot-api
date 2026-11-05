"""Bounded related-group retrieval; never substitute a group's identity or status.

No organization names/EINs or registration outcomes are configured here. IRS
metadata can establish a reviewable relationship, not state registration scope.
"""
import copy
import json
import re
import secrets
import time
from urllib.parse import urlencode

STATES = frozenset({'CA', 'MA', 'MD', 'MI', 'OR', 'VA', 'WA'})
REASON = 'DOCUMENTED_GROUP_IDENTITY_REVIEW'
API = 'https://projects.propublica.org/nonprofits/api/v2/'


def profile(master, ein, deadline):
    payload = master.PUBLIC_PROFILE_CACHE.get(ein)
    if not payload:
        payload = json.loads(master.identity_fetch(API + 'organizations/' + ein + '.json', deadline))
    row = payload.get('organization') or {}
    if master.canonical_ein_digits(str(row.get('ein', ''))) != ein:
        raise ValueError('IRS profile EIN differs from request')
    return row


def proof_from_profiles(master, name, ein, member, group):
    digits = master.canonical_ein_digits
    key = master.complete_name_identity_key
    group_ein = digits(str(group.get('ein', '')))
    number = str(member.get('exemption_number') or '').zfill(4)
    # Require an explicitly identified group return, the same issued group
    # number, full legal name, and city/state. A parent alias is insufficient.
    if (digits(str(member.get('ein', ''))) != digits(ein)
            or not re.fullmatch(r'\d{9}', group_ein) or group_ein == digits(ein)
            or not re.fullmatch(r'\d{4}', number) or number == '0000'
            or str(group.get('exemption_number') or '').zfill(4) != number
            or str(member.get('affiliation_code')) not in {'6', '9'}
            or str(group.get('affiliation_code')) not in {'6', '9'}
            or key(group.get('sort_name', '')) != key('Group Return')
            or not key(name) or key(name) != key(member.get('name', ''))
            or key(name) != key(group.get('name', ''))
            or any(not member.get(k) or str(member[k]).casefold() != str(group.get(k, '')).casefold()
                   for k in ('city', 'state'))):
        return None
    # Do not inherit a parent's primary BMF name for a distinct subordinate.
    secondary = str(member.get('sort_name') or '').strip()
    if secondary and key(secondary) not in {key(name), key('Group Return')}:
        return None
    return {'kind': 'same_name_irs_group_return', 'requested_ein': digits(ein),
            'registry_ein': group_ein, 'name': name, 'group_exemption_number': number,
            'member_source_url': 'https://projects.propublica.org/nonprofits/organizations/' + digits(ein),
            'group_source_url': 'https://projects.propublica.org/nonprofits/organizations/' + group_ein,
            'observed_at': int(time.time())}


def find_relationship(master, name, ein, deadline):
    member = profile(master, ein, deadline)
    if (not member.get('exemption_number') or str(member.get('affiliation_code')) not in {'6', '9'}
            or master.complete_name_identity_key(member.get('name', '')) != master.complete_name_identity_key(name)):
        return None
    query = '"' + str(member['name']).replace('"', '') + '"'
    payload = json.loads(master.identity_fetch(API + 'search.json?' + urlencode({'q': query}), deadline))
    rows = payload.get('organizations')
    if not isinstance(rows, list) or len(rows) > 25:
        return None
    candidates = [r for r in rows if isinstance(r, dict)
        and master.complete_name_identity_key(r.get('name', '')) == master.complete_name_identity_key(name)
        and re.search(r'\bgroup\s+return\s*$', str(r.get('sub_name', '')), re.I)
        and master.canonical_ein_digits(str(r.get('ein', ''))) != ein]
    if len(candidates) != 1:
        return None
    other = master.canonical_ein_digits(str(candidates[0].get('ein', '')))
    group = profile(master, other, deadline)
    return proof_from_profiles(master, name, ein, member, group)


def allowed(master, row, name, ein):
    p = row.get('group_identity')
    if not isinstance(p, dict):
        return False
    requested = master.canonical_ein_digits(ein)
    observed = master.canonical_ein_digits(str(row.get('ein', '')))
    return (p.get('kind') == 'same_name_irs_group_return'
        and p.get('requested_ein') == requested and p.get('registry_ein') == observed
        and re.fullmatch(r'\d{9}', observed or '') is not None and observed != requested
        and re.fullmatch(r'(?!0000)\d{4}', str(p.get('group_exemption_number', ''))) is not None
        and master.complete_name_identity_key(p.get('name', '')) == master.complete_name_identity_key(name)
        and master.complete_name_identity_key(row.get('name', '')) == master.complete_name_identity_key(name)
        and p.get('member_source_url') == 'https://projects.propublica.org/nonprofits/organizations/' + requested
        and p.get('group_source_url') == 'https://projects.propublica.org/nonprofits/organizations/' + observed
        and type(p.get('observed_at')) is int and 0 <= time.time() - p['observed_at'] < 86400)


def explanation(p):
    return (f"Entered EIN {p['requested_ein']}; registry group-return EIN {p['registry_ein']}. "
            f"IRS metadata gives both same-name records group exemption {p['group_exemption_number']}. "
            "This relationship does not establish that this state's registration covers the entered organization. "
            "Confirm whether this record applies. Both EINs are retained; the state record determines its status.")


def convert(master, base, related, proof):
    """Retain the retrieved group's original pixels with explicit ownership notes."""
    from deployment import state_snapshots as ss
    row = {'name': related.get('matched_registry_name', ''),
           'identifier': related.get('matched_registry_identifier', ''),
           'ein': proof['registry_ein'], 'url': related.get('source_url', ''),
           'raw_status': related.get('raw_status_text', ''), 'status': related.get('status'),
           'expiration': related.get('computed_due_date', ''), 'group_identity': proof,
           '_identity_outcome': 'possible'}
    if (not allowed(master, row, base['organization_name'], base['ein'])
            or related.get('success') is not True or not row['identifier']
            or row['status'] not in {'Current', 'Upcoming Filing', 'Delinquent', 'Exempt', 'Pending',
                'Suspended', 'Revoked', 'Failed to Renew', 'Closed / Withdrawn / Canceled'}
            or ss.digits(related.get('ein')) != proof['registry_ein'] or related.get('state') != base['state']
            or (related.get('verified_registry_ein') and ss.digits(related['verified_registry_ein']) != proof['registry_ein'])
            or related.get('identity_review') or related.get('_worker_identity_review')):
        return None
    data = copy.deepcopy(base)
    note = explanation(proof)
    history = data.get('_worker_search_history') or {}
    run_id = history.get('source_archive_run_id') or secrets.token_hex(16)
    related_history = related.get('_worker_search_history') or {}
    if related_history:
        if not history:
            history = {**copy.deepcopy(related_history), 'ein': ss.digits(base['ein']),
                       'organization_name': base['organization_name'], 'source_archive_run_id': run_id,
                       'completed': [], 'search_failed_receipts': []}
        if related_history.get('state') != base['state'] or related_history.get('ein') != proof['registry_ein']:
            raise ValueError('Related search history belongs to another identity')
        for field in ('completed', 'search_failed_receipts'):
            history.setdefault(field, []).extend(copy.deepcopy(related_history.get(field, [])))
        history['issued'] = min(history['issued'], related_history['issued'])
        # Member and group capture runs each start request order at one.
        # Rebase only the joined presentation order; keep query hashes and
        # original timestamps/IDs intact, including incomplete attempts.
        receipts = [x['search_receipt'] for x in history.get('completed', [])]
        receipts += history.get('search_failed_receipts', [])
        receipts.sort(key=lambda x: x.get('issued_at') or x.get('completed_at') or x.get('reported_at'))
        history['history_order'] = 'issued-sequence-v1'
        for sequence, receipt in enumerate(receipts, 1):
            receipt['source_order'] = sequence
        data['_worker_search_history'] = history
    assets = []
    for asset in related.get('_worker_source_archives', [])[:12]:
        if asset.get('identifier') != row['identifier'] or asset.get('record_name') != row['name']:
            continue
        meta, raw = ss.validate_asset(asset, ein=proof['registry_ein'], state=base['state'], run_id=asset.get('run_id'))
        # Pixels, public source URL, record number and capture time are unchanged.
        # This archive belongs to the user's review, not to an automatic match.
        rebased = {**asset, 'ein': ss.digits(base['ein']), 'run_id': run_id,
                   'organization_name': base['organization_name'],
                   'capture_note': note + ' Original source capture: ' + meta.get('capture_note', '')}
        # OR's extract proof remains about the group EIN; never recast it as
        # an exact-EIN extract match for the member.
        rebased.pop('or_export_evidence', None)
        ss.validate_asset(rebased, ein=base['ein'], state=base['state'], run_id=run_id)
        assets.append(rebased)
    if not assets and ss.STORE is not None:
        ref = re.fullmatch(r'/state-snapshots/([a-f0-9]{64})\.pdf', str(related.get('evidence_url', '')))
        loaded = ss.STORE.load(ref[1]) if ref else None
        if loaded:
            meta, raw, _ = loaded
            if (meta.get('ein') == proof['registry_ein'] and meta.get('state') == base['state']
                    and meta.get('identifier') == row['identifier'] and meta.get('record_name') == row['name']):
                asset = ss.asset_for(raw, kind=meta['kind'], state=base['state'], ein=base['ein'],
                    run_id=run_id, source_url=meta['source_url'], identifier=row['identifier'], record_name=row['name'],
                    organization_name=base['organization_name'], public_text=meta.get('public_text', ''), capture_note=note)
                asset['captured_at'] = meta['captured_at']; assets.append(asset)
    data.update(status='Needs Review', success=False, reason_code=REASON, status_reason=REASON,
        matched_registry_name='', matched_registry_identifier='', raw_status_text='', computed_due_date='',
        error='', source_note=note, comments=note, evidence_url='', group_identity=proof,
        _worker_identity_review={'records': [row], 'search_complete': False, 'exclusive': True},
        _worker_source_archives=assets)
    data.pop('identity_review', None)
    return data


def completed_group_negative(base, related, proof):
    """A completed related no-match is not a transport or identity failure."""
    from deployment.search_history import manifest
    for row, ein in [(base, proof['requested_ein']), (related, proof['registry_ein'])]:
        if (not isinstance(row, dict) or row.get('state') != base['state']
                or re.sub(r'\D', '', str(row.get('ein', ''))) != ein
                or row.get('status') != 'Not Registered' or row.get('success') is not True
                or row.get('error') or row.get('matched_registry_identifier')
                or row.get('identity_review') or row.get('_worker_identity_review')):
            return None
        history = row.get('_worker_search_history') or {}
        if (history.get('state') != base['state'] or history.get('ein') != ein
                or not history.get('completed') or history.get('search_failed_receipts')
                or not isinstance(history.get('issued'), (int, float))):
            return None
        try:
            manifest(history, row, {}, time.time())
        except (ValueError, KeyError, TypeError):
            return None
    data = copy.deepcopy(base)
    history = data['_worker_search_history']
    related_history = related['_worker_search_history']
    history['completed'].extend(copy.deepcopy(related_history['completed']))
    history['issued'] = min(history['issued'], related_history['issued'])
    # These are sequential capture runs, each with its own one-based order.
    # Preserve all original receipts while assigning the joined report order.
    history['completed'].sort(key=lambda item: item['search_receipt'].get('issued_at', item['search_receipt']['completed_at']))
    history['history_order'] = 'issued-sequence-v1'
    for sequence, item in enumerate(history['completed'], 1):
        item['search_receipt']['source_order'] = sequence
    try:
        manifest(history, data, {}, time.time())
    except (ValueError, KeyError, TypeError):
        return None
    note = (f"The requested EIN {proof['requested_ein']} and documented group-return EIN "
            f"{proof['registry_ein']} both completed the state's search without a qualifying registration. "
            "The search history retains both identities and the actual queries; no group registration was assumed.")
    data.update(group_identity=proof, reason_code='GROUP_AND_MEMBER_COMPLETED_NO_MATCH',
                source_note=note, comments=note)
    return data


def recover(master, base, lookup):
    """One bounded fallback after completed no-match/CA identity conflict only."""
    from deployment.state_snapshots import DEADLINE, CaptureRun
    state = base.get('state')
    negative = base.get('success') is True and base.get('status') == 'Not Registered'
    conflict = state == 'CA' and str(base.get('error', '')).startswith('CA name fallback:')
    if (state not in STATES or not (negative or conflict) or base.get('identity_review')
            or base.get('_worker_identity_review') or DEADLINE.get() - time.monotonic() < 8):
        return base
    started = time.monotonic()
    proof = None
    related = None

    def incomplete(error_type=''):
        # Retain why the related lookup failed instead of presenting the
        # member's earlier empty-search explanation as the current outcome.
        observed = related if isinstance(related, dict) else {}
        diagnostic = {key: observed.get(key, '') for key in
                      ('status', 'status_reason', 'reason_code', 'evidence_capture')}
        if error_type:
            diagnostic['error_type'] = error_type
        reason = str(observed.get('source_note') or observed.get('comments') or '').strip()
        note = (f"Entered EIN {proof['requested_ein']}; registry group-return EIN {proof['registry_ein']}. "
                "The documented group relationship does not establish this state's registration coverage. "
                "The related state record could not be confirmed in this lookup.")
        if reason:
            note += ' Related lookup: ' + reason[:1200]
        return {**base, 'status': 'Unable to Confirm', 'success': False, 'group_identity': proof,
                'reason_code': 'GROUP_RECORD_LOOKUP_INCOMPLETE', 'status_reason': 'GROUP_RECORD_LOOKUP_INCOMPLETE',
                'comments': note, 'source_note': note, 'group_lookup_diagnostics': diagnostic,
                'lookup_seconds': round(float(base.get('lookup_seconds') or 0) + time.monotonic() - started, 2)}
    try:
        proof = find_relationship(master, base['organization_name'], master.canonical_ein_digits(base['ein']),
                                  min(DEADLINE.get() - 4, started + 4))
        if not proof or DEADLINE.get() - time.monotonic() < 4:
            return base
        token = DEADLINE.set(min(DEADLINE.get(), started + 45))
        try:
            with CaptureRun(base['organization_name'], proof['registry_ein'], state) as capture:
                capture.semantic_history_scope = True
                capture.known_names = [base['organization_name']]
                related = lookup(base['organization_name'], proof['registry_ein'], state)
                # Keep all observed group queries even when its own lookup is
                # conclusive; the member's identity decision is still pending.
                had_review = bool(related.get('_worker_identity_review') or related.get('identity_review'))
                if not had_review:
                    related['_worker_identity_review'] = {'records': []}
                related = capture.finish(related)
                if not had_review:
                    related.pop('_worker_identity_review', None)
        finally:
            DEADLINE.reset(token)
        data = completed_group_negative(base, related, proof) or convert(master, base, related, proof)
        if data:
            data['lookup_seconds'] = round(float(base.get('lookup_seconds') or 0) + time.monotonic() - started, 2)
            return data
        # The relationship is known but the related source was unavailable.
        # Do not leave a definitive no-registration claim behind.
        return incomplete()
    except Exception as exc:
        if proof:
            return incomplete(type(exc).__name__)
        return base
