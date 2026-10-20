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
    if (u.scheme != 'https' or u.hostname not in OFFICIAL_HOSTS.get(state, set())
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
    return {'url':snapshot_link(store.save(meta,raw)),'identifier':meta['identifier'],
            'record_name':meta['record_name'],'source_sha256':meta['source_sha256'],
            'source_url':meta['source_url'],'captured_at':meta['captured_at'],
            'kind':meta['kind'],'run_id':run_id,'ein':meta['ein'],'state':state}

def matching_reference(result, refs):
    """Never offer another candidate's screenshot for a selected registration."""
    ident=str(result.get('matched_registry_identifier') or result.get('identifier') or '')
    name=str(result.get('matched_registry_name') or result.get('name') or '')
    ein=digits(result.get('ein',''));state=result.get('state')
    candidates=[r for r in refs if r.get('ein')==ein and r.get('state')==state]
    if state=='GA':
        candidates=sorted(candidates,key=lambda r:r.get('operation')=='detail')
    if state=='NC':
        candidates=sorted(candidates,key=lambda r:r.get('operation')=='detail')
    if state=='NM' and re.fullmatch(r'\d{2}-?\d{7}',ident) and digits(ident)==ein:
        # The connector uses the nine-digit FEIN while the public result keeps
        # New Mexico's displayed hyphen. This is one already-bound credential.
        return next((r for r in reversed(candidates)
                     if re.fullmatch(r'\d{2}-?\d{7}',str(r.get('identifier','')))
                     and digits(r['identifier'])==ein
                     and (not name or key(r.get('record_name'))==key(name))),None)
    if state=='TN':
        # Later alias searches must not replace a captured detail for the same
        # selected registration. Stable order retains latest-within-kind rules.
        candidates=sorted(candidates,key=lambda r:r.get('operation')=='detail')
    if state=='NY':
        path=urlsplit(result.get('source_url') or result.get('url') or '').path
        observed=re.fullmatch(r'/RegistrySearch/(\d{2}-\d{2}-\d{2})/?',path)
        if observed:
            return next((r for r in reversed(candidates) if r.get('identifier')==observed[1]
                         and (not name or key(r.get('record_name'))==key(name))),None)
    if ident:return next((r for r in reversed(candidates) if r.get('identifier')==ident
                         and (not name or key(r.get('record_name'))==key(name))),None)
    if name:
        named=[r for r in candidates if key(r.get('record_name'))==key(name)]
        # Same-name registrations are not interchangeable evidence. Without a
        # selected credential, an ambiguous collection must offer no row link.
        if len({r.get('identifier','') for r in named})!=1:return None
        return named[-1] if named else None
    if result.get('status')=='Not Registered' and result.get('success') is True:
        return next((r for r in reversed(candidates) if r.get('identifier')=='@completed-search'),None)
    return None

def attach_links(result, refs):
    data=dict(result);ref=matching_reference(data,refs)
    if ref:data.update(evidence_url=ref['url'],evidence_captured_at=ref['captured_at'])
    else:data['evidence_url']=''
    review=data.get('identity_review')
    if review:
        # The signed record is populated in the master before this public view.
        data['identity_review']={**review,'candidates':[dict(c) for c in review.get('candidates',[])]}
        for row in data['identity_review']['candidates']:
            candidate=matching_reference({**row,'ein':data['ein'],'state':data['state']},refs)
            if candidate:row['evidence_url']=candidate['url']
    data['evidence_capture']='saved' if ref else ('candidate_only' if review and any(r.get('evidence_url') for r in data['identity_review']['candidates']) else 'unavailable')
    return data

def persist_worker_result(queue,result,job,store=None):
    """Supervisor only, after reaping. Never give child processes DB access."""
    if not isinstance(result,dict):return result
    data=dict(result);assets=data.pop('_worker_source_archives',[])
    history=data.pop('_worker_search_history',None)
    if not assets:
        from deployment.search_history import persist_worker_history
        return persist_worker_history(data,job,history,[],store=store or (PostgresStore(queue.pool) if history and queue else None))
    data['evidence_url']=''
    refs=[];started=time.perf_counter()
    if (not isinstance(assets,list) or len(assets)>12
            or digits(data.get('ein'))!=digits(job['payload']['ein']) or data.get('state')!=job['state']):
        data['evidence_capture']='unavailable';return data
    try:
        store=store or PostgresStore(queue.pool)
        for asset in assets:
            if time.perf_counter()-started>1:
                data['evidence_capture']='partial' if refs else 'unavailable';break
            refs.append(archive(asset,ein=data['ein'],state=data['state'],run_id=asset.get('run_id',''),store=store))
    except Exception:
        data['evidence_capture']='partial' if refs else 'unavailable'
    data=attach_links(data,refs)
    data['evidence_archive_ms']=round((time.perf_counter()-started)*1000,2)
    context=data.get('_worker_identity_review')
    if context:
        context={**context,'records':[dict(r) for r in context['records']]}
        for row in context['records']:
            ref=matching_reference({**row,'ein':data['ein'],'state':data['state']},refs)
            if ref:row['evidence_url']=ref['url']
        data['_worker_identity_review']=context
    from deployment.search_history import persist_worker_history
    return persist_worker_history(data,job,history,refs,store=store)

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
        data['identity_review']=master.identity_review_view(record)
    except Exception:
        pass  # Preserve the original signed choice and status if unavailable.
    return data

class CaptureRun:
    def __init__(self,name,ein,state):
        self.name,self.ein,self.state=name,digits(ein),state
        self.run_id=secrets.token_hex(16);self.documents=[];self.errors=[];self.capture_ms=0
        self.provenance={}
    def __enter__(self):self.token=CURRENT.set(self);return self
    def __exit__(self,*args):CURRENT.reset(self.token)
    def document(self,url,raw,kind='source_text',public_text='',note=''):
        try:
            url=public_url(url,self.state)
            if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:return
            while self.documents and (len(self.documents)>=8 or sum(len(d[1]) for d in self.documents)+len(raw)>6_000_000):
                self.documents.pop(0)
            self.documents.append((url,raw,kind,public_text,time.time(),note or self.provenance.get(url,'')))
        except (ValueError,UnicodeError):return
    def page(self,page):
        """Capture before its existing context closes; do not navigate or scroll."""
        started=time.perf_counter()
        try:
            if time.monotonic()+3>=DEADLINE.get():
                self.errors.append('capture_skipped_near_task_deadline');return
            url=public_url(page.url,self.state)
            text=page.inner_text('body',timeout=400)[:20000]
            size=page.locator('body').evaluate(
                '(b)=>({width:Math.max(b.scrollWidth,document.documentElement.scrollWidth,innerWidth),height:Math.max(b.scrollHeight,document.documentElement.scrollHeight,innerHeight)})',timeout=300)
            if not size or size['width']<=0 or size['height']<=0 or size['width']*size['height']>MAX_PIXELS:
                self.errors.append('source_page_exceeds_capture_bound');return
            raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=1000)
            if page.url!=url or page.inner_text('body',timeout=400)[:20000]!=text:
                self.errors.append('source_page_changed_during_capture');return
            self.document(url,raw,'image',text)
        except Exception:self.errors.append('source_page_capture_unavailable')
        finally:self.capture_ms+=(time.perf_counter()-started)*1000
    def finish(self,result):
        if not isinstance(result,dict):return result
        data=dict(result);assets=[]
        records=[data]+[{**row,'state':self.state,'ein':self.ein} for row in (data.get('_worker_identity_review') or {}).get('records',[])]
        for row in records[:12]:
            identifier=str(row.get('matched_registry_identifier') or row.get('identifier') or '')
            name=str(row.get('matched_registry_name') or row.get('name') or '')
            negative=row.get('status')=='Not Registered' and row.get('success') is True
            # Only source visuals are eligible; no text/JSON substitute is permitted.
            ordered=sorted((d for d in self.documents if d[2] in {'image','source_pdf'}),key=lambda d:({'image':3,'source_pdf':2}[d[2]],d[4]),reverse=True)
            for url,raw,kind,public_text,stamp,source_note in ordered:
                text=public_text
                matched=(self.ein in digits(text) or bool(name and (source_name_present(name,text,self.state) if kind=='source_pdf' else key(name) in key(text))))
                if identifier:matched=matched and bool(re.search(r'(?<![\w])'+re.escape(identifier)+r'(?![\w])',text+' '+url,re.I))
                if negative:
                    matched=bool(re.search(r'no\s+(?:matching\s+)?(?:records?|results?)|0\s+results',text,re.I))
                if re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):continue
                if not matched:continue
                asset=asset_for(raw,kind=kind,state=self.state,ein=self.ein,run_id=self.run_id,source_url=url,
                    organization_name=self.name,identifier='@completed-search' if negative else identifier,
                    record_name=name,public_text=public_text[:20000],capture_note='Saved during this lookup; no new registry search occurs when this PDF is opened. '+source_note)
                asset['captured_at']=stamp;assets.append(asset);break
        if assets:data['_worker_source_archives']=assets
        data['evidence_capture_ms']=round(self.capture_ms,2)
        data['evidence_capture']='captured' if assets else 'unavailable'
        from deployment.search_history import finish_worker_history
        return finish_worker_history(self,data)

class ContextCaptureProxy:
    def __init__(self,context):
        self._context=context;self._captured=False;self._closed=False
        run=CURRENT.get()
        if run:
            from deployment.search_observation import observe_browser_context
            observe_browser_context(context,run)
    def __getattr__(self,key):return getattr(self._context,key)
    def capture(self):
        run=CURRENT.get()
        if run and not self._closed and not self._captured:
            self._captured=True
            try:
                for page in self._context.pages[:3]:run.page(page)
            except Exception:run.errors.append('source_context_capture_unavailable')
    def close(self,*args,**kwargs):
        self.capture()
        value=self._context.close(*args,**kwargs);self._closed=True
        return value

class BrowserCaptureProxy:
    def __init__(self,browser):self._browser=browser;self._owned_contexts=[]
    def __getattr__(self,key):return getattr(self._browser,key)
    def new_context(self,*args,**kwargs):
        context=ContextCaptureProxy(self._browser.new_context(*args,**kwargs))
        self._owned_contexts.append(context);return context
    def close(self,*args,**kwargs):
        # Never inspect other contexts in a borrowed/shared browser.
        for context in self._owned_contexts:context.capture()
        return self._browser.close(*args,**kwargs)


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

def connector_archive(record,payload,query,evidence):
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
        if record['state']=='AL' and isinstance(evidence,dict):
            headers=evidence.get('headers',[])
            for cells in evidence.get('rows',[]):
                if isinstance(cells,list) and len(cells)==len(headers):walk(dict(zip(headers,cells)))
        if (not rows and isinstance(evidence,dict) and evidence.get('complete') is True
                and evidence.get('total')==0 and evidence.get('rows')==[]
                and re.search(r'no\s+(?:matching\s+)?(?:records?|results?)|0\s+results',text,re.I)
                or not rows and ga_completed_empty_grid_snapshot(record,query,evidence,url,text)
                or not rows and nc_completed_empty_snapshot(record,query,evidence,url,text)):
            rows=[('@completed-search',record['organization_name'])]
        elif nc_completed_results_snapshot(record,query,evidence,url,text):
            # Archive once as search evidence. This marker cannot be selected
            # as a positive credential or used to manufacture a zero count.
            rows=[('@completed-search',record['organization_name']),*rows]
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
            multi_source=(record['state'] in {'TN','NV'} and query.get('operation')=='detail') or (record['state']=='NV' and query.get('operation')=='search' and ident=='@completed-search')
            multiple=multi_source and isinstance(images,list) and 2<=len(images)<=(8 if record['state']=='NV' and query.get('operation')=='detail' else 3)
            if 'images' in incoming and (not multiple or images[0]!=incoming.get('image')):raise ValueError('Invalid snapshot page binding')
            content=base64.b64encode(json.dumps(images).encode()).decode() if multiple else incoming['image']
            asset=dict(kind='image_pages' if multiple else 'image',state=record['state'],ein=record['ein'],run_id=run_id,
                source_url=url,captured_at=incoming['captured_at'],content=content,
                identifier=ident,record_name=name,organization_name=record['organization_name'],operation=query.get('operation',''),
                public_text=text,query_id=str(payload['query_id']))
            ref=archive(asset,ein=record['ein'],state=record['state'],run_id=run_id)
            # The complete metadata stays in persistent storage. Continuations
            # carry short references, never images or repeated source URLs.
            record.setdefault('source_snapshots',[]).append({
                **{k:ref[k] for k in ('url','identifier','record_name','captured_at','ein','state')},
                'operation':'detail' if ga_detail else query.get('operation','')})
        refs=record.get('source_snapshots',[])
        if record['state']=='TN':refs=sorted(refs,key=lambda r:r.get('operation')=='detail')
        record['source_snapshots']=refs[-24:]
    except Exception:
        record['snapshot_capture_unavailable']=True
    finally:
        record['source_archive_ms']=round(record.get('source_archive_ms',0)+(time.perf_counter()-started)*1000,2)

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
                    run.document(source_url,out.getvalue(),'source_pdf','\n'.join(texts)[:20000])
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
