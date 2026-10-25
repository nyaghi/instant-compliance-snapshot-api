"""Original evidence for an unresolved WI credential; no identity decision."""
import copy,hashlib,json,re,time
from datetime import datetime

def target(result):
    from deployment.desktop_source_evidence import exact_wi_detail_url
    if result.get('state')!='WI' or result.get('success') is not False or result.get('status') not in {'Unable to Confirm','Needs Review'}:return None
    ctx=result.get('_worker_identity_review')
    if not isinstance(ctx,dict) or type(ctx.get('search_complete')) is not bool:return None
    rows=ctx.get('records')
    if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict):return None
    row=rows[0]
    if row.get('_identity_outcome') not in {'possible','conflict'}:return None
    name=row.get('name');identifier=row.get('identifier');raw=row.get('raw_status');url=row.get('url')
    if (not isinstance(name,str) or not 1<=len(name)<=300 or not isinstance(raw,str) or not 1<=len(raw)<=1000
        or not re.fullmatch(r'\d{1,10}-800',str(identifier)) or not exact_wi_detail_url(url)
        or (row.get('ein') and re.sub(r'\D','',str(row['ein']))!=re.sub(r'\D','',str(result.get('ein',''))))):return None
    expiration=row.get('expiration') or ''
    if expiration:
        try:formatted=datetime.strptime(expiration,'%Y-%m-%d').strftime('%m/%d/%Y')
        except (TypeError,ValueError):return None
        raw+='; Expiration Date: '+formatted
    return dict(name=name,identifier=identifier,url=url,raw_status=raw)

def projection(result,expected):
    projected={**result,'success':True,'status':'Evidence review only','confirmation_required':False,
               'matched_registry_name':expected['name'],'matched_registry_identifier':expected['identifier'],
               'raw_status_text':expected['raw_status']}
    projected.pop('_worker_identity_review',None)
    return projected

def retained_request(run,result):
    from deployment.desktop_source_evidence import retained_request as ordinary
    expected=target(result)
    if not expected or run.state!='WI' or run.ein!=re.sub(r'\D','',str(result.get('ein',''))):return None
    hint=getattr(run,'source_detail_hints',{}).get(expected['identifier'])
    if not hint or hint.get('url')!=expected['url'] or re.sub(r'[^a-z0-9]','',str(hint.get('name','')).lower())!=re.sub(r'[^a-z0-9]','',expected['name'].lower()):return None
    request=ordinary(run,projection(result,expected))
    return {**request,'review_candidate':True} if request else None

def describe(result):
    from deployment.desktop_source_evidence import describe as ordinary
    expected=target(result);d=result.get('_worker_desktop_evidence')
    if not expected or not isinstance(d,dict) or d.get('review_candidate') is not True:return None
    if any(d.get(k)!=v for k,v in expected.items()):return None
    return ordinary(projection(result,expected))

def attach_reference(result,ref,store):
    from deployment.identity_evidence import _load,_source
    expected=target(result);d=describe(result)
    if not expected or not d:raise ValueError('WI review candidate changed')
    payload=copy.deepcopy(_load({'base':result},store));doc=payload['history']
    if doc['run_id']!=d['run_id'] or ref.get('identifier')!=expected['identifier'] or ref.get('record_name')!=expected['name']:raise ValueError('WI review source binding changed')
    _source(ref,'WI',d['ein'],d['run_id'],store)
    payload['sources']=[r for r in payload['sources'] if r.get('identifier')!=expected['identifier']]+[copy.deepcopy(ref)]
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    if len(raw)>200000:raise ValueError('Review evidence exceeds bound')
    meta=dict(kind='identity_evidence',state='WI',ein=d['ein'],run_id=d['run_id'],source_sha256=hashlib.sha256(raw).hexdigest(),captured_at=doc['completed_at'])
    context=copy.deepcopy(result['_worker_identity_review'])
    context['records'][0]['evidence_url']=ref['url']
    return {'_worker_identity_review':context,'review_evidence_context':store.save(meta,raw)}
