"""Current short-name license: prove its linked full corporate identity.

Independent of the old license's corporate ID. No generic-name acceptance:
the source link, complete legal name, EIN-linked address and license fields
must all agree. Runs only for one newer candidate of an accepted old record.
"""
import re, time, math, json, base64
from datetime import date, datetime
from types import SimpleNamespace

CORPORATE_URL = 'https://boss.dc.gov/business/info'

def address_key(value):
    from registry_snapshot_server import registry_street_key
    return registry_street_key(value).replace('P O BOX', 'PO BOX')

def candidate(master, org, selected, rows):
    from deployment.dc_native_capture import expected_record
    from deployment.dc_boss_evidence import norm
    if (selected.get('status') not in {'Delinquent', 'Closed / Withdrawn / Canceled'}
            or selected.get('_identity_outcome') != 'accepted' or not selected.get('expiration')):
        return None
    names = list(dict.fromkeys([org.organization_name, *master.known_names_for_ein(org.ein)]))
    def short_name(row):
        words = master.normalized_match_name(row.get('name', '')).split()
        return (len(norm(row.get('name'))) >= 4 and master.distinctive_match_tokens(row.get('name', ''))
                and any(master.normalized_match_name(n).split()[:len(words)] == words
                        and norm(n) != norm(row.get('name')) for n in names))
    eligible = [r for r in rows if r is not selected and not r.get('ein')
        and r.get('match', {}).get('reason') not in {'REJECT_DIFFERENT_EIN', 'USER_REJECTED_IDENTITY'}
        and r.get('status') in {'Current', 'Upcoming Filing'} and r.get('raw_status') == 'Active'
        and r.get('license_category', '').casefold() == 'charitable solicitation'
        and r.get('expiration') and r['expiration'] > selected['expiration'] and short_name(r)]
    if len(eligible) != 1:
        return None
    ein = master.canonical_ein_digits(org.ein)
    with master.IDENTITY_CACHE_LOCK:
        sources = [v for (e, _, _), (expires, v) in master.IDENTITY_SOURCE_CACHE.items() if e == ein and expires > time.time()]
    profile = (master.PUBLIC_PROFILE_CACHE.get(ein, {}).get('organization') or {})
    if master.canonical_ein_digits(str(profile.get('ein', ''))) == ein:
        sources.append({'source':'IRS organization metadata','address':dict(profile, address_role='organization')})
    addresses = [dict(street=a['street'], region=a['state'], postal=a['postal_code'][:5])
                 for a in master.discovered_organization_addresses(ein, sources)
                 if a.get('street') and re.fullmatch(r'\d{5}', a.get('postal_code', '')[:5])]
    expected = expected_record(eligible[0])
    return dict(candidate=expected, proof={'names': names[:32], 'addresses': addresses[:12]}) if expected and addresses else None

def request_for_candidate(request):
    from deployment.dc_boss_evidence import norm
    c, p = request.get('corporate_continuity_candidate'), request.get('corporate_link_proof')
    if (type(request.get('corporate_continuity_schema')) is not int or request['corporate_continuity_schema'] != 2
            or request.get('review_candidate') or request.get('boss_reconcile_schema')
            or not isinstance(c, dict) or set(c) != {'identifier','name','raw_status','expiration'}
            or not isinstance(p, dict) or set(p) != {'names','addresses'}
            or not isinstance(p['names'], list) or not 1 <= len(p['names']) <= 32
            or any(not isinstance(n,str) or not 1 <= len(n) <= 300 for n in p['names'])
            or not isinstance(p['addresses'], list) or not 1 <= len(p['addresses']) <= 12
            or request.get('raw_status','').casefold() not in {'expired - enforcement','expired','closed','cancelled','canceled','withdrawn'}
            or c['raw_status'] != 'Active' or not re.fullmatch(r'\d{5,16}',str(c['identifier']))
            or c['identifier'] == request['identifier'] or norm(c['name']) == norm(request['name'])
            or date.fromisoformat(c['expiration']) <= date.fromisoformat(request['expiration'])):
        raise ValueError('Invalid DC linked corporate request')
    for a in p['addresses']:
        if (not isinstance(a,dict) or set(a) != {'street','region','postal'}
                or not isinstance(a['street'],str) or not 1 <= len(a['street']) <= 300
                or not re.fullmatch(r'[A-Za-z]{2}',a['region']) or not re.fullmatch(r'\d{5}',a['postal'])):
            raise ValueError('Invalid EIN-linked office')
    return {**{k:v for k,v in request.items() if k not in {'corporate_continuity_schema','corporate_continuity_candidate','corporate_link_proof'}}, **c}

def corporate_fields(url, text):
    if url != CORPORATE_URL or not isinstance(text,str) or not 1 <= len(text) <= 80000:
        return None
    # Read only the entity heading, before jurisdiction/agent/owner sections.
    part = re.split(r'Jurisdiction of Formation|Biennial Report Information', text, maxsplit=1)[0]
    lines = [v.strip() for v in part.splitlines() if v.strip()]
    labels = ['Record Name','Entity Type','Election Type','Initial File No.','Entity Status','Street Address','Mailing Address','Entity Email','File Date','Purpose']
    if any(lines.count(k) != 1 for k in labels): return None
    positions = [lines.index(k) for k in labels]
    if positions != sorted(positions): return None
    f = {k:' '.join(lines[positions[i]+1:positions[i+1]]) for i,k in enumerate(labels[:-1])}
    if not re.fullmatch(r'[A-Z]\d{6,16}',f['Initial File No.']) or not f['Record Name'] or 'Nonprofit' not in f['Entity Type']:
        return None
    return f

def validate(result, payload):
    from deployment import dc_boss_evidence as b
    from deployment.dc_corporate_continuity import corporate_record
    request = b.describe(result)
    if not request or payload.get('request') != request: raise ValueError('DC linked request changed')
    target = request_for_candidate(request)
    current, corporate = payload.get('current_license'), payload.get('corporate_detail')
    if not isinstance(current,dict) or not isinstance(corporate,dict) or current.get('request') != target:
        raise ValueError('DC linked original captures missing')
    for item in (current,corporate):
        stamp = item.get('captured_at')
        if (type(stamp) not in (int,float) or not math.isfinite(stamp)
                or not request['issued_at'] <= stamp <= min(time.time()+5,request['expires_at'])
                or not isinstance(item.get('image'),str) or not 1 <= len(item['image']) <= 4_000_000):
            raise ValueError('DC linked capture invalid')
    fields = b.fields(current.get('url'),current.get('public_text'),target)
    link = corporate_record(current.get('public_text',''))
    entity = corporate_fields(corporate.get('url'),corporate.get('public_text'))
    if (not fields or fields != current.get('source_fields') or not link or not entity
            or corporate.get('linked_identifier') != link[1] or entity['Initial File No.'] != link[1]
            or b.norm(link[0]) != b.norm(target['name'])
            or b.norm(entity['Record Name']) not in {b.norm(n) for n in request['corporate_link_proof']['names']}
            or address_key(entity['Street Address']) != address_key(fields['Premise Address'])):
        raise ValueError('DC corporate identity or license address differs')
    addresses = [entity['Street Address'],entity['Mailing Address']]
    def matches(a, shown):
        parts = [v.strip() for v in shown.split(',')]
        if len(parts) < 4: return False
        if parts[-1].upper() in {'USA','UNITED STATES'}: parts.pop()
        return (parts[-2].upper() == a['region'].upper() and parts[-1][:5] == a['postal']
                and address_key(', '.join(parts[:-3])) == address_key(a['street']))
    if not any(matches(a,shown) for a in request['corporate_link_proof']['addresses'] for shown in addresses):
        raise ValueError('DC corporate office lacks EIN corroboration')
    return request,target,current,corporate,entity

def asset(result,payload):
    request,target,current,corporate,entity = validate(result,payload)
    return dict(kind='image_pages',state='DC',ein=request['ein'],run_id=request['run_id'],source_url=current['url'],
        captured_at=current['captured_at'],content=base64.b64encode(json.dumps([current['image'],corporate['image']]).encode()).decode(),identifier=target['identifier'],
        record_name=target['name'],organization_name=result.get('organization_name',''),
        public_text=current['public_text']+'\n'+corporate['public_text'],
        capture_note='Original current license and its source-linked corporate profile. Full legal name and EIN-linked organization address confirmed.')

def update(result,payload):
    request,target,current,corporate,entity = validate(result,payload)
    import registry_snapshot_server as master
    expiry=date.fromisoformat(target['expiration']); fields=current['source_fields']
    issue=datetime.strptime(fields['Issue Date'],'%m/%d/%Y').date(); status=master.licensed_charity_status(fields['License Status'],expiry)
    if status not in {'Current','Upcoming Filing'}: raise ValueError('DC linked license no longer current')
    out=dict(status=status,success=True,matched_registry_identifier=target['identifier'],matched_registry_name=target['name'],
        raw_status_text=fields['License Status'],computed_due_date=expiry.isoformat(),source_url=current['url'],
        renewal_date=issue.isoformat(),renewal_date_type='current_issue_date',renewal_date_source_label='Issue Date',
        renewal_date_source_url=current['url'],renewal_date_note='Current license issue date from BOSS.',
        comments=f"DC BOSS lists {target['name']} ({target['identifier']}) as Active, expiring {expiry.isoformat()}. Its source-linked corporate record {entity['Initial File No.']} identifies {entity['Record Name']}; the organization address agrees with EIN-linked evidence. This current charitable license supersedes the expired license.",
        dc_source_reconciliation=dict(schema=1,kind='corporate_continuity',identity_method='linked_corporate_profile',
            corporate_record=entity['Initial File No.'],ein=request['ein'],run_id=request['run_id'],prior_identifier=request['identifier'],
            prior_name=request['name'],prior_status=result['status'],prior_expiration=request['expiration'],identifier=target['identifier'],
            name=target['name'],expiration=target['expiration'],raw_status=fields['License Status'],status=status,
            issue_date=issue.isoformat(),source_url=current['url'],captured_at=current['captured_at']))
    out.update(master.renewal_filing_metadata(SimpleNamespace(**{**result,**out}),out,status))
    return out
