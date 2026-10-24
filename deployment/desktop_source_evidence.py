from deployment.workflow_observation import workflow_call, trace_return, workflow_stage
"""Evidence-only fallback for a proven Wisconsin record in the owned browser.

Status and identity remain the existing worker's decision. No URL discovery,
challenge solving, search planning or shared-browser session access lives here.
"""
import re,time,json
from urllib.parse import urlsplit,parse_qsl

def normalized(value):
    return trace_return('deployment/desktop_source_evidence.py:normalized:10:4:return',(re.sub(r'[^a-z0-9]','',str(value).lower())))

def exact_wi_detail_url(value):
    if not isinstance(value,str) or len(value)>1000:return trace_return('deployment/desktop_source_evidence.py:exact_wi_detail_url:13:52:return',(False))
    try:
        u=urlsplit(value);pairs=parse_qsl(u.query,keep_blank_values=True)
        return (trace_return('deployment/desktop_source_evidence.py:exact_wi_detail_url:16:8:return',(u.scheme=='https' and u.hostname=='apps.dfi.wi.gov'
            and u.port in (None,443) and not u.username and not u.password and not u.fragment
            and u.path=='/ice/berg/Registration/CredSummaryDetails.aspx'
            and len(pairs)==2 and set(dict(pairs))=={'chid','h'}
            and all(re.fullmatch(r'\d{1,15}',v) for _,v in pairs))))
    except ValueError:return trace_return('deployment/desktop_source_evidence.py:exact_wi_detail_url:21:22:return',(False))

def exact_wi_search_url(value,name):
    if not isinstance(value,str) or len(value)>1500 or not isinstance(name,str) or not 1<=len(name)<=300:return trace_return('deployment/desktop_source_evidence.py:exact_wi_search_url:24:105:return',(False))
    try:
        u=urlsplit(value);pairs=parse_qsl(u.query,keep_blank_values=True)
        return (trace_return('deployment/desktop_source_evidence.py:exact_wi_search_url:27:8:return',(u.scheme=='https' and u.hostname=='apps.dfi.wi.gov' and u.port in (None,443)
            and not u.username and not u.password and not u.fragment
            and u.path=='/ice/berg/Registration/OrgCredentialSearchResults.aspx'
            and len(pairs)==3 and dict(pairs)=={'CredentialType':'800','LicenseNumber':'','FirmName':name})))
    except ValueError:return trace_return('deployment/desktop_source_evidence.py:exact_wi_search_url:31:22:return',(False))

def empty_metadata(d,payload):
    m=workflow_call('deployment/desktop_source_evidence.py:empty_metadata:34:6:get',payload.get,locals(), 'source_fields')
    return (trace_return('deployment/desktop_source_evidence.py:empty_metadata:35:4:return',(isinstance(m,dict) and workflow_call('deployment/desktop_source_evidence.py:empty_metadata:35:35:get',m.get,locals(), 'profession')=='Charitable Organization'
        and workflow_call('deployment/desktop_source_evidence.py:empty_metadata:36:12:get',m.get,locals(), 'name')==d['name'] and workflow_call('deployment/desktop_source_evidence.py:empty_metadata:36:41:get',m.get,locals(), 'rows')==[['There are no query results.']]
        and workflow_call('deployment/desktop_source_evidence.py:empty_metadata:37:12:get',m.get,locals(), 'visible') is True)))

def retained_request(run,result):
    """Retain the source-issued URL before the owned lookup context closes."""
    if run.state=='DC':
        from deployment.dc_boss_evidence import retained_request as dc_request
        return dc_request(run,result)
    if (run.state!='WI' or workflow_call('deployment/desktop_source_evidence.py:retained_request:41:27:get',result.get,locals(), 'state')!='WI' or workflow_call('deployment/desktop_source_evidence.py:retained_request:41:56:get',result.get,locals(), 'success') is not True
        or workflow_call('deployment/desktop_source_evidence.py:retained_request:42:11:get',result.get,locals(), 'status') in {'Unable to Confirm','Unable to Verify','Site Not Reachable','Needs Review'}
        or workflow_call('deployment/desktop_source_evidence.py:retained_request:43:11:get',result.get,locals(), 'confirmation_required') or workflow_call('deployment/desktop_source_evidence.py:retained_request:43:50:get',result.get,locals(), '_worker_identity_review')):return trace_return('deployment/desktop_source_evidence.py:retained_request:43:89:return',(None))
    if workflow_call('deployment/desktop_source_evidence.py:retained_request:44:7:get',result.get,locals(), 'status')=='Not Registered':
        hint=getattr(run,'source_search_hint',None)
        if not isinstance(hint,dict) or not exact_wi_search_url(workflow_call('deployment/desktop_source_evidence.py:retained_request:46:64:get',hint.get,locals(), 'url'),workflow_call('deployment/desktop_source_evidence.py:retained_request:46:80:get',hint.get,locals(), 'name')):return trace_return('deployment/desktop_source_evidence.py:retained_request:46:98:return',(None))
        return trace_return('deployment/desktop_source_evidence.py:retained_request:47:8:return',(dict(state='WI',ein=run.ein,name=hint['name'],url=hint['url'],run_id=run.run_id,
            issued_at=time.time(),operation='empty_search')))
    identifier=workflow_call('deployment/desktop_source_evidence.py:retained_request:49:15:get',result.get,locals(), 'matched_registry_identifier');name=workflow_call('deployment/desktop_source_evidence.py:retained_request:49:62:get',result.get,locals(), 'matched_registry_name')
    hint=workflow_call('deployment/desktop_source_evidence.py:retained_request:50:9:get',getattr(run,'source_detail_hints',{}).get,locals(), identifier)
    if (not isinstance(identifier,str) or not re.fullmatch(r'\d{1,10}-800',identifier)
        or not isinstance(name,str) or not 1<=len(name)<=300 or not hint
        or normalized(workflow_call('deployment/desktop_source_evidence.py:retained_request:53:22:get',hint.get,locals(), 'name'))!=normalized(name) or not exact_wi_detail_url(workflow_call('deployment/desktop_source_evidence.py:retained_request:53:85:get',hint.get,locals(), 'url'))):return trace_return('deployment/desktop_source_evidence.py:retained_request:53:103:return',(None))
    raw=workflow_call('deployment/desktop_source_evidence.py:retained_request:54:8:get',result.get,locals(), 'raw_status_text')
    if not isinstance(raw,str) or not 1<=len(raw)<=1000:return trace_return('deployment/desktop_source_evidence.py:retained_request:55:56:return',(None))
    return trace_return('deployment/desktop_source_evidence.py:retained_request:56:4:return',(dict(state='WI',ein=run.ein,name=name,identifier=identifier,url=hint['url'],
        raw_status=raw,run_id=run.run_id,issued_at=time.time(),operation='detail')))

def describe(result):
    """Expose only a bounded request produced by the successful source lookup."""
    if result.get('state')=='DC':
        from deployment.dc_boss_evidence import describe as dc_describe
        return dc_describe(result)
    d=workflow_call('deployment/desktop_source_evidence.py:describe:61:6:get',result.get,locals(), '_worker_desktop_evidence')
    if (workflow_call('deployment/desktop_source_evidence.py:describe:62:8:get',result.get,locals(), 'state')!='WI' or workflow_call('deployment/desktop_source_evidence.py:describe:62:37:get',result.get,locals(), 'success') is not True or workflow_call('deployment/desktop_source_evidence.py:describe:62:74:get',result.get,locals(), 'evidence_url')
        or not isinstance(d,dict) or workflow_call('deployment/desktop_source_evidence.py:describe:63:37:get',d.get,locals(), 'state')!='WI' or workflow_call('deployment/desktop_source_evidence.py:describe:63:61:get',d.get,locals(), 'operation') not in {'detail','empty_search'}
        or re.sub(r'\D','',str(workflow_call('deployment/desktop_source_evidence.py:describe:64:31:get',result.get,locals(), 'ein','')))!=workflow_call('deployment/desktop_source_evidence.py:describe:64:55:get',d.get,locals(), 'ein')
        or not re.fullmatch(r'[a-f0-9]{32}',str(workflow_call('deployment/desktop_source_evidence.py:describe:65:48:get',d.get,locals(), 'run_id','')))
        or type(workflow_call('deployment/desktop_source_evidence.py:describe:66:16:get',d.get,locals(), 'issued_at')) not in (int,float)
        or not 0<=time.time()-d['issued_at']<600):return trace_return('deployment/desktop_source_evidence.py:describe:67:50:return',(None))
    if workflow_call('deployment/desktop_source_evidence.py:describe:68:7:get',result.get,locals(), 'confirmation_required') or workflow_call('deployment/desktop_source_evidence.py:describe:68:46:get',result.get,locals(), '_worker_identity_review'):return trace_return('deployment/desktop_source_evidence.py:describe:68:84:return',(None))
    if d['operation']=='detail':
        if (workflow_call('deployment/desktop_source_evidence.py:describe:70:12:get',result.get,locals(), 'matched_registry_identifier')!=workflow_call('deployment/desktop_source_evidence.py:describe:70:55:get',d.get,locals(), 'identifier')
            or workflow_call('deployment/desktop_source_evidence.py:describe:71:15:get',result.get,locals(), 'matched_registry_name')!=workflow_call('deployment/desktop_source_evidence.py:describe:71:52:get',d.get,locals(), 'name')
            or workflow_call('deployment/desktop_source_evidence.py:describe:72:15:get',result.get,locals(), 'raw_status_text')!=workflow_call('deployment/desktop_source_evidence.py:describe:72:46:get',d.get,locals(), 'raw_status')
            or not exact_wi_detail_url(workflow_call('deployment/desktop_source_evidence.py:describe:73:39:get',d.get,locals(), 'url'))):return trace_return('deployment/desktop_source_evidence.py:describe:73:54:return',(None))
    elif workflow_call('deployment/desktop_source_evidence.py:describe:74:9:get',result.get,locals(), 'status')!='Not Registered' or not exact_wi_search_url(workflow_call('deployment/desktop_source_evidence.py:describe:74:75:get',d.get,locals(), 'url'),workflow_call('deployment/desktop_source_evidence.py:describe:74:88:get',d.get,locals(), 'name')):return trace_return('deployment/desktop_source_evidence.py:describe:74:103:return',(None))
    return trace_return('deployment/desktop_source_evidence.py:describe:75:4:return',(dict(d)))

def dates(value):
    return trace_return('deployment/desktop_source_evidence.py:dates:78:4:return',({(int(m),int(d),int(y)) for m,d,y in re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',value)}))

def validate_completion(result,payload):
    if result.get('state')=='DC':
        from deployment.dc_boss_evidence import validate_completion as dc_validate
        return dc_validate(result,payload)
    d=describe(result)
    if not d or not isinstance(payload,dict):raise ValueError('No bound source record')
    if workflow_call('deployment/desktop_source_evidence.py:validate_completion:83:7:get',payload.get,locals(), 'request')!=d:raise ValueError('Source request changed')
    if workflow_call('deployment/desktop_source_evidence.py:validate_completion:84:7:get',payload.get,locals(), 'url')!=d['url']:raise ValueError('Source URL changed')
    text=workflow_call('deployment/desktop_source_evidence.py:validate_completion:85:9:get',payload.get,locals(), 'public_text');stamp=workflow_call('deployment/desktop_source_evidence.py:validate_completion:85:42:get',payload.get,locals(), 'captured_at')
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
    image=workflow_call('deployment/desktop_source_evidence.py:validate_completion:98:10:get',payload.get,locals(), 'image')
    if not isinstance(image,str) or not 1<=len(image)<=4_000_000:raise ValueError('Invalid original image')
    return trace_return('deployment/desktop_source_evidence.py:validate_completion:100:4:return',(dict(kind='image',state='WI',ein=d['ein'],run_id=d['run_id'],source_url=d['url'],
        captured_at=stamp,content=image,identifier=workflow_call('deployment/desktop_source_evidence.py:validate_completion:101:51:get',d.get,locals(), 'identifier','@completed-search'),record_name=d['name'],
        organization_name=workflow_call('deployment/desktop_source_evidence.py:validate_completion:102:26:get',result.get,locals(), 'organization_name',''),public_text=text,
        capture_note='Original selected Wisconsin state page captured by the owned browser during this run; no status change.')))

def persist_completion(result,payload,store=None):
    from deployment.state_snapshots import archive
    a=validate_completion(result,payload)
    record=None
    if payload['request']['operation']=='empty_search':
        import copy,hashlib,secrets
        from deployment.search_history import attach
        record=copy.deepcopy(workflow_call('deployment/desktop_source_evidence.py:persist_completion:112:29:get',result.get,locals(), '_worker_desktop_history'))
        if not isinstance(record,dict):raise ValueError('Original search history required')
        if (workflow_call('deployment/desktop_source_evidence.py:persist_completion:114:12:get',record.get,locals(), 'state')!='WI' or workflow_call('deployment/desktop_source_evidence.py:persist_completion:114:41:get',record.get,locals(), 'ein')!=a['ein'] or workflow_call('deployment/desktop_source_evidence.py:persist_completion:114:72:get',record.get,locals(), 'source_archive_run_id')!=a['run_id']):
            raise ValueError('History identity changed')
        query=dict(state='WI',operation='search',name=payload['request']['name'],url=a['source_url'],
            filter_label='Charitable Organization; name comparison not exposed by source',source_kind='state_portal')
        prior=[workflow_call('deployment/desktop_source_evidence.py:persist_completion:118:15:get',workflow_call('deployment/desktop_source_evidence.py:persist_completion:118:15:get',v.get,locals(), 'search_receipt',{}).get,locals(), 'source_order',0) for v in workflow_call('deployment/desktop_source_evidence.py:persist_completion:118:73:get',record.get,locals(), 'completed',[])]+[workflow_call('deployment/desktop_source_evidence.py:persist_completion:118:102:get',v.get,locals(), 'source_order',0) for v in workflow_call('deployment/desktop_source_evidence.py:persist_completion:118:135:get',record.get,locals(), 'search_failed_receipts',[])]
        order=max(prior,default=0)+1
        if order>150:raise ValueError('History bound exceeded')
        issued=workflow_call('deployment/desktop_source_evidence.py:persist_completion:121:15:get',payload.get,locals(), 'navigation_started_at')
        if type(issued) not in (int,float) or not payload['request']['issued_at']-5<=issued<=a['captured_at']:raise ValueError('Search timestamp missing')
        receipt=dict(query_id=secrets.token_hex(12),source_order=order,issued_at=issued,completed_at=a['captured_at'],
            outcome='Completed source response',returned_rows=0,operation='search',observation_kind='validated_visual_response',
            query_sha256=hashlib.sha256(json.dumps(query,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        record.setdefault('completed',[]).append(dict(query=query,search_receipt=receipt))
    # Validate the entire negative receipt before saving either artifact.
    ref=workflow_call('deployment/desktop_source_evidence.py:persist_completion:128:8:archive',archive,locals(), a,ein=a['ein'],state=a['state'],run_id=a['run_id'],store=store)
    update={'evidence_url':ref['url'],'evidence_capture':'captured','evidence_captured_at':ref['captured_at']}
    if record is not None:
        record['source_snapshots']=[ref]
        combined=attach(record,{**result,**update},store)
        if not workflow_call('deployment/desktop_source_evidence.py:persist_completion:133:15:get',combined.get,locals(), 'search_history_url') or workflow_call('deployment/desktop_source_evidence.py:persist_completion:133:53:get',combined.get,locals(), 'search_history_url')==workflow_call('deployment/desktop_source_evidence.py:persist_completion:133:89:get',result.get,locals(), 'search_history_url'):
            raise ValueError('Completed visual search was not retained')
        update.update({k:combined[k] for k in ['search_history_url','search_history_capture'] if k in combined})
        update['_worker_desktop_history']=record
    return trace_return('deployment/desktop_source_evidence.py:persist_completion:137:4:return',(update))

def handle_completion(master,handler,queue):
    """Authorized workflow owner may attach pixels only to its settled record."""
    from deployment.staging_workflows import unpack
    from deployment.state_snapshots import PostgresStore
    from psycopg.types.json import Jsonb
    try:
        length=int(workflow_call('deployment/desktop_source_evidence.py:handle_completion:145:19:get',handler.headers.get,locals(), 'Content-Length','0'))
        if not 0<length<=4_100_000:raise ValueError('Invalid evidence size')
        p=json.loads(workflow_call('deployment/desktop_source_evidence.py:handle_completion:147:21:read',handler.rfile.read,locals(), length))
        email=master.normalize_email(workflow_call('deployment/desktop_source_evidence.py:handle_completion:148:37:get',p.get,locals(), 'email',''));device=master.normalize_device_id(workflow_call('deployment/desktop_source_evidence.py:handle_completion:148:90:get',p.get,locals(), 'device_id',''))
        code=str(workflow_call('deployment/desktop_source_evidence.py:handle_completion:149:17:get',p.get,locals(), 'admin_passcode','')).strip()
        if master.staging_access_error(email,code) or not master.is_verified_internal_passcode(email,code):
            return trace_return('deployment/desktop_source_evidence.py:handle_completion:151:12:return',(handler._send_json(403,{'error':'Authorized staging access required'})))
        record=unpack(master,workflow_call('deployment/desktop_source_evidence.py:handle_completion:152:29:get',p.get,locals(), 'token'),[email,device])
        state=p.get('state')
        if state not in {'WI','DC'} or state not in record['states']:raise ValueError('State not in workflow')
        status=queue.status('private-performance-lab',record['id'])
        jobs=[j for j in status['jobs'] if j['state']==state and j['phase']=='done' and isinstance(workflow_call('deployment/desktop_source_evidence.py:handle_completion:155:98:get',j.get,locals(), 'result'),dict)]
        if len(jobs)!=1:raise ValueError('Settled source record required')
        result=jobs[0]['result']
        if re.sub(r'\D','',str(workflow_call('deployment/desktop_source_evidence.py:handle_completion:158:31:get',result.get,locals(), 'ein','')))!=record['ein'] or workflow_call('deployment/desktop_source_evidence.py:handle_completion:158:72:get',result.get,locals(), 'app_version')!=workflow_call('deployment/desktop_source_evidence.py:handle_completion:158:99:get',status.get,locals(), 'source_version'):
            raise ValueError('Source record identity mismatch')
        if workflow_call('deployment/desktop_source_evidence.py:handle_completion:160:11:get',result.get,locals(), 'evidence_url'):return trace_return('deployment/desktop_source_evidence.py:handle_completion:160:38:return',(handler._send_json(200,{k:result[k] for k in ['evidence_url','evidence_capture','evidence_captured_at'] if k in result})))
        completion=workflow_call('deployment/desktop_source_evidence.py:handle_completion:161:19:get',p.get,locals(), 'completion');validate_completion(result,completion)
        import math
        seconds=workflow_call('deployment/desktop_source_evidence.py:handle_completion:163:16:get',workflow_call('deployment/desktop_source_evidence.py:handle_completion:163:16:get',completion.get,locals(), 'timing',{}).get,locals(), 'seconds')
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<=seconds<=30:
            raise ValueError('Invalid capture duration')
        # Serialization is bounded; no changes to phase, status, search or identity.
        start=time.perf_counter();update=persist_completion(result,completion,PostgresStore(queue.pool))
        update['desktop_evidence_timing']={'archive_seconds':round(time.perf_counter()-start,4),
            'capture_seconds':seconds}
        metrics=dict(workflow_call('deployment/desktop_source_evidence.py:handle_completion:170:21:get',result.get,locals(), 'evidence_metrics') or {})
        metrics.update(row_link=True,missing_stage='',desktop_original=True)
        update['evidence_metrics']=metrics
        with queue.transaction() as (c,_):
            changed=c.execute("UPDATE cc_lab_jobs SET result=result || %s WHERE workflow_id=%s AND state=%s AND phase='done' AND result->'_worker_desktop_evidence'=%s AND COALESCE(result->>'evidence_url','')='' RETURNING id",
                (Jsonb(update),record['id'],state,Jsonb(result['_worker_desktop_evidence']))).fetchone()
            if not changed:raise ValueError('Source result changed before archive completion')
        return trace_return('deployment/desktop_source_evidence.py:handle_completion:177:8:return',(handler._send_json(200,{k:v for k,v in update.items() if not k.startswith('_')},{'Cache-Control':'no-store'})))
    except (ValueError,TypeError,KeyError,UnicodeError):
        return trace_return('deployment/desktop_source_evidence.py:handle_completion:179:8:return',(handler._send_json(400,{'error':'Source evidence did not match this completed workflow'})))
    except Exception:
        return trace_return('deployment/desktop_source_evidence.py:handle_completion:181:8:return',(handler._send_json(503,{'error':'Original state evidence could not be saved; state result retained'})))
