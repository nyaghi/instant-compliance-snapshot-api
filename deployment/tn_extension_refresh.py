"""Fresh read-only Tennessee evidence for the isolated extension pilot.

Public records come from the existing authenticated public connector, never
client-supplied eligibility facts. Account observations are read-only browser
observations, not proof of absence in every account or of a filing's period.
"""
import copy,json,re,secrets,time
from datetime import datetime,timezone
from psycopg.types.json import Jsonb

AGE=300
PATH='/api/tn-extension-source'

def stored(c,account,identifier):
    row=c.execute('SELECT data FROM cc_tn_extension_demo_checks WHERE account=%s AND ein=%s',(account,identifier)).fetchone()
    return row['data'] if row else {}

def save(c,account,identifier,data,now):
    c.execute('INSERT INTO cc_tn_extension_demo_checks VALUES (%s,%s,%s,%s) ON CONFLICT(account,ein) DO UPDATE SET checked=excluded.checked,data=excluded.data',(account,identifier,now,Jsonb(data)))

def empty(identifier):
    return dict(ein=identifier,name='',coid='',address='',phone='',website='',period_start='',period_end='',expiration='',checked_at='',source='https://tncab.tnsos.gov/portal/registered-charities-search',
        identity_verified=False,current_verified=False,period_verified=False,expiration_verified=False,first_extension_verified=False,existing_filing=None)

def facts(service,c,account,identifier,now):
    data=stored(c,account,identifier);fresh=data.get('fresh',{})
    result=copy.deepcopy(fresh.get('facts') or empty(identifier))
    if fresh.get('state')!='confirmed' or not 0<=now-fresh.get('checked',0)<=AGE:
        for key in ['identity_verified','current_verified','period_verified','expiration_verified','first_extension_verified','second_extension_verified']:result[key]=False
        result['refresh_error']=fresh.get('error') or ('Click Check for extensions to retrieve a fresh Tennessee record.' if not fresh else 'The Tennessee check is stale or still running. Check for extensions again.')
    result['account_check']=copy.deepcopy(data.get('account_check') or {'state':'not_checked','records':[]})
    result['checked_at_epoch']=fresh.get('checked');result['refresh_nonce']=fresh.get('nonce')
    return result

def begin(service,c,account,p,now):
    from deployment.tn_extensions_demo import ein,Invalid
    identifier=ein(p.get('ein'));name=p.get('name','')
    if not isinstance(name,str) or not 1<=len(name.strip())<=200:raise Invalid('Organization name is required for the fresh Tennessee check.')
    data=dict(fresh=dict(state='pending',nonce=secrets.token_hex(24),started=now,ein=identifier,name=name.strip()))
    save(c,account,identifier,data,now)
    return dict(nonce=data['fresh']['nonce'],ein=identifier,name=name.strip(),maximum_seconds=60)

def context(c,account,identifier,nonce,now):
    from deployment.tn_extensions_demo import Invalid
    data=stored(c,account,identifier);fresh=data.get('fresh',{})
    if not isinstance(nonce,str) or not re.fullmatch('[a-f0-9]{48}',nonce) or fresh.get('nonce')!=nonce or not 0<=now-fresh.get('started',0)<=AGE:
        raise Invalid('This extension check expired or was replaced. Check for extensions again.')
    return data

def result_facts(result,identifier,now):
    from deployment.tn_extensions_demo import reference_facts,local_day,Invalid
    if (not isinstance(result,dict) or result.get('state')!='TN' or re.sub(r'\D','',''+str(result.get('ein','')))!=identifier
        or result.get('success') is not True or result.get('error') or any(result.get(k) for k in ['confirmation_required','identity_review','_worker_identity_review','source_truth_conflict'])
        or result.get('identity_anchor')=='POSSIBLE_NAME'):
        raise Invalid('Tennessee did not return a confirmed organization. Review the state result or retry the extension check.')
    if result.get('source_url')!='https://tncab.tnsos.gov/portal/registered-charities-search':raise Invalid('The Tennessee source could not be verified.')
    if result.get('status')=='Not Registered':
        f=empty(identifier);f.update(name=result.get('organization_name',''),checked_at=local_day(now).isoformat(),checked_at_epoch=now,
            ineligibility_reason='The fresh Tennessee search found no qualifying registration. A current registration is required for an extension.')
        return f
    record=dict(ein=identifier,name=result.get('matched_registry_name') or result.get('organization_name',''),coid=result.get('matched_registry_identifier',''),
        expiration=result.get('computed_due_date',''),last_reported_period=result.get('renewal_filing_value',''),status=result.get('raw_status_text',''),
        checked_at=local_day(now).isoformat(),source=result['source_url'],identity_verified=True)
    if not re.fullmatch('CO[0-9]{1,15}',record['coid']):raise Invalid('A confirmed Tennessee CO number is required.')
    if result.get('renewal_filing_type')!='filed_period_end':record['last_reported_period']=''
    f=reference_facts(record,local_day(now));f['checked_at_epoch']=now
    if record['status']!='Active':f['ineligibility_reason']='Tennessee currently reports '+str(record['status'] or 'an unconfirmed registration status')+'. A verified active registration is required.'
    f['limitation']='Fresh public registry observation. Pending or returned filings and their fiscal periods require account review and filer confirmation.'
    return f

def complete(service,c,account,identifier,nonce,result,now):
    data=context(c,account,identifier,nonce,now);f=result_facts(result,identifier,now)
    # Federal prefill is optional context, never an eligibility input. Only
    # retain reviewed prefill when the fresh CO/name match that exact reference.
    from deployment.tn_extensions_demo import public_facts
    old=public_facts(identifier)
    if old.get('coid')==f['coid']:
        for key in ['return_type','irs_street','irs_city_state_zip','irs_source']:f[key]=old.get(key,'')
    data['fresh'].update(state='confirmed',checked=now,facts=f);save(c,account,identifier,data,now)
    return f

def failure(service,c,account,p,now):
    from deployment.tn_extensions_demo import ein
    identifier=ein(p.get('ein'));data=context(c,account,identifier,p.get('nonce'),now)
    reason={'connector_unavailable':'The registry connector did not start. Refresh its connection, then Check for extensions again.',
        'timeout':'The Tennessee source check timed out. Eligibility remains unconfirmed; use Check for extensions to retry.',
        'public_unconfirmed':'The fresh Tennessee check did not confirm eligibility. Review the state result or use Check for extensions to retry.'}.get(p.get('kind'),'The fresh Tennessee check did not complete. Eligibility is unconfirmed; use Check for extensions to retry.')
    data['fresh'].update(state='failed',checked=now,error=reason)
    save(c,account,identifier,data,now)

def account_observation(service,c,account,p,now):
    from deployment.tn_extensions_demo import ein,Invalid
    identifier=ein(p.get('ein'));data=context(c,account,identifier,p.get('nonce'),now)
    f=data['fresh'].get('facts') or {};observation=p.get('observation')
    if data['fresh'].get('state')!='confirmed' or not isinstance(observation,dict):raise Invalid('Refresh the public Tennessee record before checking the account.')
    state=observation.get('state');records=observation.get('records',[])
    if state not in {'checked','sign_in_required','partial','unavailable','busy','connector_update_required'} or not isinstance(records,list) or len(records)>50:raise Invalid('Invalid account observation.')
    filtered=[]
    for r in records:
        if not isinstance(r,dict) or not re.fullmatch('[0-9]{6,18}',str(r.get('tracking',''))):raise Invalid('Invalid account filing reference.')
        if r.get('coid')!=f.get('coid') and r.get('identity_method')!='exact_name':raise Invalid('An account filing belongs to a different CO number.')
        if r.get('identity_method')=='exact_name' and r.get('coid'):raise Invalid('Conflicting account filing identity.')
        if r.get('source') not in {'https://tncab.tnsos.gov/portal/my-filings','https://tncab.tnsos.gov/portal/my-filings-complete'}:raise Invalid('Unrecognized Tennessee account source.')
        if r.get('identity_method')=='exact_name':
            normalized=lambda s:re.sub('[^A-Z0-9]+',' ',s.upper()).strip()
            description=re.sub(r'^(FIRST|SECOND) EXTENSION REQUEST FOR ','',normalized(str(r.get('description',''))))
            if description!=normalized(f.get('name','')):raise Invalid('The account filing name does not match the fresh registration.')
        filtered.append({k:str(r.get(k,''))[:300] for k in ['tracking','coid','description','type','status','updated','source','identity_method']})
    data['account_check']=dict(state=state,checked=now,records=filtered,period_verified=False,
        requires_period_review=any(r['status'].strip().lower() not in {'draft','incomplete','not submitted'} for r in filtered),
        note='Account history does not display the fiscal period. Confirm whether a listed filing covers this period. A completed filing is not automatically an approved extension.')
    if filtered:data.pop('answer',None)
    save(c,account,identifier,data,now);return data['account_check']

def handle_source(alerts,master,handler,origin):
    """Only the mature PUBLIC TN lookup. No filing or arbitrary URL actions."""
    from deployment.tn_extensions_demo import Service,Invalid,ein
    headers={'Cache-Control':'no-store'}
    try:
        if handler.headers.get('Origin')!=origin:raise Invalid('Invalid request origin.')
        n=int(handler.headers.get('Content-Length','0'))
        if not 0<n<=2900000:raise Invalid('Invalid public check size.')
        p=json.loads(handler.rfile.read(n));identifier=ein(p.get('extension_ein'));nonce=p.pop('extension_refresh',None);p.pop('extension_ein',None)
        with alerts.transaction() as c:
            owner=alerts.account(c,handler)
            if not owner:return handler._send_json(403,{'error':'Sign into CharityClarity to refresh extension eligibility.'},headers)
            service=Service(alerts);service.initialize(c);data=context(c,owner,identifier,nonce,time.time())
            if p.get('action')=='start':
                if p.get('state')!='TN' or ein(p.get('ein'))!=identifier or p.get('organization_name')!=data['fresh']['name']:raise Invalid('The public check changed organization or state.')
            else:
                token=master.ny_connector_unpack(p.get('check_token'),master.normalize_email(p.get('email','')),p.get('device_id'))
                if token.get('state')!='TN' or ein(token.get('ein'))!=identifier:raise Invalid('A Tennessee continuation is required.')
        status,result=master.final_four_connector_request(p,origin)
        if status==200 and result.get('phase')=='complete':
            with alerts.transaction() as c:complete(service,c,owner,identifier,nonce,result.get('result'),time.time())
        return handler._send_json(status,result,headers)
    except (Invalid,ValueError,TypeError,KeyError):return handler._send_json(400,{'error':'The fresh Tennessee check could not be verified. Check for extensions again.'},headers)
    except Exception:return handler._send_json(503,{'error':'The fresh Tennessee check is temporarily unavailable.'},headers)
