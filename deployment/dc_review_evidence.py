"""Original BOSS evidence for one unresolved DC candidate, never acceptance.

Multiple candidates keep the existing path. Every selected license field is
bound to the server's retained candidate. The existing signed decision owns
status interpretation; evidence completion only supplies the original PDF.
"""
import copy,hashlib,json,re
from deployment.dc_native_capture import expected_record

def target(result):
    if result.get('state')!='DC' or result.get('success') is not False or result.get('status') not in {'Unable to Confirm','Needs Review'}:return None
    ctx=result.get('_worker_identity_review')
    if not isinstance(ctx,dict) or ctx.get('search_complete') is not True:return None
    rows=ctx.get('records')
    if not isinstance(rows,list) or not 1<=len(rows)<=100 or any(not isinstance(r,dict) for r in rows):return None
    candidates=[r for r in rows if r.get('_identity_outcome') in {'accepted','possible','conflict'}]
    if len(candidates)!=1 or candidates[0].get('_identity_outcome') not in {'possible','conflict'}:return None
    row=candidates[0]
    if row.get('ein') and re.sub(r'\D','',str(row['ein']))!=re.sub(r'\D','',str(result.get('ein',''))):return None
    return expected_record(row)

def request_matches(result,d):
    if d.get('review_candidate') is True:
        expected=target(result)
        return bool(expected and all(d.get(k)==v for k,v in expected.items()) and result.get('raw_status_text')==d.get('result_raw_status'))
    if 'review_candidate' in d or target(result):return False
    from deployment.dc_boss_evidence import norm
    return (str(result.get('matched_registry_identifier'))==d['identifier']
            and norm(result.get('matched_registry_name'))==norm(d['name'])
            and result.get('raw_status_text')==d.get('result_raw_status'))

def attach_reference(result,ref,store):
    from deployment.identity_evidence import _load,_source
    expected=target(result);d=result.get('_worker_desktop_evidence',{})
    if not expected or not request_matches(result,d):raise ValueError('Review candidate changed')
    payload=copy.deepcopy(_load({'base':result},store));doc=payload['history']
    if doc['run_id']!=d['run_id'] or ref.get('identifier')!=expected['identifier'] or ref.get('record_name')!=expected['name']:raise ValueError('Review source binding changed')
    _source(ref,'DC',d['ein'],d['run_id'],store)
    # A single bound candidate gets one new source. Never retain a stale PDF
    # for the same identifier, or attach this image to another candidate.
    payload['sources']=[r for r in payload['sources'] if r.get('identifier')!=expected['identifier']]+[copy.deepcopy(ref)]
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    if len(raw)>200000:raise ValueError('Review evidence exceeds bound')
    meta=dict(kind='identity_evidence',state='DC',ein=d['ein'],run_id=d['run_id'],source_sha256=hashlib.sha256(raw).hexdigest(),captured_at=doc['completed_at'])
    context=copy.deepcopy(result['_worker_identity_review'])
    changed=0
    for row in context['records']:
        if row.get('_identity_outcome') in {'possible','conflict'} and expected_record(row)==expected:
            row['evidence_url']=ref['url'];changed+=1
    if changed!=1:raise ValueError('Review identity changed')
    return {'_worker_identity_review':context,'review_evidence_context':store.save(meta,raw)}
