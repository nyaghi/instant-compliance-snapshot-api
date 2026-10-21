"""Evidence-only fallback for a proven Wisconsin record in the owned browser.

Status and identity remain the existing worker's decision. No URL discovery,
challenge solving, search planning or shared-browser session access lives here.
"""
import re,time,json
from urllib.parse import urlsplit,parse_qsl

def normalized(value):
    return re.sub(r'[^a-z0-9]','',str(value).lower())

def exact_wi_detail_url(value):
    if not isinstance(value,str) or len(value)>1000:return False
    try:
        u=urlsplit(value);pairs=parse_qsl(u.query,keep_blank_values=True)
        return (u.scheme=='https' and u.hostname=='apps.dfi.wi.gov'
            and u.port in (None,443) and not u.username and not u.password and not u.fragment
            and u.path=='/ice/berg/Registration/CredSummaryDetails.aspx'
            and len(pairs)==2 and set(dict(pairs))=={'chid','h'}
            and all(re.fullmatch(r'\d{1,15}',v) for _,v in pairs))
    except ValueError:return False

def exact_wi_search_url(value,name):
    if not isinstance(value,str) or len(value)>1500 or not isinstance(name,str) or not 1<=len(name)<=300:return False
    try:
        u=urlsplit(value);pairs=parse_qsl(u.query,keep_blank_values=True)
        return (u.scheme=='https' and u.hostname=='apps.dfi.wi.gov' and u.port in (None,443)
            and not u.username and not u.password and not u.fragment
            and u.path=='/ice/berg/Registration/OrgCredentialSearchResults.aspx'
            and len(pairs)==3 and dict(pairs)=={'CredentialType':'800','LicenseNumber':'','FirmName':name})
    except ValueError:return False

def empty_metadata(d,payload):
    m=payload.get('source_fields')
    return (isinstance(m,dict) and m.get('profession')=='Charitable Organization'
        and m.get('name')==d['name'] and m.get('rows')==[['There are no query results.']]
        and m.get('visible') is True)

def retained_request(run,result):
    """Retain the source-issued URL before the owned lookup context closes."""
    if (run.state!='WI' or result.get('state')!='WI' or result.get('success') is not True
        or result.get('status') in {'Unable to Confirm','Unable to Verify','Site Not Reachable','Needs Review'}
        or result.get('confirmation_required') or result.get('_worker_identity_review')):return None
    if result.get('status')=='Not Registered':
        hint=getattr(run,'source_search_hint',None)
        if not isinstance(hint,dict) or not exact_wi_search_url(hint.get('url'),hint.get('name')):return None
        return dict(state='WI',ein=run.ein,name=hint['name'],url=hint['url'],run_id=run.run_id,
            issued_at=time.time(),operation='empty_search')
    identifier=result.get('matched_registry_identifier');name=result.get('matched_registry_name')
    hint=getattr(run,'source_detail_hints',{}).get(identifier)
    if (not isinstance(identifier,str) or not re.fullmatch(r'\d{1,10}-800',identifier)
        or not isinstance(name,str) or not 1<=len(name)<=300 or not hint
        or normalized(hint.get('name'))!=normalized(name) or not exact_wi_detail_url(hint.get('url'))):return None
    raw=result.get('raw_status_text')
    if not isinstance(raw,str) or not 1<=len(raw)<=1000:return None
    return dict(state='WI',ein=run.ein,name=name,identifier=identifier,url=hint['url'],
        raw_status=raw,run_id=run.run_id,issued_at=time.time(),operation='detail')

def describe(result):
    """Expose only a bounded request produced by the successful source lookup."""
    d=result.get('_worker_desktop_evidence')
    if (result.get('state')!='WI' or result.get('success') is not True or result.get('evidence_url')
        or not isinstance(d,dict) or d.get('state')!='WI' or d.get('operation') not in {'detail','empty_search'}
        or re.sub(r'\D','',str(result.get('ein','')))!=d.get('ein')
        or not re.fullmatch(r'[a-f0-9]{32}',str(d.get('run_id','')))
        or type(d.get('issued_at')) not in (int,float)
        or not 0<=time.time()-d['issued_at']<600):return None
    if result.get('confirmation_required') or result.get('_worker_identity_review'):return None
    if d['operation']=='detail':
        if (result.get('matched_registry_identifier')!=d.get('identifier')
            or result.get('matched_registry_name')!=d.get('name')
            or result.get('raw_status_text')!=d.get('raw_status')
            or not exact_wi_detail_url(d.get('url'))):return None
    elif result.get('status')!='Not Registered' or not exact_wi_search_url(d.get('url'),d.get('name')):return None
    return dict(d)

def dates(value):
    return {(int(m),int(d),int(y)) for m,d,y in re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',value)}

def validate_completion(result,payload):
    d=describe(result)
    if not d or not isinstance(payload,dict):raise ValueError('No bound source record')
    if payload.get('request')!=d:raise ValueError('Source request changed')
    if payload.get('url')!=d['url']:raise ValueError('Source URL changed')
    text=payload.get('public_text');stamp=payload.get('captured_at')
    if (not isinstance(text,str) or not 1<=len(text)<=20000
        or type(stamp) not in (int,float) or not d['issued_at']-1<=stamp<=time.time()+30
        or normalized(d['name']) not in normalized(text)
        or re.search(r'verify you are human|user validation required|access denied|just a moment|you have been blocked',text,re.I)):
        raise ValueError('Source detail does not match the selected record')
    if d['operation']=='detail':
        if (not re.search(r'(?<!\d)'+re.escape(d['identifier'])+r'(?!\d)',text)
            or 'Credential Summary' not in text or 'CHARITABLE ORGANIZATION (800)' not in text
            or normalized(d['raw_status'].split(';',1)[0]) not in normalized(text)
            or not dates(d['raw_status'])<=dates(text)):raise ValueError('Selected detail changed')
    elif not empty_metadata(d,payload) or 'Organization Search Results' not in text:
        raise ValueError('Completed empty search not proven')
    image=payload.get('image')
    if not isinstance(image,str) or not 1<=len(image)<=4_000_000:raise ValueError('Invalid original image')
    return dict(kind='image',state='WI',ein=d['ein'],run_id=d['run_id'],source_url=d['url'],
        captured_at=stamp,content=image,identifier=d.get('identifier','@completed-search'),record_name=d['name'],
        organization_name=result.get('organization_name',''),public_text=text,
        capture_note='Original selected Wisconsin state page captured by the owned browser during this run; no status change.')

def persist_completion(result,payload,store=None):
    from deployment.state_snapshots import archive
    a=validate_completion(result,payload)
    record=None
    if payload['request']['operation']=='empty_search':
        import copy,hashlib,secrets
        from deployment.search_history import attach
        record=copy.deepcopy(result.get('_worker_desktop_history'))
        if not isinstance(record,dict):raise ValueError('Original search history required')
        if (record.get('state')!='WI' or record.get('ein')!=a['ein'] or record.get('source_archive_run_id')!=a['run_id']):
            raise ValueError('History identity changed')
        query=dict(state='WI',operation='search',name=payload['request']['name'],url=a['source_url'],
            filter_label='Charitable Organization; name comparison not exposed by source',source_kind='state_portal')
        prior=[v.get('search_receipt',{}).get('source_order',0) for v in record.get('completed',[])]+[v.get('source_order',0) for v in record.get('search_failed_receipts',[])]
        order=max(prior,default=0)+1
        if order>150:raise ValueError('History bound exceeded')
        issued=payload.get('navigation_started_at')
        if type(issued) not in (int,float) or not payload['request']['issued_at']-5<=issued<=a['captured_at']:raise ValueError('Search timestamp missing')
        receipt=dict(query_id=secrets.token_hex(12),source_order=order,issued_at=issued,completed_at=a['captured_at'],
            outcome='Completed source response',returned_rows=0,operation='search',observation_kind='validated_visual_response',
            query_sha256=hashlib.sha256(json.dumps(query,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        record.setdefault('completed',[]).append(dict(query=query,search_receipt=receipt))
    # Validate the entire negative receipt before saving either artifact.
    ref=archive(a,ein=a['ein'],state='WI',run_id=a['run_id'],store=store)
    update={'evidence_url':ref['url'],'evidence_capture':'captured','evidence_captured_at':ref['captured_at']}
    if record is not None:
        record['source_snapshots']=[ref]
        combined=attach(record,{**result,**update},store)
        if not combined.get('search_history_url') or combined.get('search_history_url')==result.get('search_history_url'):
            raise ValueError('Completed visual search was not retained')
        update.update({k:combined[k] for k in ['search_history_url','search_history_capture'] if k in combined})
        update['_worker_desktop_history']=record
    return update

def handle_completion(master,handler,queue):
    """Authorized workflow owner may attach pixels only to its settled record."""
    from deployment.staging_workflows import unpack
    from deployment.state_snapshots import PostgresStore
    from psycopg.types.json import Jsonb
    try:
        length=int(handler.headers.get('Content-Length','0'))
        if not 0<length<=4_100_000:raise ValueError('Invalid evidence size')
        p=json.loads(handler.rfile.read(length))
        email=master.normalize_email(p.get('email',''));device=master.normalize_device_id(p.get('device_id',''))
        code=str(p.get('admin_passcode','')).strip()
        if master.staging_access_error(email,code) or not master.is_verified_internal_passcode(email,code):
            return handler._send_json(403,{'error':'Authorized staging access required'})
        record=unpack(master,p.get('token'),[email,device])
        if 'WI' not in record['states'] or p.get('state')!='WI':raise ValueError('State not in workflow')
        status=queue.status('private-performance-lab',record['id'])
        jobs=[j for j in status['jobs'] if j['state']=='WI' and j['phase']=='done' and isinstance(j.get('result'),dict)]
        if len(jobs)!=1:raise ValueError('Settled source record required')
        result=jobs[0]['result']
        if re.sub(r'\D','',str(result.get('ein','')))!=record['ein'] or result.get('app_version')!=status.get('source_version'):
            raise ValueError('Source record identity mismatch')
        if result.get('evidence_url'):return handler._send_json(200,{k:result[k] for k in ['evidence_url','evidence_capture','evidence_captured_at'] if k in result})
        completion=p.get('completion');validate_completion(result,completion)
        import math
        seconds=completion.get('timing',{}).get('seconds')
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<=seconds<=30:
            raise ValueError('Invalid capture duration')
        # Serialization is bounded; no changes to phase, status, search or identity.
        start=time.perf_counter();update=persist_completion(result,completion,PostgresStore(queue.pool))
        update['desktop_evidence_timing']={'archive_seconds':round(time.perf_counter()-start,4),
            'capture_seconds':seconds}
        metrics=dict(result.get('evidence_metrics') or {})
        metrics.update(row_link=True,missing_stage='',desktop_original=True)
        update['evidence_metrics']=metrics
        with queue.transaction() as (c,_):
            changed=c.execute("UPDATE cc_lab_jobs SET result=result || %s WHERE workflow_id=%s AND state='WI' AND phase='done' AND result->'_worker_desktop_evidence'=%s AND COALESCE(result->>'evidence_url','')='' RETURNING id",
                (Jsonb(update),record['id'],Jsonb(result['_worker_desktop_evidence']))).fetchone()
            if not changed:raise ValueError('Source result changed before archive completion')
        return handler._send_json(200,{k:v for k,v in update.items() if not k.startswith('_')},{'Cache-Control':'no-store'})
    except (ValueError,TypeError,KeyError,UnicodeError):
        return handler._send_json(400,{'error':'Source evidence did not match this completed workflow'})
    except Exception:
        return handler._send_json(503,{'error':'Original state evidence could not be saved; state result retained'})
