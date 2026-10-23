"""Local DC original-evidence candidate. Status and identity are read-only."""
import hashlib,re,time
from urllib.parse import urlencode,urlsplit,parse_qsl
from deployment.dc_native_capture import SOURCE,VIEWER,expected_record,navigate_and_capture

API=SOURCE+'/query'
LARGE_RESULT_FIELDS='CUSTOMERNUMBER,ENTITYNAME,ENTITYTRADENAME,LICENSESTATUS,BUSINESSACTIVITY,LICENSEENDDATE'
NOTE="Original DC published-license extract used by this lookup. It may lag BOSS; the result's source freshness limitation still applies."

def selected_records(result,rows):
    selected=getattr(result,'_cc_license_record',None)
    if selected:
        return [selected] if selected in rows and expected_record(selected) else []
    review=getattr(result,'_cc_identity_review',None)
    if not isinstance(review,dict) or review.get('search_complete') is not True:return []
    candidates=[r for r in review.get('records',[]) if r.get('_identity_outcome') in {'accepted','possible','conflict'}]
    if not 1<=len(candidates)<=3:return []
    if any(r not in rows or not expected_record(r) for r in candidates):return []
    if len({str(r['identifier']) for r in candidates})!=len(candidates):return []
    return candidates

def negative_url(hint):
    if not isinstance(hint,dict) or hint.get('complete') is not True:return None
    count=hint.get('row_count');rows=hint.get('raw_rows',[])
    if type(count) is not int or not 0<=count<=32 or not isinstance(rows,list) or len(rows)!=count:return None
    if any(not isinstance(r,dict) or not re.fullmatch(r'\d{5,16}',str(r.get('CUSTOMERNUMBER',''))) or not r.get('ENTITYNAME') or not r.get('LICENSESTATUS') for r in rows):return None
    where=hint.get('where','')
    # Only the exact generated charity/name clauses from the completed lookup.
    clause=r"UPPER\((?:ENTITYNAME|ENTITYTRADENAME)\) LIKE '%[A-Z0-9%]+'"
    if not re.fullmatch(r"UPPER\(BUSINESSACTIVITY\) LIKE '%CHARITABLE%' AND \("+clause+r"(?: OR "+clause+r")*\)",where):return None
    if len(where)>3600:return None
    return API+'?'+urlencode({'where':where,'outFields':LARGE_RESULT_FIELDS if count>8 else '*','returnGeometry':'false','f':'html'})

def empty_values(page,url,where,rows=()):
    if page.url!=url:return None
    value=page.locator('#where').input_value(timeout=400)
    text=page.inner_text('body',timeout=400)
    if value!=where or re.search(r'Error:|Access denied|verify you are human',text,re.I):return None
    if not rows:
        if not re.search(r'\bNo records found\.\s*$',text) or re.search(r'CUSTOMERNUMBER:|ENTITYNAME:|# records:',text):return None
    else:
        if re.findall(r'# records:\s*(\d+)',text)!=[str(len(rows))] or 'No records found.' in text:return None
        blocks=re.split(r'CUSTOMERNUMBER:\s*',text)[1:]
        if len(blocks)!=len(rows):return None
        seen=set()
        for block in blocks:
            number=block.splitlines()[0].strip()
            candidates=[r for r in rows if str(r['CUSTOMERNUMBER'])==number]
            if len(candidates)!=1 or number in seen:return None
            seen.add(number);row=candidates[0]
            for field in (('ENTITYNAME','ENTITYTRADENAME','LICENSESTATUS','BUSINESSACTIVITY','LICENSEENDDATE') if len(rows)>8 else ('ENTITYNAME','LICENSESTATUS','BUSINESSACTIVITY','LICENSEENDDATE')):
                values=re.findall(r'(?:^|\n)'+field+r':\s*([^\n]+)',block)
                expected='null' if row.get(field) is None else str(row[field])
                if values!=[expected]:return None
    if page.locator('#outFields').input_value(timeout=400)!=(LARGE_RESULT_FIELDS if len(rows)>8 else '*'):return None
    return value,text

def capture_empty(page,hint,deadline,receipt=None):
    url=negative_url(hint)
    if not url or deadline-time.monotonic()<2:return None
    if hint['row_count']>8:page.set_viewport_size({'width':1280,'height':1000})
    response=page.goto(url,wait_until='domcontentloaded',timeout=max(1,int((deadline-time.monotonic()-1)*1000)))
    if response is None or response.status!=200:return None
    before=empty_values(page,url,hint['where'],hint.get('raw_rows',[]))
    if not before or deadline-time.monotonic()<1:return None
    if receipt:receipt.complete(hint['row_count'],rows=hint.get('raw_rows',[]))
    started=time.perf_counter()
    raw=page.screenshot(type='png',full_page=True,timeout=max(1,int(min(1.5,deadline-time.monotonic()-.5)*1000)))
    if empty_values(page,url,hint['where'],hint.get('raw_rows',[]))!=before or time.monotonic()>=deadline:return None
    return {'source_url':url,'bytes':raw,'text':before[1],'capture_ms':round((time.perf_counter()-started)*1000,2),'note':NOTE+' Original completed query result; returned unrelated records are not a registration match. The separate history retains every actual submitted search.'}

def capture_dc(master,org,result,rows,deadline):
    """One owned context; bounded evidence work; never propagate into status."""
    from deployment.state_snapshots import CURRENT,DEADLINE
    from deployment.search_history import begin_source_query
    run=CURRENT.get()
    if run is None or run.state!='DC' or run.ein!=re.sub(r'\D','',str(org.ein)) or not master.trial_identity():return
    if getattr(run,'dc_visual_attempted',False):return
    run.dc_visual_attempted=True
    targets=selected_records(result,rows)
    negative=(getattr(result,'success',False) is True and getattr(result,'status','')=='Not Registered')
    hint=getattr(run,'dc_completed_query',None)
    if not targets and not (negative and negative_url(hint)):return
    start=time.perf_counter();browser=context=None;held=False;receipt=None
    fact={'adapter':'DC-native-original','outcome':'not_started','total_ms':0,'capture_ms':0,'records_requested':len(targets),'records_captured':0}
    run.visual_adapter_facts.append(fact)
    try:
        stop=min(deadline,DEADLINE.get(),time.monotonic()+(30 if targets else 20))-1
        if stop-time.monotonic()<3:fact['outcome']='deadline_reserve';return
        held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
        if not held:fact['outcome']='browser_capacity_unavailable';return
        with master.checker.sync_playwright() as p:
            phase=time.perf_counter();browser=master.launch_lookup_browser(p,headless=True)
            fact['browser_start_ms']=round((time.perf_counter()-phase)*1000,2)
            try:
                context=browser.new_context(viewport={'width':2200,'height':1000},locale='en-US',timezone_id='America/New_York')
                # This adapter captures only after strict source binding.
                if hasattr(context,'_captured'):context._captured=True
                page=context.new_page()
                if negative:
                    receipt=begin_source_query('DC',hint['query_name'],'Repeated completed query for original visual evidence',API)
                    phase=time.perf_counter();item=capture_empty(page,hint,stop,receipt)
                    fact['negative_visual_ms']=round((time.perf_counter()-phase)*1000,2)
                    if item:
                        fact['capture_ms']+=item['capture_ms'];run.capture_ms+=item['capture_ms']
                        before=len(run.documents);run.document(item['source_url'],item['bytes'],'image',item['text'],item['note'])
                        if len(run.documents)>before:
                            run.dc_validated_empty_images=getattr(run,'dc_validated_empty_images',set())
                            run.dc_validated_empty_images.add(hashlib.sha256(item['bytes']).hexdigest());fact['records_captured']+=1
                else:
                    fact['record_phases']=[]
                    for row in targets:
                        if stop-time.monotonic()<3:break
                        def query_started():
                            nonlocal receipt
                            receipt=begin_source_query('DC',str(row['identifier']),'Exact Customer Number for original visual evidence',VIEWER)
                        detail={'identifier':str(row['identifier']),'captured':False};fact['record_phases'].append(detail)
                        phase=time.perf_counter();item=navigate_and_capture(page,row,stop,on_query=query_started,metrics=detail)
                        detail.update(visual_ms=round((time.perf_counter()-phase)*1000,2),captured=bool(item))
                        if item:
                            fact['capture_ms']+=item['capture_ms'];run.capture_ms+=item['capture_ms']
                            if receipt:receipt.complete(1,rows=[{'name':row['name'],'identifier':row['identifier'],'status':row['raw_status']}])
                            text='\n'.join(k+': '+v for k,v in item['fields'].items())
                            before=len(run.documents);run.document(item['source_url'],item['bytes'],'image',text,item['note'])
                            fact['records_captured']+=int(len(run.documents)>before)
                        if receipt:receipt.incomplete();receipt=None
                fact['outcome']='captured' if fact['records_captured']==(1 if negative else len(targets)) else 'original_incomplete'
            finally:
                phase=time.perf_counter()
                if context is not None:
                    if hasattr(context,'_captured'):context._captured=True
                    context.close()
                if browser is not None:browser.close()
                fact['close_ms']=round((time.perf_counter()-phase)*1000,2)
    except Exception as exc:
        fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__
        fact['error_summary']=str(exc).splitlines()[0][:180]
    finally:
        if receipt:receipt.incomplete()
        if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
        fact['total_ms']=round((time.perf_counter()-start)*1000,2)
