"""Reconcile a same-license renewal only after stable original BOSS capture.

The existing master owns interpretation. Unresolved identities and different
standing/activity keep the strict legacy path; no evidence-only date override.
"""
import hashlib,re
from datetime import date,datetime,timezone
from types import SimpleNamespace

PUBLIC_KEYS=('status','success','comments','computed_due_date','source_url','renewal_date',
 'renewal_date_type','renewal_date_note','renewal_date_source_url','renewal_date_source_label',
 'renewal_filing_value','renewal_filing_type','renewal_filing_label','renewal_filing_source_url','renewal_filing_note',
 'dc_source_reconciliation')
ACTIVITIES={'charitable solicitation','charitable exempt'}
STANDINGS={'active','current','issued','approved'}
def norm(value):return re.sub(r'[^a-z0-9]','',str(value).lower())
def digest(value):return hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()
def enabled(request):return type(request.get('boss_reconcile_schema'))is int and request['boss_reconcile_schema']==1
def article_key(value):
    value=str(value).strip()
    leading=bool(re.match(r'^THE\s+',value,re.I));trailing=bool(re.search(r'\(\s*THE\s*\)\s*\.?$',value,re.I))
    if leading and trailing:return norm(value) # Never remove two articles.
    if leading:value=re.sub(r'^THE\s+','',value,flags=re.I)
    elif trailing:value=re.sub(r',?\s*\(\s*THE\s*\)\s*\.?$','',value,flags=re.I)
    return norm(value)
def name_matches(observed,selected,request):
    return norm(observed)==norm(selected)or enabled(request)and bool(article_key(selected))and article_key(observed)==article_key(selected)

def request_fields(run,result,review):
    if review:return {}
    import registry_snapshot_server as master
    activity=str(getattr(run,'dc_boss_selected_activity','')).strip().lower()
    if (not master.trial_identity()or master.LAB_LOOKUP_MODE_CONTEXT.get()!='standard'
        or result.get('address_evidence',{}).get('decision')!='corroborated'
        or str(result.get('raw_status_text','')).lower()not in STANDINGS or activity not in ACTIVITIES
        or result.get('status')not in {'Current','Upcoming Filing','Delinquent','Exempt'}):return {}
    try:date.fromisoformat(result['renewal_date'])
    except (KeyError,ValueError,TypeError):return {}
    return {'boss_reconcile_schema':1,'expected_activity':activity,'prior_status':result['status'],
        'prior_renewal_date':result['renewal_date'],'prior_comments_sha256':digest(result.get('comments')),
        **({'prior_renewal_date_type':'current_effective_date'} if result.get('renewal_date_type')=='current_effective_date' else {})}

def request_matches_period(result,request):
    if 'boss_reconcile_schema'not in request:return True
    if (not enabled(request)or 'review_candidate'in request or request.get('expected_activity')not in ACTIVITIES
        or request.get('prior_status')not in {'Current','Upcoming Filing','Delinquent','Exempt'}
        or str(request.get('raw_status','')).lower()not in STANDINGS
        or result.get('address_evidence',{}).get('decision')!='corroborated'
        or result.get('status')!=request.get('prior_status')
        or result.get('renewal_date')!=request.get('prior_renewal_date')
        or ('prior_renewal_date_type' in request and (request['prior_renewal_date_type']!='current_effective_date' or result.get('renewal_date_type')!='current_effective_date'))
        or digest(result.get('comments'))!=request.get('prior_comments_sha256')):return False
    try:date.fromisoformat(request['prior_renewal_date'])
    except (ValueError,KeyError,TypeError):return False
    return True

def period_allowed(fields,request):
    if (not enabled(request) and request.get('expiration') == ''
        and str(request.get('raw_status','')).casefold() in {'cancelled','canceled','closed','withdrawn','revoked'}):
        return fields.get('Expiration Date') == 'N/A' and fields.get('License Status') == request['raw_status']
    try:
        expiry=datetime.strptime(fields['Expiration Date'],'%m/%d/%Y').date()
        if not enabled(request):return expiry.isoformat()==request['expiration']
        issue=datetime.strptime(fields['Issue Date'],'%m/%d/%Y').date()
        prior=date.fromisoformat(request['expiration']);prior_issue=date.fromisoformat(request['prior_renewal_date'])
        observed_day=datetime.fromtimestamp(request['issued_at'],timezone.utc).date()
        return (fields['License Activity'].lower()==request['expected_activity']
            and expiry>=prior and issue<=min(expiry,observed_day)
            and ((request.get('prior_renewal_date_type')=='current_effective_date' and expiry==prior)
                 or (prior_issue<=issue and (expiry==prior or issue>prior_issue))))
    except (ValueError,KeyError,TypeError,OverflowError,OSError):return False

def completed_update(result,payload):
    request=payload['request']
    if request.get('corporate_continuity_schema')==2:
        from deployment.dc_linked_identity import update
        return update(result,payload)
    if request.get('corporate_continuity_schema')==1:
        from deployment.dc_corporate_continuity import update
        return update(result,payload)
    if not enabled(request):return {}
    from deployment.dc_boss_evidence import describe,fields
    if describe(result)!=request:raise ValueError('DC period request changed')
    observed=fields(payload['url'],payload['public_text'],request)
    if not observed or observed!=payload['source_fields']:raise ValueError('DC period source changed')
    import registry_snapshot_server as master
    expiry=datetime.strptime(observed['Expiration Date'],'%m/%d/%Y').date()
    issue=datetime.strptime(observed['Issue Date'],'%m/%d/%Y').date()
    standing=master.licensed_charity_status(observed['License Status'],expiry)
    if 'exempt'in observed['License Activity'].lower()and standing in {'Current','Upcoming Filing'}:standing='Exempt'
    if standing not in {'Current','Upcoming Filing','Delinquent','Exempt'}:raise ValueError('DC period interpretation incomplete')
    comments=(f"DC BOSS lists {observed['Licensee']} ({request['identifier']}) as {observed['License Status']}. "
        f"The selected license expires {expiry.isoformat()}. CharityClarity reports {standing}. "
        f"The exact license number and the previously corroborated organization identity were retained. "
        f"BOSS detail captured during this run supersedes the public extract's expiration of {request['expiration']}. "
        f"License activity: {observed['License Activity']}. Registry match: {result['matched_registry_name']} (ID: {request['identifier']}).")
    proof={'schema':1,'ein':request['ein'],'identifier':request['identifier'],'selected_name':request['name'],
        'source_name':observed['Licensee'],'prior_status':request['prior_status'],'prior_expiration':request['expiration'],
        'prior_renewal_date':request['prior_renewal_date'],'prior_comments_sha256':request['prior_comments_sha256'],
        'issue_date':issue.isoformat(),'expiration':expiry.isoformat(),'status':standing,
        'captured_at':payload['captured_at'],'source_url':payload['url']}
    update={'status':standing,'success':True,'comments':comments,'computed_due_date':expiry.isoformat(),
        'source_url':payload['url'],'renewal_date':issue.isoformat(),'renewal_date_type':'current_issue_date',
        'renewal_date_source_label':'Issue Date','renewal_date_source_url':payload['url'],
        'renewal_date_note':'Current license issue date from BOSS; not the date a renewal application was submitted.',
        'dc_source_reconciliation':proof}
    if request.get('prior_renewal_date_type')=='current_effective_date' and issue.isoformat()<request['prior_renewal_date']:
        # BOSS Issue Date and extract License Start Date are different facts.
        # Keep the existing sourced period-effective projection; do not relabel
        # an older license issue as the current renewal. The image still binds
        # to this exact license, activity, standing and nonregressing expiry.
        for key in ('renewal_date','renewal_date_type','renewal_date_note',
                    'renewal_date_source_url','renewal_date_source_label'):
            if key in result:update[key]=result[key]
        proof['period_effective_date_retained']=True
        update['comments'] += (f" BOSS labels its license Issue Date {issue.isoformat()}; the extract's separately sourced "
            f"current-period effective date {request['prior_renewal_date']} is retained.")
    # Public results already contain a separate renewal/filing projection used
    # by the table and Excel export. Recompute it with the existing master
    # policy in this same atomic update; retaining it would display an old date.
    update.update(master.renewal_filing_metadata(SimpleNamespace(**{**result,**update}),update,standing))
    return update

def public_completed_fields(result):
    proof=result.get('dc_source_reconciliation')
    keys=PUBLIC_KEYS
    if isinstance(proof,dict) and proof.get('kind')=='corporate_continuity':
        keys=(*keys,'matched_registry_identifier','matched_registry_name','raw_status_text')
    return {key:result[key]for key in keys if key in result}if isinstance(proof,dict)and proof.get('schema')==1 else {}
