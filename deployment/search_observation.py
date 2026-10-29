"""Passive public-name request observations. Never issue or repeat a request.

Transport receipts deliberately do not certify application-level completion.
Only explicit source validators may supply a validated row count.
"""
import json
import re
from contextlib import contextmanager
from urllib.parse import urlsplit, parse_qsl, parse_qs

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
        # Only the actual name text field is a search term. Radio/button labels
        # also contain CharityNameSearch in their field names.
        if u.hostname=='www.sos.ok.gov' and u.path=='/corp/charityInquiryFind.aspx' and field.lstrip('.')!='ctl00$DefaultContent$CharityNameSearch1$_singlename':continue
        leaf=re.split(r'[.$]',field)[-1]
        if leaf.casefold() in {'option', 'options', 'flags'}:continue
        if not value or len(value)>1000 or CONTROL_FIELD.search(field) or PRIVATE_FIELD.search(field) and not field.endswith('tbDBA_Contact'):continue
        if re.fullmatch(r'[\d\s-]+',value):continue
        explicit=bool(NAME_FIELD.search(field) or re.search(r'(?:^|[.$])(?:fullName|primaryName)(?:[.$](?:like|contains|startsWith|eq))?$',field,re.I)
                      or re.search(r'(?:^|[.$])name[.$](?:like|contains|startsWith|eq)$',field,re.I))
        generic=bool((GENERIC_FIELD.fullmatch(leaf) or re.search(r'filter|criteria|search',field,re.I))
                     and any(tokens(value) and tokens(value)<=k for k in known))
        if explicit or generic:
            label='Organization / DBA name' if field.endswith('tbDBA_Contact') else 'Organization name'
            result.append((value,label+'; search method not captured'))
        elif leaf.lower() in {'where','filter','filters'}:
            # SQL/OData name filters: retain the actual quoted pattern only.
            for match in re.finditer(r"(?:\b(?:[A-Z_]*NAME[A-Z_]*|[A-Z_]*ORG[A-Z_]*)\b)\s+(?:LIKE|ILIKE|=)\s*'((?:''|[^'])*)'",value,re.I):
                pattern=match.group(1).replace("''", "'")
                if pattern and len(pattern)<=1000:result.append((pattern,'Name pattern submitted to the public source'))
    return list(dict.fromkeys(result))[:20]

def ein_criteria(url,body=None,params=None,known_ein=''):
    """Record only submitted EIN fields or an exact known EIN in a search field."""
    pairs=list(parse_qsl(urlsplit(str(url)).query,keep_blank_values=True))
    if isinstance(params,dict):pairs+=list(params.items())
    if isinstance(body,bytes):body=body.decode('utf-8','replace')
    if isinstance(body,str) and len(body)<=200000:
        try:body=json.loads(body)
        except (ValueError,TypeError):pairs+=parse_qsl(body,keep_blank_values=True);body=None
    if isinstance(body,(dict,list)):pairs+=_pairs(body)
    for field,value in list(pairs):
        if isinstance(value,str) and value.lstrip().startswith(('{','[')) and len(value)<=200000:
            try:pairs+=_pairs(json.loads(value),str(field))
            except (ValueError,TypeError):pass
    result=[]
    for field,value in pairs[:600]:
        field=str(field);value=str(value).strip()
        if PRIVATE_FIELD.search(field) or CONTROL_FIELD.search(field):continue
        if not re.fullmatch(r'(?:[0-9]{9}|[0-9]{2}-[0-9]{7})',value):continue
        leaf=re.split(r'[.$]',field)[-1]
        explicit=bool(re.search(r'(?:^|[^a-z])(?:f?ein)(?:[^a-z]|$)|(?:federal|tax).*id|federal.*ein$|f?ein(?:number|no|searchfield)$',field,re.I))
        generic=bool(GENERIC_FIELD.fullmatch(leaf) and value.replace('-','')==known_ein)
        md_ein=(urlsplit(str(url)).scheme=='https' and urlsplit(str(url)).netloc=='onestop.md.gov'
                and urlsplit(str(url)).path=='/list_views/62f3e1797f7e3200016a3dab/entries'
                and field in {'a87e8739-62de-600d-728c-6300bf865f9e','filter[a87e8739-62de-600d-728c-6300bf865f9e]'}
                and value.replace('-','')==known_ein)
        if explicit or generic or md_ein:
            label='Federal EIN field' if explicit or md_ein else 'Public search field; EIN entered'
            result.append((value,label))
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
        observed=[('name',value,label) for value,label in criteria(url,body,params,getattr(run,'known_names',[run.name]))]
        if (run.state=='FL' and u.scheme=='https' and u.netloc=='csapp.fdacs.gov'
                and u.path=='/CSPublicApp/CheckACharity/CheckACharity.aspx'
                and isinstance(body,(str,bytes)) and 200000<len(body)<=8000000):
            # ASP.NET state can exceed the generic observation size cap. Read
            # only this exact public name input; never retain the opaque state.
            from urllib.parse import unquote_plus
            encoded=body.decode('utf8','replace') if isinstance(body,bytes) else body
            fields=re.findall(r'(?:^|&)ctl00(?:%24|\$)cpMainContent(?:%24|\$)BusinessNameTb=([^&]{0,4000})(?=&|$)',encoded,re.I)
            names=[unquote_plus(v).strip() for v in fields]
            if len(names)==1 and 0<len(names[0])<=1000:
                value=names[0]
                if not any(k=='name' and v==value for k,v,_ in observed):
                    observed.append(('name',value,'Florida submitted Business Name field'))
            observation=getattr(run,'observation',None)
            if observation:observation.emit('history.FL.large_post','observed',body_bytes=len(body),name_fields=len(names),names_retained=sum(k=='name' for k,_,_ in observed))
        if (run.state=='MI' and u.netloc=='www.ag.state.mi.us'
            and u.path=='/CharitableTrust/frmDefault.aspx' and not u.query and not u.fragment):
            # MI uses txtName, which the generic public-field detector does not
            # recognize. Record only the actual form field and submitted modes.
            fields=body if isinstance(body,dict) else dict(parse_qsl(body.decode('utf8') if isinstance(body,bytes) else body or '',keep_blank_values=True))
            name=fields.get('ctl00$MainContent$txtName','')
            first=fields.get('ctl00$MainContent$ddlName1','');second=fields.get('ctl00$MainContent$ddlName2','')
            if isinstance(name,str) and name.strip() and len(name)<=1000:
                label=(first+'; '+second if first in {'Includes','Starts with'} and second in {'All words','At least one word'} else 'Michigan name field; search method not captured')
                if not any(kind=='name' and value==name.strip() for kind,value,_ in observed):observed.append(('name',name.strip(),label))
        if (run.state=='MN' and u.hostname=='www.ag.state.mn.us'
            and u.path=='/Charity/Search/Results.asp'):
            # The original Minnesota form posts txtOrg and txtEIN. Observe
            # only those actual submitted fields; never infer reviewed names.
            fields=body if isinstance(body,dict) else dict(parse_qsl(body.decode('utf8') if isinstance(body,bytes) else body or '',keep_blank_values=True))
            for kind,field in [('name','txtOrg'),('ein','txtEIN')]:
                value=fields.get(field,'')
                if not isinstance(value,str):continue
                value=value.strip()
                if not value or len(value)>1000:continue
                if kind=='ein' and not re.fullmatch(r'(?:[0-9]{9}|[0-9]{2}-[0-9]{7})',value):continue
                if not any(k==kind and v==value for k,v,_ in observed):observed.append((kind,value,'Minnesota submitted '+field+' field'))
        observed += [('ein',value,label) for value,label in ein_criteria(url,body,params,getattr(run,'ein',''))]
        receipts = [SourceQueryReceipt(run,{'state':run.state,'operation':'search',kind:value,
                    'filter_label':label,'source_kind':'state_portal','url':public})
                for kind,value,label in observed]
        if run.state in {'WV','AR','CT','OK','ME'}:
            from deployment.validated_search_history import bind_transport
            bind_transport(run,receipts)
        return receipts
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
        from deployment.workflow_observation import workflow_call
        response=workflow_call('source.http',call,{},*args,**kwargs)
    except BaseException:
        for receipt in receipts:receipt.incomplete()
        raise
    try:received(receipts,getattr(response,'status_code',None) or getattr(response,'status',None))
    except Exception:
        for receipt in receipts:receipt.incomplete()
    try:
        from deployment.completed_response_history import remember
        remember(response,receipts)
    except Exception:pass
    return response

def observe_browser_context(context,run):
    """Listen to existing Playwright traffic; no interception, polling or waits."""
    observed=getattr(run,'search_history_observed_contexts',None)
    if observed is None:observed=run.search_history_observed_contexts=set()
    if id(context) in observed:return
    observed.add(id(context));pending={}
    def request(req):
        try:
            source=urlsplit(str(req.url))
            hosts=OFFICIAL_HOSTS.get(run.state,set())|({'ccfs-api.prod.sos.wa.gov'} if run.state=='WA' else set())
            if source.scheme!='https' or source.hostname not in hosts:return
            receipts=start_transport(req.url,req.post_data,run=run)
            if receipts:
                pending[id(req)]=receipts
                # Retain bounded Request identity, not time/query similarity.
                # Explicit source validators can refine this same request.
                observed_requests=getattr(run,'search_history_transport_requests',None)
                if observed_requests is None:observed_requests=run.search_history_transport_requests={}
                if len(observed_requests)<150:observed_requests[req]=receipts
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
def dataset_scope(names, *, records=None, record_name=None, name_score=None):
    run=CURRENT.get();receipts=[]
    if run:
        for name in dict.fromkeys(names):
            # KY retries evaluate many of the same names in the same dataset.
            # The names-only report retains each actual term once; it does not
            # need a second scoring pass or duplicate attempt rows.
            if run.state=='KY':
                seen=getattr(run,'ky_observed_dataset_names',set())
                if name in seen:continue
            label='Name filter in downloaded state list; identity reviewed separately' if records is not None else 'Safe-name evaluation of official dataset'
            receipt=begin_source_query(run.state,name,label,'','official_dataset')
            if receipt:
                receipts.append(receipt)
                if run.state=='KY':
                    if not hasattr(run,'ky_observed_dataset_names'):run.ky_observed_dataset_names=set()
                    run.ky_observed_dataset_names.add(name)
    try:yield
    except BaseException:
        for receipt in receipts:receipt.incomplete()
        raise
    else:
        # History reports actual names evaluated by the matcher. It must not
        # run a second scorer over the dataset to manufacture optional row counts.
        # None means no row count recorded, never zero or a completed no-match.
        for receipt in receipts:
            receipt.complete(None)


def observed_dataset_call(call,names,*args,**kwargs):
    with dataset_scope(names):return call(*args,**kwargs)

def complete_public_rows(receipt,count,rows=None):
    """Optional row reporting must never replace a successful source result.

    Preserve counts with older receipt implementations or failed row metadata.
    This compatibility fallback does not retry the registry request.
    """
    if receipt is None:return
    try:receipt.complete(count,rows=rows)
    except Exception:
        try:receipt.complete(count)
        except Exception:
            try:receipt.incomplete()
            except Exception:pass

def observed_named_call(state,name,label,url,call,*args,**kwargs):
    receipt=begin_source_query(state,name,label,url)
    try:result=call(*args,**kwargs)
    except BaseException:
        if receipt:receipt.incomplete()
        raise
    if receipt:complete_public_rows(receipt,len(result) if isinstance(result,list) else None,rows=result if isinstance(result,list) else None)
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
            if complete:
                # Observe the already-returned WI reader table. No new request,
                # no candidate ranking, and no change to source validation.
                rows=None
                if state=='WI':
                    try:
                        from deployment.history_returned_rows import wi_text_records
                        rows=wi_text_records(result)
                    except Exception:pass
                if isinstance(rows,list) and (count is None or count==len(rows)):
                    complete_public_rows(receipt,len(rows),rows=rows)
                else:complete_public_rows(receipt,count)
            else:receipt.incomplete()
        except Exception:receipt.incomplete()
    return result


from contextlib import contextmanager

@contextmanager
def ak_query_observation(page,ein,button):
    """Observe one real Search submission and its matching EventOccurred reply.

    Does not wait, submit, retry or change the source result. Source callbacks
    are removed on exit so late replies cannot become another year's proof.
    """
    receipt=None;listener=None
    try:
        run=CURRENT.get()
        if run is not None and run.state=='AK':
            category=page.locator('select[id$="-8"]:visible option:checked').inner_text(timeout=300).strip()
            year=page.locator('select[id$="-9"]:visible option:checked').inner_text(timeout=300).strip()
            name=page.locator('input[id$="-a"]:visible').input_value(timeout=300).strip()
            fein=page.locator('input[id$="-b"]:visible').input_value(timeout=300).strip()
            event_id=button.get_attribute('id')
            if (category=='Charitable Organization' and re.fullmatch(r'20[0-9]{2}',year)
                and (name or fein) and (not fein or re.sub(r'\D','',fein)==re.sub(r'\D','',ein))
                and event_id):
                receipt=begin_source_query('AK',name or fein,'Displayed submission type: '+category+'; Displayed Year: '+year+'; '+('Name and FEIN fields' if name and fein else 'Name field' if name else 'FEIN field')+'; no name matching-mode selector',page.url)
                if receipt:
                    if not name:receipt.query.pop('name',None)
                    if fein:receipt.query['ein']=fein
                    def listener(response):
                        try:
                            u=urlsplit(response.url)
                            submitted=parse_qs(response.request.post_data or '')
                            if (u.scheme!='https' or u.hostname!='online-registrations-law.alaska.gov'
                                or not u.path.endswith('/EventOccurred') or response.request.method!='POST'
                                or submitted.get('EVENT__')!=[event_id]):return
                            # The submitted public fields take priority over a
                            # preceding DOM read when the state rerenders a view.
                            fields={}
                            for key,values in submitted.items():
                                match=re.fullmatch(r'D[a-zA-Z0-9]+-([89ab])',key)
                                if match and len(values)==1:fields.setdefault(match.group(1),[]).append(values[0])
                            if (all(len(values)==1 for values in fields.values())
                                and fields.get('8')==['CharOrg'] and re.fullmatch(r'20[0-9]{2}',fields.get('9',[''])[0])
                                and (fields.get('a',[''])[0] or fields.get('b',[''])[0])):
                                actual_name=fields.get('a',[''])[0];actual_ein=fields.get('b',[''])[0]
                                receipt.query.pop('name',None);receipt.query.pop('ein',None)
                                if actual_name:receipt.query['name']=actual_name
                                if actual_ein:receipt.query['ein']=actual_ein
                                receipt.query['filter_label']='Submitted type: Charitable Organization; Submitted Year: '+fields['9'][0]+'; '+('Name and FEIN fields' if actual_name and actual_ein else 'Name field' if actual_name else 'FEIN field')+'; no name matching-mode selector'
                            if 200<=response.status<300:
                                body=response.text()
                                count=0 if 'There are no charitable organizations' in body else None
                                complete_public_rows(receipt,count)
                            else:receipt.incomplete()
                        except Exception:pass
                    page.on('response',listener)
    except Exception:pass
    try:yield
    finally:
        if listener is not None:
            try:page.remove_listener('response',listener)
            except Exception:pass
        if receipt is not None:
            try:receipt.incomplete()
            except Exception:pass


def complete_browser_query(receipt,response,count,rows=None):
    """Refine only the exact observed Request; preserve repeated submissions."""
    if receipt is None:return
    complete_public_rows(receipt,count,rows)
    try:
        run=receipt.run
        entries=getattr(run,'search_history_receipts',[])
        validated=next((e for e in entries if e['query_id']==receipt.query_id and e['outcome']=='Completed source response' and e['returned_rows']==count),None)
        if validated is None:return
        observations=getattr(run,'search_history_transport_requests',{}).get(response.request,[])
        duplicates=[]
        for old in observations:
            q=old.query;expected=receipt.query
            if old is receipt or q.get('state')!=expected.get('state') or q.get('operation')!=expected.get('operation'):continue
            if urlsplit(q.get('url','')).netloc!=urlsplit(expected.get('url','')).netloc:continue
            criteria={k:q[k] for k in ['ein','name'] if k in q}
            wanted={k:expected[k] for k in ['ein','name'] if k in expected}
            if not criteria or criteria!=wanted:continue
            existing=next((e for e in entries if e['query_id']==old.query_id),None)
            if existing and existing.get('observation_kind')!='transport_response':continue
            old.saved=True;duplicates.append(old.query_id)
        if duplicates:
            run.search_history_receipts=[e for e in entries if e['query_id'] not in duplicates]
    except Exception:
        # Optional reporting refinement must not replace the source result.
        return


def complete_hi_empty_receipt(run,response,name,fein,issued):
    """One validated HI request, with its actual posted name/EIN formatting."""
    try:
        if run is None or run.state!='HI' or response is None or response.status!=200:return False
        request=response.request;u=urlsplit(response.url)
        if (u.scheme!='https' or u.hostname!='charity.ehawaii.gov'
            or u.path!='/charity/search-charity.json' or request.method!='POST'):return False
        fields=parse_qs(request.post_data or '',keep_blank_values=True)
        if fields.get('name')!=[name] or len(fields.get('fein',[]))!=1:return False
        actual=fields['fein'][0];digits=lambda x:re.sub(r'\D','',x)
        if actual and (not re.fullmatch(r'\d{9}|\d{2}-\d{7}',actual) or digits(actual)!=digits(fein) or digits(actual)!=run.ein):return False
        if not actual and fein or not (actual or name):return False
        query={'state':'HI','operation':'search','source_kind':'state_portal',
               'url':'https://charity.ehawaii.gov/charity/search-charity.json',
               'filter_label':'Contains; '+('FEIN '+actual if actual else 'FEIN blank')+'; other search filters blank'}
        if name:query['name']=name
        if actual:query['ein']=actual
        observations=getattr(run,'search_history_transport_requests',{}).get(request,[])
        validated=getattr(run,'hi_validated_request_receipts',None)
        if validated is None:validated=run.hi_validated_request_receipts={}
        if request in validated:return validated[request]==query
        if len(validated)>=150:return False
        receipt=SourceQueryReceipt(run,query);receipt.issued=issued;receipt.complete(0,rows=[])
        entries=getattr(run,'search_history_receipts',[])
        if not any(e['query_id']==receipt.query_id and e['returned_rows']==0 for e in entries):return False
        duplicate_ids=[]
        for old in observations:
            q=old.query;criteria={k:q[k] for k in ('name','ein') if q.get(k)}
            if (q.get('state')!='HI' or q.get('operation')!='search'
                or urlsplit(q.get('url','')).hostname!='charity.ehawaii.gov'
                or not criteria or any(query.get(k)!=value for k,value in criteria.items())):continue
            entry=next((e for e in entries if e['query_id']==old.query_id),None)
            if entry and entry.get('observation_kind')!='transport_response':continue
            old.saved=True;duplicate_ids.append(old.query_id)
        run.search_history_receipts=[e for e in entries if e['query_id'] not in duplicate_ids]
        validated[request]=query
        return True
    except Exception:return False
