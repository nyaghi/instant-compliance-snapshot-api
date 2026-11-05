"""Same corporate record required before replacing an old DC license.

No company identifiers are hardcoded. Both exact license details must be read
and captured in the existing aggregate active allowance and signed deadline.
"""
import re, time, math
from datetime import date, datetime
from types import SimpleNamespace

def candidate(selected, rows):
    from deployment.dc_native_capture import expected_record
    from deployment.dc_boss_evidence import norm
    if (selected.get('status') not in {'Delinquent','Closed / Withdrawn / Canceled'}
        or not selected.get('expiration')
        or selected.get('_identity_outcome') != 'accepted'
        or selected.get('address_evidence',{}).get('decision') != 'corroborated'):
        return None
    current=[r for r in rows if r is not selected and r.get('_identity_outcome') in {'possible','conflict'}
        and r.get('match',{}).get('reason') != 'REJECT_DIFFERENT_EIN'
        and norm(r.get('name')) == norm(selected.get('name'))
        and r.get('status') in {'Current','Upcoming Filing'}
        and str(r.get('raw_status','')).casefold() == 'active'
        and str(r.get('license_category','')).casefold() == 'charitable solicitation'
        and r.get('expiration') and r['expiration'] > (selected.get('expiration') or date.min)]
    return expected_record(current[0]) if len(current)==1 else None

def request_for_candidate(request):
    if request.get('corporate_continuity_schema') == 2:
        from deployment.dc_linked_identity import request_for_candidate as linked_request
        return linked_request(request)
    value=request.get('corporate_continuity_candidate')
    if (request.get('corporate_continuity_schema') != 1 or type(request.get('corporate_continuity_schema')) is not int
        or not isinstance(value,dict) or set(value)!={'identifier','name','raw_status','expiration'}
        or request.get('review_candidate') or request.get('boss_reconcile_schema')
        or request.get('raw_status','').casefold() not in {'expired - enforcement','expired','closed','cancelled','canceled','withdrawn'}
        or value['raw_status']!='Active'):
        raise ValueError('Invalid DC corporate continuity request')
    from deployment.dc_boss_evidence import norm
    if (not re.fullmatch(r'\d{5,16}',str(value['identifier'])) or value['identifier']==request['identifier']
        or norm(value['name'])!=norm(request['name'])
        or date.fromisoformat(value['expiration'])<=date.fromisoformat(request['expiration'])):
        raise ValueError('DC candidate identity or period changed')
    return {**{k:v for k,v in request.items() if k not in {'corporate_continuity_schema','corporate_continuity_candidate'}},**value}

def corporate_record(text):
    if text.count('Licensee Information')!=1 or text.count('Registered/Resident Agent Information')!=1:
        return None
    part=text.split('Licensee Information')[1].split('Registered/Resident Agent Information')[0]
    match=re.fullmatch(r'\s*Licensee Name\s+(.+?)\s+Record Name\s+([A-Z]\d{6,16})\s+Entity Status\s+(.+?)\s*',part,re.S)
    return match.groups() if match else None

def validate(result,payload):
    from deployment import dc_boss_evidence as b
    request=b.describe(result)
    if not request or payload.get('request')!=request:raise ValueError('DC source binding changed')
    target=request_for_candidate(request)
    prior=payload.get('prior_license');current=payload.get('current_license')
    if not isinstance(prior,dict) or not isinstance(current,dict):raise ValueError('Both original DC captures required')
    for item,expected in [(prior,request),(current,target)]:
        if item.get('request')!=expected:raise ValueError('DC continuity request changed')
        stamp=item.get('captured_at')
        if type(stamp) not in (int,float) or not math.isfinite(stamp) or not expected['issued_at']<=stamp<=min(time.time()+5,expected['expires_at']):
            raise ValueError('DC continuity capture outside deadline')
        fields=b.fields(item.get('url'),item.get('public_text'),expected)
        if not fields or fields!=item.get('source_fields'):raise ValueError('DC license fields changed')
        if not isinstance(item.get('image'),str) or not 1<=len(item['image'])<=4_000_000:raise ValueError('DC original image missing')
    old=corporate_record(prior['public_text']);new=corporate_record(current['public_text'])
    if not old or not new or old[1]!=new[1] or b.norm(old[0])!=b.norm(request['name']) or b.norm(new[0])!=b.norm(target['name']):
        raise ValueError('DC corporate records do not establish continuity')
    return request,target,current,old[1]

def asset(result,payload):
    request,target,current,corporate=validate(result,payload)
    return dict(kind='image',state='DC',ein=request['ein'],run_id=request['run_id'],source_url=current['url'],
        captured_at=current['captured_at'],content=current['image'],identifier=target['identifier'],record_name=target['name'],
        organization_name=result.get('organization_name',''),public_text=current['public_text'],
        capture_note='Original current BOSS license. Both prior and current license details identify the same corporate record '+corporate+'.')

def update(result,payload):
    request,target,current,corporate=validate(result,payload)
    import registry_snapshot_server as master
    expiry=date.fromisoformat(target['expiration']);fields=current['source_fields']
    issue=datetime.strptime(fields['Issue Date'],'%m/%d/%Y').date()
    status=master.licensed_charity_status(fields['License Status'],expiry)
    if status not in {'Current','Upcoming Filing'}:raise ValueError('DC current license expired during check')
    out={'status':status,'success':True,'matched_registry_identifier':target['identifier'],'matched_registry_name':target['name'],
        'raw_status_text':fields['License Status'],'computed_due_date':expiry.isoformat(),'source_url':current['url'],
        'renewal_date':issue.isoformat(),'renewal_date_type':'current_issue_date','renewal_date_source_label':'Issue Date',
        'renewal_date_source_url':current['url'],'renewal_date_note':'Current license issue date from BOSS.',
        'comments':f"DC BOSS lists {target['name']} ({target['identifier']}) as Active, expiring {expiry.isoformat()}. Both this license and prior license {request['identifier']} identify corporate record {corporate}. The current license supersedes the expired license despite the changed office address.",
        'dc_source_reconciliation':{'schema':1,'kind':'corporate_continuity','corporate_record':corporate,
            'ein':request['ein'],'run_id':request['run_id'],'prior_identifier':request['identifier'],
            'prior_name':request['name'],'prior_status':result['status'],'prior_expiration':request['expiration'],
            'identifier':target['identifier'],'name':target['name'],'expiration':target['expiration'],
            'raw_status':fields['License Status'],'status':status,'issue_date':issue.isoformat(),
            'source_url':current['url'],'captured_at':current['captured_at']}}
    out.update(master.renewal_filing_metadata(SimpleNamespace(**{**result,**out}),out,status))
    return out
