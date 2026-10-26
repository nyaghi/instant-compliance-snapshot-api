from deployment.workflow_observation import workflow_call, trace_return, workflow_stage
"""Immutable source archives. Reading a PDF never performs a registry lookup.

Archive bytes are kept outside result payloads and identity-review tokens.
SQLite is for isolated local controls; staging uses the existing Postgres pool.
"""
import base64
from contextvars import ContextVar
from contextlib import closing, contextmanager
import hashlib
import io
import json
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

MAX_BYTES = 3_000_000
MAX_PIXELS = 20_000_000
CURRENT = ContextVar('state_snapshot_capture', default=None)
REFERENCES = ContextVar('state_snapshot_references', default=())
DEADLINE = ContextVar('state_snapshot_deadline',default=float('inf'))
STORE = None
@contextmanager
def task_deadline(job):
    token=DEADLINE.set(job.get('_deadline_monotonic',float('inf')))
    try:yield
    finally:DEADLINE.reset(token)
OFFICIAL_HOSTS = {
 'AL': {'ago.igovsolution.net'}, 'AK': {'online-registrations-law.alaska.gov'},
 'AR': {'sos-corp-search.ark.org'}, 'CA': {'ca-rcf.evokeplatform.com'},
 'CO': {'www.coloradosos.gov'}, 'CT': {'www.elicense.ct.gov'},
 'DC': {'maps2.dcgis.dc.gov','boss.dc.gov'}, 'FL': {'csapp.fdacs.gov'},
 'GA': {'verify.sos.ga.gov'}, 'HI': {'charity.ehawaii.gov'},
 'IL': {'charitable.illinoisattorneygeneral.gov'}, 'KS': {'www.ag.ks.gov'},
 'KY': {'www.ag.ky.gov'}, 'LA': {'www.ag.state.la.us'},
 'MA': {'masscharities.my.site.com'}, 'MD': {'onestop.md.gov'},
 'ME': {'www.pfr.maine.gov'}, 'MI': {'www.ag.state.mi.us'},
 'MN': {'www.ag.state.mn.us'}, 'MS': {'charities.sos.ms.gov'},
 'NC': {'www.sosnc.gov'}, 'ND': {'firststop.sos.nd.gov'},
 'NH': {'www.doj.nh.gov','mm.nh.gov'}, 'NJ': {'charportal.dca.njoag.gov'},
 'NM': {'secure.nmdoj.gov'}, 'NV': {'orion.nv.gov'},
 'NY': {'charities-search.ag.ny.gov','charities-search-api.ag.ny.gov'},
 'OH': {'charitableregistration.ohioago.gov'}, 'OK': {'www.sos.ok.gov'},
 'OR': {'justice.oregon.gov'}, 'PA': {'www.charities.pa.gov'},
 'RI': {'ridbrprod-search.state-reg-eastern.tylerapp.com','ridbrprod.state-reg-eastern.tylerapp.com'},
 'SC': {'search.scsos.com'}, 'TN': {'tncab.tnsos.gov'},
 'VA': {'vdacs.evokeplatform.com','cos.vdacs.virginia.gov'}, 'WA': {'ccfs.sos.wa.gov'},
 'WI': {'apps.dfi.wi.gov'}, 'WV': {'erls.wvsos.gov'},
}

def public_url(value, state):
    if not isinstance(value,str) or len(value)>5000:raise ValueError('Invalid source URL')
    u = urlsplit(str(value))
    # The exact native viewer linked by DC's official layer, not arbitrary ArcGIS.
    dc_viewer=False
    if state=='DC' and u.hostname=='www.arcgis.com':
        from deployment.dc_native_capture import valid_viewer
        dc_viewer=valid_viewer(value)
        if not dc_viewer:raise ValueError('Unbound DC viewer URL')
    if (u.scheme != 'https' or (u.hostname not in OFFICIAL_HOSTS.get(state, set()) and not dc_viewer)
            or u.username or u.password or u.port not in (None,443)
            or re.search(r'(?:/auth/|/logout|/login|/signin|challenge-platform)',u.path,re.I)):
        raise ValueError('Snapshot must originate at this state public registry')
    pairs = [(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True)
             if not re.search(r'token|password|passcode|captcha|cookie|session|authorization|api.?key',k,re.I)]
    fragment='' if re.search(r'token|password|passcode|captcha|cookie|session|authorization|api.?key',u.fragment,re.I) else u.fragment
    return urlunsplit(('https',u.netloc,u.path,urlencode(pairs),fragment))

def digits(value): return re.sub(r'\D','',str(value))
def key(value): return re.sub(r'[^a-z0-9]','',str(value).lower())

def source_name_present(name,text,state):
    # Kentucky's stored display name joins two original PDF columns with an
    # app-only separator. Verify both original columns, never redraw them.
    parts=str(name).split(' | DBA: ') if state=='KY' else [str(name)]
    normalized=key(text)
    return bool(parts and all(key(part) and key(part) in normalized for part in parts))

def validate_asset(asset, *, ein, state, run_id):
    if not isinstance(asset,dict):raise ValueError('Invalid source archive')
    if (asset.get('state')!=state or digits(asset.get('ein'))!=digits(ein)
            or asset.get('run_id')!=run_id or not re.fullmatch(r'[a-zA-Z0-9_-]{16,100}',run_id)):
        raise ValueError('Snapshot belongs to a different run, EIN or state')
    url=public_url(asset.get('source_url',''),state)
    kind=asset.get('kind')
    if kind not in {'image','image_pages','source_pdf'}:raise ValueError('Snapshot requires actual page pixels or original state PDF pages')
    raw=base64.b64decode(asset.get('content',''),validate=True)
    if not 1<=len(raw)<=MAX_BYTES:raise ValueError('Source archive exceeds bound')
    stamp=asset.get('captured_at')
    if type(stamp) not in (int,float) or not 0<stamp<=time.time()+60:raise ValueError('Invalid capture time')
    if kind in {'image','image_pages'}:
        from PIL import Image
        pages=[raw]
        if kind=='image_pages':
            encoded=json.loads(raw)
            if not isinstance(encoded,list) or not 2<=len(encoded)<=(8 if state=='NV' and asset.get('operation')=='detail' else 3) or any(not isinstance(v,str) for v in encoded):raise ValueError('Invalid source image pages')
            pages=[base64.b64decode(v,validate=True) for v in encoded]
        pixels=0
        for page in pages:
            with Image.open(io.BytesIO(page)) as im:
                pixels+=im.width*im.height
                if im.format not in {'PNG','JPEG'} or pixels>MAX_PIXELS:raise ValueError('Invalid source image')
                im.verify()
            with Image.open(io.BytesIO(page)) as im:
                low,high=im.convert('L').getextrema()
                if high-low<8:raise ValueError('Blank source screenshot')
    elif kind=='source_pdf':
        from pypdf import PdfReader
        if not raw.startswith(b'%PDF-') or not 1<=len(PdfReader(io.BytesIO(raw)).pages)<=12:raise ValueError('Invalid source PDF')
    meta={k:asset.get(k,'') for k in ('organization_name','identifier','record_name','public_text','capture_note','query_id')}
    if any(not isinstance(v,str) or len(v)>20000 for v in meta.values()):raise ValueError('Invalid archive metadata')
    meta.update(state=state,ein=digits(ein),run_id=run_id,kind=kind,source_url=url,
                captured_at=stamp,source_sha256=hashlib.sha256(raw).hexdigest())
    return meta,raw

def asset_for(raw, *, kind, state, ein, run_id, source_url, **meta):
    return dict(meta,kind=kind,state=state,ein=digits(ein),run_id=run_id,source_url=source_url,
                captured_at=time.time(),content=base64.b64encode(raw).decode('ascii'))

class SQLiteStore:
    """Local test storage only. Never connects to a staging database."""
    def __init__(self,path):
        self.path=str(path);self.lock=threading.Lock()
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute('CREATE TABLE IF NOT EXISTS snapshots(id TEXT PRIMARY KEY,metadata TEXT NOT NULL,source BLOB NOT NULL,pdf BLOB)')
    def save(self,meta,raw):
        ident=secrets.token_hex(32)
        with self.lock,closing(sqlite3.connect(self.path)) as c,c:c.execute('INSERT INTO snapshots VALUES(?,?,?,NULL)',(ident,json.dumps(meta),raw))
        return ident
    def load(self,ident):
        if not re.fullmatch(r'[a-f0-9]{64}',ident):return None
        with closing(sqlite3.connect(self.path)) as c:r=c.execute('SELECT metadata,source,pdf FROM snapshots WHERE id=?',(ident,)).fetchone()
        return None if not r else (json.loads(r[0]),bytes(r[1]),bytes(r[2]) if r[2] else None)
    def cache_pdf(self,ident,pdf):
        with self.lock,closing(sqlite3.connect(self.path)) as c,c:c.execute('UPDATE snapshots SET pdf=? WHERE id=? AND pdf IS NULL',(pdf,ident))

class PostgresStore:
    def __init__(self,pool):self.pool=pool
    def save(self,meta,raw):
        from psycopg.types.json import Jsonb
        ident=secrets.token_hex(32)
        with self.pool.connection(timeout=.25) as c:
            c.execute("SET LOCAL statement_timeout = '500ms'")
            c.execute('INSERT INTO cc_state_snapshots(id,metadata,source) VALUES(%s,%s,%s)',(ident,Jsonb(meta),raw))
        return ident
    def load(self,ident):
        if not re.fullmatch(r'[a-f0-9]{64}',ident):return None
        with self.pool.connection() as c:r=c.execute('SELECT metadata,source,pdf FROM cc_state_snapshots WHERE id=%s',(ident,)).fetchone()
        return None if not r else (r['metadata'],bytes(r['source']),bytes(r['pdf']) if r['pdf'] else None)
    def cache_pdf(self,ident,pdf):
        with self.pool.connection() as c:c.execute('UPDATE cc_state_snapshots SET pdf=%s WHERE id=%s AND pdf IS NULL',(pdf,ident))

def snapshot_link(ident):return '/state-snapshots/'+ident+'.pdf'

def archive(asset, *, ein, state, run_id, store=None):
    store=store or STORE
    if store is None:raise RuntimeError('Persistent source archive is not configured')
    meta,raw=validate_asset(asset,ein=ein,state=state,run_id=run_id)
    return trace_return('deployment/state_snapshots.py:archive:162:4:return',({'url':snapshot_link(store.save(meta,raw)),'identifier':meta['identifier'],
            'record_name':meta['record_name'],'source_sha256':meta['source_sha256'],
            'source_url':meta['source_url'],'captured_at':meta['captured_at'],
            'kind':meta['kind'],'run_id':run_id,'ein':meta['ein'],'state':state}))

def completed_negative_result(result):
    """Illinois absence has an explicitly qualified public label."""
    return (isinstance(result,dict) and result.get('success') is True
            and (result.get('status')=='Not Registered'
                 or result.get('state')=='IL' and result.get('status')=='Not Registered / Non-Compliant'))

def matching_reference(result, refs):
    """Never offer another candidate's screenshot for a selected registration."""
    ident=str(workflow_call('deployment/state_snapshots.py:matching_reference:175:14:get',result.get,locals(), 'matched_registry_identifier') or workflow_call('deployment/state_snapshots.py:matching_reference:175:59:get',result.get,locals(), 'identifier') or '')
    name=str(workflow_call('deployment/state_snapshots.py:matching_reference:176:13:get',result.get,locals(), 'matched_registry_name') or workflow_call('deployment/state_snapshots.py:matching_reference:176:52:get',result.get,locals(), 'name') or '')
    ein=digits(workflow_call('deployment/state_snapshots.py:matching_reference:177:15:get',result.get,locals(), 'ein',''));state=workflow_call('deployment/state_snapshots.py:matching_reference:177:43:get',result.get,locals(), 'state')
    candidates=[r for r in refs if workflow_call('deployment/state_snapshots.py:matching_reference:178:35:get',r.get,locals(), 'ein')==ein and workflow_call('deployment/state_snapshots.py:matching_reference:178:57:get',r.get,locals(), 'state')==state]
    if state=='GA':
        if (ident or name) and not completed_negative_result(result):
            # A completed empty search is not a competing same-name credential.
            # Positive/review records require their original selected detail;
            # a search-list fallback must not masquerade as that detail.
            candidates=[r for r in candidates if r.get('operation')=='detail'
                        and r.get('identifier')!='@completed-search']
        else:
            candidates=sorted(candidates,key=lambda r:r.get('operation')=='detail')
    if state=='NC':
        candidates=sorted(candidates,key=lambda r:workflow_call('deployment/state_snapshots.py:matching_reference:182:50:get',r.get,locals(), 'operation')=='detail')
    if state=='NM' and re.fullmatch(r'\d{2}-?\d{7}',ident) and digits(ident)==ein:
        # The connector uses the nine-digit FEIN while the public result keeps
        # New Mexico's displayed hyphen. This is one already-bound credential.
        return trace_return('deployment/state_snapshots.py:matching_reference:186:8:return',(next((r for r in reversed(candidates)
                     if re.fullmatch(r'\d{2}-?\d{7}',str(workflow_call('deployment/state_snapshots.py:matching_reference:187:57:get',r.get,locals(), 'identifier','')))
                     and digits(r['identifier'])==ein
                     and (not name or key(workflow_call('deployment/state_snapshots.py:matching_reference:189:42:get',r.get,locals(), 'record_name'))==key(name))),None)))
    if state=='IL' and ident:
        # A results list cannot substantiate the selected record's dates.
        candidates=[r for r in candidates if workflow_call('deployment/state_snapshots.py:matching_reference:192:45:get',r.get,locals(), 'operation')=='detail']
    if state=='TN':
        # A selected record's dates require its detail page. A matching name
        # in a search list is useful context, not a substitute for that page.
        if (ident or name) and not completed_negative_result(result):
            candidates=[r for r in candidates if workflow_call('deployment/state_snapshots.py:matching_reference:197:49:get',r.get,locals(), 'operation')=='detail']
        else:
            candidates=sorted(candidates,key=lambda r:workflow_call('deployment/state_snapshots.py:matching_reference:199:54:get',r.get,locals(), 'operation')=='detail')
    if state=='NY':
        candidates=[r for r in candidates if r.get('operation')=='detail']
        path=urlsplit(workflow_call('deployment/state_snapshots.py:matching_reference:201:22:get',result.get,locals(), 'source_url') or workflow_call('deployment/state_snapshots.py:matching_reference:201:50:get',result.get,locals(), 'url') or '').path
        observed=re.fullmatch(r'/RegistrySearch/(\d{2}-\d{2}-\d{2})/?',path)
        if observed:
            return trace_return('deployment/state_snapshots.py:matching_reference:204:12:return',(next((r for r in reversed(candidates) if workflow_call('deployment/state_snapshots.py:matching_reference:204:60:get',r.get,locals(), 'identifier')==observed[1]
                         and (not name or key(workflow_call('deployment/state_snapshots.py:matching_reference:205:46:get',r.get,locals(), 'record_name'))==key(name))),None)))
    if state=='VA' and completed_negative_result(result) and re.fullmatch(r'\d{1,12}',ident):
        proof=workflow_call('deployment/state_snapshots.py:matching_reference:207:14:get',result.get,locals(), 'va_entity_evidence')
        if (isinstance(proof,dict) and workflow_call('deployment/state_snapshots.py:matching_reference:208:39:get',proof.get,locals(), 'ein')==ein and workflow_call('deployment/state_snapshots.py:matching_reference:208:65:get',proof.get,locals(), 'id')==ident
                and workflow_call('deployment/state_snapshots.py:matching_reference:209:20:get',proof.get,locals(), 'entity_id')==ident and bool(name) and key(workflow_call('deployment/state_snapshots.py:matching_reference:209:73:get',proof.get,locals(), 'name'))==key(name)
                and workflow_call('deployment/state_snapshots.py:matching_reference:210:20:get',proof.get,locals(), 'status')=='Unregistered' and type(workflow_call('deployment/state_snapshots.py:matching_reference:210:65:get',proof.get,locals(), 'registration_count')) is int
                and proof['registration_count']==0):
            return trace_return('deployment/state_snapshots.py:matching_reference:212:12:return',(next((r for r in reversed(candidates) if workflow_call('deployment/state_snapshots.py:matching_reference:212:60:get',r.get,locals(), 'identifier')=='@completed-search'
                         and workflow_call('deployment/state_snapshots.py:matching_reference:213:29:get',r.get,locals(), 'source_url')=='https://vdacs.evokeplatform.com/app/publicPortal/entity/'+ident
                         and key(workflow_call('deployment/state_snapshots.py:matching_reference:214:33:get',r.get,locals(), 'record_name'))==key(name)),None)))
    if ident:return trace_return('deployment/state_snapshots.py:matching_reference:215:13:return',(next((r for r in reversed(candidates) if workflow_call('deployment/state_snapshots.py:matching_reference:215:61:get',r.get,locals(), 'identifier')==ident
                         and (not name or key(workflow_call('deployment/state_snapshots.py:matching_reference:216:46:get',r.get,locals(), 'record_name'))==key(name))),None)))
    if name:
        named=[r for r in candidates if key(workflow_call('deployment/state_snapshots.py:matching_reference:218:44:get',r.get,locals(), 'record_name'))==key(name)]
        # Same-name registrations are not interchangeable evidence. Without a
        # selected credential, an ambiguous collection must offer no row link.
        if len({workflow_call('deployment/state_snapshots.py:matching_reference:221:16:get',r.get,locals(), 'identifier','') for r in named})!=1:return trace_return('deployment/state_snapshots.py:matching_reference:221:59:return',(None))
        return trace_return('deployment/state_snapshots.py:matching_reference:222:8:return',(named[-1] if named else None))
    if completed_negative_result(result):
        return trace_return('deployment/state_snapshots.py:matching_reference:224:8:return',(next((r for r in reversed(candidates) if workflow_call('deployment/state_snapshots.py:matching_reference:224:56:get',r.get,locals(), 'identifier')=='@completed-search'),None)))
    return trace_return('deployment/state_snapshots.py:matching_reference:225:4:return',(None))

def attach_links(result, refs):
    data=dict(result);ref=workflow_call('deployment/state_snapshots.py:attach_links:228:26:matching_reference',matching_reference,locals(), data,refs)
    if ref:data.update(evidence_url=ref['url'],evidence_captured_at=ref['captured_at'])
    else:data['evidence_url']=''
    review=workflow_call('deployment/state_snapshots.py:attach_links:231:11:get',data.get,locals(), 'identity_review')
    if review:
        # The signed record is populated in the master before this public view.
        data['identity_review']={**review,'candidates':[dict(c) for c in workflow_call('deployment/state_snapshots.py:attach_links:234:73:get',review.get,locals(), 'candidates',[])]}
        for row in data['identity_review']['candidates']:
            candidate=workflow_call('deployment/state_snapshots.py:attach_links:236:22:matching_reference',matching_reference,locals(), {**row,'ein':data['ein'],'state':data['state']},refs)
            if candidate:row['evidence_url']=candidate['url']
    data['evidence_capture']='saved' if ref else ('candidate_only' if review and any(workflow_call('deployment/state_snapshots.py:attach_links:238:85:get',r.get,locals(), 'evidence_url') for r in data['identity_review']['candidates']) else 'unavailable')
    return trace_return('deployment/state_snapshots.py:attach_links:239:4:return',(data))

def persist_history_timed(data,job,history,refs,store):
    from deployment.search_history import persist_worker_history
    started=time.perf_counter()
    out=persist_worker_history(data,job,history,refs,store=store)
    if isinstance(out.get('evidence_metrics'),dict):
        out['evidence_metrics']={**out['evidence_metrics'],'history_archive_ms':round((time.perf_counter()-started)*1000,2)}
    return out

from deployment.workflow_observation import archive_stage
@archive_stage
def persist_worker_result(queue,result,job,store=None):
    """Supervisor only, after reaping. Never give child processes DB access."""
    if not isinstance(result,dict):return trace_return('deployment/state_snapshots.py:persist_worker_result:251:35:return',(result))
    data=dict(result);assets=data.pop('_worker_source_archives',[])
    if isinstance(workflow_call('deployment/state_snapshots.py:persist_worker_result:253:18:get',data.get,locals(), 'evidence_metrics'),dict):data['evidence_metrics']={**data['evidence_metrics'],'archive_ms':0}
    history=data.pop('_worker_search_history',None)
    if workflow_call('deployment/state_snapshots.py:persist_worker_result:255:7:get',workflow_call('deployment/state_snapshots.py:persist_worker_result:255:7:get',data.get,locals(), '_worker_desktop_evidence',{}).get,locals(), 'operation')=='empty_search' and isinstance(history,dict):
        data['_worker_desktop_history']=history
    if not assets:
        return trace_return('deployment/state_snapshots.py:persist_worker_result:258:8:return',(persist_history_timed(data,job,history,[],store or (PostgresStore(queue.pool) if history and queue else None))))
    data['evidence_url']=''
    refs=[];started=time.perf_counter()
    if (not isinstance(assets,list) or len(assets)>12
            or digits(workflow_call('deployment/state_snapshots.py:persist_worker_result:262:22:get',data.get,locals(), 'ein'))!=digits(job['payload']['ein']) or workflow_call('deployment/state_snapshots.py:persist_worker_result:262:73:get',data.get,locals(), 'state')!=job['state']):
        data['evidence_capture']='unavailable';return trace_return('deployment/state_snapshots.py:persist_worker_result:263:47:return',(data))
    try:
        store=store or PostgresStore(queue.pool)
        for asset in assets:
            if time.perf_counter()-started>1:
                data['evidence_capture']='partial' if refs else 'unavailable';break
            refs.append(workflow_call('deployment/state_snapshots.py:persist_worker_result:269:24:archive',archive,locals(), asset,ein=data['ein'],state=data['state'],run_id=workflow_call('deployment/state_snapshots.py:persist_worker_result:269:81:get',asset.get,locals(), 'run_id',''),store=store))
    except Exception:
        data['evidence_capture']='partial' if refs else 'unavailable'
    data=workflow_call('deployment/state_snapshots.py:persist_worker_result:272:9:attach_links',attach_links,locals(), data,refs)
    data['evidence_archive_ms']=round((time.perf_counter()-started)*1000,2)
    if isinstance(workflow_call('deployment/state_snapshots.py:persist_worker_result:274:18:get',data.get,locals(), 'evidence_metrics'),dict):data['evidence_metrics'].update(archive_ms=data['evidence_archive_ms'],archived_assets=len(refs),row_link=bool(workflow_call('deployment/state_snapshots.py:persist_worker_result:274:164:get',data.get,locals(), 'evidence_url')))
    context=workflow_call('deployment/state_snapshots.py:persist_worker_result:275:12:get',data.get,locals(), '_worker_identity_review')
    if context:
        context={**context,'records':[dict(r) for r in context['records']]}
        for row in context['records']:
            ref=workflow_call('deployment/state_snapshots.py:persist_worker_result:279:16:matching_reference',matching_reference,locals(), {**row,'ein':data['ein'],'state':data['state']},refs)
            if ref:row['evidence_url']=ref['url']
        data['_worker_identity_review']=context
    return trace_return('deployment/state_snapshots.py:persist_worker_result:282:4:return',(persist_history_timed(data,job,history,refs,store)))

def persist_inline_result(master,result):
    """API-owned continuation: archive now, never expose private image bytes."""
    if STORE is None:
        data=dict(result);data.pop('_worker_source_archives',None)
        data.pop('_worker_search_history',None)
        data['evidence_capture']='unavailable';return data
    data=persist_worker_result(None,result,{'state':result['state'],'payload':{'ein':result['ein']}},store=STORE)
    try:
        review=data.get('identity_review')
        if not review:return data
        # This is the master's own generated token. Verify its signature and
        # retain its existing owner/expiry; never rebind it to another caller.
        body=review['token'].rsplit('.',1)[0]
        original=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
        record=master.identity_review_unpack(review['token'],*(original.get('owner') or ['','']))
        by_id={row['id']:row.get('evidence_url','') for row in review['candidates']}
        for row in record['records']:
            if by_id.get(row['id']):row['evidence_url']=by_id[row['id']]
        record['base']['evidence_url']=data.get('evidence_url','')
        if data.get('review_evidence_context'):record['base']['review_evidence_context']=data['review_evidence_context']
        data['identity_review']=master.identity_review_view(record)
    except Exception:
        pass  # Preserve the original signed choice and status if unavailable.
    return data

def ak_empty_controls(page,run,text):
    """Read original public form criteria; never fill or reconstruct the page."""
    if run.state!='AK' or 'There are no charitable organizations.' not in text:return None
    if not page.get_by_text('There are no charitable organizations.',exact=True).is_visible():return None
    category=page.locator('select[id$="-8"]:visible option:checked').inner_text(timeout=300).strip()
    year=page.locator('select[id$="-9"]:visible option:checked').inner_text(timeout=300).strip()
    name=page.locator('input[id$="-a"]:visible').input_value(timeout=300).strip()
    fein=page.locator('input[id$="-b"]:visible').input_value(timeout=300).strip()
    if category!='Charitable Organization' or not re.fullmatch(r'20[0-9]{2}',year):return None
    if fein and digits(fein)!=run.ein:return None
    known={key(n) for n in [run.name,*getattr(run,'known_names',[])] if n}
    if name and key(name) not in known:return None
    if not fein and not name:return None
    return dict(category=category,year=year,name=name,ein=fein)



def capture_ma_scan(run, scanned, record, source_url, text):
    """Keep the first original scan page already read by the MA lookup."""
    if (run is None or run.state != 'MA' or not isinstance(record,dict)
        or digits(record.get('ein','')) != run.ein or not run.ein
        or not re.fullmatch(r'\d{6}',str(record.get('ago_account','')))
        or not re.fullmatch(r'a09[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?',str(record.get('record_id','')))
        or time.monotonic()+2 >= DEADLINE.get()):return
    u=urlsplit(source_url)
    if (u.scheme!='https' or u.netloc!='masscharities.my.site.com' or u.query or u.fragment
        or not re.fullmatch(r'/FilingSearch/sfc/servlet\.shepherd/document/download/069[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?',u.path)):return
    eins={digits(x) for x in re.findall(r'(?<!\d)\d{2}[- ]?\d{7}(?!\d)',text)}
    if eins!={run.ein} or not source_name_present(record.get('name',''),text,'MA'):return
    accounts=re.findall(r"Attorney\s+General(?:['’]s)?\s+Account\s*#?\s*:?\s*(\d{6})(?!\d)",text,re.I)
    if any(x.lstrip('0')!=record['ago_account'].lstrip('0') for x in accounts):return
    if scanned.tell()!=0 or not 0<scanned.width*scanned.height<=20_000_000:return
    original=io.BytesIO();scanned.save(original,format='PNG');raw=original.getvalue()
    if not 0<len(raw)<=MAX_BYTES or time.monotonic()>=DEADLINE.get():return
    count=getattr(scanned,'n_frames',1)
    note=f'Original first page of the selected state attachment ({count} source pages). No reconstructed source content; no fiscal period inferred from this image.'
    run.document(source_url,raw,'image',text,note)
    if not any(d[1]==raw and d[0]==source_url for d in run.documents):return
    bindings=getattr(run,'ma_scan_bindings',None)
    if bindings is None:run.ma_scan_bindings={};bindings=run.ma_scan_bindings
    bindings[hashlib.sha256(raw).hexdigest()]={k:record[k] for k in ('ein','name','ago_account','record_id')}
    bindings[hashlib.sha256(raw).hexdigest()]['url']=source_url


def ma_selected_scan(run, ordered, row):
    """Pair only the same selected account's original scan and original list."""
    if (run.state!='MA' or row.get('state')!='MA' or digits(row.get('ein',''))!=run.ein
        or row.get('success') is not True
        or row.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable','Unable to Verify'}):return ordered
    identifier=str(row.get('matched_registry_identifier') or '')
    name=row.get('matched_registry_name','')
    for detail in ordered:
        proof=getattr(run,'ma_scan_bindings',{}).get(hashlib.sha256(detail[1]).hexdigest(),{})
        if (not proof or detail[2]!='image' or detail[0]!=proof.get('url')
            or proof.get('ein')!=run.ein or proof.get('ago_account')!=identifier
            or key(proof.get('name',''))!=key(name)):continue
        for listing in ordered:
            u=urlsplit(listing[0])
            if (listing[2]!='image' or u.scheme!='https' or u.netloc!='masscharities.my.site.com'
                or u.path!='/FilingSearch/s/' or u.query or u.fragment
                or run.ein not in digits(listing[3]) or not source_name_present(name,listing[3],'MA')
                or not re.search(r'(?<![\w])'+re.escape(identifier)+r'(?![\w])',listing[3])):continue
            raw=json.dumps([base64.b64encode(d[1]).decode('ascii') for d in (listing,detail)]).encode('utf8')
            if len(raw)>MAX_BYTES:return ordered
            paired=(detail[0],raw,'image_pages',(listing[3]+'\n\n'+detail[3])[:20000],detail[4],
                'Original filing list and '+detail[5])
            return [paired,*ordered]
    return ordered


def capture_ma_formpc(run, page, evidence):
    """Retain an existing validated MA popup; no navigation or extra query."""
    if (run is None or run.state!='MA' or not isinstance(evidence,dict)
        or evidence.get('filing_status')!='Submitted'
        or not re.fullmatch(r'\d+',str(evidence.get('ago_account','')))
        or not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',str(evidence.get('period_end','')))
        or evidence.get('source_url')!=page.url):return
    u=urlsplit(page.url)
    if (u.scheme!='https' or u.netloc!='masscharities.my.site.com'
        or not re.fullmatch(r'/FilingSearch/s/detail/[A-Za-z0-9]{15,18}',u.path)
        or u.query or u.fragment):return
    before=len(run.documents)
    run.page(page)
    if len(run.documents)<=before:return
    document=run.documents[-1]
    if document[0]!=page.url or document[2]!='image':return
    bindings=getattr(run,'ma_formpc_bindings',None)
    if bindings is None:run.ma_formpc_bindings={};bindings=run.ma_formpc_bindings
    bindings[hashlib.sha256(document[1]).hexdigest()]=dict(evidence)

def ma_selected_originals(run, ordered, row):
    """Pair the final selected submitted Form PC with the original filing list."""
    if run.state!='MA':return ordered
    evidence=row.get('ma_filing_evidence') or {}
    url=row.get('source_url','');identifier=str(row.get('matched_registry_identifier') or '')
    if (row.get('state')!='MA' or digits(row.get('ein',''))!=run.ein
        or row.get('success') is not True or row.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable','Unable to Verify'}
        or evidence.get('filing_status')!='Submitted' or not identifier
        or evidence.get('ago_account')!=identifier or evidence.get('source_url')!=url):return ordered
    bindings=getattr(run,'ma_formpc_bindings',{})
    for detail in ordered:
        binding=bindings.get(hashlib.sha256(detail[1]).hexdigest(),{})
        if (detail[2]!='image' or detail[0]!=url or not binding
            or any(binding.get(k)!=evidence.get(k) for k in ('ago_account','filing_status','period_start','period_end','source_url'))
            or not source_name_present(row.get('matched_registry_name',''),detail[3],'MA')
            or not re.search(r'(?<![\w])'+re.escape(identifier)+r'(?![\w])',detail[3])):continue
        for listing in ordered:
            u=urlsplit(listing[0])
            if (listing[2]!='image' or u.netloc!='masscharities.my.site.com' or u.path!='/FilingSearch/s/'
                or u.query or u.fragment or run.ein not in digits(listing[3])
                or not source_name_present(row.get('matched_registry_name',''),listing[3],'MA')
                or not re.search(r'(?<![\w])'+re.escape(identifier)+r'(?![\w])',listing[3])):continue
            raw=json.dumps([base64.b64encode(d[1]).decode('ascii') for d in (listing,detail)]).encode('utf8')
            if len(raw)>MAX_BYTES:break
            paired=(detail[0],raw,'image_pages',(listing[3]+'\n\n'+detail[3])[:20000],detail[4],
                'Original filing list and the selected submitted Form PC detail used to interpret the fiscal period. No new search or reconstructed source content.')
            return [paired,*ordered]
        return [detail,*[d for d in ordered if d is not detail]]
    run.errors.append('MA_selected_form_pc_original_unavailable')
    return ordered

def capture_ak_selected_before_recheck(page,year,ein,deadline):
    """Save the actual selected cycle without interrupting newer-cycle checks."""
    run=CURRENT.get()
    if run is None or run.state!='AK' or digits(ein)!=run.ein or type(year) is not int:return
    remaining=(deadline-time.perf_counter()) if deadline is not None else DEADLINE.get()-time.monotonic()
    if remaining<3:return
    start=len(run.documents);prior_stop=getattr(run,'page_capture_stop',None)
    try:
        def selected():
            rows=page.get_by_role('table',name='Charitable Organizations',exact=True).get_by_role('row').evaluate_all(
                '(rs)=>rs.slice(0,201).map(r=>Array.from(r.querySelectorAll("td")).map(c=>c.innerText.trim()))')
            if len(rows)>200:return None
            hits=[r for r in rows if len(r)>=4 and r[0]==str(year) and digits(r[1])==run.ein and r[2]]
            return hits[0] if len(hits)==1 else None
        row=selected()
        if row is None:return
        run.page_capture_stop=min(prior_stop or float('inf'),time.monotonic()+remaining)
        run.page(page)
        if selected()!=row or (deadline is not None and time.perf_counter()>=deadline):
            del run.documents[start:];return
        bindings=getattr(run,'ak_selected_cycle_images',None)
        if bindings is None:run.ak_selected_cycle_images={}
        for doc in run.documents[start:]:
            if doc[2]=='image':run.ak_selected_cycle_images[hashlib.sha256(doc[1]).hexdigest()]=dict(year=year,ein=run.ein,name=row[2])
    except Exception:
        del run.documents[start:]
        run.errors.append('AK_selected_cycle_capture_unavailable')
    finally:
        if prior_stop is None:
            if hasattr(run,'page_capture_stop'):del run.page_capture_stop
        else:run.page_capture_stop=prior_stop


def capture_oh_selected_grid(page, detail_ref, ein):
    """Retain the original exact-EIN result before a potentially broken detail."""
    run=CURRENT.get()
    if (run is None or run.state!='OH' or digits(ein)!=run.ein
            or not isinstance(detail_ref,dict) or detail_ref.get('einConfirmed') is not True
            or str(detail_ref.get('inCompliance','')).strip().casefold()!='yes'
            or not re.fullmatch(r'\d+',str(detail_ref.get('id','')))):
        return
    url='https://charitableregistration.ohioago.gov/Charities/ResearchCharities'
    before=len(run.documents)
    try:
        if page.url not in {url,url+'#results'} or DEADLINE.get()-time.monotonic()<3:return
        def selected():
            return page.evaluate(r'''({ein,id,name})=>{
                const norm=x=>String(x||'').toLowerCase().replace(/[^a-z0-9]/g,'');
                if(document.querySelector('#EIN')?.value.replace(/\D/g,'')!==ein
                   ||document.querySelector('#ddlEINFilterCriteriaList')?.value!=='3')return null;
                const rows=[...document.querySelectorAll('tr')].filter(r=>r.querySelectorAll('td').length===10);
                const hits=rows.filter(r=>{
                    const c=[...r.querySelectorAll('td')].map(x=>x.innerText.trim());
                    const links=[...r.querySelectorAll('a')].map(a=>(a.getAttribute('onclick')||'').match(/OpenDetailsLink\('([^']+)','(\d+)'\)/i)).filter(Boolean);
                    return c[2].replace(/\D/g,'')===ein && norm(c[0])===norm(name)
                      &&c[8].toLowerCase()==='yes'&&links.length===1&&links[0][2]===id;
                });
                if(hits.length!==1)return null;
                return {ein,id,name: hits[0].querySelector('td').innerText.trim(),row:hits[0].innerText};
            }''',{'ein':run.ein,'id':str(detail_ref['id']),'name':detail_ref.get('registryName','')})
        proof=selected()
        if not proof:return
        run.page(page)
        if selected()!=proof or page.url not in {url,url+'#results'}:
            del run.documents[before:];return
        if not hasattr(run,'oh_selected_grid_images'):run.oh_selected_grid_images={}
        for doc in run.documents[before:]:
            if doc[2]=='image':run.oh_selected_grid_images[hashlib.sha256(doc[1]).hexdigest()]=proof
        run.oh_pending_selected_grid=list(run.documents[before:])
        del run.documents[before:]
    except Exception:
        del run.documents[before:]
        run.errors.append('OH_selected_grid_capture_unavailable')


def publish_oh_selected_grid(result):
    """Publish the retained grid only after the existing fallback is selected."""
    run=CURRENT.get()
    if run is None or run.state!='OH':return
    row=result if isinstance(result,dict) else vars(result)
    pending=getattr(run,'oh_pending_selected_grid',[])
    run.oh_pending_selected_grid=[]
    for doc in pending:
        if doc[2]=='image' and oh_selected_grid_bound(run,doc[1],doc[0],row):
            run.documents.append(doc)


def oh_selected_grid_bound(run,raw,url,row):
    """Only the existing exact-EIN compliance fallback may use this image."""
    proof=getattr(run,'oh_selected_grid_images',{}).get(hashlib.sha256(raw).hexdigest())
    return bool(proof and url in {
        'https://charitableregistration.ohioago.gov/Charities/ResearchCharities',
        'https://charitableregistration.ohioago.gov/Charities/ResearchCharities#results'}
        and row.get('success') is True and row.get('status')=='Current'
        and row.get('raw_status_text')=='Ohio exact-EIN search: In Compliance: Yes | Detail page unavailable'
        and proof['ein']==run.ein==digits(row.get('ein',''))
        and proof['id']==str(row.get('matched_registry_identifier',''))
        and key(proof['name'])==key(row.get('matched_registry_name','')))


def me_detail_name_bound(name,text,identifier):
 """Maine moves its indexed trailing ', THE' to the original detail heading."""
 def canonical(value):
  value=re.sub(r',\s*THE\s*$','',str(value),flags=re.I)
  value=re.sub(r'^THE\s+','',value.strip(),flags=re.I)
  return re.sub(r'[^a-z0-9]','',value.lower())
 headings=re.findall(r'CHARITABLE SOLICITATIONS\s+(.*?)\s+CHARITABLE ORGANIZATION\s+License Number:',text,re.S|re.I)
 return bool(re.fullmatch(r'CO\d+',str(identifier),re.I) and len(headings)==1
             and canonical(name) and canonical(headings[0])==canonical(name)
             and re.search(r'License\s+Number:\s*'+re.escape(identifier)+r'(?!\w)',text,re.I))


class CaptureRun:
    def __init__(self,name,ein,state):
        self.name,self.ein,self.state=name,digits(ein),state
        self.run_id=secrets.token_hex(16);self.documents=[];self.errors=[];self.capture_ms=0
        self.provenance={};self.source_detail_hints={};self.source_search_hint=None;self.validated_negative_visual_urls=set();self.visual_adapter_facts=[];self.lookup_started=time.perf_counter();self.source_clock_calls=0;self.source_wall_ms=0;self.source_only_ms=0;self.source_pdf_extract_ms=0
    def remember_detail(self,identifier,name,url):
        try:
            if not identifier or not name or len(self.source_detail_hints)>=12:return
            self.source_detail_hints[str(identifier)]={'name':str(name),'url':public_url(url,self.state)}
        except (ValueError,UnicodeError):return
    def remember_search(self,name,url):
        try:
            approved=public_url(url,self.state)
            u=urlsplit(approved);pairs=parse_qsl(u.query,keep_blank_values=True)
            values=dict(pairs)
            if (self.state!='WI' or u.path!='/ice/berg/Registration/OrgCredentialSearchResults.aspx'
                or len(pairs)!=3 or set(values)!={'CredentialType','FirmName','LicenseNumber'}
                or values['CredentialType']!='800' or values['LicenseNumber'] or values['FirmName']!=name):return
            self.source_search_hint={'name':str(name),'url':approved}
        except (ValueError,UnicodeError):return
    def source_clock(self):
        return (time.perf_counter(),self.capture_ms,
                sum(f.get('total_ms',0) for f in self.visual_adapter_facts),
                sum(f.get('capture_ms',0) for f in self.visual_adapter_facts))
    def source_done(self,mark):
        wall=(time.perf_counter()-mark[0])*1000
        adapter=sum(f.get('total_ms',0) for f in self.visual_adapter_facts)-mark[2]
        adapter_pixels=sum(f.get('capture_ms',0) for f in self.visual_adapter_facts)-mark[3]
        other_capture=max(0,self.capture_ms-mark[1]-adapter_pixels)
        self.source_clock_calls+=1;self.source_wall_ms+=wall
        self.source_only_ms+=max(0,wall-adapter-other_capture)
    def __enter__(self):
        from deployment.workflow_observation import Observation,ACTIVE
        self.observation=Observation(self.run_id,self.state,DEADLINE.get())
        self.observation_token=ACTIVE.set(self.observation)
        self.token=CURRENT.set(self);return self
    def __exit__(self,*args):
        from deployment.workflow_observation import ACTIVE
        self.observation.release();ACTIVE.reset(self.observation_token);CURRENT.reset(self.token)
    def document(self,url,raw,kind='source_text',public_text='',note=''):
        try:
            url=public_url(url,self.state)
            if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:return trace_return('deployment/state_snapshots.py:document:413:70:return',None)
            while self.documents and (len(self.documents)>=8 or sum(len(d[1]) for d in self.documents)+len(raw)>6_000_000):
                self.documents.pop(0)
            self.documents.append((url,raw,kind,public_text,time.time(),note or workflow_call('deployment/state_snapshots.py:document:416:80:get',self.provenance.get,locals(), url,'')))
        except (ValueError,UnicodeError):return trace_return('deployment/state_snapshots.py:document:417:41:return',None)
    def page(self,page):
        """Capture before its existing context closes; do not navigate or scroll."""
        started=time.perf_counter()
        ma_capture_end=min(DEADLINE.get()-1,getattr(self,'page_capture_stop',float('inf'))-1,time.monotonic()+8) if self.state=='MA' else None
        def ma_timeout(seconds):
            remaining=ma_capture_end-time.monotonic()
            if remaining<=0:raise TimeoutError('MA_capture_allowance_exhausted')
            return max(1,int(min(seconds,remaining)*1000))
        observation=None
        if self.state=='CO':
            observation={'phase':'admission','outcome':'pending'}
            self.visual_adapter_facts.append({'adapter':'CO-existing-page-observation','page_capture_observations':[observation]})
        if self.state=='SC':
            facts=[f for f in self.visual_adapter_facts if workflow_call('deployment/state_snapshots.py:page:426:59:get',f.get,locals(), 'adapter')=='SC-selected-original-detail' and workflow_call('deployment/state_snapshots.py:page:426:111:get',f.get,locals(), 'phase')=='capture']
            if facts:
                observation={'phase':'admission','outcome':'pending'}
                facts[-1].setdefault('page_capture_observations',[]).append(observation)
        def observed(phase):
            if observation is not None:observation.update(phase=phase,elapsed_seconds=round(time.perf_counter()-started,6))
        try:
            if time.monotonic()+3>=workflow_call('deployment/state_snapshots.py:page:433:35:get',DEADLINE.get,locals()):
                self.errors.append('capture_skipped_near_task_deadline');return trace_return('deployment/state_snapshots.py:page:434:73:return',None)
            if self.state=='AK':
                # Wait for the original site's view transition, never hide it.
                try:
                    workflow_call('deployment/state_snapshots.py:page:438:20:wait_for_function',page.wait_for_function,locals(), """async()=>{
                        const url=location.href,text=document.body.innerText;
                        await new Promise(resolve=>setTimeout(resolve,200));
                        return location.href===url && document.body.innerText===text;
                    }""",timeout=700)
                except Exception:
                    self.errors.append('source_view_not_stable');return trace_return('deployment/state_snapshots.py:page:444:65:return',None)
            if self.state=='WA':
                try:
                    if not wa_painted_result_ready(page):
                        self.errors.append('WA_source_overlay_visible');return trace_return('deployment/state_snapshots.py:page:448:72:return',None)
                except Exception:
                    self.errors.append('WA_source_overlay_not_cleared');return trace_return('deployment/state_snapshots.py:page:450:72:return',None)
            observed('public_url')
            original_url=page.url
            url=public_url(original_url,self.state)
            observed('read_text')
            text=workflow_call('deployment/state_snapshots.py:page:455:17:inner_text',page.inner_text,locals(), 'body',timeout=ma_timeout(2) if self.state=='MA' else 400)[:20000]
            ak_empty=ak_empty_controls(page,self,text) if self.state=='AK' else None
            observed('read_dimensions')
            size=workflow_call('deployment/state_snapshots.py:page:458:17:evaluate',page.locator('body').evaluate,locals(),
                '(b)=>({width:Math.max(b.scrollWidth,document.documentElement.scrollWidth,innerWidth),height:Math.max(b.scrollHeight,document.documentElement.scrollHeight,innerHeight)})',timeout=ma_timeout(1) if self.state=='MA' else 300)
            if not size or size['width']<=0 or size['height']<=0 or size['width']*size['height']>MAX_PIXELS:
                self.errors.append('source_page_exceeds_capture_bound');return trace_return('deployment/state_snapshots.py:page:461:72:return',None)
            observed('screenshot')
            raw=workflow_call('deployment/state_snapshots.py:page:463:16:screenshot',page.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=(ma_timeout(5) if self.state=='MA' else max(1,int(min(5.0,DEADLINE.get()-time.monotonic()-1,getattr(self,'page_capture_stop',float('inf'))-time.monotonic()-1)*1000)) if self.state in {'AK','OK','ME'} or (self.state in {'WV','RI'} and hasattr(self,'page_capture_stop')) else 1000))
            if self.state=='WA' and workflow_call('deployment/state_snapshots.py:page:464:36:is_visible',page.locator('#loaderDiv').is_visible,locals()):
                self.errors.append('WA_source_overlay_returned_during_capture');return trace_return('deployment/state_snapshots.py:page:465:80:return',None)
            observed('post_capture_binding')
            if page.url!=original_url or workflow_call('deployment/state_snapshots.py:page:467:41:inner_text',page.inner_text,locals(), 'body',timeout=ma_timeout(2) if self.state=='MA' else 400)[:20000]!=text:
                self.errors.append('source_page_changed_during_capture');return trace_return('deployment/state_snapshots.py:page:468:73:return',None)
            if ak_empty is not None:
                if ak_empty_controls(page,self,text)!=ak_empty:
                    self.errors.append('AK_empty_criteria_changed_during_capture');return trace_return('deployment/state_snapshots.py:page:471:83:return',None)
                bindings=getattr(self,'ak_empty_image_bindings',None)
                if bindings is None:self.ak_empty_image_bindings={}
                self.ak_empty_image_bindings[hashlib.sha256(raw).hexdigest()]=ak_empty
            workflow_call('deployment/state_snapshots.py:page:475:12:document',self.document,locals(), url,raw,'image',text,note=('Original Alaska empty search view for displayed year '+ak_empty['year']+'. This one image does not by itself establish all yearly/name searches.' if ak_empty else ''))
        except Exception as exc:
            self.errors.append('source_page_capture_unavailable')
            if observation is not None:observation.update(outcome='failed',error_type=type(exc).__name__,error_summary=str(exc)[:800])
        finally:
            elapsed=time.perf_counter()-started;self.capture_ms+=elapsed*1000
            if observation is not None:
                observation['total_seconds']=round(elapsed,6)
                if observation['outcome']=='pending':observation['outcome']='returned'
    def finish(self,result):
        if not isinstance(result,dict):return trace_return('deployment/state_snapshots.py:finish:485:39:return',(result))
        data=dict(result);assets=[]
        review_rows=workflow_call('deployment/state_snapshots.py:finish:487:20:get',(workflow_call('deployment/state_snapshots.py:finish:487:21:get',data.get,locals(), '_worker_identity_review') or {}).get,locals(), 'records',[])
        if not review_rows:
            review_rows=workflow_call('deployment/state_snapshots.py:finish:489:24:get',(workflow_call('deployment/state_snapshots.py:finish:489:25:get',data.get,locals(), 'identity_review') or {}).get,locals(), 'candidates',[])
        records=[data]+[{**row,'state':self.state,'ein':self.ein} for row in review_rows]
        for row in records[:12]:
            identifier=str(workflow_call('deployment/state_snapshots.py:finish:492:27:get',row.get,locals(), 'matched_registry_identifier') or workflow_call('deployment/state_snapshots.py:finish:492:69:get',row.get,locals(), 'identifier') or '')
            name=str(workflow_call('deployment/state_snapshots.py:finish:493:21:get',row.get,locals(), 'matched_registry_name') or workflow_call('deployment/state_snapshots.py:finish:493:57:get',row.get,locals(), 'name') or '')
            negative=completed_negative_result(row)
            # Only source visuals are eligible; no text/JSON substitute is permitted.
            ordered=sorted((d for d in self.documents if d[2] in {'image','image_pages','source_pdf'}),key=lambda d:({'image':3,'image_pages':3,'source_pdf':2}[d[2]],d[4]),reverse=True)
            if self.state=='MA' and not negative:
                from deployment.ma_view_more_evidence import select
                ordered=select(self,ordered,row)
            for url,raw,kind,public_text,stamp,source_note in ordered:
                text=public_text
                matched=(self.ein in digits(text) or bool(name and (source_name_present(name,text,self.state) if kind=='source_pdf' else key(name) in key(text))))
                if self.state=='ME' and not negative and me_detail_name_bound(name,text,identifier):matched=True
                if identifier:matched=matched and bool(re.search(r'(?<![\w])'+re.escape(identifier)+r'(?![\w])',text+' '+url,re.I))
                if self.state=='OH' and not negative and oh_selected_grid_bound(self,raw,url,row):matched=True
                if self.state=='AK' and not negative:
                    cycle_image=getattr(self,'ak_selected_cycle_images',{}).get(hashlib.sha256(raw).hexdigest())
                    if cycle_image:
                        cycle=re.search(r'\bRegistration Cycle:\s*(20\d{2})\b',str(row.get('raw_status_text') or ''))
                        matched=matched and bool(cycle and int(cycle.group(1))==cycle_image['year'] and cycle_image['ein']==self.ein and (not name or key(name)==key(cycle_image['name'])))
                if negative:
                    matched=bool(re.search(r'no\s+(?:matching\s+)?(?:records?|results?)|0\s+results',text,re.I))
                    if self.state=='DC':matched=hashlib.sha256(raw).hexdigest() in getattr(self,'dc_validated_empty_images',set())
                    if self.state=='WA':matched='No Value Found' in text and url=='https://ccfs.sos.wa.gov/#/cftSearch'
                    if self.state=='AK':matched='There are no charitable organizations.' in text and hashlib.sha256(raw).hexdigest() in getattr(self,'ak_empty_image_bindings',{})
                    if self.state=='CA':matched=bool(re.search(r'\bNo Data\b',text)) and hashlib.sha256(raw).hexdigest() in getattr(self,'ca_validated_empty_images',set())
                    if self.state=='VA':matched='No Data' in text and hashlib.sha256(raw).hexdigest() in getattr(self,'va_validated_empty_images',set())
                    if self.state=='NJ':matched='No records to show' in text and hashlib.sha256(raw).hexdigest() in getattr(self,'nj_validated_empty_images',set())
                    if self.state=='WI' and url in self.validated_negative_visual_urls:matched=bool(re.search(r'(?:There are )?no query results',text,re.I))
                    if self.state=='CT' and url in self.validated_negative_visual_urls:matched=bool(re.search(r'Showing\s+0\s+result\(s\)\.',text,re.I))
                    if self.state=='HI' and url in self.validated_negative_visual_urls:matched='The charitable organization you entered is not registered in our system.' in text and hashlib.sha256(raw).hexdigest() in getattr(self,'hi_validated_empty_images',set())
                    if self.state=='FL':matched=url in self.validated_negative_visual_urls and ('No result found for '+self.name) in text and hashlib.sha256(raw).hexdigest() in getattr(self,'fl_validated_empty_images',set())
                    if self.state=='OH':matched='No organizations found' in text and hashlib.sha256(raw).hexdigest() in getattr(self,'oh_validated_empty_images',set())
                    if self.state=='MI' and getattr(self,'mi_negative_visual_guard',False):matched='No records found for your search criteria' in text and hashlib.sha256(raw).hexdigest() in getattr(self,'mi_validated_empty_images',set())
                    if self.state=='RI':matched=url in self.validated_negative_visual_urls and 'No search results were found. Please refine your search criteria and try again.' in text and hashlib.sha256(raw).hexdigest() in getattr(self,'ri_validated_empty_images',set())
                if re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):continue
                if not matched:continue
                asset=workflow_call('deployment/state_snapshots.py:finish:519:22:asset_for',asset_for,locals(), raw,kind=kind,state=self.state,ein=self.ein,run_id=self.run_id,source_url=url,
                    organization_name=self.name,identifier='@completed-search' if negative else identifier,
                    record_name=name,public_text=public_text[:20000],capture_note='Saved during this lookup; no new registry search occurs when this PDF is opened. '+source_note)
                asset['captured_at']=stamp;assets.append(asset);break
        if assets:data['_worker_source_archives']=assets
        data['evidence_capture_ms']=round(self.capture_ms,2)
        data['evidence_capture']='captured' if assets else 'unavailable'
        visual_ms=sum(workflow_call('deployment/state_snapshots.py:finish:526:22:get',f.get,locals(), 'total_ms',0) for f in self.visual_adapter_facts)
        data['evidence_metrics']={
            'lookup_and_visual_ms':round((time.perf_counter()-self.lookup_started)*1000,2),
            'capture_ms':round(self.capture_ms,2),'visual_adapter_ms':round(visual_ms,2),
            'status_lookup_excluding_inline_visual_ms':round(self.source_only_ms,2) if self.source_clock_calls else None,
            'source_call_wall_ms':round(self.source_wall_ms,2) if self.source_clock_calls else None,
            'source_pdf_extract_ms':round(self.source_pdf_extract_ms,2),
            'archive_ms':0,'documents_collected':len(self.documents),
            'visual_documents':sum(d[2] in {'image','image_pages','source_pdf'} for d in self.documents),
            'bound_original_assets':len(assets),'capture_errors':list(dict.fromkeys(self.errors))[:12],
            'visual_adapters':[dict(f) for f in self.visual_adapter_facts[:2]],
            'missing_stage':('' if assets else 'record_binding' if any(d[2] in {'image','image_pages','source_pdf'} for d in self.documents)
                else 'capture' if self.errors else 'source_visual_not_collected')}
        if getattr(self,'observation',None):data['workflow_observation']=self.observation.export()
        if self.state in {'WI','DC'} and not assets:
            try:
                from deployment.desktop_source_evidence import retained_request
                request=retained_request(self,data)
                if request:data['_worker_desktop_evidence']=request
            except Exception:self.errors.append('desktop_evidence_request_unavailable')
        from deployment.search_history import finish_worker_history
        return trace_return('deployment/state_snapshots.py:finish:546:8:return',(finish_worker_history(self,data)))

class ContextCaptureProxy:
    def __init__(self,context):
        self._context=context;self._captured=False;self._closed=False
        run=CURRENT.get()
        if run:
            from deployment.search_observation import observe_browser_context
            observe_browser_context(context,run)
            from deployment.workflow_observation import observe_context
            observe_context(context,getattr(run,'observation',None))
    def __getattr__(self,key):return getattr(self._context,key)
    def capture(self):
        run=workflow_call('deployment/state_snapshots.py:capture:557:12:get',CURRENT.get,locals())
        if run and not self._closed and not self._captured:
            self._captured=True
            try:
                for page in self._context.pages[:3]:workflow_call('deployment/state_snapshots.py:capture:561:52:page',run.page,locals(), page)
            except Exception:run.errors.append('source_context_capture_unavailable')
            # AK's route hash can change from the previous result view during
            # its first photograph. One fresh read/capture only, no re-search.
            if run.state=='AK' and run.errors and run.errors[-1]=='source_page_changed_during_capture':
                try:
                    if self._context.pages:workflow_call('deployment/state_snapshots.py:capture:567:43:page',run.page,locals(), self._context.pages[0])
                except Exception:run.errors.append('source_context_recapture_unavailable')
    def close(self,*args,**kwargs):
        workflow_call('deployment/state_snapshots.py:close:570:8:capture',self.capture,locals())
        value=workflow_call('deployment/state_snapshots.py:close:571:14:close',self._context.close,locals(), *args,**kwargs);self._closed=True
        return trace_return('deployment/state_snapshots.py:close:572:8:return',(value))

class BrowserCaptureProxy:
    def __init__(self,browser):self._browser=browser;self._owned_contexts=[]
    def __getattr__(self,key):return getattr(self._browser,key)
    def new_context(self,*args,**kwargs):
        context=ContextCaptureProxy(workflow_call('deployment/state_snapshots.py:new_context:578:36:new_context',self._browser.new_context,locals(), *args,**kwargs))
        self._owned_contexts.append(context);return trace_return('deployment/state_snapshots.py:new_context:579:45:return',(context))
    def close(self,*args,**kwargs):
        # Never inspect other contexts in a borrowed/shared browser.
        for context in self._owned_contexts:workflow_call('deployment/state_snapshots.py:close:582:44:capture',context.capture,locals())
        return trace_return('deployment/state_snapshots.py:close:583:8:return',(workflow_call('deployment/state_snapshots.py:close:583:15:close',self._browser.close,locals(), *args,**kwargs)))


def nm_detail_snapshot_bound(record,query,evidence,url,text,identifier):
    """Accept only this observed NM FEIN detail, including its display hyphen."""
    if (record.get('state')!='NM' or query.get('state')!='NM'
            or query.get('operation')!='detail' or not re.fullmatch(r'\d{9}',identifier)
            or digits(record.get('ein'))!=identifier or not isinstance(evidence,dict)
            or evidence.get('complete') is not True or evidence.get('ein')!=identifier
            or not query.get('name') or key(evidence.get('name'))!=key(query['name'])):
        return False
    parsed=urlsplit(url)
    feins=[v for k,v in parse_qsl(parsed.query,keep_blank_values=True) if k.casefold()=='fein']
    return (parsed.scheme=='https' and parsed.hostname=='secure.nmdoj.gov'
            and parsed.path=='/CharitySearch/CharityDetail.aspx' and len(feins)==1
            and re.fullmatch(r'\d{2}-?\d{7}',feins[0]) is not None
            and digits(feins[0])==identifier
            and re.search(r'(?<!\d)'+identifier[:2]+r'-?'+identifier[2:]+r'(?!\d)',text) is not None)



def il_completed_empty_snapshot(record,query,evidence,url,text):
    """Called after the unchanged IL cleaner has certified pagination."""
    source=urlsplit(url)
    if (record.get('state')!='IL' or query.get('state')!='IL'
        or set(query) not in ({'state','ein'},{'state','orgName'})
        or not (query.get('ein') or str(query.get('orgName') or '').strip())
        or evidence!={'rows':[]} or source.scheme!='https'
        or source.hostname!='charitable.illinoisattorneygeneral.gov'
        or source.path!='/search' or source.query or source.fragment
        or not isinstance(text,str)
        or re.search(r'verify you are human|user validation required|just a moment|access denied',text,re.I)):
        return False
    observed=' '.join(text.split())
    return ('Charities Search' in observed and bool(re.search(
        r'(?:CO #\s+Name\s+Address\s+City\s+State\s+Zip|Summary)\s+No Records Available\s+(?:0\s+)?No items to display(?:\s|$)',observed)))


def ga_completed_empty_grid_snapshot(record,query,evidence,url,text):
    """The existing cleaner has already verified complete GA search pagination."""
    source=urlsplit(url)
    return (record.get('state')=='GA' and query.get('state')=='GA'
        and 'identifier' not in query and isinstance(query.get('orgName'),str)
        and bool(query['orgName'].strip()) and evidence=={'rows':[]}
        and source.scheme=='https' and source.hostname=='verify.sos.ga.gov'
        and source.path=='/verification/SearchResults.aspx' and not source.query
        and not source.fragment and isinstance(text,str)
        and text.strip().startswith('Search Results')
        and bool(re.search(r'(?:Full Name\s+License Number\s+Profession\s+License Type\s+License Status\s+City\s+State|Results\s+Full Name\s+License #\s+Profession\s+License Type\s+Status\s+Address)\s+1\s*\Z',text)))


def ga_completed_results_snapshot(record,query,evidence,url,text):
    """Keep a validated original GA results page for a negative lookup.

    Returned unrelated rows do not turn it into an empty search or a positive
    registration. The signed query/cleaner boundary remains authoritative.
    """
    if ga_completed_empty_grid_snapshot(record,query,evidence,url,text):return True
    source=urlsplit(url)
    if (record.get('state')!='GA' or query.get('state')!='GA' or 'identifier' in query
        or not isinstance(query.get('orgName'),str) or not query['orgName'].strip()
        or not isinstance(evidence,dict) or set(evidence)!={'rows'}
        or not isinstance(evidence['rows'],list) or not 0<len(evidence['rows'])<=100
        or source.scheme!='https' or source.hostname!='verify.sos.ga.gov'
        or source.path!='/verification/SearchResults.aspx' or source.query or source.fragment
        or not isinstance(text,str) or not text.strip().startswith('Search Results')
        or re.search(r'verify you are human|user validation required|just a moment|access denied',text,re.I)):
        return False
    if not re.search(r'Full Name\s+License (?:#\s+Profession\s+License Type\s+Status\s+Address|Number\s+Profession\s+License Type\s+License Status\s+City\s+State)',text):return False
    return any(isinstance(row,dict) and isinstance(row.get('name'),str) and row['name'].strip()
        and isinstance(row.get('identifier'),str) and row['identifier'].strip()
        and key(row['name']) in key(text)
        and re.search(r'(?<![\w])'+re.escape(row['identifier'])+r'(?![\w])',text,re.I)
        for row in evidence['rows'])


def nc_completed_empty_snapshot(record,query,evidence,url,text):
    """Require this issued query's original NC zero-result heading."""
    source=urlsplit(url)
    if (record.get('state')!='NC' or query.get('state')!='NC'
        or query.get('operation')!='search' or not isinstance(evidence,dict)
        or evidence.get('query')!=query or evidence.get('complete') is not True
        or evidence.get('state')!='NC' or evidence.get('verification_pending') is not False
        or type(evidence.get('total')) is not int or evidence['total']!=0
        or evidence.get('rows')!=[] or not isinstance(query.get('name'),str)
        or not query['name'].strip() or not isinstance(text,str)
        or source.scheme!='https' or source.hostname!='www.sosnc.gov'
        or source.path!='/online_services/search/Charities_Results'
        or source.query or source.fragment
        or re.search(r'verify you are human|user validation required|just a moment|access denied',text,re.I)):
        return False
    mode={None:'Starting With','STARTS_WITH':'Starting With',
          'ALL_WORDS':'All Words','EXACT_MATCH':'Exact'}.get(query.get('search_mode'))
    if mode is None:return False
    observed=' '.join(text.split())
    expected='Words: '+mode+' Organization Name '+' '.join(query['name'].split())+' Search Time '
    return bool(re.search(r'\bRecords Found:\s*0(?:\s|$)',observed)
                and expected.casefold() in observed.casefold())

def nc_completed_results_snapshot(record,query,evidence,url,text):
    """A bound results list may contain unrelated rows on a negative check.

    This is an original results page, not a declaration that it was empty.
    Selected registrations still require their own credential-bound evidence.
    """
    if nc_completed_empty_snapshot(record,query,evidence,url,text):return True
    source=urlsplit(url)
    if (record.get('state')!='NC' or query.get('state')!='NC'
        or query.get('operation')!='search' or not isinstance(evidence,dict)
        or evidence.get('query')!=query or evidence.get('complete') is not True
        or evidence.get('state')!='NC' or evidence.get('verification_pending') is not False
        or type(evidence.get('total')) is not int or not 0<evidence['total']<=100
        or not isinstance(evidence.get('rows'),list) or len(evidence['rows'])!=evidence['total']
        or not isinstance(query.get('name'),str) or not query['name'].strip()
        or not isinstance(text,str) or source.scheme!='https' or source.hostname!='www.sosnc.gov'
        or source.path!='/online_services/search/Charities_Results' or source.query or source.fragment
        or re.search(r'verify you are human|user validation required|just a moment|access denied',text,re.I)):
        return False
    mode={None:'Starting With','STARTS_WITH':'Starting With','ALL_WORDS':'All Words','EXACT_MATCH':'Exact'}.get(query.get('search_mode'))
    if mode is None:return False
    observed=' '.join(text.split())
    heading='Words: '+mode+' Organization Name '+' '.join(query['name'].split())+' Search Time '
    if heading.casefold() not in observed.casefold() or not re.search(r'\bRecords Found:\s*'+str(evidence['total'])+r'(?:\s|$)',observed):return False
    # Require at least one returned registration to be visible in the image's
    # bound original text. Do not archive an unrelated page sharing a heading.
    return any(isinstance(row,dict) and str(row.get('name') or row.get('CSL Legal Name') or row.get('Organization Name') or '').strip()
        and key(row.get('name') or row.get('CSL Legal Name') or row.get('Organization Name')) in key(text)
        for row in evidence['rows'])

def al_completed_results_snapshot(record,query,evidence,url,text):
    """Preserve an actual complete AL results grid for a settled negative.

    Rows may be unrelated. This marker is search evidence, never an empty-grid
    assertion or a positive identity. Existing query/capture binding still applies.
    """
    if (record.get('state')!='AL' or query.get('state')!='AL'
        or query.get('operation')!='search' or set(query)!={'state','operation','name'}
        or not isinstance(query.get('name'),str) or not query['name'].strip()
        or not isinstance(evidence,dict) or evidence.get('state')!='AL'
        or evidence.get('query')!=query or evidence.get('complete') is not True
        or evidence.get('verification_pending') is not False
        or type(evidence.get('total')) is not int or not 0<evidence['total']<=50
        or not isinstance(evidence.get('rows'),list) or len(evidence['rows'])!=evidence['total']
        or not isinstance(text,str) or len(text)>20000):return False
    source=urlsplit(url)
    if (source.scheme!='https' or source.hostname!='ago.igovsolution.net'
        or source.path!='/online/Lookups/Business.aspx' or source.query or source.fragment
        or re.search(r'no records found|verification failed|invalid verification|user validation required|access denied',text,re.I)):
        return False
    headers=['Name','License/Registration#','Status','Registration Type','Issued Date','Expiration Date','Address','City','State','Zip','Print']
    if evidence.get('headers')!=headers:return False
    normalized=' '.join(text.split())
    if ('Business Lookup Search' not in normalized
        or not re.search(r'Records\s*:\s*1\s+to\s+'+str(evidence['total'])+r'\s+of\s+'+str(evidence['total'])+r'\b',normalized)):
        return False
    for row in evidence['rows']:
        if (not isinstance(row,list) or len(row)!=len(headers)
            or not all(isinstance(cell,str) for cell in row)
            or not row[0].strip() or not re.fullmatch(r'(?:AL\d{2}-\d+|EC-\d+)',row[1])
            or key(row[0]) not in key(text) or row[1] not in text):return False
    return True


def il_selected_detail_snapshot(query,evidence,url,text):
    """Bind the validated detail body to its original photographed IL modal."""
    try:
        source=urlsplit(url)
        identifier=query.get('identifier','')
        body=evidence.get('body')
        if (source.hostname!='charitable.illinoisattorneygeneral.gov' or source.path!='/search'
                or source.query or source.fragment or not re.fullmatch(r'\d{8}',identifier)
                or not isinstance(body,str) or not 1<=len(body)<=60000
                or not isinstance(text,str) or len(text)>20000):return None
        lines=[' '.join(line.split()) for line in body.splitlines() if line.strip()]
        shown=[' '.join(line.split()) for line in text.splitlines() if line.strip()]
        if not lines or re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):return None
        fields={}
        for label in ['CO Number:','FEIN:','Status:','Registration Date:','Annual Report Due Date:']:
            values=[line for line in lines if line.startswith(label)]
            if len(values)>1 or (label!='Annual Report Due Date:' and len(values)!=1):return None
            if values:
                if shown.count(values[0])!=1:return None
                fields[label]=values[0][len(label):].strip()
        if (fields['CO Number:']!=identifier or len(digits(fields['FEIN:']))!=9
                or not fields['Status:'] or shown.count(lines[0])!=1):return None
        return identifier,lines[0]
    except (AttributeError,TypeError,ValueError,KeyError):return None


def _connector_archive(record,payload,query,evidence):
    """Called only after the original query ID and source schema were validated."""
    incoming=payload.get('state_snapshot')
    if not incoming or STORE is None:return
    started=time.perf_counter()
    try:
        if incoming.get('query')!=query:return
        stamp=incoming.get('captured_at')
        if type(stamp) not in (int,float) or stamp<record['issued']-60 or stamp>time.time()+60:return
        run_id=record.setdefault('source_archive_run_id',secrets.token_hex(16))
        url=public_url(incoming.get('source_url',''),record['state'])
        if record['state']=='NY' and query.get('orgID'):
            if urlsplit(url).path.rstrip('/')!='/RegistrySearch/'+query['orgID']:return
        il_detail=record['state']=='IL' and 'identifier' in query
        ga_detail=record['state']=='GA' and 'identifier' in query
        if ga_detail:
            source=urlsplit(url)
            keys=[v for k,v in parse_qsl(source.query,keep_blank_values=True) if k=='result']
            if (source.hostname!='verify.sos.ga.gov' or source.path!='/verification/Details.aspx'
                    or len(keys)!=1
                    or not re.fullmatch(r'[a-f0-9-]{36}',keys[0])):return
        if record['state']=='NC' and query.get('operation')=='detail':
            fields=evidence.get('fields') if isinstance(evidence,dict) else None
            identifier=str(query.get('identifier') or '')
            profile=urlsplit(url)
            application=re.fullmatch(r'NCAPP-(\d+)',identifier)
            if (not isinstance(fields,dict) or url!=query.get('url')
                    or profile.hostname!='www.sosnc.gov'
                    or not re.fullmatch(r'/online_services/search/charities_profile/\d+',profile.path)
                    or fields.get('profile_url')!=url
                    or (application and (profile.path.rsplit('/',1)[-1]!=application[1] or fields.get('Registration #')))
                    or (not application and fields.get('Registration #')!=identifier)):
                return
        text=incoming.get('public_text','')
        if not isinstance(text,str) or len(text)>20000:return
        rows=[]
        def walk(value):
            if len(rows)>1000:return
            if isinstance(value,list):
                for item in value:walk(item)
            elif isinstance(value,dict):
                name=next((str(value[k]) for k in ('Name','CSL Legal Name','Entity Name','Organization Name','Business Name','orgName','name','full_name') if value.get(k)), '')
                ident=next((str(value[k]) for k in ('identifier','License','License/Registration#','Registration/License#','Registration #','CO Number','NV Business ID','orgID','license_no') if value.get(k)), '')
                if name:rows.append((ident,name))
                for field,item in value.items():
                    # Request query names are not registry rows. In particular,
                    # they must not hide an explicit completed empty receipt.
                    if field!='query' and isinstance(item,(dict,list)):walk(item)
        walk(evidence)
        if il_detail:
            selected=il_selected_detail_snapshot(query,evidence,url,text)
            if selected is None:return
            rows=[selected]
        if record['state']=='AL' and isinstance(evidence,dict):
            headers=evidence.get('headers',[])
            for cells in evidence.get('rows',[]):
                if isinstance(cells,list) and len(cells)==len(headers):walk(dict(zip(headers,cells)))
        if (not rows and isinstance(evidence,dict) and evidence.get('complete') is True
                and evidence.get('total')==0 and evidence.get('rows')==[]
                and re.search(r'no\s+(?:matching\s+)?(?:records?|results?)|0\s+results',text,re.I)
                or not rows and il_completed_empty_snapshot(record,query,evidence,url,text)
                or not rows and ga_completed_empty_grid_snapshot(record,query,evidence,url,text)
                or not rows and nc_completed_empty_snapshot(record,query,evidence,url,text)):
            rows=[('@completed-search',record['organization_name'])]
        elif nc_completed_results_snapshot(record,query,evidence,url,text):
            # Archive once as search evidence. This marker cannot be selected
            # as a positive credential or used to manufacture a zero count.
            rows=[('@completed-search',record['organization_name']),*rows]
        if al_completed_results_snapshot(record,query,evidence,url,text):
            rows=[('@completed-search',''),*rows]
        if ga_completed_results_snapshot(record,query,evidence,url,text):
            # Search-only evidence must never compete with a numberless positive
            # registration by organization name. It is selected only for NR.
            rows=[('@completed-search',''),*rows]
        identifier=str(query.get('identifier') or query.get('orgID') or '')
        if identifier and rows:rows=[(identifier,rows[0][1])]
        for ident,name in rows[:12]:
            # Do not attach a screenshot of the last page to records only seen
            # on an earlier page, or a different record behind a detail dialog.
            if ident!='@completed-search':
                if key(name) not in key(text):continue
                application=re.fullmatch(r'NCAPP-(\d+)',ident) if record['state']=='NC' and query.get('operation')=='detail' else None
                bound_application=bool(application and query.get('url')==url and urlsplit(url).path=='/online_services/search/charities_profile/'+application[1])
                nm_detail=record['state']=='NM' and query.get('operation')=='detail'
                bound_nm=nm_detail_snapshot_bound(record,query,evidence,url,text,ident) if nm_detail else False
                if nm_detail and not bound_nm:continue
                if ident and ident not in text and ident not in url and not bound_application and not bound_nm:continue
            images=incoming.get('images')
            multi_source=il_detail or (record['state'] in {'TN','NV'} and query.get('operation')=='detail') or (record['state']=='NV' and query.get('operation')=='search' and ident=='@completed-search')
            multiple=multi_source and isinstance(images,list) and 2<=len(images)<=(8 if record['state']=='NV' and query.get('operation')=='detail' else 3)
            if 'images' in incoming and (not multiple or images[0]!=incoming.get('image')):raise ValueError('Invalid snapshot page binding')
            content=base64.b64encode(json.dumps(images).encode()).decode() if multiple else incoming['image']
            asset=dict(kind='image_pages' if multiple else 'image',state=record['state'],ein=record['ein'],run_id=run_id,
                source_url=url,captured_at=incoming['captured_at'],content=content,
                identifier=ident,record_name=name,organization_name=record['organization_name'],operation='detail' if il_detail else query.get('operation',''),
                public_text=text,query_id=str(payload['query_id']))
            ref=archive(asset,ein=record['ein'],state=record['state'],run_id=run_id)
            # The complete metadata stays in persistent storage. Continuations
            # carry short references, never images or repeated source URLs.
            record.setdefault('source_snapshots',[]).append({
                **{k:ref[k] for k in ('url','identifier','record_name','captured_at','ein','state')},
                'operation':'detail' if ga_detail or il_detail or (record['state']=='NY' and query.get('orgID')) else query.get('operation','')})
        refs=record.get('source_snapshots',[])
        if record['state']=='TN':refs=sorted(refs,key=lambda r:r.get('operation')=='detail')
        record['source_snapshots']=refs[-24:]
    except Exception:
        record['snapshot_capture_unavailable']=True
    finally:
        record['source_archive_ms']=round(record.get('source_archive_ms',0)+(time.perf_counter()-started)*1000,2)


def connector_archive(record,payload,query,evidence):
    """Passive, bounded IL empty-receipt observation; archive decisions unchanged."""
    observe=(isinstance(record,dict) and record.get('state')=='IL'
        and isinstance(query,dict) and query.get('state')=='IL'
        and 'identifier' not in query and evidence=={'rows':[]})
    if not observe:return _connector_archive(record,payload,query,evidence)
    before=len(record.get('source_snapshots',[]))
    try:
        return _connector_archive(record,payload,query,evidence)
    finally:
        try:
            incoming=payload.get('state_snapshot')
            detail={'build':'il-empty-archive-observation-1','query_id':str(payload.get('query_id',''))[:100],
                'ein':digits(record.get('ein','')),'store_ready':STORE is not None,
                'snapshot_present':isinstance(incoming,dict),'references_before':before,
                'references_after':len(record.get('source_snapshots',[])),
                'archive_exception':record.get('snapshot_capture_unavailable') is True}
            if isinstance(incoming,dict):
                text=incoming.get('public_text');stamp=incoming.get('captured_at')
                detail.update(query_same=incoming.get('query')==query,
                    stamp_valid=type(stamp) in (int,float) and record['issued']-60<=stamp<=time.time()+60,
                    text_length=len(text) if isinstance(text,str) else None,
                    image_characters=len(incoming.get('image','')) if isinstance(incoming.get('image'),str) else None,
                    image_pages=len(incoming['images']) if isinstance(incoming.get('images'),list) else None)
                try:
                    url=public_url(incoming.get('source_url',''),'IL')
                    detail.update(source_url=url,empty_guard=il_completed_empty_snapshot(record,query,evidence,url,text))
                    # Public registry text only; never image bytes, tokens or request credentials.
                    if incoming.get('query')==query and isinstance(text,str):
                        detail['public_text_sha256']=hashlib.sha256(text.encode()).hexdigest()
                        detail['public_text_excerpt']=text[:2600]
                except (TypeError,ValueError):detail['source_url_valid']=False
            print('CC_IL_EMPTY_ARCHIVE '+json.dumps(detail,separators=(',',':')),flush=True)
        except Exception:
            pass  # Observation cannot change optional evidence or registry outcomes.


def downloaded_record(master,result):
    """Preserve original matching PDF pages; spreadsheets are not screenshots."""
    run=CURRENT.get()
    if not run or run.state not in {'KS','KY','LA','NH','OR'}:return
    try:
        if time.monotonic()+3>=DEADLINE.get():return
        if run.state=='OR' and '/Charities/Charity/details' in result.get('source_url',''):return
        info=master.downloadable_data_info(run.state)
        if not info.get('usable'):return
        identifier=str(result.get('matched_registry_identifier') or '')
        name=str(result.get('matched_registry_name') or '')
        if not identifier and not name:return
        source_url=public_url(info['source_url'],run.state)
        run.provenance[source_url]='Source file downloaded: '+str(info.get('downloaded_at','unverified'))+'. Publisher date: '+str(info.get('source_date') or 'not stated by source')+'.'
        index_path=Path(__file__).with_name('source-page-indexes.json')
        index=json.loads(index_path.read_text()).get(run.state,{}) if index_path.exists() else {}
        for item in info['assets']:
            path=(master.BASE_DIR/item['path']).resolve()
            if not path.is_relative_to(master.BASE_DIR.resolve()):continue
            if path.suffix.lower()=='.pdf':
                # Use original page bytes from the source PDF, with no invented
                # HTML or screenshot. A page must contain this record's name.
                from pypdf import PdfReader,PdfWriter
                if index.get('source_sha256')!=item['sha256'] or index.get('asset')!=item['path']:continue
                ids=[digits(identifier)] if digits(identifier) in index['pages'] else [i for i,n in index.get('record_names',{}).items() if key(n)==key(name)]
                pages=sorted({p for i in ids for p in index['pages'].get(i,[])})[:12]
                if not pages:continue
                reader=PdfReader(path);writer=PdfWriter();texts=[]
                for number in pages:
                    page=reader.pages[number]
                    text=page.extract_text() or ''
                    if name and source_name_present(name,text,run.state) and (not identifier or identifier in text):
                        writer.add_page(page);texts.append(text)
                        if len(texts)>=3:break
                if texts:
                    out=io.BytesIO();writer.write(out)
                    original=out.getvalue()
                    if run.state in {'KY','NH'}:
                        # Excerpt only original publisher pixels. Any uncertain
                        # identity/layout or exhausted reserve keeps the full page.
                        try:
                            from deployment.original_table_excerpt import original_row_excerpt
                            excerpt=original_row_excerpt(original,run.state,identifier,name,min(DEADLINE.get()-1,time.monotonic()+(8 if run.state=='KY' else 3)))
                            if excerpt:
                                original,facts=excerpt
                                run.visual_adapter_facts.append({'adapter':run.state+'-original-row-excerpt','outcome':'captured','total_ms':round(facts['processing_seconds']*1000,2),'record_identifier':identifier})
                            else:run.visual_adapter_facts.append({'adapter':run.state+'-original-row-excerpt','outcome':'original_full_page_retained'})
                        except Exception as exc:
                            run.visual_adapter_facts.append({'adapter':run.state+'-original-row-excerpt','outcome':'original_full_page_retained','error_type':type(exc).__name__})
                    run.document(source_url,original,'source_pdf','\n'.join(texts)[:20000])
    except Exception:run.errors.append('downloaded_source_capture_unavailable')

def render_pdf(meta,raw):
    """Wrap original source pixels only; never redraw or brand the state page.

    Provenance stays in the archive metadata, separate from the source visual.
    Original state PDF page bytes are returned without a cover or overlays.
    """
    if meta['kind']=='source_pdf':return raw
    if meta['kind'] not in {'image','image_pages'}:
        raise ValueError('Snapshot requires actual page pixels or original state PDF pages')
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image
    # Keep the entire screenshot on one zoomable PDF page. Embedding preserves
    # the captured image pixels; page dimensions only control initial display.
    pages=[raw] if meta['kind']=='image' else [base64.b64decode(v,validate=True) for v in json.loads(raw)]
    out=io.BytesIO();c=canvas.Canvas(out,pageCompression=1)
    c.setTitle('Saved state page capture')
    for raw_page in pages:
        with Image.open(io.BytesIO(raw_page)) as im:width,height=im.size
        scale=min(612/width,14400/height);w,h=width*scale,height*scale
        c.setPageSize((w,h));c.drawImage(ImageReader(io.BytesIO(raw_page)),0,0,width=w,height=h);c.showPage()
    c.save()
    return out.getvalue()


def saved_pdf(ident,store=None):
    store=store or STORE
    if store is None:return None
    item=store.load(ident)
    if item is None:return None
    meta,raw,pdf=item
    if meta.get('kind') not in {'image','image_pages','source_pdf'}:raise ValueError('No original visual source was captured')
    if hashlib.sha256(raw).hexdigest()!=meta['source_sha256']:raise ValueError('Archived source integrity failed')
    if pdf is None:pdf=render_pdf(meta,raw);store.cache_pdf(ident,pdf)
    return meta,pdf

def serve(handler,include_body=True,store=None):
    path=urlsplit(handler.path).path
    if not path.startswith('/state-snapshots/'):return False
    match=re.fullmatch(r'/state-snapshots/([a-f0-9]{64})\.pdf',path)
    if not match:handler._send_json(404,{'error':'Saved state snapshot not found.'});return True
    try:value=saved_pdf(match[1],store)
    except Exception:handler._send_json(503,{'error':'Saved state snapshot is temporarily unavailable. No registry search was run.'});return True
    if value is None:handler._send_json(404,{'error':'No saved source capture is available. No registry search was run.'});return True
    meta,pdf=value;handler.send_response(200)
    for name,val in [('Content-Type','application/pdf'),('Content-Length',str(len(pdf))),
                     ('Content-Disposition','inline; filename="'+meta['state']+'-state-snapshot.pdf"'),
                     ('Cache-Control','private, max-age=86400'),('X-Content-Type-Options','nosniff')]:handler.send_header(name,val)
    handler.end_headers()
    if include_body:handler.wfile.write(pdf)
    return True


def wa_painted_result_ready(page, timeout_ms=1000):
    """The source removes its own animated overlay; never alter original pixels."""
    page.locator('#loaderDiv').wait_for(state='hidden',timeout=timeout_ms)
    return not page.locator('#loaderDiv').is_visible()
