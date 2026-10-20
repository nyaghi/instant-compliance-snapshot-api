"""Passive public-name request observations. Never issue or repeat a request.

Transport receipts deliberately do not certify application-level completion.
Only explicit source validators may supply a validated row count.
"""
import json
import re
from contextlib import contextmanager
from urllib.parse import urlsplit, parse_qsl

from deployment.state_snapshots import CURRENT, OFFICIAL_HOSTS
from deployment.search_history import begin_source_query, SourceQueryReceipt

NAME_FIELD = re.compile(r'(?:org(?:anization)?|charity|business|entity|firm|company|corp|legal|trade|dba|search).*name|name.*(?:org|charity|business|entity|firm|company|corp)|(?:^|[$_.])(?:tbDBA_Contact|scCompanyName|txtFirmName|txtOrgName|organizationName|orgName|companyName|entityName|firmName)$', re.I)
GENERIC_FIELD = re.compile(r'^(?:name|query|search|searchkey|searchvalue|searchterm|searchtext|keyword|keywords|term|q)$',re.I)
PRIVATE_FIELD = re.compile(r'password|passcode|captcha|token|cookie|session|viewstate|validation|authorization|email|phone|address|contactperson|firstname|lastname',re.I)
CONTROL_FIELD = re.compile(r'(?:type|mode|option|column|sort|order|operator|comparison)$',re.I)

def _pairs(value, prefix='', depth=0):
    if depth>6:return []
    if isinstance(value,dict):
        return [(prefix+'.'+str(k),v) for k,v in value.items() if isinstance(v,(str,int,float))]+[p for k,v in value.items() if isinstance(v,(dict,list)) for p in _pairs(v,prefix+'.'+str(k),depth+1)]
    if isinstance(value,list):return [p for v in value[:100] for p in _pairs(v,prefix,depth+1)]
    return []

def criteria(url, body=None, params=None, known_names=()):
    """Extract only actual submitted public name fields; never retain a body."""
    u=urlsplit(str(url));pairs=list(parse_qsl(u.query,keep_blank_values=True))
    if isinstance(params,dict):pairs+=list(params.items())
    if isinstance(body,bytes):body=body.decode('utf-8','replace')
    if isinstance(body,str) and len(body)<=200000:
        try:body=json.loads(body)
        except (ValueError,TypeError):pairs+=parse_qsl(body,keep_blank_values=True);body=None
    if isinstance(body,(dict,list)):pairs+=_pairs(body)
    tokens=lambda x:set(re.findall(r'[a-z0-9]+',str(x).casefold()))
    known=[tokens(n) for n in known_names if n]
    # Portals also serialize nested filters as a query/form string value.
    for field,value in list(pairs):
        if isinstance(value,str) and value.lstrip().startswith(('{','[')) and len(value)<=200000:
            try:pairs+=_pairs(json.loads(value),str(field))
            except (ValueError,TypeError):pass
    result=[]
    for field,value in pairs[:600]:
        field=str(field);value=str(value).strip()
        leaf=re.split(r'[.$]',field)[-1]
        if not value or len(value)>1000 or CONTROL_FIELD.search(field) or PRIVATE_FIELD.search(field) and not field.endswith('tbDBA_Contact'):continue
        if re.fullmatch(r'[\d\s-]+',value):continue
        explicit=bool(NAME_FIELD.search(field) or re.search(r'(?:^|[.$])(?:fullName|primaryName)(?:[.$](?:like|contains|startsWith|eq))?$',field,re.I)
                      or re.search(r'(?:^|[.$])name[.$](?:like|contains|startsWith|eq)$',field,re.I))
        generic=bool((GENERIC_FIELD.fullmatch(leaf) or re.search(r'filter|criteria|search',field,re.I))
                     and any(tokens(value) and tokens(value)<=k for k in known))
        if explicit or generic:
            label='Organization / DBA name' if field.endswith('tbDBA_Contact') else 'Organization name'
            result.append((value,label+'; source matching filter not recorded'))
        elif leaf.lower() in {'where','filter','filters'}:
            # SQL/OData name filters: retain the actual quoted pattern only.
            for match in re.finditer(r"(?:\b(?:[A-Z_]*NAME[A-Z_]*|[A-Z_]*ORG[A-Z_]*)\b)\s+(?:LIKE|ILIKE|=)\s*'((?:''|[^'])*)'",value,re.I):
                pattern=match.group(1).replace("''", "'")
                if pattern and len(pattern)<=1000:result.append((pattern,'Name pattern submitted to the public source'))
    return list(dict.fromkeys(result))[:20]

def start_transport(url,body=None,params=None,run=None):
    run=run or CURRENT.get()
    if run is None:return []
    try:
        u=urlsplit(str(url))
        hosts=OFFICIAL_HOSTS.get(run.state,set())|({'ccfs-api.prod.sos.wa.gov'} if run.state=='WA' else set())
        if u.scheme!='https' or u.hostname not in hosts:return []
        # RI/DC are observed at their existing pagination/validation boundary.
        if run.state in {'RI','DC'}:return []
        public=u._replace(query='',fragment='').geturl()
        # Playwright dispatches callbacks in its own greenlet context. Bind the
        # already-owned run explicitly instead of reading a different ContextVar.
        return [SourceQueryReceipt(run,{'state':run.state,'operation':'search','name':name,
                    'filter_label':label,'source_kind':'state_portal','url':public})
                for name,label in criteria(url,body,params,getattr(run,'known_names',[run.name]))]
    except Exception:
        run.search_history_overflow=True;return []

def received(receipts,status):
    for receipt in receipts:
        if type(status) is int and 200<=status<400:receipt.received(status)
        else:receipt.incomplete()

def observed_http_call(call,*args,**kwargs):
    """Invoke the original callable exactly once and return its exact object."""
    receipts=[]
    try:
        url=next((v for v in args[:2] if hasattr(v,'full_url') or isinstance(v,str) and v.startswith('https://')),kwargs.get('url',''))
        body=kwargs.get('json',kwargs.get('data'))
        if hasattr(url,'full_url'):body=url.data if body is None else body;url=url.full_url
        receipts=start_transport(url,body,kwargs.get('params'))
    except Exception:pass
    try:
        response=call(*args,**kwargs)
    except BaseException:
        for receipt in receipts:receipt.incomplete()
        raise
    try:received(receipts,getattr(response,'status_code',None) or getattr(response,'status',None))
    except Exception:
        for receipt in receipts:receipt.incomplete()
    return response

def observe_browser_context(context,run):
    """Listen to existing Playwright traffic; no interception, polling or waits."""
    observed=getattr(run,'search_history_observed_contexts',None)
    if observed is None:observed=run.search_history_observed_contexts=set()
    if id(context) in observed:return
    observed.add(id(context));pending={}
    def request(req):
        try:
            receipts=start_transport(req.url,req.post_data,run=run)
            if receipts:pending[id(req)]=receipts
        except Exception:run.search_history_overflow=True
    def response(resp):
        try:received(pending.pop(id(resp.request),[]),resp.status)
        except Exception:run.search_history_overflow=True
    def failed(req):
        for receipt in pending.pop(id(req),[]):receipt.incomplete()
    try:
        context.on('request',request);context.on('response',response);context.on('requestfailed',failed)
        run.search_history_pending=getattr(run,'search_history_pending',[])+[pending]
    except Exception:run.search_history_overflow=True

def observe_existing_page(page):
    run=CURRENT.get()
    if run:
        try:observe_browser_context(page.context,run)
        except Exception:run.search_history_overflow=True

def dataset_evaluation(names,source_url=''):
    """Record criteria at a real local matcher invocation, not portal requests."""
    run=CURRENT.get()
    if run is None:return
    for name in dict.fromkeys(names):
        receipt=begin_source_query(run.state,name,'Safe-name evaluation of official dataset',source_url,'official_dataset')
        if receipt:receipt.complete(None)

@contextmanager
def dataset_scope(names):
    run=CURRENT.get();receipts=[]
    if run:
        for name in dict.fromkeys(names):
            receipt=begin_source_query(run.state,name,'Safe-name evaluation of official dataset','','official_dataset')
            if receipt:receipts.append(receipt)
    try:yield
    except BaseException:
        for receipt in receipts:receipt.incomplete()
        raise
    else:
        for receipt in receipts:receipt.complete(None)

def observed_dataset_call(call,names,*args,**kwargs):
    with dataset_scope(names):return call(*args,**kwargs)

def observed_named_call(state,name,label,url,call,*args,**kwargs):
    receipt=begin_source_query(state,name,label,url)
    try:result=call(*args,**kwargs)
    except BaseException:
        if receipt:receipt.incomplete()
        raise
    if receipt:receipt.complete(len(result) if isinstance(result,list) else None)
    return result

def observed_text_call(state,name,label,url,validator,call,*args,**kwargs):
    """Observe one existing public-reader call; retain its existing validator."""
    receipt=begin_source_query(state,name,label,url)
    try:result=call(*args,**kwargs)
    except BaseException:
        if receipt:receipt.incomplete()
        raise
    if receipt:
        try:
            complete,count=validator(result)
            if complete:receipt.complete(count)
            else:receipt.incomplete()
        except Exception:receipt.incomplete()
    return result
