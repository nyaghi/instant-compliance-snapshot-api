"""Retain original artifacts and observed searches across signed decisions.

Local candidate. No registry requests, status decisions, or fabricated pixels.
Only a reference in the verified identity token can authorize replay.
"""
import copy,hashlib,io,json,re,time
from deployment import state_snapshots as ss
from deployment import search_history as sh

SCHEMA='cc-identity-evidence-v1'
def has_review(data):
    return bool(data.get('_worker_identity_review') or data.get('identity_review'))

def _source(ref,state,ein,run_id,store):
    match=re.fullmatch(r'/state-snapshots/([a-f0-9]{64})\.pdf',str(ref.get('url','')))
    if not match:raise ValueError('Invalid original reference')
    item=store.load(match[1])
    if not item:raise ValueError('Missing original')
    meta,raw,_=item
    if (meta.get('state')!=state or meta.get('ein')!=ein or meta.get('run_id')!=run_id
        or meta.get('identifier')!=ref.get('identifier') or meta.get('record_name')!=ref.get('record_name')
        or meta.get('kind') not in {'image','image_pages','source_pdf'}
        or hashlib.sha256(raw).hexdigest()!=meta.get('source_sha256')):
        raise ValueError('Original binding changed')
    ss.public_url(meta['source_url'],state)
    return meta,raw

def retain(record,result,store):
    """Archive validated history privately while the user decides identity."""
    data=dict(result)
    if not has_review(data) or store is None:return data
    try:
        doc=sh.manifest(copy.deepcopy(record),data,{},time.time())
        refs=[]
        for ref in record.get('source_snapshots',[])[:24]:
            _source(ref,doc['state'],doc['ein'],doc['run_id'],store)
            refs.append(copy.deepcopy(ref))
        payload={'schema':SCHEMA,'history':doc,'sources':refs}
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
        if len(raw)>200000:raise ValueError('Review evidence exceeds bound')
        meta={'kind':'identity_evidence','state':doc['state'],'ein':doc['ein'],'run_id':doc['run_id'],
              'source_sha256':hashlib.sha256(raw).hexdigest(),'captured_at':doc['completed_at']}
        data['review_evidence_context']=store.save(meta,raw)
    except Exception:
        data['review_evidence_capture']='unavailable'
    return data

def bind(master,data):
    """Bind the server-created context reference into the existing signature."""
    review=data.get('identity_review');ident=data.get('review_evidence_context')
    if not review or not re.fullmatch(r'[a-f0-9]{64}',str(ident or '')):return data
    import base64
    try:
        body=review['token'].rsplit('.',1)[0]
        original=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        rec=master.identity_review_unpack(review['token'],*(original.get('owner') or ['','']))
        if rec['base']['ein']!=data['ein'] or rec['base']['state']!=data['state']:raise ValueError('Wrong review')
        rec['base']['review_evidence_context']=ident
        data={**data,'identity_review':master.identity_review_view(rec)}
    except Exception:
        data={**data,'review_evidence_capture':'unavailable'}
    return data

def _load(record,store):
    ident=record['base'].get('review_evidence_context','')
    if not re.fullmatch(r'[a-f0-9]{64}',str(ident)):raise ValueError('No retained context')
    item=store.load(ident)
    if not item:raise ValueError('Context unavailable')
    meta,raw,_=item;payload=json.loads(raw);doc=payload['history']
    base=record['base']
    if (meta.get('kind')!='identity_evidence' or payload.get('schema')!=SCHEMA
        or meta.get('source_sha256')!=hashlib.sha256(raw).hexdigest()
        or any(meta.get(k)!=doc.get(k) for k in ('ein','state','run_id'))
        or doc['ein']!=ss.digits(base['ein']) or doc['state']!=base['state']
        or doc['organization_name']!=base['organization_name']):raise ValueError('Wrong context')
    for ref in payload['sources']:_source(ref,doc['state'],doc['ein'],doc['run_id'],store)
    return payload

def _rejected_original(record,payload,store):
    """Package unchanged original PDF pages; never draw an empty result."""
    doc=payload['history'];refs=payload['sources']
    # Every signed candidate must be represented. A partial collection is not
    # offered as the final source evidence, even if one candidate has a PDF.
    chosen=[]
    for row in record['records']:
        ref=ss.matching_reference({**row,'state':doc['state'],'ein':doc['ein']},refs)
        if not ref:raise ValueError('A rejected candidate has no original')
        if ref['url'] not in [r['url'] for r in chosen]:chosen.append(ref)
    if not chosen:raise ValueError('No original rejected records')
    from pypdf import PdfReader,PdfWriter
    writer=PdfWriter();provenance=[];seen=set()
    for ref in chosen:
        meta,raw=_source(ref,doc['state'],doc['ein'],doc['run_id'],store)
        provenance.append({k:meta[k] for k in ('source_url','source_sha256','captured_at','identifier','record_name')})
        if meta['source_sha256'] in seen:continue
        seen.add(meta['source_sha256'])
        for page in PdfReader(io.BytesIO(ss.render_pdf(meta,raw))).pages:
            if len(writer.pages)>=12:raise ValueError('Too many original pages')
            writer.add_page(page)
    output=io.BytesIO();writer.write(output);raw=output.getvalue()
    if len(raw)>ss.MAX_BYTES:raise ValueError('Original collection exceeds bound')
    asset=ss.asset_for(raw,kind='source_pdf',state=doc['state'],ein=doc['ein'],run_id=doc['run_id'],
        source_url=provenance[0]['source_url'],organization_name=doc['organization_name'],
        identifier='@completed-search',record_name='',capture_note='Original retrieved records; user rejected their identities. This is not an empty state search.')
    asset['captured_at']=max(p['captured_at'] for p in provenance)
    meta,raw=ss.validate_asset(asset,ein=doc['ein'],state=doc['state'],run_id=doc['run_id'])
    meta['review_source_provenance']=provenance
    return ss.snapshot_link(store.save(meta,raw))

def _decisions(record):
    return [{'name':r['name'],'identifier':r['identifier'],'decision':'reject',
             'reviewed_at':record['decisions'][r['id']]['reviewed_at']} for r in record['records']
            if record['decisions'].get(r['id'],{}).get('decision')=='reject']

def _save_history(doc,store):
    raw=json.dumps(doc,ensure_ascii=False,separators=(',',':')).encode()
    if len(raw)>150000:raise ValueError('History exceeds bound')
    meta={'kind':'search_history','state':doc['state'],'ein':doc['ein'],'run_id':doc['run_id'],
          'source_sha256':hashlib.sha256(raw).hexdigest(),'captured_at':doc['completed_at']}
    return '/state-evidence/'+store.save(meta,raw)+'/search-history.pdf'

def _continued(record,data,store):
    """Merge observed receipts only. The fresh run remains the image authority."""
    if not has_review(data) and not sh.needs_search_history(data):return data
    out=dict(data)
    try:
        old=_load(record,store)['history']
        pending=has_review(data)
        if pending:
            current=_load({'base':data},store);doc=copy.deepcopy(current['history'])
        else:
            match=re.fullmatch(r'/state-evidence/([a-f0-9]{64})/search-history\.pdf',str(data.get('search_history_url','')))
            if not match:raise ValueError('Fresh receipts unavailable')
            loaded=sh.loaded(match[1],store)
            if not loaded:raise ValueError('Fresh receipts unavailable')
            doc=copy.deepcopy(loaded[1]);current=None
        if (doc['ein']!=old['ein'] or doc['state']!=old['state']
            or doc['organization_name']!=old['organization_name']
            or doc['started_at']<old['started_at']):raise ValueError('Wrong continuation')
        entries=[];seen={}
        for item in old['queries']+doc['queries']:
            canonical={k:v for k,v in item.items() if k not in {'sequence','source_order'}}
            qid=item['query_id']
            if qid in seen:
                if seen[qid]!=canonical:raise ValueError('Changed reused receipt')
                continue
            seen[qid]=canonical;entries.append(copy.deepcopy(item))
        if not entries or len(entries)>150:raise ValueError('Continuation history exceeds bound')
        for i,e in enumerate(entries,1):e['sequence']=i
        doc.update(queries=entries,started_at=old['started_at'],
            reviewed_names=list(dict.fromkeys(old['reviewed_names']+doc['reviewed_names'])))
        doc['identity_decisions']=old.get('identity_decisions',[])+_decisions(record)
        doc['source_limitations']+=' Earlier candidate rejections caused a continued search. The original snapshot, when present, belongs to the final source lookup; earlier requests remain listed.'
        if pending:
            current['history']=doc;raw=json.dumps(current,ensure_ascii=False,separators=(',',':')).encode()
            if len(raw)>200000:raise ValueError('Continued context exceeds bound')
            meta={'kind':'identity_evidence','state':doc['state'],'ein':doc['ein'],'run_id':doc['run_id'],
                  'source_sha256':hashlib.sha256(raw).hexdigest(),'captured_at':doc['completed_at']}
            out['review_evidence_context']=store.save(meta,raw)
        else:
            out['search_history_url']=_save_history(doc,store);out.pop('evidence_bundle_url',None)
        return out
    except Exception:
        # A partial fresh-only history must not look like the entire sequence.
        out.pop('search_history_url',None);out.pop('evidence_bundle_url',None)
        out['search_history_capture']='unavailable';out['review_evidence_capture']='continuation_history_unavailable'
        return out

def resolve(record,result,fresh=False,store=None):
    """After existing signed status resolution. Never change status/identity."""
    data=dict(result);store=store or ss.STORE
    if fresh:return _continued(record,data,store)
    rows=record.get('records',[]);decisions=record.get('decisions',{})
    if not rows or not all(r.get('reviewable') and decisions.get(r['id'],{}).get('decision')=='reject' for r in rows):return data
    if data.get('status') not in {'Not Registered','Unable to Confirm'}:return data
    data['identity_review_evidence_final']=True
    data.pop('search_history_url',None);data.pop('evidence_bundle_url',None)
    data['evidence_url']='';data['evidence_capture']='unavailable'
    try:
        payload=_load(record,store);doc=copy.deepcopy(payload['history'])
        try:
            data['evidence_url']=_rejected_original(record,payload,store)
            data['evidence_capture']='saved'
        except Exception:pass # Preserve history even when original is incomplete.
        doc.update(result_at_completion=data['status'],completed_at=time.time(),snapshot_url=data['evidence_url'],snapshot_expected=not sh.history_only_result(data))
        doc['identity_decisions']=doc.get('identity_decisions',[])+_decisions(record)
        doc['source_limitations']+=' The state returned candidate records. The user rejected their identities; the original pages are not a zero-results search. Search completeness is determined separately.'
        data['search_history_url']=_save_history(doc,store)
        data['evidence_basis']='Original retrieved records; all candidate identities rejected by the user.'
    except Exception:data['search_history_capture']='unavailable'
    return data
