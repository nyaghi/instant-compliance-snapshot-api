from deployment.workflow_observation import workflow_call, trace_return, workflow_stage
"""Local candidate: photograph proven official detail URLs after status lookup.

No status interpretation, status query planning, page reconstruction or URL guessing.
Positive-record paths only; negative and candidate-review routes remain separate.
"""
import base64,hashlib,json,re,time
from urllib.parse import urlsplit,parse_qsl,parse_qs


def completed_names_only_result(run,result):
 """A completed, same-run negative needs actual search names, not a new search."""
 from deployment.state_snapshots import completed_negative_result
 from deployment.identity_evidence import has_review
 return (run is not None and completed_negative_result(result) and not has_review(result)
         and result.get('state')==run.state
         and re.sub(r'\D','',str(result.get('ein','')))==run.ein)

def capture_result_visuals(master,result,run,deadline):
 """Measure visual-only requests separately; never alter a completed status."""
 if completed_names_only_result(run,result):return None
 for capture in (capture_selected_source,capture_negative_search):
  try:workflow_call('deployment/source_visual_adapters.py:capture_result_visuals:12:6:capture',capture,locals(), master,result,run,deadline)
  except Exception:
   if run is not None:run.errors.append('source_visual_adapter_unavailable')

def _selected_url(run,result):
 if (not isinstance(result,dict) or result.get('state')!=run.state
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True
     or result.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable','Unable to Verify'}
     or not result.get('matched_registry_name')):return None
 identifier=str(result.get('matched_registry_identifier') or '')
 url=result.get('source_url') or '';u=urlsplit(url)
 if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or u.fragment:return None
 if run.state=='HI':
  if (u.hostname!='charity.ehawaii.gov' or u.path!='/charity/'+run.ein+'/details.html'
      or u.query or re.sub(r'\D','',identifier)!=run.ein):return None
 elif run.state=='OH':
  params=parse_qsl(u.query,keep_blank_values=True)
  ordinary=(u.path in {'/Charities/OrganizationDetails','/Charities/FullyExemptOrganization'} and params==[('Id',identifier)])
  exempt=(u.path=='/Charities/PartiallyExemptOrganization'
      and params in [[('Id',identifier),('ExemptionStatus','109')],
                     [('Id',identifier),('ExemptionStatus','1716')]])
  if (u.hostname!='charitableregistration.ohioago.gov' or not re.fullmatch(r'\d+',identifier)
      or not (ordinary or exempt)):return None
 elif run.state=='ME':
  params=parse_qsl(u.query,keep_blank_values=True)
  if (u.hostname!='www.pfr.maine.gov' or u.path!='/ALMSOnline/ALMSQuery/ShowDetail.aspx'
      or not re.fullmatch(r'CO\d+',identifier,re.I) or len(params)!=1
      or params[0][0]!='SearchResultToken' or not re.fullmatch(r'[A-Fa-f0-9]{32,256}',params[0][1])):return None
 elif run.state=='MD':
  if (u.hostname!='onestop.md.gov' or u.path!='/list_views/62f3e1797f7e3200016a3dab'
      or u.query or not re.fullmatch(r'\d+',identifier)):return None
 elif run.state=='RI':
  if (u.hostname!='ridbrprod-search.state-reg-eastern.tylerapp.com'
      or not re.fullmatch(r'/search/C\d+/detail',u.path) or u.query
      or not re.fullmatch(r'CO\.\d+',identifier)):return None
 elif run.state=='FL':
  if (u.hostname!='csapp.fdacs.gov' or u.path!='/CSPublicApp/BusinessSearch/BusinessSearch.aspx'
      or u.query or not re.fullmatch(r'CH\d+',identifier)):return None
 elif run.state=='WI':
  if (u.hostname!='apps.dfi.wi.gov' or not u.path.startswith('/ice/berg/Registration/')
      or u.path.endswith('OrganizationCredentialSearch.aspx') or not re.fullmatch(r'\d+-800',identifier)
      or re.search(r'token|password|passcode|captcha|cookie|session|authorization|api.?key',u.query,re.I)):return None
 elif run.state=='OR':
  if (u.hostname!='justice.oregon.gov' or u.path!='/Charities/Charity/details'
      or len(parse_qsl(u.query))!=1 or parse_qsl(u.query)[0][0]!='charityID'
      or not re.fullmatch(r'\d+',parse_qsl(u.query)[0][1])
      or re.sub(r'\D','',identifier)!=run.ein):return None
 else:return None
 return url

def selected_url(run,result):
 try:return _selected_url(run,result) if run is not None else None
 except (ValueError,TypeError,AttributeError):return None

def capture_selected_source(master,result,run,deadline):
 """Best-effort, isolated visual work. Failure never modifies lookup result."""
 if run is not None and run.state=='KS':
  from deployment.kansas_row_evidence import capture_kansas_review_or_selected as capture_selected_kansas
  return trace_return('deployment/source_visual_adapters.py:capture_selected_source:71:2:return',(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:71:9:capture_selected_kansas',capture_selected_kansas,locals(), master,result,run,deadline)))
 if run is not None and run.state=='CA':return trace_return('deployment/source_visual_adapters.py:capture_selected_source:72:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:72:47:capture_selected_ca_source',capture_selected_ca_source,locals(), master,result,run,deadline)))
 if run is not None and run.state=='SC':return trace_return('deployment/source_visual_adapters.py:capture_selected_source:73:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:73:47:capture_selected_sc_source',capture_selected_sc_source,locals(), master,result,run,deadline)))
 if run is not None and run.state=='WA':return trace_return('deployment/source_visual_adapters.py:capture_selected_source:74:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:74:47:capture_selected_wa_source',capture_selected_wa_source,locals(), master,result,run,deadline)))
 if run is not None and run.state=='VA':return trace_return('deployment/source_visual_adapters.py:capture_selected_source:75:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:75:47:capture_selected_va_source',capture_selected_va_source,locals(), master,result,run,deadline)))
 if run is not None and run.state=='CT':return trace_return('deployment/source_visual_adapters.py:capture_selected_source:76:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:76:47:capture_selected_ct_source',capture_ct_review_or_selected,locals(), master,result,run,deadline)))
 if run is not None and run.state=='LA':return trace_return('deployment/source_visual_adapters.py:capture_selected_source:77:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:77:47:capture_selected_la_source',capture_selected_la_source,locals(), master,result,run,deadline)))
 if run is not None and run.state=='NJ':return trace_return('deployment/source_visual_adapters.py:capture_selected_source:78:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:78:47:capture_selected_nj_source',capture_selected_nj_source,locals(), master,result,run,deadline)))
 if run is not None and run.state=='WV':return trace_return('deployment/source_visual_adapters.py:capture_selected_source:79:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:79:47:capture_selected_wv_source',capture_selected_wv_source,locals(), master,result,run,deadline)))
 if run is None or run.state not in {'HI','OH','RI','WI','OR'}:return trace_return('deployment/source_visual_adapters.py:capture_selected_source:80:63:return',None)
 if run.state=='OR':
  # This is the existing live-confirmation route, using the validated official
  # export's selected charityID. It never invents an organization/search URL.
  reader=getattr(master,'or_snapshot_row_for_ein',None)
  if not callable(reader):return trace_return('deployment/source_visual_adapters.py:capture_selected_source:85:26:return',None)
  row=reader(run.ein);norm=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
  if (not isinstance(row,list) or len(row)<16 or not re.fullmatch(r'\d+',str(row[0]))
      or norm(str(row[6]).strip('"'))!=norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:88:44:get',result.get,locals(), 'matched_registry_name'))):return trace_return('deployment/source_visual_adapters.py:capture_selected_source:88:82:return',None)
  result={**result,'source_url':'https://justice.oregon.gov/Charities/Charity/details?charityID='+str(row[0])}
 if run.state=='WI':
  hint=workflow_call('deployment/source_visual_adapters.py:capture_selected_source:91:7:get',getattr(run,'source_detail_hints',{}).get,locals(), str(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:91:53:get',result.get,locals(), 'matched_registry_identifier') or ''))
  norm=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
  if not hint or norm(hint['name'])!=norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_source:93:42:get',result.get,locals(), 'matched_registry_name')):return trace_return('deployment/source_visual_adapters.py:capture_selected_source:93:79:return',None)
  result={**result,'source_url':hint['url']}
 url=selected_url(run,result)
 if url is None:return trace_return('deployment/source_visual_adapters.py:capture_selected_source:96:16:return',None)
 if getattr(run,'selected_visual_attempted',False):return trace_return('deployment/source_visual_adapters.py:capture_selected_source:97:51:return',None)
 run.selected_visual_attempted=True
 # Existing owned browser captures must remain the first choice.
 if any(d[2] in {'image','source_pdf'} and run.ein in re.sub(r'\D','',d[3])
        and re.sub(r'[^a-z0-9]','',result['matched_registry_name'].lower()) in re.sub(r'[^a-z0-9]','',d[3].lower())
        for d in run.documents):return trace_return('deployment/source_visual_adapters.py:capture_selected_source:102:32:return',None)
 started=time.perf_counter();context=browser=None;held=False
 fact={'adapter':run.state+'-selected-detail','outcome':'not_started','playwright_start_ms':0,'browser_acquire_ms':0,'context_start_ms':0,'navigation_ms':0,'binding_ms':0,'capture_ms':0,'browser_close_ms':0,'playwright_close_ms':0,'total_ms':0}
 facts=getattr(run,'visual_adapter_facts',None)
 if facts is None:run.visual_adapter_facts=[]
 run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1.0
  if remaining<3.0:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_source:110:54:return',None)
  stop=time.monotonic()+min(22.0 if run.state=='RI' else 30.0 if run.state=='OR' else 8.0,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_selected_source:112:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_selected_source:113:61:return',None)
  runtime_started=time.perf_counter();runtime_close_started=None
  with master.checker.sync_playwright() as p:
   fact['playwright_start_ms']=round((time.perf_counter()-runtime_started)*1000,2)
   acquire_started=time.perf_counter()
   browser=workflow_call('deployment/source_visual_adapters.py:capture_selected_source:118:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   fact['browser_acquire_ms']=round((time.perf_counter()-acquire_started)*1000,2)
   try:
    context_started=time.perf_counter()
    context_options={'viewport':{'width':1280,'height':900},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):context_options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_selected_source:124:12:new_context',browser.new_context,locals(), **context_options)
    page=workflow_call('deployment/source_visual_adapters.py:capture_selected_source:125:9:new_page',context.new_page,locals())
    fact['context_start_ms']=round((time.perf_counter()-context_started)*1000,2)
    nav=time.perf_counter()
    if run.state=='OR':
     # Keep one pending request alive within the original thirty-second allowance.
     # Restarting at fifteen seconds discarded the pending document response.
     fact['navigation_attempts']=1
     response=workflow_call('OR selected document uninterrupted navigation',page.goto,locals(),url,wait_until='commit',timeout=max(1,int((stop-time.monotonic()-3)*1000)))
    else:
     response=workflow_call('deployment/source_visual_adapters.py:capture_selected_source:128:13:goto',page.goto,locals(), url,wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-3 if run.state=='RI' else min(5.0,stop-time.monotonic()))*1000)))
    fact['navigation_ms']=round((time.perf_counter()-nav)*1000,2)
    fact['http_status']=response.status if response else None
    fact['url_stable']=page.url==url
    if response is None or response.status!=200 or page.url!=url:
     fact['outcome']='source_navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_source:133:50:return',None)
    if run.state=='OR':
     begin=time.perf_counter()
     workflow_call('deployment/source_visual_adapters.py:capture_selected_source:136:5:wait_for_function',page.wait_for_function,locals(), '''({ein,name})=>{
       const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
       const text=document.body.innerText;
       return document.querySelector('#info')&&document.querySelector('#disclaimer')
         &&text.replace(/\\D/g,'').includes(ein)&&norm(text).includes(norm(name))
         &&/Fiscal Year Beginning.*Ending/.test(text)&&/Status:/.test(text);
     }''',arg={'ein':run.ein,'name':result['matched_registry_name']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     fact['selected_view_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    if run.state in {'RI','WI'}:
     begin=time.perf_counter()
     workflow_call('deployment/source_visual_adapters.py:capture_selected_source:146:5:wait_for_function',page.wait_for_function,locals(), '''({name,id})=>{
      const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
      const text=document.body?.innerText||'';
      return norm(text).includes(norm(name)) && text.includes(id)
        && /Charitable Organization/i.test(text) && /Status/i.test(text);
     }''',arg={'name':result['matched_registry_name'],'id':result['matched_registry_identifier']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     fact['selected_view_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    if run.state=='MD':
     search_started=time.perf_counter()
     field=page.locator('#filter-a87e8739-62de-600d-728c-6300bf865f9e')
     workflow_call('deployment/source_visual_adapters.py:capture_selected_source:156:5:fill',field.fill,locals(), run.ein[:2]+'-'+run.ein[2:],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     workflow_call('deployment/source_visual_adapters.py:capture_selected_source:157:5:press',field.press,locals(), 'Enter',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     workflow_call('deployment/source_visual_adapters.py:capture_selected_source:158:5:wait_for_function',page.wait_for_function,locals(), '''({ein,name,id})=>{
       const normalize=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
       const input=document.querySelector('#filter-a87e8739-62de-600d-728c-6300bf865f9e');
       const text=document.body.innerText;
       return input && input.value.replace(/\\D/g,'')===ein && !/Loading\\.\\.\\./i.test(text)
         && /\\b1 record\\b/.test(text) && normalize(text).includes(normalize(name))
         && text.replace(/\\D/g,'').includes(ein)
         && new RegExp('Charity ID:\\\\s*'+id+'(?![0-9])').test(text);
     }''',arg={'ein':run.ein,'name':result['matched_registry_name'],'id':result['matched_registry_identifier']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     fact['visual_ein_search_ms']=round((time.perf_counter()-search_started)*1000,2)
    # Require the actual rendered official record to corroborate the EIN and name.
    binding_started=time.perf_counter()
    text=workflow_call('deployment/source_visual_adapters.py:capture_selected_source:170:9:inner_text',page.inner_text,locals(), 'body',timeout=max(1,int(min(.6,stop-time.monotonic())*1000)))
    fact['binding_ms']=round((time.perf_counter()-binding_started)*1000,2)
    normalize=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
    identifier=str(result['matched_registry_identifier'])
    identity_visible=(bool(re.search(r'(?<!\w)'+re.escape(identifier)+r'(?!\w)',text,re.I)) if run.state in {'ME','RI','WI'} else run.ein in re.sub(r'\D','',text))
    if run.state=='MD':identity_visible=identity_visible and bool(re.search(r'Charity ID:\s*'+re.escape(identifier)+r'(?![0-9])',text))
    if (not identity_visible or normalize(result['matched_registry_name']) not in normalize(text)
        or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
     fact['outcome']='record_not_ready_or_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_selected_source:178:53:return',None)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_source:179:66:return',None)
    before=len(run.documents);capture=time.perf_counter()
    # Preserve RI's existing absolute visual stop inside the screenshot call.
    if run.state in {'RI','OR'}:run.page_capture_stop=stop
    if run.state=='HI':run.page_capture_stop=min(stop,getattr(run,'page_capture_stop',float('inf')))
    # Owned ContextCaptureProxy captures once; its close must not capture again.
    workflow_call('deployment/source_visual_adapters.py:capture_selected_source:182:4:capture',context.capture,locals())
    fact['capture_ms']=round((time.perf_counter()-capture)*1000,2)
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    close_started=time.perf_counter()
    if context is not None:
     # Do not capture a rejected/error page incidentally on close.
     context._captured=True
     workflow_call('deployment/source_visual_adapters.py:capture_selected_source:190:5:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_selected_source:191:27:close',browser.close,locals())
    fact['browser_close_ms']=round((time.perf_counter()-close_started)*1000,2)
    runtime_close_started=time.perf_counter()
  if runtime_close_started is not None:fact['playwright_close_ms']=round((time.perf_counter()-runtime_close_started)*1000,2)
 except Exception:
  fact['outcome']='source_visual_unavailable'
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_selected_source:198:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def remember_ca_exempt_entity(run,result):
 if run is None or run.state!='CA' or not getattr(result,'success',False) or getattr(result,'status','')!='Exempt':return
 entity=getattr(result,'_cc_selected_entity',None)
 if not isinstance(entity,dict) or getattr(result,'_cc_registration_records',None)!=[]:return
 identifier=str(getattr(result,'matched_registry_identifier','') or '')
 name=str(getattr(result,'matched_registry_name','') or '')
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 if (not re.fullmatch(r'\d+',identifier) or str(entity.get('id'))!=identifier
     or entity.get('entityStatus')!='Exempt' or re.sub(r'\D','',str(entity.get('fein') or ''))!=run.ein
     or not name or norm(entity.get('entityName') or entity.get('legalName') or entity.get('name'))!=norm(name)):return
 run.remember_detail(identifier,name,'https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/'+identifier)
 if identifier in run.source_detail_hints:run.source_detail_hints[identifier]['exempt_entity_ein']=run.ein

def ca_exempt_entity_core(text,name,ein):
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 heading=re.search(r'Entity Details:\s*(.*?)\s+Exempt\s+',text,re.S)
 core=re.search(r'Entity Type\b[\s\S]*?Out of State\?\s*(?:Yes|No)\b',text)
 shown=re.search(r'Entity Name\s+(.*?)\s+DBA\b',text,re.S)
 fein=re.search(r'\bFEIN:\s*(\d{2}-?\d{7})(?!\d)',text)
 if (not heading or not shown or norm(heading[1])!=norm(name) or norm(shown[1])!=norm(name)
     or not fein or re.sub(r'\D','',fein[1])!=ein or not core
     or not re.search(r'Entity Status\s+Exempt\b',core[0])
     or re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I)):return None
 return heading[0]+'\nFEIN: '+fein[1]+'\n'+core[0]

def capture_ca_exempt_entity(master,result,run,deadline,hint):
 identifier=str(result.get('matched_registry_identifier') or '')
 url='https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/'+identifier
 if (not re.fullmatch(r'\d+',identifier) or result.get('status')!='Exempt'
     or hint.get('url')!=url or hint.get('exempt_entity_ein')!=run.ein):return
 run.selected_visual_attempted=True
 fact={'adapter':'CA-exempt-entity-detail','phase':'admission','outcome':'not_started','total_ms':0}
 run.visual_adapter_facts.append(fact);start=time.perf_counter();held=False;browser=context=None
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(30.0,remaining)
  def timeout():return max(1,int((stop-time.monotonic()-1)*1000))
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    context=browser.new_context(viewport={'width':1600,'height':1000},locale='en-US');page=context.new_page()
    fact['phase']='navigation';response=page.goto(url,wait_until='commit',timeout=timeout())
    if response is None or response.status!=200 or page.url!=url:fact['outcome']='navigation_rejected';return
    fact['phase']='selected_entity_ready'
    for field in ['entityStatus','entityName']:
     fact['waiting_for_field']=field
     page.locator('.formio-component-'+field).wait_for(state='visible',timeout=timeout())
    fact['waiting_for_field']=''
    # Form containers can be visible before their bound values arrive. Keep the
    # exact identity predicate and wait for its values within the existing cap.
    core=None
    while time.monotonic()+1<stop:
     text=page.inner_text('body',timeout=timeout())
     core=ca_exempt_entity_core(text,result['matched_registry_name'],run.ein)
     if core:break
     fact['waiting_for_field']='bound_entity_values'
     page.wait_for_timeout(min(100,timeout()))
    if not core:fact['outcome']='selected_entity_not_bound';return
    fact['waiting_for_field']=''
    panel=page.locator('.formio-form').filter(has=page.locator('.formio-component-entityStatus'))
    if panel.count()!=1:fact['outcome']='source_panel_not_unique';return
    bounds=panel.bounding_box()
    import math
    height=math.ceil(bounds['y']+bounds['height']+20) if bounds else 0
    if not bounds or bounds['width']<=0 or bounds['height']<=0 or not 100<=height<=1000:fact['outcome']='source_panel_exceeds_viewport';return
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    fact['phase']='capture';begin=time.perf_counter()
    raw=page.screenshot(type='jpeg',quality=80,clip={'x':0,'y':0,'width':1600,'height':height},timeout=max(1,min(5000,timeout())))
    run.capture_ms+=(time.perf_counter()-begin)*1000
    if page.url!=url or ca_exempt_entity_core(page.inner_text('body',timeout=timeout()),result['matched_registry_name'],run.ein)!=core:
     fact['outcome']='source_changed_during_capture';return
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return
    before=len(run.documents)
    run.document(url,raw,'image',core,note='Original state entity page: explicit Exempt standing, organization name and EIN. No registration record exists in the completed lookup.')
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:
  fact.update(outcome='source_visual_unavailable',error_type=type(exc).__name__,error_summary=str(exc).splitlines()[0][:180])
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)


def remember_ca_selected(run,result):
 remember_ca_exempt_entity(run,result)
 """Retain only the already selected registration's original public detail ID."""
 if run is None or run.state!='CA' or not getattr(result,'success',False):return
 number=str(getattr(result,'matched_registry_identifier','') or '')
 name=str(getattr(result,'matched_registry_name','') or '')
 records=getattr(result,'_cc_registration_records',[])
 selected=[r for r in records if isinstance(r,dict) and str(r.get('registrationNumber') or '')==number]
 if len(selected)!=1 or not number or not name:return
 record=selected[0];identifier=str(record.get('id') or '')
 related=record.get('entityRelated') or {};entity_id=str(related.get('id') or '')
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 if (not re.fullmatch(r'\d+',identifier) or not re.fullmatch(r'\d+',entity_id)
     or norm(related.get('name'))!=norm(name+' - '+entity_id)
     or str(record.get('registrationType') or '')!='Charitable Organization'):return
 run.remember_detail(number,name,'https://ca-rcf.evokeplatform.com/app/publicPortal/registrationDetails/'+identifier)

def ca_registration_core(text):
 """Original selected fields; later optional grid paint is outside this block."""
 parts=re.findall(r'\bEntity Related\b[\s\S]*?\bCHARITABLE ORGANIZATION DETAILS\b',text)
 return parts[0] if len(parts)==1 else None

def observe_selected_readiness(page, fact, expected_url, expected_name, expected_id, stop):
 """Passive dependency metadata and one bounded failure-state read; no source requests."""
 from urllib.parse import urlsplit
 import hashlib
 started=time.monotonic(); pending={}; callbacks=[]; finalized=False
 data={'lane':'server_chromium','requests':0,'finished':0,'failed':0,'pending_overflow':0,'errors':[],'failures':[]}
 fact['selected_readiness_observation']=data
 allowed={'document','script','xhr','fetch','stylesheet'}
 def resource(req):
  u=urlsplit(req.url)
  # Public resource identity only: never include query, fragment or credentials.
  return {'host':u.hostname or '', 'path':u.path[:240], 'type':req.resource_type}
 def request(req):
  try:
   if req.resource_type not in allowed:return
   data['requests']+=1
   if len(pending)>=128:data['pending_overflow']+=1;return
   pending[req]=(time.monotonic(),resource(req))
  except Exception:data['observer_error']=True
 def response(resp):
  try:
   item=pending.get(resp.request)
   if item:item[1]['status']=int(resp.status)
  except Exception:data['observer_error']=True
 def ended(req,failed=False):
  try:
   item=pending.pop(req,None)
   if not item:return
   data['failed' if failed else 'finished']+=1
   if failed and len(data['failures'])<8:
    failure=str(req.failure or '')
    # Chromium network error codes are useful; arbitrary URL/message text is not saved.
    codes=re.findall(r'(?:net::)?ERR_[A-Z_]+',failure)
    data['failures'].append({**item[1],'seconds':round(time.monotonic()-item[0],3),'code':codes[0] if codes else 'request_failed'})
  except Exception:data['observer_error']=True
 def page_error(error):
  try:
   raw=str(error)
   if len(data['errors'])<8:
    # Error type plus digest groups recurring failures without storing source data.
    kind=next((x for x in ['TypeError','ReferenceError','SyntaxError','ChunkLoadError','SecurityError'] if x in raw),'page_error')
    data['errors'].append({'kind':kind,'sha256':hashlib.sha256(raw.encode()).hexdigest()[:16],'seconds':round(time.monotonic()-started,3)})
  except Exception:data['observer_error']=True
 for event,callback in [('request',request),('response',response),('requestfinished',ended),('requestfailed',lambda req:ended(req,True)),('pageerror',page_error)]:
  try:page.on(event,callback);callbacks.append((event,callback))
  except Exception:data['observer_error']=True
 def finish():
  nonlocal finalized
  if finalized:return
  finalized=True
  try:
   data['elapsed_seconds']=round(time.monotonic()-started,3)
   data['remaining_seconds']=round(max(0,stop-time.monotonic()),3)
   data['pending_count']=len(pending)
   data['pending']=[{**item,'age_seconds':round(time.monotonic()-when,3)} for when,item in list(pending.values())[:12]]
   data['route_matches']=page.url==expected_url
   if fact.get('outcome')=='captured':return
   remaining=stop-time.monotonic()-.25
   if remaining<=0:data['terminal_read']='no_time_remaining';return
   labels=(['Registration Number','Registration Type','Registration Status','Initial Registration Date','Current Expiration Date']
           if fact.get('adapter')=='CA-selected-registration-detail' else ['Registration Information','Registration ID','Initial Registration Date','Current Registration Date'])
   timeout=max(1,int(min(.25,remaining)*1000))
   data['terminal_read_timeout_ms']=timeout
   try:
    data['terminal']=page.locator('body').evaluate(r'''(body,expected)=>{
     const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden';};
     const text=(body.innerText||'').slice(0,100000), norm=s=>s.toLowerCase().replace(/[^a-z0-9]/g,'');
     const nodes=[...body.querySelectorAll('label,p,span,div,h1,h2,h3,h4')].slice(0,10000);
     return {document_state:document.readyState,body_text_chars:text.length,
      form_count:body.querySelectorAll('.formio-form').length,
      expected_name_present:norm(text).includes(norm(expected.name)),
      expected_id_present:text.includes(expected.id),
      headings:[...body.querySelectorAll('h1,h2,h3,h4,[role="heading"]')].filter(visible).slice(0,8).map(e=>(e.innerText||'').trim().slice(0,80)),
      required:expected.labels.map(label=>{const found=nodes.filter(e=>e.children.length===0&&(e.innerText||'').trim()===label);return {label,count:found.length,visible:found.some(visible)};}),
      verification_present:/verify you are human|user validation required|just a moment/i.test(text),
      error_present:/access denied|something went wrong|failed to load|service unavailable/i.test(text)};
    }''',{'name':expected_name,'id':expected_id,'labels':labels},timeout=timeout)
    data['terminal_read']='completed'
   except Exception as exc:data['terminal_read']='unavailable';data['terminal_error_type']=type(exc).__name__
  except Exception:data['observer_error']=True
  finally:
   for event,callback in callbacks:
    try:page.remove_listener(event,callback)
    except Exception:pass
 return finish


def initialization_completion_stop(fact, old_stop, state_deadline, now):
 """One same-page continuation earned by observed same-navigation public-portal boot."""
 if fact.get('initialization_continuation'):return None
 obs=fact.get('selected_readiness_observation',{})
 terminal=obs.get('terminal',{})
 host={'CA-selected-registration-detail':'ca-rcf.evokeplatform.com','VA-selected-original-registration':'vdacs.evokeplatform.com'}.get(fact.get('adapter'))
 paths={'/api/webContent/themes','/api/admin/environment/public','/api/webContent/apps/publicPortal/public','/api/webContent/apps/publicPortal'}
 # Failed body reads, partial selected records, errors and verification do not
 # earn a new allowance. Body text can be zero during the proven bootstrap.
 if (not host or obs.get('route_matches') is not True or obs.get('terminal_read')!='completed'
     or terminal.get('document_state')!='complete' or terminal.get('form_count')!=0
     or terminal.get('expected_name_present') is not False or terminal.get('expected_id_present') is not False
     or terminal.get('verification_present') is not False or terminal.get('error_present') is not False
     or terminal.get('body_text_chars')!=0 or obs.get('pending_overflow')!=0
     or obs.get('failed')!=0 or obs.get('observer_error') or obs.get('errors')):return None
 # The observer starts on the new owned page before navigation. A request
 # still pending from that navigation is not stale merely because it began
 # more than three seconds ago. Never grant a second continuation or reset
 # the parent deadline; this changes eligibility, not the existing maximum.
 elapsed=obs.get('elapsed_seconds')
 if type(elapsed) not in (float,int) or not 0<=elapsed<float('inf'):return None
 pending=[p for p in obs.get('pending',[]) if p.get('host')==host and p.get('path') in paths
          and p.get('type') in {'xhr','fetch'} and type(p.get('age_seconds')) in (float,int)
          and 0<=p['age_seconds']<=elapsed+.01 and ('status' not in p or p['status']==200)]
 if not pending:return None
 # Absolute stop is extended once, never reset from the time of the retry.
 # A five-second completion reserve applies to the continued first-field wait.
 new_stop=min(old_stop+15,state_deadline-1)
 if new_stop-now<6:return None
 return new_stop

def capture_selected_ca_source(master,result,run,deadline):
 """Photograph the selected actual registration, never the entity Listed label."""
 if (workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:224:5:get',result.get,locals(), 'state')!='CA' or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:224:54:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:225:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:225:45:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:226:12:get',result.get,locals(), 'matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:226:99:return',None)
 identifier=str(workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:227:16:get',result.get,locals(), 'matched_registry_identifier') or '')
 hint=workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:228:6:get',getattr(run,'source_detail_hints',{}).get,locals(), identifier)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 if not hint or not re.fullmatch(r'(?:CT)?\d+',identifier) or norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:230:67:get',hint.get,locals(), 'name'))!=norm(result['matched_registry_name']):return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:230:124:return',None)
 if hint.get('exempt_entity_ein'):
  return capture_ca_exempt_entity(master,result,run,deadline,hint)
 try:
  u=urlsplit(hint['url'])
  if (u.scheme!='https' or u.hostname!='ca-rcf.evokeplatform.com' or u.port not in (None,443)
      or u.username or u.password or u.query or u.fragment
      or not re.fullmatch(r'/app/publicPortal/registrationDetails/\d+',u.path)):return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:235:80:return',None)
 except (ValueError,TypeError,KeyError):return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:236:40:return',None)
 run.selected_visual_attempted=True
 start=time.perf_counter();held=False;browser=context=None
 finish_readiness=lambda:None
 fact={'adapter':'CA-selected-registration-detail','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission','local_visual_budget_ms':30000};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:242:52:return',None)
  # Allow loaded selected fields enough time for original-pixel capture.
  # Keep this evidence work inside the existing state deadline.
  # Full38 live recovery and timing remain required.
  stop=time.monotonic()+min(30.0,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:247:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:248:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:250:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:254:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:254:48:new_page',context.new_page,locals())
    finish_readiness=observe_selected_readiness(page,fact,hint['url'],result['matched_registry_name'],identifier,stop);fact['phase']='navigation';begin=time.perf_counter()
    response=workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:256:13:goto',page.goto,locals(), hint['url'],wait_until='commit',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=hint['url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:258:111:return',None)
    fact['phase']='selected_fields_ready';begin=time.perf_counter()
    # Source CSP disallows wait_for_function's eval. Visible source locators
    # preserve that policy; no CSP bypass or security setting is used.
    for label in ['Registration Number','Registration Type','Registration Status','Initial Registration Date','Current Expiration Date']:
     fact['waiting_for_label']=label
     label_started=time.perf_counter()
     try:
      try:
       workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:266:6:wait_for',page.get_by_text(label,exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
      except Exception as ready_error:
       if label!='Registration Number' or type(ready_error).__name__!='TimeoutError':raise
       finish_readiness()
       proposed_stop=initialization_completion_stop(fact,stop,deadline,time.monotonic())
       if proposed_stop is None:raise
       fact['initialization_continuation']={'count':1,'extra_cap_seconds':15,'extra_granted_seconds':round(proposed_stop-stop,3),'completion_reserve_seconds':5}
       fact['initialization_boundary_observation']=fact['selected_readiness_observation']
       stop=proposed_stop
       finish_readiness=observe_selected_readiness(page,fact,hint['url'],result['matched_registry_name'],identifier,stop)
       workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:266:6:wait_for',page.get_by_text(label,exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-5)*1000)))
     finally:
      fact.setdefault('label_wait_seconds',{})[label]=round(time.perf_counter()-label_started,6)
    fact['waiting_for_label']=''
    fact['selected_fields_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    text=workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:271:9:inner_text',page.inner_text,locals(), 'body',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    core=ca_registration_core(text)
    # Validate source labels and selected values, not merely a sidebar/list hit.
    if (not core or not re.search(r'Registration Number\s+'+re.escape(identifier)+r'(?!\d)',core)
        or norm(result['matched_registry_name']) not in norm(text)
        or not re.search(r'Registration Type\s+Charitable Organization',text)
        or not re.search(r'Registration Status\s+\S+',text)
        or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
     fact['outcome']='selected_registration_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:279:55:return',None)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:280:66:return',None)
    # Capture the original visible registration panel plus the official page
    # header. Optional filing grids below are not the data used here and may
    # still be loading. Clip original pixels; never hide or redraw the grid.
    panel=page.locator('.formio-form').filter(has=page.locator('.formio-component-registrationNumber'))
    if workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:285:7:count',panel.count,locals())!=1:fact['outcome']='source_panel_not_unique';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:285:66:return',None)
    bounds=panel.bounding_box()
    if not bounds or bounds['width']<=0 or bounds['height']<=0:fact['outcome']='source_panel_not_visible';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:287:106:return',None)
    import math
    height=math.ceil(bounds['y']+bounds['height']+20)
    if height<100 or height>1000:fact['outcome']='source_panel_exceeds_viewport';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:290:81:return',None)
    fact['phase']='capture';begin=time.perf_counter()
    raw=workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:292:8:screenshot',page.screenshot,locals(), type='jpeg',quality=80,clip={'x':0,'y':0,'width':1600,'height':height},timeout=max(1,int(min(5.0,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    import io
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as im:
     if im.width*im.height>20000000:fact['outcome']='source_size_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:297:75:return',None)
    if page.url!=hint['url'] or ca_registration_core(workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:298:53:inner_text',page.inner_text,locals(), 'body',timeout=max(1,int((stop-time.monotonic()-1)*1000))))!=core:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:298:144:return',None)
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_selected_ca_source:299:78:return',None)
    before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:300:30:document',run.document,locals(), hint['url'],raw,'image',core[:20000],note='Original selected registration panel and state header. Optional lower filing grids are outside this captured view.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    finish_readiness()
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:302:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:303:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_selected_ca_source:306:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_selected_sc_source(master,result,run,deadline):
 """One visual selected-name query and the actual bound SC public-ID link."""
 if (workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:311:5:get',result.get,locals(), 'state')!='SC' or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:311:54:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:312:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:312:45:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:313:12:get',result.get,locals(), 'matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_selected_sc_source:313:99:return',None)
 identifier=str(workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:314:16:get',result.get,locals(), 'matched_registry_identifier') or '')
 if not re.fullmatch(r'P\d+',identifier) or workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:315:44:get',result.get,locals(), 'source_url')!='https://search.scsos.com/charities':return trace_return('deployment/source_visual_adapters.py:capture_selected_sc_source:315:107:return',None)
 run.selected_visual_attempted=True
 start=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'SC-selected-original-detail','outcome':'not_started','navigation_ms':0,'search_ms':0,'detail_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission'};run.visual_adapter_facts.append(fact)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_sc_source:322:52:return',None)
  stop=time.monotonic()+min(16.0,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:324:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_selected_sc_source:325:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:327:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1280,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:331:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:331:48:new_page',context.new_page,locals());begin=time.perf_counter();fact['phase']='navigation'
    response=workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:332:13:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_sc_source:334:120:return',None)
    fact['phase']='visual_selected_name_search';begin=time.perf_counter()
    workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:336:4:select_option',page.locator('#MainContent_dd_CharitySearchOperator').select_option,locals(), 'Contains',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:337:4:fill',page.locator('#MainContent_txt_CharitySearchName').fill,locals(), result['matched_registry_name'],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:338:4:click',page.locator('#MainContent_butt_Search').click,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['visual_name_queries']=1;fact['visual_query_name']=result['matched_registry_name'];fact['visual_query_mode']='Contains'
    # A credential can have multiple name rows (actual P2775 has both the
    # current and "The" alias). Match the already selected name as well as ID.
    link=page.locator('a[href="javascript:CharityInfo('+identifier[1:]+')"]').filter(has_text=re.compile(r'^\s*'+re.escape(result['matched_registry_name'])+r'\s*$',re.I))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:343:4:wait_for',link.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:344:7:count',link.count,locals())!=1 or norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:344:31:inner_text',link.inner_text,locals(), timeout=400))!=norm(result['matched_registry_name']):fact['outcome']='selected_result_link_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_selected_sc_source:344:149:return',None)
    fact['search_ms']=round((time.perf_counter()-begin)*1000,2)
    fact['phase']='selected_detail';begin=time.perf_counter();workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:346:62:click',link.click,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    panel=page.locator('#MainContent_Panel_CharityDetail');workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:347:59:wait_for',panel.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    text=workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:348:9:inner_text',panel.inner_text,locals(), timeout=400);heading=panel.locator('h4')
    selected_name_key=norm(re.sub(r'^\s*the\s+','',result['matched_registry_name'],flags=re.I))
    # The exact selected name+public-ID link can open a differently spelled
    # canonical heading. Bind that transition to the unique public ID, not a
    # second name-match decision (actual P54670 includes a typo and DBA).
    detail_name_key=norm(re.sub(r'^\s*the\s+','',workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:352:49:inner_text',heading.inner_text,locals(), timeout=400),flags=re.I)) if workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:352:97:count',heading.count,locals())==1 else ''
    if (not detail_name_key
        or re.findall(r'Public Id:\s*(P\d+)(?!\w)',text)!=[identifier]
        or not re.search(r'Status:\s*\S+',text) or page.url!=result['source_url']):fact['outcome']='selected_detail_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_selected_sc_source:355:127:return',None)
    fact['detail_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_sc_source:357:66:return',None)
    begin=time.perf_counter();fact['phase']='capture';before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:358:80:capture',context.capture,locals());fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
    # The context captures original pixels and rejects URL/text changes.
    # Carry the already validated source-link binding into archive selection.
    if len(run.documents)>before:
     import hashlib
     bindings=getattr(run,'sc_selected_image_bindings',None)
     if bindings is None:bindings=run.sc_selected_image_bindings={}
     for url,raw,kind,body,*_ in run.documents[before:]:
      if (kind=='image' and url==result['source_url'] and norm(text) in norm(body)
          and re.findall(r'Public Id:\s*(P\d+)(?!\w)',body)==[identifier]):
       bindings[hashlib.sha256(raw).hexdigest()]=(result['matched_registry_name'],identifier)
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:361:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:362:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_selected_sc_source:365:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)


def wa_summary_core(text):
 parts=re.findall(r'\bORGANIZATION INFORMATION\b[\s\S]*?\bCONTACT INFORMATION\b',text)
 return parts[0] if len(parts)==1 else None

def capture_selected_wa_source(master,result,run,deadline):
 """Original WA summary through renewal date after one exact-EIN UI query."""
 if (workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:374:5:get',result.get,locals(), 'state')!='WA' or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:374:54:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:375:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:375:45:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:376:12:get',result.get,locals(), 'matched_registry_name') or getattr(run,'selected_visual_attempted',False)
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:377:8:get',result.get,locals(), 'source_url')!='https://ccfs.sos.wa.gov/#/cftSearch'):return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:377:73:return',None)
 run.selected_visual_attempted=True;start=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'WA-selected-original-summary','outcome':'not_started','navigation_ms':0,'search_ms':0,'detail_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission','local_visual_budget_ms':30000};run.visual_adapter_facts.append(fact)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 name=result['matched_registry_name'];parts=[norm(part) for part in re.split(r'[()]',name) if norm(part)]
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:384:52:return',None)
  # Observed ordinary WA EIN responses take9-16s before detail. The separate
  # local visual allowance is measured, stays inside the existing state
  # deadline, and is NOT an accepted global performance change.
  stop=time.monotonic()+min(30.0,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:389:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:390:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:392:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1280,'height':1800},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:396:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:396:48:new_page',context.new_page,locals());begin=time.perf_counter();fact['phase']='navigation'
    response=workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:397:13:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:399:120:return',None)
    fact['phase']='visual_EIN_search';begin=time.perf_counter()
    page.get_by_role('radio',name='FEIN Number',exact=True).check(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:402:4:fill',page.locator('#FEINNoSearchField').fill,locals(), run.ein,timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:403:4:click',page.get_by_role('button',name='Search',exact=True).click,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['visual_EIN_queries']=1
    cells=page.get_by_role('cell').filter(has_text=name)
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:406:4:wait_for',cells.first.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:407:7:count',cells.count,locals())>20:fact['outcome']='selected_row_not_unique';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:407:66:return',None)
    exact=[cells.nth(i) for i in range(workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:408:39:count',cells.count,locals())) if norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:408:62:inner_text',cells.nth(i).inner_text,locals(), timeout=400))==norm(name)]
    if len(exact)!=1:fact['outcome']='selected_row_not_unique';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:409:63:return',None)
    cell=exact[0]
    # The public result cell includes blank space; only its name anchor opens
    # the selected organization. Keep the exact-row and detail identity guards.
    anchors=cell.locator('a').filter(has_text=name)
    if anchors.count()!=1 or norm(anchors.inner_text(timeout=400))!=norm(name):
     fact['outcome']='selected_name_link_not_unique';return
    fact['search_ms']=round((time.perf_counter()-begin)*1000,2)
    fact['phase']='selected_detail';begin=time.perf_counter();workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:412:62:click',anchors.click,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:413:4:wait_for',page.get_by_role('heading',name='ORGANIZATION SUMMARY',exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fein=page.locator('label:visible').filter(has_text=re.compile(r'^\s*FEIN Number:\s*$')).locator('..')
    renewal=page.locator('label:visible').filter(has_text=re.compile(r'^\s*Renewal Date:\s*$')).locator('..')
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:416:4:wait_for',renewal.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    # Wait for a populated original field, then reject a foreign FEIN promptly.
    # Waiting for our requested FEIN would disguise a completed mismatch as a
    # long readiness timeout.
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:420:4:wait_for',fein.locator('strong').filter(has_text=re.compile(r'\d')).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    text=workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:421:9:inner_text',page.inner_text,locals(), 'body',timeout=400);core=wa_summary_core(text)
    if (page.url!='https://ccfs.sos.wa.gov/#/organization' or not core or workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:422:74:count',fein.count,locals())!=1 or workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:422:93:count',renewal.count,locals())!=1
        or re.sub(r'\D','',workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:423:27:inner_text',fein.inner_text,locals(), timeout=400))!=run.ein
        or not all(part in norm(core) for part in parts)
        or not re.search(r'Status:\s*\S+',core)):
     fact['outcome']='selected_summary_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:426:50:return',None)
    bounds=renewal.bounding_box()
    if not bounds or bounds['width']<=0 or bounds['height']<=0:fact['outcome']='renewal_not_visible';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:428:101:return',None)
    import math
    height=math.ceil(bounds['y']+bounds['height']+24)
    from deployment.state_snapshots import MAX_PIXELS
    fact['summary_height_px']=height;fact['summary_pixel_limit']=MAX_PIXELS
    if height<100 or 1280*height>MAX_PIXELS:fact['outcome']='summary_exceeds_image_limit';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:431:76:return',None)
    fact['detail_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:433:66:return',None)
    from deployment.state_snapshots import wa_painted_result_ready
    fact['phase']='painted_result_ready';begin=time.perf_counter()
    if not wa_painted_result_ready(page,max(1,int((stop-time.monotonic()-2)*1000))):fact['outcome']='source_overlay_visible';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:436:130:return',None)
    fact['painted_result_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:438:66:return',None)
    fact['phase']='capture';begin=time.perf_counter();raw=workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:439:58:screenshot',page.screenshot,locals(), type='jpeg',quality=80,full_page=height>1800,clip={'x':0,'y':0,'width':1280,'height':height},timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    import io
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as captured:
     if captured.size!=(1280,height):fact['outcome']='summary_image_incomplete';return
    after_bounds=renewal.bounding_box()
    if not after_bounds or any(abs(after_bounds[k]-bounds[k])>1 for k in ('x','y','width','height')):fact['outcome']='summary_geometry_changed';return
    if page.url!='https://ccfs.sos.wa.gov/#/organization' or workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:441:61:is_visible',page.locator('#loaderDiv').is_visible,locals()) or wa_summary_core(workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:441:120:inner_text',page.inner_text,locals(), 'body',timeout=400))!=core:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:441:211:return',None)
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_selected_wa_source:442:78:return',None)
    before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:443:30:document',run.document,locals(), page.url,raw,'image',core[:20000],note='Original organization summary and state header through renewal date; lower financial history is outside this view.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:445:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:446:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_selected_wa_source:449:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def remember_va_selected(run,result):
 """Keep only the already fetched exact-EIN selected Charity registration ID."""
 if run is None or run.state!='VA' or not getattr(result,'success',False):return
 proof=getattr(result,'va_entity_evidence',None);identifier=str(getattr(result,'matched_registry_identifier','') or '');name=str(getattr(result,'matched_registry_name','') or '')
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 if (not isinstance(proof,dict) or proof.get('ein')!=run.ein or proof.get('id')!=identifier
     or norm(proof.get('name'))!=norm(name) or not re.fullmatch(r'\d+',identifier)
     or not re.fullmatch(r'\d+',str(proof.get('entity_id') or ''))):return
 rows=[r for r in getattr(result,'_cc_registration_records',[]) if isinstance(r,dict) and str(r.get('id') or '')==identifier]
 if len(rows)!=1:return
 row=rows[0];entity=row.get('entity') or {};kind=row.get('registrationType') or {}
 if (str(row.get('registrationNumber') or '')!=identifier or row.get('type')!='Registration'
     or not isinstance(kind,dict) or kind.get('name') not in {'Charity','ExemptCharity','Exempt Charity'}
     or str(entity.get('id') or '')!=proof['entity_id'] or norm(entity.get('name'))!=norm(name)):return
 from datetime import date
 expected={}
 for field in ['initialIssueDate','dateOfLastRenewal','issueDate','expirationDate','extensionDate']:
  raw=row.get(field)
  if raw in (None,''):expected[field]='';continue
  if not isinstance(raw,str) or not re.match(r'^\d{4}-\d{2}-\d{2}(?:T|$)',raw):return
  try:d=date.fromisoformat(raw[:10])
  except ValueError:return
  if d.year<1900:return
  expected[field]=d.strftime('%m/%d/%Y')
 status=row.get('status') or {}
 expected['calculatedRegistrationStatusLabel']=str(row.get('calculatedRegistrationStatusLabel') or (status.get('name') if isinstance(status,dict) else '') or '')
 expected['renewalStatus']=str(row.get('renewalStatus') or '')
 run.remember_detail(identifier,name,'https://vdacs.evokeplatform.com/app/publicPortal/registration/'+identifier)
 if identifier in run.source_detail_hints:
  if kind['name'] in {'ExemptCharity','Exempt Charity'}:
   # This official page omits these date components when their values are empty.
   # A populated source date must still be visible and match exactly.
   for field in ['dateOfLastRenewal','expirationDate','extensionDate']:
    if expected[field]=='':expected.pop(field)
   run.source_detail_hints[identifier]['registration_type']='ExemptCharity'
  run.source_detail_hints[identifier]['source_fields']=expected

def va_registration_core(text):
 return re.split(r'\nSubmissions\n',text,maxsplit=1)[0]

def observe_visual_readiness(page,fact):
 """Bounded event metadata only: no URLs, response bodies, requests or waits."""
 started=time.perf_counter();attached=[]
 observation={'events':[],'counts':{}}
 fact['readiness_observation']=observation
 def record(kind,resource='',status=None):
  try:
   if resource not in {'','document','script','stylesheet','xhr','fetch'}:return
   key=kind+(':'+resource if resource else '')
   counts=observation['counts'];counts[key]=min(999,counts.get(key,0)+1)
   keep_tail=fact.get('adapter')=='VA-selected-original-registration'
   if len(observation['events'])>=24 and not keep_tail:return
   item={'event':kind,'seconds':round(time.perf_counter()-started,3)}
   if resource:item['resource']=resource
   if type(status) is int and 100<=status<=599:item['status']=status
   if len(observation['events'])<24:observation['events'].append(item)
   if keep_tail:
    tail=observation.setdefault('last_events',[]);tail.append(item);del tail[:-24]
  except Exception:pass
 def request_event(kind,r):
  try:record(kind,r.resource_type)
  except Exception:pass
 def response_event(r):
  try:record('response',r.request.resource_type,r.status)
  except Exception:pass
 callbacks=[('request',lambda r:request_event('request',r)),
  ('response',response_event),
  ('requestfailed',lambda r:request_event('request_failed',r)),
  ('domcontentloaded',lambda *args:record('dom_ready')),
  ('load',lambda *args:record('load_ready')),
  ('pageerror',lambda *args:record('page_error'))]
 for event,callback in callbacks:
  try:page.on(event,callback);attached.append((event,callback))
  except Exception:pass
 def detach():
  for event,callback in attached:
   try:page.remove_listener(event,callback)
   except Exception:pass
 return trace_return('deployment/source_visual_adapters.py:observe_visual_readiness:523:1:return',(detach))

def capture_selected_va_source(master,result,run,deadline):
 """Original selected VA registration: standing, initial/current/expiry dates."""
 if (workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:527:5:get',result.get,locals(), 'state')!='VA' or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:527:54:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:528:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:528:45:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:529:12:get',result.get,locals(), 'matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:529:99:return',None)
 identifier=str(workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:530:16:get',result.get,locals(), 'matched_registry_identifier') or '');hint=workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:530:70:get',getattr(run,'source_detail_hints',{}).get,locals(), identifier)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 if (not re.fullmatch(r'\d+',identifier) or not hint or norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:532:61:get',hint.get,locals(), 'name'))!=norm(result['matched_registry_name'])
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:533:8:get',hint.get,locals(), 'url')!='https://vdacs.evokeplatform.com/app/publicPortal/registration/'+identifier):return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:533:102:return',None)
 run.selected_visual_attempted=True;start=time.perf_counter();held=False;browser=context=None;detach_observer=lambda:None
 finish_readiness=lambda:None
 fact={'adapter':'VA-selected-original-registration','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission','local_visual_budget_ms':30000};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:538:52:return',None)
  stop=time.monotonic()+min(30.0,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:540:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:541:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:543:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1400},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:547:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:547:48:new_page',context.new_page,locals());finish_readiness=observe_selected_readiness(page,fact,hint['url'],result['matched_registry_name'],identifier,stop);detach_observer=observe_visual_readiness(page,fact);begin=time.perf_counter();fact['phase']='navigation';fact['waiting_for']='document_commit'
    response=workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:548:13:goto',page.goto,locals(), hint['url'],wait_until='commit',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=hint['url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:550:111:return',None)
    begin=time.perf_counter();fact['phase']='selected_fields_ready'
    fact['waiting_for']='Registration Information heading'
    try:
     workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:553:4:wait_for',page.get_by_role('heading',name='Registration Information',exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    except Exception as ready_error:
     if type(ready_error).__name__!='TimeoutError':raise
     finish_readiness()
     proposed_stop=initialization_completion_stop(fact,stop,deadline,time.monotonic())
     if proposed_stop is None:raise
     fact['initialization_continuation']={'count':1,'extra_cap_seconds':15,'extra_granted_seconds':round(proposed_stop-stop,3),'completion_reserve_seconds':5}
     fact['initialization_boundary_observation']=fact['selected_readiness_observation']
     stop=proposed_stop
     finish_readiness=observe_selected_readiness(page,fact,hint['url'],result['matched_registry_name'],identifier,stop)
     workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:553:4:wait_for',page.get_by_role('heading',name='Registration Information',exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-5)*1000)))
    labels=['Registration ID','Initial Registration Date','Current Registration Date']
    if hint.get('registration_type')!='ExemptCharity' or 'expirationDate' in hint.get('source_fields',{}):labels.append('Expiration Date')
    for label in labels:
     fact['waiting_for']=label
     workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:556:5:wait_for',page.get_by_text(label,exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['waiting_for']=''
    fact['selected_fields_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    # Visible labels can precede their selected-record values. Keep every
    # existing binding requirement and wait only within the current allowance.
    bound_started=time.perf_counter();fact['phase']='selected_identity_ready'
    while True:
     text=workflow_call('VA.selected_identity_text',page.inner_text,locals(), 'body',timeout=max(1,int(min(1.0,stop-time.monotonic()-1)*1000)));core=va_registration_core(text)
     checks={'registration_id':bool(re.search(r'Registration ID:\s*'+re.escape(identifier)+r'(?!\d)',core)),
             'organization_name':norm(result['matched_registry_name']) in norm(core),
             'status_value':bool(re.search(r'Status\s+\S+',core)),
             'source_clear':not bool(re.search('verify you are human|user validation required|access denied|just a moment',text,re.I))}
     fact['selected_binding_checks']=checks
     if page.url!=hint['url'] or not checks['source_clear']:
      fact['outcome']='selected_registration_not_bound';return None
     if all(checks.values()):break
     if time.monotonic()+1.1>=stop:
      fact['outcome']='selected_registration_not_bound';return None
     workflow_call('VA.selected_identity_wait',page.wait_for_timeout,locals(), min(100,max(1,int((stop-time.monotonic()-1)*1000))))
    fact['selected_identity_wait_ms']=round((time.perf_counter()-bound_started)*1000,2)
    panel=page.locator('.formio-form')
    if workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:565:7:count',panel.count,locals())!=1:fact['outcome']='source_panel_not_unique';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:565:66:return',None)
    expected=workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:566:13:get',hint.get,locals(), 'source_fields')
    required={'initialIssueDate','issueDate','calculatedRegistrationStatusLabel','renewalStatus'}
    optional={'dateOfLastRenewal','expirationDate','extensionDate'}
    exempt=hint.get('registration_type')=='ExemptCharity'
    if (not isinstance(expected,dict) or not required<=set(expected) or not set(expected)<=required|optional
        or not exempt and set(expected)!=required|optional):
     fact['outcome']='source_field_proof_missing';return None
    for field,wanted in expected.items():
     component=panel.locator('.formio-component-'+field)
     if workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:570:8:count',component.count,locals())!=1:fact['outcome']='source_field_component_changed';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:570:78:return',None)
     lines=[line.strip() for line in workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:571:37:inner_text',component.inner_text,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000))).splitlines() if line.strip()]
     observed=' '.join(lines[1:])
     if observed.casefold()!=wanted.casefold():fact['outcome']='source_fields_changed_since_lookup';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:573:100:return',None)
    # Bind the screenshot to a fresh frame after all seven source fields are
    # populated. The earlier identity read can precede late panel values.
    def selected_frame():
     return workflow_call('VA.selected_capture_frame',page.locator('body').evaluate,locals(),
      r'''(body,keys)=>{const panels=[...body.querySelectorAll('.formio-form')];
       if(panels.length!==1)return null;const p=panels[0],fields={};
       for(const key of keys){const nodes=p.querySelectorAll('.formio-component-'+key);
        if(nodes.length!==1)return null;
        fields[key]=nodes[0].innerText.split(/\n/).map(s=>s.trim()).filter(Boolean).slice(1).join(' ');}
       return {url:location.href,text:body.innerText,fields};}''',list(expected),timeout=max(1,int((stop-time.monotonic()-.5)*1000)))
    for capture_attempt in range(2):
     frame=selected_frame()
     if (not frame or frame['url']!=hint['url'] or
         any(frame['fields'].get(k,'').casefold()!=wanted.casefold() for k,wanted in expected.items())):
      fact['outcome']='source_fields_changed_since_lookup';return None
     capture_core=va_registration_core(frame['text'])
     if (not re.search(r'Registration ID:\s*'+re.escape(identifier)+r'(?!\d)',capture_core)
         or norm(result['matched_registry_name']) not in norm(capture_core)
         or re.search('verify you are human|user validation required|access denied|just a moment',frame['text'],re.I)):
      fact['outcome']='selected_registration_not_bound';return None
     bounds=panel.bounding_box()
     if not bounds or bounds['width']<=0 or bounds['height']<=0:fact['outcome']='source_panel_not_visible';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:575:106:return',None)
     import math
     height=math.ceil(bounds['y']+bounds['height']+20);width=page.viewport_size['width']
     if height<100 or height>1400 or width<100:fact['outcome']='source_panel_exceeds_viewport';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:578:94:return',None)
     if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:579:66:return',None)
     begin=time.perf_counter();fact['phase']='capture';raw=workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:580:58:screenshot',page.screenshot,locals(), type='jpeg',quality=80,clip={'x':0,'y':0,'width':width,'height':height},timeout=max(1,int(min(5.0,stop-time.monotonic()-1)*1000)))
     capture_elapsed=round((time.perf_counter()-begin)*1000,2);fact['capture_ms']+=capture_elapsed;run.capture_ms+=capture_elapsed
     after=selected_frame()
     if not after or after['url']!=frame['url'] or after['fields']!=frame['fields']:
      fact['capture_change']='selected_url_or_fields'
      fact['outcome']='source_changed_during_capture';return None
     if va_registration_core(after['text'])!=capture_core:
      fact['capture_change']='selected_page_text'
      # Do not keep the first image. Re-read and validate the entire record,
      # recompute its bounds, then require an unchanged replacement image.
      if capture_attempt==0 and time.monotonic()+2<stop:
       fact['capture_recaptures']=1
       continue
      fact['outcome']='source_changed_during_capture';return None
     break
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_selected_va_source:583:78:return',None)
    before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:584:30:document',run.document,locals(), hint['url'],raw,'image',capture_core[:20000],note='Original selected registration fields and state header; lower optional submissions grid outside captured view.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    finish_readiness()
    detach_observer()
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:587:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:588:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_selected_va_source:591:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def ct_primary_registration_text(text):
 return re.split(r'\nActive Campaign Solicitations\n|\nSolicitation Reports',text,maxsplit=1)[0]

def capture_ct_review_or_selected(master,result,run,deadline):
 """Capture original signed candidates without resolving their identities."""
 import copy
 review=result.get('_worker_identity_review')
 if not review:return capture_selected_ct_source(master,result,run,deadline)
 if (run is None or run.state!='CT' or result.get('state')!='CT'
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('source_url')!='https://www.elicense.ct.gov/lookup/licenselookup.aspx'
     or getattr(run,'selected_visual_attempted',False)):
  return
 rows=review.get('records') if isinstance(review,dict) else None
 if not isinstance(rows,list) or not 1<=len(rows)<=12:return
 seen=set()
 for row in rows:
  if (not isinstance(row,dict) or not isinstance(row.get('name'),str) or not row['name'].strip()
      or not re.fullmatch(r'CHR\.\d{7}(?:-EXEMPT)?',str(row.get('identifier','')))
      or row.get('identifier') in seen or row.get('url')!=result['source_url']
      or row.get('status') not in {'Current','Upcoming Filing','Exempt','Delinquent','Closed / Withdrawn / Canceled','Revoked / Suspended','Pending / In Process','Failed to Renew'}
      or (row.get('ein') and re.sub(r'\D','',str(row['ein']))!=run.ein)):
   return
  seen.add(row['identifier'])
 # Every candidate shares one existing 20-second visual allowance.
 stop=min(deadline,time.monotonic()+20)
 run.selected_visual_attempted=True
 for row in rows:
  if time.monotonic()+3>=stop:break
  local=copy.copy(run)
  local.selected_visual_attempted=False
  visual={**result,'success':True,'status':row['status'],
          'matched_registry_name':row['name'],'matched_registry_identifier':row['identifier']}
  capture_selected_ct_source(master,visual,local,stop)
  run.capture_ms=local.capture_ms



def capture_selected_ct_source(master,result,run,deadline):
 """Fresh credential search and actual source-issued selected detail link."""
 if (workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:599:5:get',result.get,locals(), 'state')!='CT' or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:599:54:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:600:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:600:45:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:601:12:get',result.get,locals(), 'matched_registry_name') or getattr(run,'selected_visual_attempted',False)
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:602:8:get',result.get,locals(), 'source_url')!='https://www.elicense.ct.gov/lookup/licenselookup.aspx'):return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:602:91:return',None)
 identifier=str(workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:603:16:get',result.get,locals(), 'matched_registry_identifier') or '')
 match=re.fullmatch(r'CHR\.(\d{7})(?:-EXEMPT)?',identifier)
 if not match:return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:605:14:return',None)
 run.selected_visual_attempted=True;start=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'CT-fresh-selected-original-detail','outcome':'not_started','navigation_ms':0,'search_ms':0,'detail_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission'};run.visual_adapter_facts.append(fact)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:611:52:return',None)
  stop=time.monotonic()+min(20.0,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:613:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:614:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:616:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1400},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:620:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:620:48:new_page',context.new_page,locals());begin=time.perf_counter();fact['phase']='navigation'
    response=workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:621:13:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:623:120:return',None)
    begin=time.perf_counter();fact['phase']='visual_credential_search'
    prefix='#ctl00_MainContentPlaceHolder_ucLicenseLookup_'
    workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:626:4:select_option',page.locator(prefix+'ctl03_ddCredPrefix').select_option,locals(), 'CHR',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:627:4:fill',page.locator(prefix+'ctl03_tbLicenseNumber').fill,locals(), match[1],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:628:4:click',page.locator(prefix+'btnLookup').click,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['visual_credential_queries']=1
    card=page.locator('forge-card').filter(has_text=identifier);workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:630:64:wait_for',card.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:631:7:count',card.count,locals())!=1 or norm(result['matched_registry_name']) not in norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:631:76:inner_text',card.inner_text,locals(), timeout=400)):fact['outcome']='selected_card_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:631:148:return',None)
    fact['search_ms']=round((time.perf_counter()-begin)*1000,2);begin=time.perf_counter();fact['phase']='selected_detail'
    workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:633:4:click',card.get_by_role('link',name='Details',exact=True).click,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    frame=page.locator('#iFrmLicenseDetailPopup[src*="licensedetail.aspx" i]');workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:634:79:wait_for',frame.wait_for,locals(), state='attached',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    from urllib.parse import urljoin
    url=urljoin(page.url,frame.get_attribute('src') or '');u=urlsplit(url);pairs=parse_qsl(u.query,keep_blank_values=True)
    if (u.scheme!='https' or u.hostname!='www.elicense.ct.gov' or u.port not in (None,443)
        or u.username or u.password or u.fragment or u.path.lower()!='/lookup/licensedetail.aspx'
        or len(pairs)!=1 or pairs[0][0]!='id' or not 1<=len(pairs[0][1])<=1000):fact['outcome']='source_detail_link_changed';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:639:125:return',None)
    # Use the selected source-issued URL in the same public session.
    # The official iframe can remain blank while this exact URL is readable.
    fact['phase']='selected_direct_detail'
    response=workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:643:13:goto',page.goto,locals(), url,wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['visual_detail_navigation_attempts']=2
    if response is None or response.status!=200 or page.url!=url:fact['outcome']='selected_direct_navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:645:119:return',None)
    detail=page
    heading=detail.get_by_text('Registration Information',exact=True);workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:647:70:wait_for',heading.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    text=workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:648:9:inner_text',detail.inner_text,locals(), 'body',timeout=400);core=ct_primary_registration_text(text)
    if (norm(result['matched_registry_name']) not in norm(core)
        or not re.search(r'\bRegistration\s+'+re.escape(identifier)+r'(?![\w.])',core)
        or not re.search(r'Status\s+\S+',core) or 'Expiration Date' not in core
        or re.search('Invalid Request|verify you are human|access denied|just a moment',core,re.I)):
     fact['outcome']='selected_detail_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:653:49:return',None)
    panel=heading
    for _ in range(5):
     panel=panel.locator('..');panel_text=workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:656:42:inner_text',panel.inner_text,locals(), timeout=400)
     if identifier in panel_text and 'Expiration Date' in panel_text:break
    if identifier not in panel_text or 'Expiration Date' not in panel_text or 'Active Campaign Solicitations' in panel_text:fact['outcome']='primary_registration_panel_changed';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:658:177:return',None)
    bounds=panel.bounding_box()
    if not bounds or bounds['height']<=0 or bounds['width']<=0:fact['outcome']='primary_panel_not_visible';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:660:107:return',None)
    import math
    height=math.ceil(bounds['y']+bounds['height']+8)
    viewport=page.viewport_size
    if (not viewport or height<100 or height>viewport['height']
        or viewport['width']<600 or bounds['x']<0 or bounds['y']<0
        or workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:666:11:evaluate',detail.locator('body').evaluate,locals(), '(el)=>el.ownerDocument.defaultView.scrollY')!=0):
     fact['outcome']='primary_panel_outside_visible_page';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:667:58:return',None)
    if detail.url!=url:fact['outcome']='selected_page_url_changed';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:668:67:return',None)
    fact['detail_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:670:66:return',None)
    clip={'x':0,'y':0,'width':viewport['width'],'height':height}
    begin=time.perf_counter();fact['phase']='capture';raw=workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:672:58:screenshot',page.screenshot,locals(), type='jpeg',quality=80,clip=clip,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    if panel.bounding_box()!=bounds:fact['outcome']='source_panel_moved_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:674:88:return',None)
    if detail.url!=url or ct_primary_registration_text(workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:675:55:inner_text',detail.inner_text,locals(), 'body',timeout=400))!=core:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_selected_ct_source:675:148:return',None)
    before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:676:30:document',run.document,locals(), url,raw,'image',core[:20000],note='Original selected source-issued detail page and state header through primary registration dates; one direct detail navigation; solicitor campaign records outside this view.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:678:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:679:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_selected_ct_source:682:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_selected_la_source(master,result,run,deadline,negative=False):
 if not negative:
  from deployment.la_original_row import capture_original_la_row
  if capture_original_la_row(master,result,run,deadline):return

 """Original public publisher row; retain its Registered Through label."""
 if (run is None or run.state!='LA' or workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:687:39:get',result.get,locals(), 'state')!='LA'
     or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:688:28:get',result.get,locals(), 'ein','')))!=run.ein or workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:688:63:get',result.get,locals(), 'success') is not True
     or (workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:689:9:get',result.get,locals(), 'status')!='Not Registered' if negative else workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:689:65:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Unable to Verify','Site Not Reachable'})
     or (bool(workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:690:14:get',result.get,locals(), 'matched_registry_name') or workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:690:53:get',result.get,locals(), 'matched_registry_identifier')) if negative else not workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:690:117:get',result.get,locals(), 'matched_registry_name'))
     or getattr(run,'selected_visual_attempted',False)
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:692:8:get',result.get,locals(), 'source_url')!='https://www.ag.state.la.us/Charity/Registration/Listing'
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:693:8:get',result.get,locals(), 'status_reason')!=('LA_EXPORT_NO_SAFE_MATCH' if negative else 'LA_STATUS_FROM_OFFICIAL_EXCEL_EXPORT')):return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:693:122:return',None)
 expected=master.parse_due_date(workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:694:32:get',result.get,locals(), 'computed_due_date') or '')
 if not negative and expected is None:return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:695:38:return',None)
 query_name=workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:696:12:get',result.get,locals(), 'matched_registry_name')
 if negative:
  evaluated=[workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:698:13:get',workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:698:13:get',r.get,locals(), 'query',{}).get,locals(), 'name') for r in getattr(run,'search_history_receipts',[]) if workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:698:97:get',r.get,locals(), 'outcome')=='Completed official dataset evaluation' and workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:698:159:get',workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:698:159:get',r.get,locals(), 'query',{}).get,locals(), 'source_kind')=='official_dataset' and workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:698:220:get',workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:698:220:get',r.get,locals(), 'query',{}).get,locals(), 'state')=='LA']
  if not evaluated or run.name not in evaluated:return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:699:48:return',None)
  query_name=run.name
 run.selected_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'LA-original-publisher-selected-row','phase':'admission','outcome':'not_started','navigation_ms':0,'filter_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:706:52:return',None)
  stop=time.monotonic()+min(16.0,remaining);held=workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:707:48:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:708:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:710:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1500,'height':1100},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:714:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:714:48:new_page',context.new_page,locals());fact['phase']='navigation';begin=time.perf_counter()
    response=workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:715:13:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)));fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:716:120:return',None)
    fact['phase']='source_table_filter';begin=time.perf_counter()
    table=page.get_by_role('table')
    if negative:
     from deployment.search_history import SourceQueryReceipt
     receipt=SourceQueryReceipt(run,{'state':'LA','operation':'search','name':query_name,'filter_label':'Original publisher table; client-side contains filter','source_kind':'state_portal','url':result['source_url']})
    workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:722:4:fill',page.get_by_role('searchbox',name='Search:',exact=True).fill,locals(), query_name,timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if negative:
     try:
      workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:725:6:wait_for',table.get_by_role('cell',name='No matching records found',exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
      if (workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:726:10:count',table.locator('tbody tr').count,locals())!=1 or not re.search(r'Showing 0 to 0 of 0 entries',workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:726:95:inner_text',page.inner_text,locals(), 'body',timeout=400))):receipt.incomplete();fact['outcome']='not_a_completed_empty_view';return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:726:199:return',None)
      receipt.complete(0)
     except Exception:receipt.incomplete();raise
    else:
     row=table.locator('tbody tr').filter(has=page.get_by_role('cell',name=result['matched_registry_name'],exact=True));workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:730:120:wait_for',row.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     cells=row.get_by_role('cell')
     if (workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:732:9:count',row.count,locals())!=1 or workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:732:27:count',cells.count,locals())!=3 or norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:732:52:inner_text',cells.nth(0).inner_text,locals(), timeout=400))!=norm(result['matched_registry_name'])
         or master.parse_due_date(workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:733:34:inner_text',cells.nth(1).inner_text,locals(), timeout=400))!=expected
         or workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:734:12:count',table.get_by_role('button',name='Registered Through',exact=True).count,locals())!=1):fact['outcome']='publisher_fields_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:734:134:return',None)
    fact['filter_ms']=round((time.perf_counter()-begin)*1000,2);fact['visual_selected_name_filters']=1
    text=workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:736:9:inner_text',page.inner_text,locals(), 'body',timeout=400)
    if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='verification_pending';return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:737:143:return',None)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:738:66:return',None)
    fact['phase']='capture';begin=time.perf_counter();raw=workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:739:58:screenshot',page.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    if page.url!=result['source_url'] or workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:741:41:inner_text',page.inner_text,locals(), 'body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_selected_la_source:741:131:return',None)
    before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:742:30:document',run.document,locals(), page.url,raw,'image',text[:20000],note=('Original Louisiana public table: completed empty client-side filter of an already evaluated name. The separate search history distinguishes official dataset evaluations from this visual filter.' if negative else 'Original Louisiana public registered-charities table filtered to the already selected source name. Registered Through date agrees with retained official export. No invented EIN/license/detail page.'))
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:745:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:746:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_selected_la_source:749:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def remember_md_selected(master,run,result,body,org):
 """Retain the already selected public entry ID and source status/year."""
 if run is None or run.state!='MD':return
 run.md_verified_empty=False
 if not getattr(result,'success',False):return
 try:
  selected=master.md_prefer_active_entry_body(body,org);payload,_=json.JSONDecoder().raw_decode(selected[selected.index('{'):]);entries=payload.get('entries',[])
  if not isinstance(payload.get('entries'),list):return
  if entries==[] and master.public_status(result)=='Not Registered':run.md_verified_empty=True;return
  if len(entries)!=1:return
  entry=entries[0];entry_id=entry.get('id');name=str(getattr(result,'matched_registry_name','') or '');identifier=str(getattr(result,'matched_registry_identifier','') or '')
  if not isinstance(entry_id,str) or not re.fullmatch(r'[a-f0-9]{24}',entry_id) or not re.fullmatch(r'\d+',identifier) or not name:return
  values=[master.html_fragment_text(str(v)) for v in entry.get('view_data',{}).get('content_element_data',{}).values()]
  def field(label):
   found=[v.split(':',1)[1].strip() for v in values if v.startswith(label+':')]
   return trace_return('deployment/source_visual_adapters.py:field:767:3:return',(found[0] if len(found)==1 else None))
  ein=field('Charity EIN');status=field('Registration Status');year=field('Year Represented')
  if (re.sub(r'\D','',ein or '')!=run.ein or field('Charity ID')!=identifier or not status
      or master.useful_registry_name(entry.get('f_aedd5545-808f-4725-9b1d-5fa61e994a75') or '')!=name):return
  if year not in (None,'') and not re.fullmatch(r'(?:19|20)\d{2}',year):return
  run.remember_detail(identifier,name,'https://onestop.md.gov/detail_views/62f3e17b7f7e3200016a4b6c/entry/'+entry_id)
  if identifier in run.source_detail_hints:run.source_detail_hints[identifier]['source_fields']={'status':status,'year':year or None}
 except (ValueError,TypeError,KeyError,AttributeError):return

def capture_owned_md_page(run,result,page,context,deadline):
 """Original General Information page in a separate owned source page."""
 if completed_names_only_result(run,result):
  context._captured=True
  return None
 if run is None or run.state!='MD':return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:778:35:return',None)
 context._captured=True
 if workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:780:4:get',result.get,locals(), 'status')=='Not Registered':return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:780:43:return',(workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:780:50:capture_owned_md_empty',capture_owned_md_empty,locals(), run,result,context,deadline)))
 if selected_url(run,result) is None or getattr(run,'selected_visual_attempted',False):return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:781:87:return',None)
 run.selected_visual_attempted=True;start=time.perf_counter();detail=None;detach_observer=lambda:None
 fact={'adapter':'MD-owned-selected-general','outcome':'not_started','navigation_ms':0,'general_ms':0,'financial_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission','local_visual_budget_ms':30000};run.visual_adapter_facts.append(fact)
 identifier=str(result['matched_registry_identifier']);hint=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:784:60:get',run.source_detail_hints.get,locals(), identifier);norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 if not hint or norm(workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:785:21:get',hint.get,locals(), 'name'))!=norm(result['matched_registry_name']) or not isinstance(workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:785:96:get',hint.get,locals(), 'source_fields'),dict):fact['outcome']='selected_source_proof_missing';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:785:176:return',None)
 expected=hint['source_fields'];u=urlsplit(hint['url'])
 if (u.scheme!='https' or u.hostname!='onestop.md.gov' or u.port not in (None,443) or u.username or u.password or u.query or u.fragment
     or not re.fullmatch(r'/detail_views/62f3e17b7f7e3200016a4b6c/entry/[a-f0-9]{24}',u.path)):fact['outcome']='selected_link_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:788:136:return',None)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:791:52:return',None)
  stop=time.monotonic()+min(30.0,remaining)
  detail=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:793:9:new_page',context.new_page,locals());detach_observer=observe_visual_readiness(detail,fact);detail.set_extra_http_headers({});begin=time.perf_counter();fact['phase']='navigation';fact['waiting_for']='document_domcontentloaded'
  response=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:794:11:goto',detail.goto,locals(), hint['url'],referer=result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['waiting_for']=''
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200:fact['outcome']='detail_navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:797:91:return',None)
  def same_record():
   actual=urlsplit(detail.url)
   return actual.scheme=='https' and actual.hostname=='onestop.md.gov' and actual.path==u.path and not actual.username and not actual.password
  begin=time.perf_counter();fact['phase']='general_information'
  general=detail.get_by_role('tabpanel',name='General Information',exact=True);workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:802:79:wait_for',general.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:803:2:wait_for',general.locator('.dvce-model-property').filter(has=detail.get_by_role('heading',name='Charity ID',exact=True)).locator('p').filter(has_text=re.compile(r'\d')).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  def value(panel,label):
   field=panel.locator('.dvce-model-property').filter(has=detail.get_by_role('heading',name=label,exact=True))
   if field.count()!=1:return None
   return field.locator('p').inner_text(timeout=max(1,int((stop-time.monotonic()-1)*1000))).strip()
  if (not same_record() or norm(value(general,'Charity Name'))!=norm(result['matched_registry_name'])
      or value(general,'Charity ID')!=identifier or (value(general,'Registration Status') or '').casefold()!=expected['status'].casefold()):fact['outcome']='general_source_fields_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:809:190:return',None)
  fact['approval_date_visible']=bool(value(general,'Latest Approval Date'))
  dismiss=detail.get_by_role('button',name='Dismiss alert.',exact=True)
  if workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:812:5:count',dismiss.count,locals())==1 and workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:812:28:is_visible',dismiss.is_visible,locals()):
   # Wait for the source's own alert to finish dismissing. Preserve three
   # seconds for the original screenshot and post-capture identity checks.
   fact['phase']='dismiss_source_alert'
   if stop-time.monotonic()<=3:fact['outcome']='capture_reserve';return None
   workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:813:3:click',dismiss.click,locals(), timeout=max(1,int((stop-time.monotonic()-3)*1000)))
   if stop-time.monotonic()<=3:fact['outcome']='capture_reserve';return None
   workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:813:30:wait_for',dismiss.wait_for,locals(), state='hidden',timeout=max(1,int((stop-time.monotonic()-3)*1000)))
   if (not same_record() or norm(value(general,'Charity Name'))!=norm(result['matched_registry_name'])
       or value(general,'Charity ID')!=identifier or (value(general,'Registration Status') or '').casefold()!=expected['status'].casefold()):
    fact['outcome']='general_source_changed_during_alert';return None
  general_text=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:814:15:inner_text',detail.inner_text,locals(), 'body',timeout=400)
  general_fields=tuple(general.locator('.dvce-model-property').all_inner_texts())
  if not general_fields:fact['outcome']='general_fields_missing';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:816:65:return',None)
  if re.search('verify you are human|user validation required|access denied|just a moment',general_text,re.I):fact['outcome']='source_verification_pending';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:817:156:return',None)
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:818:64:return',None)
  def shot():
   begin_shot=time.perf_counter()
   try:return detail.screenshot(type='jpeg',quality=80,full_page=True,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
   finally:fact['capture_ms']+=round((time.perf_counter()-begin_shot)*1000,2)
  fact['phase']='general_capture';images=[shot()]
  after_general=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:824:16:inner_text',detail.inner_text,locals(), 'body',timeout=400)
  if (not same_record() or tuple(general.locator('.dvce-model-property').all_inner_texts())!=general_fields
      or re.search('verify you are human|user validation required|access denied|just a moment',after_general,re.I)):
   fact['outcome']='general_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:827:52:return',None)
  fact['general_other_text_changed']=after_general!=general_text
  fact['general_ms']=round((time.perf_counter()-begin)*1000,2);texts=[general_text]
  raw=images[0] if len(images)==1 else json.dumps([base64.b64encode(raw).decode('ascii') for raw in images]).encode('utf8')
  if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_page:849:76:return',None)
  before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:850:28:document',run.document,locals(), detail.url,raw,'image' if len(images)==1 else 'image_pages','\n\n'.join(texts)[:20000],note='Original selected public record General Information. Organization, identifier and standing match retained lookup fields. All visible source fields retained; no financial-tab navigation or source reconstruction.')
  fact['original_views']=len(images);fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception as exc:fact['outcome']='owned_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  detach_observer()
  run.capture_ms+=fact['capture_ms']
  if detail is not None:
   try:workflow_call('deployment/source_visual_adapters.py:capture_owned_md_page:857:7:close',detail.close,locals())
   except Exception:fact['owned_page_close_error']=True
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_owned_md_empty(run,result,context,deadline):
 """Original zero-entry EIN filter, using only the existing owned context."""
 if (run is None or run.state!='MD' or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:863:39:get',result.get,locals(), 'state')!='MD' or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:863:68:get',result.get,locals(), 'status')!='Not Registered'
     or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:864:8:get',result.get,locals(), 'success') is not True or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:864:65:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:865:8:get',result.get,locals(), 'matched_registry_name') or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:865:47:get',result.get,locals(), 'matched_registry_identifier')
     or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:866:8:get',result.get,locals(), 'source_url')!='https://onestop.md.gov/list_views/62f3e1797f7e3200016a3dab'
     or getattr(run,'md_verified_empty',False) is not True or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_owned_md_empty:867:110:return',None)
 run.negative_visual_attempted=True;started=time.perf_counter();detail=None
 fact={'adapter':'MD-owned-original-empty-EIN-view','phase':'admission','outcome':'not_started','navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_empty:872:52:return',None)
  stop=time.monotonic()+min(10.0,remaining);detail=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:873:51:new_page',context.new_page,locals());detail.set_extra_http_headers({});detail.set_viewport_size({'width':1600,'height':1100});begin=time.perf_counter();fact['phase']='navigation'
  response=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:874:11:goto',detail.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)));fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200 or detail.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_empty:875:120:return',None)
  table=detail.get_by_role('table');workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:876:36:wait_for',table.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  field_id='a87e8739-62de-600d-728c-6300bf865f9e';field=detail.locator('#filter-'+field_id);criterion=run.ein[:2]+'-'+run.ein[2:];begin=time.perf_counter();fact['phase']='visual_EIN_query'
  from deployment.search_history import SourceQueryReceipt
  receipt=SourceQueryReceipt(run,{'state':'MD','operation':'search','ein':run.ein,'filter_label':'Search by Charity EIN; original public filter','source_kind':'state_portal','url':result['source_url']})
  workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:880:2:fill',field.fill,locals(), criterion,timeout=max(1,int((stop-time.monotonic()-1)*1000)));workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:880:75:press',field.press,locals(), 'Enter',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:881:2:wait_for',table.get_by_role('cell',name='No results found.',exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  # The actual source paints its empty row before the aria-live record count.
  # Wait for both original signals; never classify that intermediate view.
  workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:884:2:wait_for',detail.locator('[role="status"]').filter(has_text=re.compile(r'\b0\s+records\b')).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  u=urlsplit(detail.url);pairs=parse_qsl(u.query,keep_blank_values=True);text=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:885:78:inner_text',detail.inner_text,locals(), 'body',timeout=400)
  fact['empty_binding']={'official_origin':u.scheme=='https' and u.hostname=='onestop.md.gov','path_match':u.path=='/list_views/62f3e1797f7e3200016a3dab','query_keys':[k for k,_ in pairs],'only_EIN_query':pairs==[(field_id,criterion)],'criterion_matches':workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:886:255:input_value',field.input_value,locals(), timeout=400)==criterion,'zero_counter':bool(re.search(r'\b0\s+records\b',text)),'row_count':workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:886:365:count',table.get_by_role('row').count,locals()),'empty_cells':workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:886:412:count',table.get_by_role('cell',name='No results found.',exact=True).count,locals())}
  if (u.scheme!='https' or u.hostname!='onestop.md.gov' or u.path!='/list_views/62f3e1797f7e3200016a3dab'
      or u.username or u.password or u.fragment or pairs!=[(field_id,criterion)]
      or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:889:9:input_value',field.input_value,locals(), timeout=400)!=criterion or not re.search(r'\b0\s+records\b',text)
      or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:890:9:count',table.get_by_role('row').count,locals())!=2 or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:890:48:count',table.get_by_role('cell',name='No results found.',exact=True).count,locals())!=1):receipt.incomplete();fact['outcome']='empty_source_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_empty:890:184:return',None)
  receipt.complete(0);fact['visual_EIN_queries']=1;fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
  dismiss=detail.get_by_role('button',name='Dismiss alert.',exact=True)
  if workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:893:5:count',dismiss.count,locals())==1 and workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:893:28:is_visible',dismiss.is_visible,locals()):workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:893:49:click',dismiss.click,locals(), timeout=400);workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:893:76:wait_for',dismiss.wait_for,locals(), state='hidden',timeout=500)
  text=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:894:7:inner_text',detail.inner_text,locals(), 'body',timeout=400)
  if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='source_verification_pending';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_empty:895:148:return',None)
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_empty:896:64:return',None)
  fact['phase']='capture';begin=time.perf_counter();raw=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:897:56:screenshot',detail.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
  fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
  if detail.url!=u.geturl() or workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:899:31:inner_text',detail.inner_text,locals(), 'body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_empty:899:123:return',None)
  before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:900:28:document',run.document,locals(), detail.url,raw,'image',text[:20000],note='Original completed Maryland zero-result EIN filter. Existing API response independently had zero entries. No name search is claimed; the separate query receipt records the actual visual EIN submission.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception as exc:fact['outcome']='owned_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if detail is not None:
   try:workflow_call('deployment/source_visual_adapters.py:capture_owned_md_empty:904:7:close',detail.close,locals())
   except Exception:fact['owned_page_close_error']=True
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def capture_owned_md_results_view_legacy(run,result,page,context,deadline):
 """Use the existing MD browser; original lookup result/body stay unchanged."""
 if run is None or run.state!='MD' or selected_url(run,result) is None:return trace_return('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:910:71:return',None)
 if getattr(run,'selected_visual_attempted',False):return trace_return('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:911:51:return',None)
 run.selected_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'MD-owned-public-view','outcome':'not_started','navigation_ms':0,'visual_ein_search_ms':0,'capture_ms':0,'total_ms':0}
 run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:917:52:return',None)
  stop=time.monotonic()+min(6.0,remaining)
  # The existing entries reader leaves AJAX-only headers on this page. They
  # must not accompany the subsequent normal public-page navigation.
  page.set_extra_http_headers({});fact['page_headers_restored']=True
  begin=time.perf_counter()
  response=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:923:11:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int(min(3,stop-time.monotonic()-1)*1000)))
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:925:118:return',None)
  # Static filter inputs precede the live table/event handlers. Wait for its
  # first completed render before entering the one visual-only EIN query.
  begin=time.perf_counter()
  workflow_call('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:929:2:wait_for_function',page.wait_for_function,locals(), '''()=>{
   const text=document.body.innerText,table=document.querySelector('table,[role="table"]');
   return table && table.querySelectorAll('tr,[role="row"]').length>1
    && /\\b[0-9]+ records?\\b/.test(text) && !/Loading\\.\\.\\./i.test(text);
  }''',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['initial_view_ready_ms']=round((time.perf_counter()-begin)*1000,2)
  begin=time.perf_counter();field=page.locator('#filter-a87e8739-62de-600d-728c-6300bf865f9e')
  workflow_call('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:936:2:fill',field.fill,locals(), run.ein[:2]+'-'+run.ein[2:],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  workflow_call('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:937:2:press',field.press,locals(), 'Enter',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  workflow_call('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:938:2:wait_for_function',page.wait_for_function,locals(), '''({ein,name,id})=>{
   const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
   const input=document.querySelector('#filter-a87e8739-62de-600d-728c-6300bf865f9e');
   const text=document.body.innerText;
   return input && input.value.replace(/\\D/g,'')===ein && !/Loading\\.\\.\\./i.test(text)
    && /\\b1 record\\b/.test(text) && norm(text).includes(norm(name))
    && text.replace(/\\D/g,'').includes(ein)
    && new RegExp('Charity ID:\\\\s*'+id+'(?![0-9])').test(text);
  }''',arg={'ein':run.ein,'name':result['matched_registry_name'],'id':str(result['matched_registry_identifier'])},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['visual_ein_search_ms']=round((time.perf_counter()-begin)*1000,2)
  # Recheck the specific credential even when a modeled wait adapter is used.
  text=workflow_call('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:949:7:inner_text',page.inner_text,locals(), 'body',timeout=300)
  norm=lambda value:re.sub(r'[^a-z0-9]','',value.lower())
  if (run.ein not in re.sub(r'\D','',text) or norm(result['matched_registry_name']) not in norm(text)
      or not re.search(r'Charity ID:\s*'+re.escape(str(result['matched_registry_identifier']))+r'(?![0-9])',text)):
   fact['outcome']='record_binding_failed';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:953:43:return',None)
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:954:64:return',None)
  before=len(run.documents);begin=time.perf_counter();workflow_call('deployment/source_visual_adapters.py:capture_owned_md_results_view_legacy:955:54:capture',context.capture,locals())
  fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
  fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception:fact['outcome']='owned_visual_unavailable'
 finally:fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_owned_me_page(run,result,page,context,deadline):
 """ME redirects its temporary detail key; bind the rendered credential instead."""
 if run is None or run.state!='ME' or selected_url(run,result) is None:return trace_return('deployment/source_visual_adapters.py:capture_owned_me_page:963:71:return',None)
 if getattr(run,'selected_visual_attempted',False):return trace_return('deployment/source_visual_adapters.py:capture_owned_me_page:964:51:return',None)
 run.selected_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'ME-owned-selected-detail','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_me_page:969:52:return',None)
  stop=time.monotonic()+min(15.0,remaining)
  begin=time.perf_counter();response=workflow_call('deployment/source_visual_adapters.py:capture_owned_me_page:971:37:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int(min(10,stop-time.monotonic()-5)*1000)))
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  current=urlsplit(page.url)
  if (response is None or response.status!=200 or current.scheme!='https' or current.hostname!='www.pfr.maine.gov'
      or current.path!='/ALMSOnline/ALMSQuery/ShowDetail.aspx'):
   fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_me_page:976:41:return',None)
  text=workflow_call('deployment/source_visual_adapters.py:capture_owned_me_page:977:7:inner_text',page.inner_text,locals(), 'body',timeout=max(1,int(min(1,stop-time.monotonic()-4)*1000)))
  norm=lambda value:re.sub(r'[^a-z0-9]','',value.lower())
  from deployment.state_snapshots import me_detail_name_bound
  if ((norm(result['matched_registry_name']) not in norm(text) and not me_detail_name_bound(result['matched_registry_name'],text,result['matched_registry_identifier']))
      or not re.search(r'License\s+Number:\s*'+re.escape(result['matched_registry_identifier'])+r'(?!\w)',text,re.I)
      or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
   fact['outcome']='record_binding_failed';return trace_return('deployment/source_visual_adapters.py:capture_owned_me_page:982:43:return',None)
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_me_page:983:64:return',None)
  run.page_capture_stop=stop
  before=len(run.documents);begin=time.perf_counter();workflow_call('deployment/source_visual_adapters.py:capture_owned_me_page:984:54:capture',context.capture,locals());fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
  fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception:fact['outcome']='owned_visual_unavailable'
 finally:
  if hasattr(run,'page_capture_stop'):del run.page_capture_stop
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_owned_fl_page(master,run,result,page,context,deadline):
 """Photograph the already-selected FL license in the existing owned browser."""
 if run is not None and run.state=='FL' and workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:991:44:get',result.get,locals(), 'status')=='Not Registered':
  return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_page:992:2:return',(workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:992:9:capture_owned_fl_empty',capture_owned_fl_empty,locals(), master,run,result,page,deadline)))
 if run is None or run.state!='FL' or selected_url(run,result) is None:return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_page:993:71:return',None)
 if getattr(run,'selected_visual_attempted',False):return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_page:994:51:return',None)
 run.selected_visual_attempted=True
 start=time.perf_counter();transport=None;fact={'adapter':'FL-owned-selected-license','outcome':'not_started','phase':'admission','navigation_ms':0,'credential_view_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_page:999:52:return',None)
  stop=time.monotonic()+min(20.0,remaining)
  begin=time.perf_counter();fact['phase']='navigation'
  try:response=workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:1002:15:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  except Exception as exc:
   if 'ERR_CERT_AUTHORITY_INVALID' not in str(exc):raise
   # Preserve the existing verified certificate-chain recovery. Never disable
   # TLS validation, ignore certificate errors or use a different origin.
   transport=master.FloridaVerifiedTransport(page);transport.deadline=stop;transport.enable()
   response=workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:1008:12:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_page:1010:118:return',None)
  begin=time.perf_counter();field=page.locator('#cpMainContent_LicenseTb')
  fact['phase']='license_field'
  workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:1013:2:fill',field.fill,locals(), result['matched_registry_identifier'],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['phase']='search_click'
  workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:1015:2:click',page.locator('#cpMainContent_SingleSearchBt').click,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['phase']='credential_ready'
  workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:1017:2:wait_for_function',page.wait_for_function,locals(), '''({name,id})=>{
   const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
   if (!document.body) return false;
   const text=document.body.innerText;
   return norm(text).includes(norm(name)) && text.includes(id)
    && /Charitable Organization/i.test(text) && /Expires/i.test(text);
  }''',arg={'name':result['matched_registry_name'],'id':result['matched_registry_identifier']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['phase']='credential_binding'
  rows=master.fl_business_candidate_rows(page.content());norm=lambda value:re.sub(r'[^a-z0-9]','',value.lower())
  bound=[r for r in rows if workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:1026:28:get',workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:1026:28:get',r.get,locals(), 'business_evidence',{}).get,locals(), 'identifier')==result['matched_registry_identifier'] and norm(r['business_evidence']['name'])==norm(result['matched_registry_name'])]
  fact['credential_view_ms']=round((time.perf_counter()-begin)*1000,2)
  if len(bound)!=1:fact['outcome']='credential_binding_failed';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_page:1028:63:return',None)
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_page:1029:64:return',None)
  fact['phase']='capture'
  before=len(run.documents);begin=time.perf_counter()
  previous_stop=getattr(run,'fl_selected_capture_stop',None)
  run.fl_selected_capture_stop=min(stop,previous_stop) if previous_stop is not None else stop
  try:workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:1031:54:capture',context.capture,locals())
  finally:
   if previous_stop is None:del run.fl_selected_capture_stop
   else:run.fl_selected_capture_stop=previous_stop
  fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
  fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception as exc:fact['outcome']='owned_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if transport is not None:workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_page:1035:27:close',transport.close,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

FL_EMPTY_CRITERIA = '''()=>{
 const values={};
 for(const suffix of ['BusinessNameTb','LicenseTb','AllWordsTb','PhraseTb','MoreWordsTb','MoreWords_1Tb','MoreWords_2Tb']) {
  const els=document.querySelectorAll('#cpMainContent_'+suffix);
  if(els.length!==1)return null;
  values[suffix]=els[0].value;
 }
 const warning=document.querySelector('#cpMainContent_NoResultLb');
 const results=document.querySelector('#cpMainContent_MasterGv');
 return {...values,warning:warning&&warning.getClientRects().length?warning.innerText:null,
  results_visible:!!(results&&results.getClientRects().length)};
}'''

def capture_owned_fl_empty(master,run,result,page,deadline):
 """One original Check-A-Charity visual search, without changing status lookup."""
 if (run is None or run.state!='FL' or workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1053:39:get',result.get,locals(), 'state')!='FL'
     or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1054:28:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1055:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1055:45:get',result.get,locals(), 'status')!='Not Registered'
     or not run.name or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_empty:1056:72:return',None)
 run.negative_visual_attempted=True
 start=time.perf_counter();transport=None
 fact={'adapter':'FL-owned-completed-empty','outcome':'not_started','phase':'admission',
       'navigation_ms':0,'visual_query_count':0,'query_ms':0,'capture_ms':0,'total_ms':0}
 run.visual_adapter_facts.append(fact)
 url='https://csapp.fdacs.gov/CSPublicApp/CheckACharity/CheckACharity.aspx'
 name=run.name
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_empty:1066:52:return',None)
  stop=time.monotonic()+min(6.0,remaining)
  timeout=lambda:max(1,int((stop-time.monotonic()-1)*1000))
  fact['phase']='navigation';begin=time.perf_counter()
  try:response=workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1070:15:goto',page.goto,locals(), url,wait_until='domcontentloaded',timeout=timeout())
  except Exception as exc:
   if 'ERR_CERT_AUTHORITY_INVALID' not in str(exc):raise
   transport=master.FloridaVerifiedTransport(page);transport.deadline=stop;transport.enable()
   response=workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1074:12:goto',page.goto,locals(), url,wait_until='domcontentloaded',timeout=timeout())
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200 or page.url!=url:
   fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_empty:1077:41:return',None)
  initial=workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1078:10:evaluate',page.evaluate,locals(), FL_EMPTY_CRITERIA)
  if not initial or any(initial[k] for k in initial if k not in {'BusinessNameTb','warning','results_visible'}):
   fact['outcome']='restricted_or_missing_filter';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_empty:1080:50:return',None)
  workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1081:2:fill',page.locator('#cpMainContent_BusinessNameTb').fill,locals(), name,timeout=timeout())
  fact['phase']='visual_query';begin=time.perf_counter();issued=time.time()
  fact['visual_query_count']=1
  workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1084:2:click',page.locator('#cpMainContent_SingleSearchBt').click,locals(), timeout=timeout())
  workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1085:2:wait_for',page.locator('#cpMainContent_NoResultLb').wait_for,locals(), state='visible',timeout=timeout())
  fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
  fields=workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1087:9:evaluate',page.evaluate,locals(), FL_EMPTY_CRITERIA)
  normalize=lambda value:re.sub(r'\s+',' ',str(value or '')).strip()
  expected='No result found for '+name
  if (page.url!=url or not fields or fields['BusinessNameTb']!=name
      or fields['results_visible'] or normalize(fields['warning'])!=normalize(expected)
      or any(fields[k] for k in fields if k not in {'BusinessNameTb','warning','results_visible'})):
   fact['outcome']='empty_view_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_empty:1093:42:return',None)
  text=workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1094:7:inner_text',page.inner_text,locals(), 'body',timeout=timeout())
  if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):
   fact['outcome']='source_verification_pending';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_empty:1096:49:return',None)
  completed_visual_name_receipt(run,name,url,issued,'Business Name; License blank; all advanced filters blank',0)
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_empty:1098:64:return',None)
  fact['phase']='capture';begin=time.perf_counter()
  raw=workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1100:6:screenshot',page.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=min(1500,timeout()))
  fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
  if (page.url!=url or workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1102:23:evaluate',page.evaluate,locals(), FL_EMPTY_CRITERIA)!=fields
      or workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1103:9:inner_text',page.inner_text,locals(), 'body',timeout=timeout())!=text):
   fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_empty:1104:51:return',None)
  if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_owned_fl_empty:1105:76:return',None)
  before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1106:28:document',run.document,locals(), url,raw,'image',text)
  if len(run.documents)>before:
   run.validated_negative_visual_urls.add(url)
   if not hasattr(run,'fl_validated_empty_images'):run.fl_validated_empty_images=set()
   run.fl_validated_empty_images.add(hashlib.sha256(raw).hexdigest());fact['outcome']='captured'
  else:fact['outcome']='capture_failed'
 except Exception as exc:
  fact['outcome']='owned_empty_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:
  if transport is not None:workflow_call('deployment/source_visual_adapters.py:capture_owned_fl_empty:1115:27:close',transport.close,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)


OH_EMPTY_FIELDS = '''()=>{
 const fields={};
 for(const id of ['EIN','ddlEINFilterCriteriaList','OrgNameOrDBAName','OrganizationPurposeCategoryValue','City','StateCode','ZipCode','CountyId']) {
  const els=document.querySelectorAll('#'+id);if(els.length!==1)return null;
  fields[id]=els[0].value;
 }
 const tables=[...document.querySelectorAll('table')].filter(t=>{
  const caption=t.querySelector('caption');
  return caption&&[...caption.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ').trim()==='Search results';
 });
 if(tables.length!==1)return null;
 const rows=[...tables[0].querySelectorAll('tr')].filter(r=>r.querySelector('td'));
 const empty=rows.length===1&&rows[0].querySelectorAll('td').length===1
  &&rows[0].innerText.trim()==='No organizations found'&&!!rows[0].getClientRects().length;
 return {...fields,empty};
}'''

def capture_owned_oh_prepare(run,page,ein):
 """Passive receipt for the existing exact-EIN submission; no extra actions."""
 if run is None or run.state!='OH' or re.sub(r'\D','',str(ein))!=run.ein:return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_prepare:1138:73:return',(None))
 url='https://charitableregistration.ohioago.gov/Charities/ResearchCharities'
 observed={'receipt':None,'request':None,'response_ok':False}
 def requested(request):
  try:
   if observed['request'] is not None or request.url!=url or request.method!='POST':return
   body=request.post_data or ''
   if len(body)>512000:return
   content_type=request.headers.get('content-type','')
   if content_type.lower().startswith('multipart/form-data;'):
    from email.parser import BytesParser
    from email.policy import default
    message=BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n'+body).encode('utf8'))
    if not message.is_multipart():return
    values={}
    for part in message.iter_parts():
     key=part.get_param('name',header='content-disposition')
     if key not in {'EIN','EINFilterCriteria','OrgNameOrDBAName','OrganizationPurposeCategoryValue','City','StateCode','ZipCode','CountyId'}:continue
     if part.get_filename() is not None:return
     values.setdefault(key,[]).append(part.get_content())
   elif content_type.lower().startswith('application/x-www-form-urlencoded'):
    values=parse_qs(body,keep_blank_values=True)
   else:return
   if (re.sub(r'\D','',values.get('EIN',[''])[0])!=run.ein
       or values.get('EINFilterCriteria')!=['3']
       or any(len(v)!=1 for v in values.values())
       or any(values.get(k,[''])[0] for k in ['OrgNameOrDBAName','OrganizationPurposeCategoryValue','City','StateCode','ZipCode','CountyId'])):return
   from deployment.search_history import SourceQueryReceipt
   observed['request']=request
   observed['receipt']=SourceQueryReceipt(run,{'state':'OH','operation':'search','ein':run.ein,
    'filter_label':'EIN Equals; name/category/location blank','source_kind':'state_portal','url':url})
  except Exception:pass
 def responded(response):
  try:
   if observed['request'] is None or response.request!=observed['request']:return
   observed['receipt'].received(response.status);observed['response_ok']=response.status==200
   page.remove_listener('request',requested);page.remove_listener('response',responded)
  except Exception:pass
 page.on('request',requested);page.on('response',responded)
 return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_prepare:1177:1:return',(observed))

def capture_owned_oh_empty(run,page,observed,deadline):
 """Original already-completed exact-EIN empty table, never an initial blank form."""
 if (run is None or run.state!='OH' or not observed or not workflow_call('deployment/source_visual_adapters.py:capture_owned_oh_empty:1181:59:get',observed.get,locals(), 'response_ok')
     or workflow_call('deployment/source_visual_adapters.py:capture_owned_oh_empty:1182:8:get',observed.get,locals(), 'receipt') is None or getattr(run,'oh_empty_captured',False)):return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_empty:1182:83:return',None)
 start=time.perf_counter();fact={'adapter':'OH-existing-completed-EIN-empty','outcome':'not_started',
  'new_queries':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 url='https://charitableregistration.ohioago.gov/Charities/ResearchCharities'
 try:
  if time.monotonic()+3>=deadline:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_empty:1187:69:return',None)
  u=urlsplit(page.url)
  if (u.scheme!='https' or u.netloc!='charitableregistration.ohioago.gov'
      or u.path!='/Charities/ResearchCharities' or u.query or u.fragment not in {'','results'}):
   fact['outcome']='wrong_source';return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_empty:1191:34:return',None)
  fields=workflow_call('deployment/source_visual_adapters.py:capture_owned_oh_empty:1192:9:evaluate',page.evaluate,locals(), OH_EMPTY_FIELDS)
  if (not fields or fields['empty'] is not True
      or re.sub(r'\D','',fields['EIN'])!=run.ein or fields['ddlEINFilterCriteriaList']!='3'
      or any(fields[k] for k in fields if k not in {'EIN','ddlEINFilterCriteriaList','empty'})):
   fact['outcome']='empty_criteria_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_empty:1196:46:return',None)
  text=workflow_call('deployment/source_visual_adapters.py:capture_owned_oh_empty:1197:7:inner_text',page.inner_text,locals(), 'body',timeout=400)
  if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):
   fact['outcome']='source_verification_pending';return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_empty:1199:49:return',None)
  entries=[r for r in getattr(run,'search_history_receipts',[]) if workflow_call('deployment/source_visual_adapters.py:capture_owned_oh_empty:1200:67:get',r.get,locals(), 'query_id')==observed['receipt'].query_id]
  if len(entries)!=1:fact['outcome']='issued_receipt_missing';return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_empty:1201:62:return',None)
  entries[0].update(outcome='Completed source response',completed_at=time.time(),reported_at=time.time(),returned_rows=0,observation_kind='validated_visual_response')
  begin=time.perf_counter();raw=workflow_call('deployment/source_visual_adapters.py:capture_owned_oh_empty:1203:32:screenshot',page.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=1000)
  fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
  if page.url!=u.geturl() or workflow_call('deployment/source_visual_adapters.py:capture_owned_oh_empty:1205:29:evaluate',page.evaluate,locals(), OH_EMPTY_FIELDS)!=fields or workflow_call('deployment/source_visual_adapters.py:capture_owned_oh_empty:1205:71:inner_text',page.inner_text,locals(), 'body',timeout=400)!=text:
   fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_empty:1206:51:return',None)
  if time.monotonic()+1>=deadline:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_owned_oh_empty:1207:79:return',None)
  before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_owned_oh_empty:1208:28:document',run.document,locals(), page.url,raw,'image',text)
  if len(run.documents)>before:
   run.oh_empty_captured=True
   if not hasattr(run,'oh_validated_empty_images'):run.oh_validated_empty_images=set()
   run.oh_validated_empty_images.add(hashlib.sha256(raw).hexdigest());fact['outcome']='captured'
  else:fact['outcome']='capture_failed'
 except Exception as exc:
  fact['outcome']='owned_empty_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:fact['total_ms']=round((time.perf_counter()-start)*1000,2)


def completed_visual_name_receipt(run,name,url,issued,label,count):
 """Bind a validated original UI response to its actual activation, once."""
 def matches(query,stamp):
  try:return stamp>=issued and query.get('state')==run.state and query.get('name')==name and urlsplit(query.get('url','')).hostname==urlsplit(url).hostname
  except (TypeError,ValueError):return False
 found=[r for r in getattr(run,'search_history_receipts',[]) if matches(r.get('query',{}),r.get('issued_at',0))]
 if found:
  found[-1].update(outcome='Completed source response',completed_at=time.time(),reported_at=time.time(),returned_rows=count,observation_kind='validated_visual_response');found[-1]['query']['filter_label']=label;return
 for pending in getattr(run,'search_history_pending',[]):
  for receipts in pending.values():
   for receipt in receipts:
    if matches(receipt.query,receipt.issued):receipt.query['filter_label']=label;receipt.complete(count);return
 # Some public widgets do not expose their name in recognizable transport
 # fields. Only a validated original UI response authorizes this fallback.
 from deployment.search_history import SourceQueryReceipt
 receipt=SourceQueryReceipt(run,{'state':run.state,'operation':'search','name':name,'filter_label':label,'source_kind':'state_portal','url':url});receipt.issued=issued;receipt.complete(count)

def capture_owned_hi_empty(run,name,fein,page,remaining,issued,response=None):
 """Original completed HI warning, during the existing validated response."""
 if (run is None or run.state!='HI' or remaining<5 or not isinstance(name,str) or not isinstance(fein,str)
     or page.url!='https://charity.ehawaii.gov/charity/search.html'):return trace_return('deployment/source_visual_adapters.py:capture_owned_hi_empty:1239:69:return',None)
 digits=lambda value:re.sub(r'\D','',value)
 if not (fein and digits(fein)==run.ein or not fein and name and name in getattr(run,'known_names',[run.name])):return trace_return('deployment/source_visual_adapters.py:capture_owned_hi_empty:1241:112:return',None)
 started=time.perf_counter();fact={'adapter':'HI-owned-completed-empty-warning','outcome':'not_started','capture_ms':0,'total_ms':0,'extra_registry_queries':0};run.visual_adapter_facts.append(fact)
 try:
  warning=page.locator('#orgWarning')
  if (workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1245:6:input_value',page.locator('#name').input_value,locals(), timeout=400)!=name or digits(workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1245:69:input_value',page.locator('#fein').input_value,locals(), timeout=400))!=digits(fein)
      or workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1246:9:input_value',page.locator('#nameFilter').input_value,locals(), timeout=400)!='CONTAINS'
      or not workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1247:13:is_visible',page.locator('#searchOrganizationWarning').is_visible,locals()) or not workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1247:76:is_visible',warning.is_visible,locals())
      or not workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1248:13:inner_text',warning.inner_text,locals(), timeout=400).strip().startswith('The charitable organization you entered is not registered in our system.')
      or workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1249:9:is_visible',page.locator('#org-results-container').is_visible,locals())
      or any(workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1250:13:input_value',page.locator('#'+field).input_value,locals(), timeout=400) for field in ['city','country','state','zipCode','registrationStatus','inactivityReason','registrationType'])):fact['outcome']='empty_query_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_owned_hi_empty:1250:213:return',None)
  label='Contains; '+('FEIN '+fein if fein else 'FEIN blank')+'; other search filters blank'
  query={'state':'HI','operation':'search','filter_label':label,'source_kind':'state_portal','url':'https://charity.ehawaii.gov/charity/search-charity.json'}
  query.update({'name':name} if name else {'ein':digits(fein)})
  if response is not None:
   from deployment.search_observation import complete_hi_empty_receipt
   complete_hi_empty_receipt(run,response,name,fein,issued)
  else:
   # Upgrade only the actual name transport receipt issued by this same action.
   # EIN-only searches have no passive name receipt; retain their actual issue clock.
   found=[r for r in getattr(run,'search_history_receipts',[]) if workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1260:66:get',r.get,locals(), 'issued_at',0)>=issued and workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1260:99:get',workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1260:99:get',r.get,locals(), 'query',{}).get,locals(), 'name','')==name and (name or workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1260:151:get',workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1260:151:get',r.get,locals(), 'query',{}).get,locals(), 'ein')==digits(fein)) and urlsplit(workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1260:208:get',workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1260:208:get',r.get,locals(), 'query',{}).get,locals(), 'url','')).hostname=='charity.ehawaii.gov']
   if found:
    entry=found[-1];entry['query'].update(query);entry.update(outcome='Completed source response',completed_at=time.time(),reported_at=time.time(),returned_rows=0,observation_kind='validated_visual_response')
   else:
    from deployment.search_history import SourceQueryReceipt
    receipt=SourceQueryReceipt(run,query);receipt.issued=issued;receipt.complete(0)
  if getattr(run,'hi_empty_original_saved',False):fact['outcome']='receipt_validated_original_already_saved';return trace_return('deployment/source_visual_adapters.py:capture_owned_hi_empty:1266:109:return',None)
  before=len(run.documents);begin=time.perf_counter();workflow_call('deployment/source_visual_adapters.py:capture_owned_hi_empty:1267:54:page',run.page,locals(), page);fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
  if len(run.documents)>before:
   run.hi_empty_original_saved=True;run.validated_negative_visual_urls.update(d[0] for d in run.documents[before:]);run.hi_validated_empty_images={hashlib.sha256(d[1]).hexdigest() for d in run.documents[before:]};fact['outcome']='captured'
  else:fact['outcome']='capture_failed'
 except Exception as exc:fact['outcome']='owned_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:fact['total_ms']=round((time.perf_counter()-started)*1000,2)


def capture_owned_wv_empty(run,query_name,page,body,remaining,issued):
 """Keep a genuine empty alert before the original search loop navigates on."""
 if (run is None or run.state!='WV' or getattr(run,'wv_empty_original_saved',False)
     or not isinstance(query_name,str) or not query_name or remaining<5.0
     or page.url!='https://erls.wvsos.gov/OnlineCharitiesSearch/Search'
     or not re.search(r'No records found with your search criteria\.',body,re.I)):return trace_return('deployment/source_visual_adapters.py:capture_owned_wv_empty:1280:82:return',None)
 started=time.perf_counter();fact={'adapter':'WV-owned-existing-empty-alert','phase':'binding','outcome':'not_started','capture_ms':0,'total_ms':0,'extra_registry_queries':0};run.visual_adapter_facts.append(fact)
 try:
  prefix='#CharitiesSearch-CharitiesSearch_'
  if (workflow_call('deployment/source_visual_adapters.py:capture_owned_wv_empty:1284:6:input_value',page.locator('#ddlType').input_value,locals(), timeout=400)!='1' or workflow_call('deployment/source_visual_adapters.py:capture_owned_wv_empty:1284:64:input_value',page.locator(prefix+'txtName').input_value,locals(), timeout=400)!=query_name
      or workflow_call('deployment/source_visual_adapters.py:capture_owned_wv_empty:1285:9:count',page.get_by_text('No records found with your search criteria.',exact=True).count,locals())!=1
      or not workflow_call('deployment/source_visual_adapters.py:capture_owned_wv_empty:1286:13:is_visible',page.get_by_text('No records found with your search criteria.',exact=True).is_visible,locals())
      or any(workflow_call('deployment/source_visual_adapters.py:capture_owned_wv_empty:1287:13:input_value',page.locator(selector).input_value,locals(), timeout=400) for selector in [prefix+'txtID','#CharitiesSearch_CharitiesSearch_txtdbaName',prefix+'txtState',prefix+'txtCity',prefix+'txtExpirationStartDate',prefix+'txtExpirationEndDate','#ddlCounty','#ddlStatus','#ddlCharityRatingWV','#ddlCharityRatingNational'])):fact['outcome']='empty_criteria_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_owned_wv_empty:1287:358:return',None)
  completed_visual_name_receipt(run,query_name,page.url,issued,'Charity Name; Type CHARITABLE ORGANIZATIONS; other filters blank; source name comparison not recorded',0)
  before=len(run.documents);begin=time.perf_counter();fact['phase']='capture';workflow_call('deployment/source_visual_adapters.py:capture_owned_wv_empty:1289:78:page',run.page,locals(), page);fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
  if len(run.documents)>before:run.wv_empty_original_saved=True;fact['outcome']='captured'
  else:fact['outcome']='capture_failed'
 except Exception as exc:fact['outcome']='owned_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def capture_negative_wv_source(master,result,run,deadline):
 """Actual WV no-record alert, with its original charity/name criteria."""
 if (run is None or run.state!='WV' or workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1297:39:get',result.get,locals(), 'state')!='WV' or workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1297:68:get',result.get,locals(), 'status')!='Not Registered'
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1298:8:get',result.get,locals(), 'success') is not True or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1298:65:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1299:8:get',result.get,locals(), 'matched_registry_name') or workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1299:47:get',result.get,locals(), 'matched_registry_identifier')
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1300:8:get',result.get,locals(), 'source_url')!='https://erls.wvsos.gov/OnlineCharitiesSearch/Search'
     or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_negative_wv_source:1301:56:return',None)
 if not any(workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1302:12:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1302:12:get',r.get,locals(), 'query',{}).get,locals(), 'name')==run.name and workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1302:56:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1302:56:get',r.get,locals(), 'query',{}).get,locals(), 'state')=='WV' for r in getattr(run,'search_history_receipts',[])):return trace_return('deployment/source_visual_adapters.py:capture_negative_wv_source:1302:145:return',None)
 run.negative_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'WV-original-completed-empty-alert','phase':'admission','outcome':'not_started','navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_wv_source:1307:52:return',None)
  stop=time.monotonic()+min(8.0,remaining);held=workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1308:48:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_negative_wv_source:1309:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1311:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1100},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1315:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1315:48:new_page',context.new_page,locals());begin=time.perf_counter();fact['phase']='navigation'
    response=workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1316:13:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)));fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_wv_source:1317:120:return',None)
    begin=time.perf_counter();fact['phase']='visual_name_query';prefix='#CharitiesSearch-CharitiesSearch_'
    workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1319:4:select_option',page.locator('#ddlType').select_option,locals(), '1',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1320:4:fill',page.locator(prefix+'txtName').fill,locals(), run.name,timeout=max(1,int((stop-time.monotonic()-1)*1000)));issued=time.time()
    workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1321:4:click',page.locator(prefix+'btnSearch').click,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1322:4:wait_for',page.get_by_text('No records found with your search criteria.',exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if (page.url!=result['source_url'] or workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1323:42:count',page.get_by_text('No records found with your search criteria.',exact=True).count,locals())!=1
        or workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1324:11:input_value',page.locator('#ddlType').input_value,locals(), timeout=400)!='1' or workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1324:69:input_value',page.locator(prefix+'txtName').input_value,locals(), timeout=400)!=run.name
        or any(workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1325:15:input_value',page.locator(selector).input_value,locals(), timeout=400) for selector in [prefix+'txtID','#CharitiesSearch_CharitiesSearch_txtdbaName',prefix+'txtState',prefix+'txtCity',prefix+'txtExpirationStartDate',prefix+'txtExpirationEndDate','#ddlCounty','#ddlStatus','#ddlCharityRatingWV','#ddlCharityRatingNational'])):fact['outcome']='empty_criteria_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_negative_wv_source:1325:360:return',None)
    completed_visual_name_receipt(run,run.name,result['source_url'],issued,'Charity Name; Type CHARITABLE ORGANIZATIONS; other filters blank; source name comparison not recorded',0)
    fact['visual_name_queries']=1;fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_wv_source:1328:66:return',None)
    before=len(run.documents);begin=time.perf_counter();fact['phase']='capture';workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1329:80:capture',context.capture,locals());fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1331:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1332:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_negative_wv_source:1335:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def capture_negative_ct_source(master,result,run,deadline):
 """Photograph one actual issued name's original CT zero-result view."""
 if (run is None or run.state!='CT' or workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1340:39:get',result.get,locals(), 'state')!='CT' or workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1340:68:get',result.get,locals(), 'status')!='Not Registered'
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1341:8:get',result.get,locals(), 'success') is not True or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1341:65:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1342:8:get',result.get,locals(), 'matched_registry_name') or workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1342:47:get',result.get,locals(), 'matched_registry_identifier')
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1343:8:get',result.get,locals(), 'source_url')!='https://www.elicense.ct.gov/lookup/licenselookup.aspx'
     or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_negative_ct_source:1344:56:return',None)
 receipts=[r for r in getattr(run,'search_history_receipts',[]) if workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1345:67:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1345:67:get',r.get,locals(), 'query',{}).get,locals(), 'state')=='CT'
           and workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1346:15:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1346:15:get',r.get,locals(), 'query',{}).get,locals(), 'operation')=='search' and workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1346:64:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1346:64:get',r.get,locals(), 'query',{}).get,locals(), 'source_kind')=='state_portal'
           and workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1347:15:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1347:15:get',r.get,locals(), 'query',{}).get,locals(), 'url')==result['source_url'] and workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1347:70:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1347:70:get',r.get,locals(), 'query',{}).get,locals(), 'name')==run.name]
 if not receipts:return trace_return('deployment/source_visual_adapters.py:capture_negative_ct_source:1348:17:return',None)
 run.negative_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'CT-original-completed-empty-view','phase':'admission','outcome':'not_started','navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_ct_source:1353:52:return',None)
  stop=time.monotonic()+min(8.0,remaining);held=workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1354:48:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_negative_ct_source:1355:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1357:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1400},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1361:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1361:48:new_page',context.new_page,locals());fact['phase']='navigation';begin=time.perf_counter()
    response=workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1362:13:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)));fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_ct_source:1363:120:return',None)
    prefix='#ctl00_MainContentPlaceHolder_ucLicenseLookup_';fact['phase']='visual_name_query';begin=time.perf_counter()
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1365:4:select_option',page.locator(prefix+'ctl03_ddCredPrefix').select_option,locals(), 'CHR',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1366:4:fill',page.locator(prefix+'ctl03_tbDBA_Contact').fill,locals(), run.name,timeout=max(1,int((stop-time.monotonic()-1)*1000)));issued=time.time()
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1367:4:click',page.locator(prefix+'btnLookup').click,locals(), timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1368:4:wait_for',page.get_by_text('Showing 0 result(s).',exact=True).wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if (workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1369:8:count',page.get_by_text('Showing 0 result(s).',exact=True).count,locals())!=1
        or workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1370:11:input_value',page.locator(prefix+'ctl03_tbDBA_Contact').input_value,locals(), timeout=400)!=run.name
        or workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1371:11:input_value',page.locator(prefix+'ctl03_ddCredPrefix').input_value,locals(), timeout=400)!='CHR'
        or workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1372:11:count',page.locator('forge-card').count,locals())!=0):fact['outcome']='empty_view_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_negative_ct_source:1372:89:return',None)
    observed=[r for r in getattr(run,'search_history_receipts',[]) if workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1373:70:get',r.get,locals(), 'issued_at',0)>=issued
              and workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1374:18:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1374:18:get',r.get,locals(), 'query',{}).get,locals(), 'name')==run.name and workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1374:62:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1374:62:get',r.get,locals(), 'query',{}).get,locals(), 'url')==result['source_url']]
    if not observed:fact['outcome']='visual_query_receipt_missing';return trace_return('deployment/source_visual_adapters.py:capture_negative_ct_source:1375:67:return',None)
    observed[-1].update(outcome='Completed source response',completed_at=time.time(),reported_at=time.time(),returned_rows=0,observation_kind='validated_visual_response')
    observed[-1]['query']['filter_label']='Business Name / DBA / Nickname; License Type CHR; source name comparison not recorded'
    fact['visual_name_queries']=1;fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    text=workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1379:9:inner_text',page.inner_text,locals(), 'body',timeout=400)
    if re.search('verify you are human|user validation required|access denied|just a moment|Searching, please wait',text,re.I):fact['outcome']='source_still_pending';return trace_return('deployment/source_visual_adapters.py:capture_negative_ct_source:1380:166:return',None)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_ct_source:1381:66:return',None)
    fact['phase']='capture';before=len(run.documents);begin=time.perf_counter();workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1382:80:capture',context.capture,locals());fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
    if len(run.documents)>before:run.validated_negative_visual_urls.update(d[0] for d in run.documents[before:]);fact['outcome']='captured'
    else:fact['outcome']='capture_failed'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1386:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1387:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_negative_ct_source:1390:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

CA_PUBLIC_SEARCH='https://ca-rcf.evokeplatform.com/app/publicPortal/verification'

def ca_empty_response_bound(response,criterion):
 """Validate the exact anonymous UI request; do not infer zero from a shell."""
 try:
  u=urlsplit(response.url)
  if (u.scheme!='https' or u.hostname!='ca-rcf.evokeplatform.com' or u.port not in (None,443)
      or u.username or u.password or u.path!='/api/data/objects/entity/instances'
      or response.status!=200 or response.request.method!='GET'):return False
  params=parse_qs(u.query);filters=params.get('filter',[])
  if len(filters)!=1:return False
  plan=json.loads(filters[0]);clauses=plan['where']['and']
  if plan.get('skip')!=0 or plan.get('limit')!=200 or len(clauses)!=2 or clauses[0]!={'entityStatus':{'neq':'Not Listed'}}:return False
  fields=clauses[1]['or']
  if not isinstance(fields,list) or not 1<=len(fields)<=30:return False
  seen=[]
  for item in fields:
   if not isinstance(item,dict) or len(item)!=1:return False
   label,term=next(iter(item.items()))
   if not isinstance(label,str) or term!={'like':criterion,'options':'i'}:return False
   seen.append(label)
  return 'fein' in seen and len(seen)==len(set(seen)) and response.json()==[]
 except (ValueError,KeyError,TypeError,AttributeError):return False

def capture_negative_ca_source(master,result,run,deadline):
 """One original CA global-search view, with a separately recorded EIN term."""
 if (run is None or run.state!='CA' or workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1419:39:get',result.get,locals(), 'state')!='CA'
     or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1420:28:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1421:8:get',result.get,locals(), 'status')!='Not Registered' or workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1421:50:get',result.get,locals(), 'success') is not True
     or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_negative_ca_source:1422:56:return',None)
 run.negative_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None;receipt=None
 fact={'adapter':'CA-original-completed-empty-global-search','phase':'admission','outcome':'not_started','extra_registry_queries':0,'navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_ca_source:1427:52:return',None)
  stop=time.monotonic()+min(18,remaining);held=workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1428:47:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_negative_ca_source:1429:61:return',None)
  criterion=run.ein[:2]+'-'+run.ein[2:]
  with master.checker.sync_playwright() as pw:
   phase_start=time.perf_counter();browser=workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1432:43:launch_lookup_browser',master.launch_lookup_browser,locals(), pw,headless=True);fact['browser_acquire_ms']=round((time.perf_counter()-phase_start)*1000,2)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    phase_start=time.perf_counter();context=workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1436:44:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1436:80:new_page',context.new_page,locals());fact['context_start_ms']=round((time.perf_counter()-phase_start)*1000,2);timeout=lambda:max(1,int((stop-time.monotonic()-1)*1000))
    begin=time.perf_counter();fact['phase']='navigation';response=workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1437:66:goto',page.goto,locals(), CA_PUBLIC_SEARCH,wait_until='domcontentloaded',timeout=timeout())
    if response is None or response.status!=200 or page.url!=CA_PUBLIC_SEARCH:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_ca_source:1438:116:return',None)
    field=page.get_by_placeholder('Search...',exact=True);workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1439:58:wait_for',field.wait_for,locals(), state='visible',timeout=timeout());fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    from deployment.search_history import begin_source_query
    receipt=begin_source_query('CA',criterion,'Global search across public fields, including FEIN; case-insensitive term match',CA_PUBLIC_SEARCH)
    if receipt:receipt.query.pop('name',None);receipt.query['ein']=criterion
    fact['phase']='visual_EIN_query';begin=time.perf_counter()
    def same_query(r):
     if urlsplit(r.url).path!='/api/data/objects/entity/instances':return False
     try:return criterion in parse_qs(urlsplit(r.url).query).get('filter',[''])[0]
     except ValueError:return False
    with page.expect_response(same_query,timeout=timeout()) as pending:
     workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1449:5:fill',field.fill,locals(), criterion,timeout=timeout());workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1449:45:press',field.press,locals(), 'Enter',timeout=timeout());fact['extra_registry_queries']=1
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1450:4:wait_for',page.get_by_text('No Data',exact=True).wait_for,locals(), state='visible',timeout=timeout())
    if not ca_empty_response_bound(pending.value,criterion):fact['outcome']='empty_response_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_ca_source:1451:102:return',None)
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1452:4:wait_for',page.locator('.ag-overlay-loading-center').wait_for,locals(), state='hidden',timeout=timeout())
    fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    if receipt:receipt.complete(0,rows=[])
    text=workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1455:9:inner_text',page.inner_text,locals(), 'body',timeout=400)
    if workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1456:7:input_value',field.input_value,locals(), timeout=300)!=criterion or workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1456:52:count',page.locator('.ag-row').count,locals())!=0 or 'Registry of Charities and Fundraisers' not in text:fact['outcome']='displayed_criteria_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_ca_source:1456:188:return',None)
    begin=time.perf_counter();raw=workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1457:34:screenshot',page.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=min(1000,timeout()))
    if page.url!=CA_PUBLIC_SEARCH or workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1458:37:input_value',field.input_value,locals(), timeout=300)!=criterion or workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1458:82:inner_text',page.inner_text,locals(), 'body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_negative_ca_source:1458:172:return',None)
    before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1459:30:document',run.document,locals(), CA_PUBLIC_SEARCH,raw,'image',text,note='Original California empty public global-search view for displayed FEIN term '+criterion+'. The separate history records this additional visual query; this image alone does not establish all name searches.')
    if len(run.documents)>before:
     run.ca_validated_empty_images=getattr(run,'ca_validated_empty_images',set());run.ca_validated_empty_images.add(hashlib.sha256(raw).hexdigest());fact['outcome']='captured'
    else:fact['outcome']='image_admission_rejected'
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
   finally:
    phase_start=time.perf_counter()
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1466:50:close',context.close,locals())
    fact['context_close_ms']=round((time.perf_counter()-phase_start)*1000,2)
    phase_start=time.perf_counter()
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1469:27:close',browser.close,locals())
    fact['browser_close_ms']=round((time.perf_counter()-phase_start)*1000,2)
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:200]
 finally:
  if receipt:receipt.incomplete()
  if held:workflow_call('deployment/source_visual_adapters.py:capture_negative_ca_source:1474:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def capture_negative_search(master,result,run,deadline):
 if run is not None and run.state=='VA':return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1478:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1478:47:capture_negative_va_source',capture_negative_va_source,locals(), master,result,run,deadline)))
 """Known completed-negative source views; never invent a page or zero count."""
 if run is not None and run.state=='CA':return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1480:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1480:47:capture_negative_ca_source',capture_negative_ca_source,locals(), master,result,run,deadline)))
 if run is not None and run.state=='NJ':return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1481:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1481:47:capture_negative_nj_source',capture_negative_nj_source,locals(), master,result,run,deadline)))
 if run is not None and run.state=='RI':return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1482:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1482:47:capture_negative_ri_source',capture_negative_ri_source,locals(), master,result,run,deadline)))
 if run is not None and run.state=='LA':return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1483:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1483:47:capture_selected_la_source',capture_selected_la_source,locals(), master,result,run,deadline,negative=True)))
 if run is not None and run.state=='CT':return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1484:40:return',(workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1484:47:capture_negative_ct_source',capture_negative_ct_source,locals(), master,result,run,deadline)))
 if (run is None or run.state!='WI' or workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1485:39:get',result.get,locals(), 'state')!='WI'
     or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1486:28:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1487:8:get',result.get,locals(), 'status')!='Not Registered' or workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1487:50:get',result.get,locals(), 'success') is not True
     or not getattr(run,'source_search_hint',None) or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1488:102:return',None)
 hint=run.source_search_hint;u=urlsplit(hint['url']);pairs=parse_qsl(u.query,keep_blank_values=True);params=dict(pairs)
 if (u.scheme!='https' or u.hostname!='apps.dfi.wi.gov' or u.path!='/ice/berg/Registration/OrgCredentialSearchResults.aspx'
     or len(pairs)!=3 or set(params)!={'CredentialType','LicenseNumber','FirmName'}
     or params['CredentialType']!='800' or params['LicenseNumber'] or params['FirmName']!=hint['name']):return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1492:104:return',None)
 run.negative_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'WI-completed-negative-view','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 held=False;context=browser=None
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1498:52:return',None)
  stop=time.monotonic()+min(8.0,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1500:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1501:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1503:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1280,'height':900},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1507:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1507:48:new_page',context.new_page,locals());begin=time.perf_counter();issued=time.time()
    response=workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1508:13:goto',page.goto,locals(), hint['url'],wait_until='domcontentloaded',timeout=max(1,int(min(4,stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=hint['url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1510:111:return',None)
    text=workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1511:9:inner_text',page.inner_text,locals(), 'body',timeout=400)
    if (not re.search(r'(?:There are )?no query results',text,re.I)
        or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
     fact['outcome']='not_a_completed_empty_view';return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1514:50:return',None)
    # Upgrade only the observed request issued by this exact visual GET.
    receipts=[r for r in getattr(run,'search_history_receipts',[]) if workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1516:70:get',r.get,locals(), 'issued_at',0)>=issued
              and workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1517:18:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1517:18:get',r.get,locals(), 'query',{}).get,locals(), 'name')==hint['name']
              and urlsplit(workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1518:27:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1518:27:get',r.get,locals(), 'query',{}).get,locals(), 'url','')).path==u.path]
    if receipts:
     receipts[-1].update(outcome='Completed source response',completed_at=time.time(),reported_at=time.time(),returned_rows=0,observation_kind='validated_visual_response')
    else:run.search_history_overflow=True
    fact['visual_query_receipt_bound']=bool(receipts)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_search:1523:66:return',None)
    before=len(run.documents);begin=time.perf_counter();workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1524:56:capture',context.capture,locals());fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
    if len(run.documents)>before:
     run.validated_negative_visual_urls.update(d[0] for d in run.documents[before:]);fact['outcome']='captured'
    else:fact['outcome']='capture_failed'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1529:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1530:27:close',browser.close,locals())
 except Exception:fact['outcome']='source_visual_unavailable'
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_negative_search:1533:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)


RI_SEARCH_ROOT='https://ridbrprod-search.state-reg-eastern.tylerapp.com/'
RI_SEARCH_API='https://ridbrprod.state-reg-eastern.tylerapp.com/licensing/api/endpoints/v1/portal/search'
RI_EMPTY_MESSAGE='No search results were found. Please refine your search criteria and try again.'
RI_FORM_FIELDS='''()=>Object.fromEntries([...document.querySelectorAll('input')].map(x=>{
 const label=[...document.querySelectorAll('label')].find(y=>y.htmlFor===x.id);
 return [label?.innerText?.trim()||'',x.value];
}))'''

def capture_ri_completed_empty(run,page,response,query,issued,deadline):
 """Photograph only this genuine submitted request's fully empty RI result."""
 if run is None or run.state!='RI' or deadline-time.monotonic()<1:return trace_return('deployment/source_visual_adapters.py:capture_ri_completed_empty:1547:66:return',(False))
 try:
  req=response.request;payload=req.post_data_json;data=workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1549:55:json',response.json,locals())
  if (response.status!=200 or response.url!=RI_SEARCH_API or req.method!='POST'
      or workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1551:9:get',payload.get,locals(), 'type')!='credential' or workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1551:46:get',payload.get,locals(), 'start')!=0
      or workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1552:9:get',payload.get,locals(), 'rows')!=10 or workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1552:36:get',payload.get,locals(), 'appliedFilters') not in (None,[])
      or workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1553:9:get',workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1553:9:get',payload.get,locals(), 'formRequest',{}).get,locals(), 'values')!={'organizationName':query,'licenseType':'Charitable Organization'}
      or type(workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1554:14:get',data.get,locals(), 'resultCount')) is not int or data['resultCount']!=0 or workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1554:79:get',data.get,locals(), 'results')!=[]
      or workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1555:9:get',workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1555:9:get',data.get,locals(), 'message',{}).get,locals(), 'errors')
      or workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1556:9:get',data.get,locals(), 'appliedFilters')!=['licenseType:Charitable Organization']
      or [workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1557:10:get',x.get,locals(), 'label') for x in workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1557:34:get',data.get,locals(), 'searchChips',[])]!=[query]
      or page.url!=RI_SEARCH_ROOT+'search'):return trace_return('deployment/source_visual_adapters.py:capture_ri_completed_empty:1558:44:return',(False))
  empty=page.get_by_role('heading',name=RI_EMPTY_MESSAGE,exact=True)
  if workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1560:5:count',empty.count,locals())!=1 or not workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1560:29:is_visible',empty.is_visible,locals()):return trace_return('deployment/source_visual_adapters.py:capture_ri_completed_empty:1560:48:return',(False))
  text=workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1561:7:inner_text',page.inner_text,locals(), 'body',timeout=400)
  if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):return trace_return('deployment/source_visual_adapters.py:capture_ri_completed_empty:1562:102:return',(False))
  completed_visual_name_receipt(run,query,RI_SEARCH_API,issued,'Organization Name; Credential Type Charitable Organization; other filters blank; source name comparison not recorded',0)
  before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_ri_completed_empty:1564:28:page',run.page,locals(), page)
  if len(run.documents)==before:return trace_return('deployment/source_visual_adapters.py:capture_ri_completed_empty:1565:32:return',(False))
  run.validated_negative_visual_urls.update(d[0] for d in run.documents[before:])
  run.ri_validated_empty_images={hashlib.sha256(d[1]).hexdigest() for d in run.documents[before:]}
  return trace_return('deployment/source_visual_adapters.py:capture_ri_completed_empty:1568:2:return',(True))
 except Exception:return trace_return('deployment/source_visual_adapters.py:capture_ri_completed_empty:1569:18:return',(False))

def capture_negative_ri_source(master,result,run,deadline):
 """One visual replay of an already completed empty RI name, without status changes."""
 if (run is None or run.state!='RI' or workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1573:39:get',result.get,locals(), 'state')!='RI'
     or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1574:28:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1575:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1575:45:get',result.get,locals(), 'status')!='Not Registered'
     or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_negative_ri_source:1576:56:return',None)
 receipts=[r for r in getattr(run,'search_history_receipts',[]) if workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1577:67:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1577:67:get',r.get,locals(), 'query',{}).get,locals(), 'state')=='RI'
           and workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1578:15:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1578:15:get',r.get,locals(), 'query',{}).get,locals(), 'url')==RI_SEARCH_API
           and isinstance(workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1579:26:get',workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1579:26:get',r.get,locals(), 'query',{}).get,locals(), 'name'),str) and r['query']['name'].strip()
           and workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1580:15:get',r.get,locals(), 'outcome')=='Completed source response' and type(workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1580:70:get',r.get,locals(), 'returned_rows')) is int and r['returned_rows']==0]
 if not receipts:return trace_return('deployment/source_visual_adapters.py:capture_negative_ri_source:1581:17:return',None)
 query=receipts[0]['query']['name'];run.negative_visual_attempted=True
 started=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'RI-completed-negative-view','outcome':'not_started','phase':'admission','extra_registry_queries':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_ri_source:1587:52:return',None)
  stop=time.monotonic()+min(8,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1589:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_negative_ri_source:1590:61:return',None)
  with master.checker.sync_playwright() as pw:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1592:11:launch_lookup_browser',master.launch_lookup_browser,locals(), pw,headless=True)
   try:
    options={'viewport':{'width':1280,'height':900},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1596:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1596:48:new_page',context.new_page,locals())
    timeout=lambda:max(1,int(min(4,stop-time.monotonic()-1)*1000))
    fact['phase']='navigation';response=workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1598:40:goto',page.goto,locals(), RI_SEARCH_ROOT,wait_until='domcontentloaded',timeout=timeout())
    if response is None or response.status!=200 or page.url!=RI_SEARCH_ROOT:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_ri_source:1599:114:return',None)
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1600:4:wait_for',page.get_by_role('button',name='Search',exact=True).wait_for,locals(), timeout=timeout())
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1601:4:fill',page.get_by_label('Organization Name',exact=True).fill,locals(), query,timeout=timeout())
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1602:4:fill',page.get_by_label('Credential Type',exact=True).fill,locals(), 'Charitable Organization',timeout=timeout())
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1603:4:click',page.get_by_role('option',name='Charitable Organization',exact=True).click,locals(), timeout=timeout())
    fields=workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1604:11:evaluate',page.evaluate,locals(), RI_FORM_FIELDS)
    expected={k:'' for k in ['Last Name','First Name','Organization Name','Board','Credential Type','Credential Number','Credential Status','City','State','Zip Code']}
    expected.update({'Organization Name':query,'Credential Type':'Charitable Organization'})
    if fields!=expected:fact['outcome']='criteria_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_ri_source:1607:60:return',None)
    fact['phase']='submitted_query';issued=time.time()
    with page.expect_response(lambda r:r.url==RI_SEARCH_API and r.request.method=='POST',timeout=timeout()) as pending:
     workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1610:5:click',page.get_by_role('button',name='Search',exact=True).click,locals(), timeout=timeout());fact['extra_registry_queries']=1
    workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1611:4:wait_for',page.get_by_role('heading',name=RI_EMPTY_MESSAGE,exact=True).wait_for,locals(), timeout=timeout())
    fact['phase']='binding_and_capture';begin=time.perf_counter()
    ok=workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1613:7:capture_ri_completed_empty',capture_ri_completed_empty,locals(), run,page,pending.value,query,issued,stop)
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);fact['outcome']='captured' if ok else 'empty_binding_rejected'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1616:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1617:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_negative_ri_source:1620:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

NJ_VISIBLE_FIELDS = '''()=>{
 const fields={};
 for(const id of ['name','crsm_federalein','accountnumber','crsm_filestanding','crsm_fiscalyearenddate_datepicker_description']) {
  const elements=document.querySelectorAll('#'+id);
  if(elements.length!==1)return null;
  const el=elements[0];if(!el.getClientRects().length)return null;
  fields[id]=el.tagName==='SELECT'?el.selectedOptions[0]?.text:el.value;
 }
 return fields;
}'''

NJ_VISIBLE_GEOMETRY = '''()=>{
 const ein=document.querySelector('#crsm_federalein'),status=document.querySelector('#crsm_filestanding');
 if(!ein||!status)return false;
 const a=ein.getBoundingClientRect(),b=status.getBoundingClientRect();
 return a.width>0&&a.height>0&&b.width>0&&b.height>0
   &&(a.right<=b.left||b.right<=a.left||a.bottom<=b.top||b.bottom<=a.top);
}'''

def capture_selected_nj_source(master,result,run,deadline):
 """Original selected NJ detail; visible input values bind pixels, not API JSON."""
 expected_ein=run.ein
 review_credential=None
 context=result.get('_worker_identity_review') or result.get('identity_review') or {}
 rows=context.get('records',context.get('candidates',[]))
 if rows:
  if len(rows)!=1 or not master.nj_conflict_review_allowed(rows[0],result.get('organization_name',''),run.ein):return
  row=rows[0];expected_ein=master.canonical_ein_digits(row['ein']);review_credential=row['identifier']
  result={**result,'success':True,'status':row.get('status',row.get('interpreted_status','Needs Review')),
          'matched_registry_identifier':row['identifier'],'matched_registry_name':row['name']}

 if (workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1644:5:get',result.get,locals(), 'state')!='NJ' or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1644:54:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1645:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1645:45:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1646:12:get',result.get,locals(), 'matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1646:99:return',None)
 identifier=str(workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1647:16:get',result.get,locals(), 'matched_registry_identifier') or '')
 hint=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1648:6:get',getattr(run,'source_detail_hints',{}).get,locals(), identifier)
 norm=lambda value:re.sub(r'[^a-z0-9]','',re.sub(r'^the\s+', '', str(value).strip(), flags=re.I).lower())
 if not hint or norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1650:21:get',hint.get,locals(), 'name'))!=norm(result['matched_registry_name']):return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1650:78:return',None)
 try:
  u=urlsplit(hint['url']);params=parse_qsl(u.query,keep_blank_values=True)
  if (u.scheme!='https' or u.hostname!='charportal.dca.njoag.gov' or u.port not in (None,443)
      or u.username or u.password or u.path!='/CHR-Public-Details-Page/' or u.fragment
      or [k for k,v in params] not in (['id','rid'],['id','rid','t'])
      or any(not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}',value) for key,value in params if key in {'id','rid'})
      or any(not re.fullmatch(r'[0-9]{10,16}',value) for key,value in params if key=='t')
      or identifier!=(review_credential or run.ein)):return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1657:30:return',None)
 except (ValueError,TypeError,KeyError):return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1658:40:return',None)
 run.selected_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'NJ-selected-original-detail','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission','local_visual_budget_ms':30000};run.visual_adapter_facts.append(fact)
 held=False;browser=context=None
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1664:52:return',None)
  stop=time.monotonic()+min(30.0,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1666:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1667:61:return',None)
  fact['phase']='playwright_start';begin=time.perf_counter()
  with master.checker.sync_playwright() as p:
   fact['playwright_start_ms']=round((time.perf_counter()-begin)*1000,2)
   fact['phase']='browser_acquire';begin=time.perf_counter();browser=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1671:69:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   fact['browser_acquire_ms']=round((time.perf_counter()-begin)*1000,2)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    fact['phase']='context_start';begin=time.perf_counter();context=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1676:68:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1676:104:new_page',context.new_page,locals())
    fact['context_start_ms']=round((time.perf_counter()-begin)*1000,2);begin=time.perf_counter();fact['phase']='navigation'
    # Required public values are present in the response HTML. Waiting for all
    # document scripts can consume the allowance before those values are read.
    # Readiness below still requires the actual visible selected fields; the
    # state deadline and capture reserve stay intact.
    response=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1682:13:goto',page.goto,locals(), hint['url'],wait_until='commit',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=hint['url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1684:111:return',None)
    fact['phase']='selected_fields_ready';begin=time.perf_counter();workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1685:68:wait_for_function',page.wait_for_function,locals(), '''({ein,name})=>{
     const n=document.querySelector('#name'),e=document.querySelector('#crsm_federalein'),r=document.querySelector('#accountnumber'),f=document.querySelector('#crsm_fiscalyearenddate_datepicker_description');
     const norm=x=>String(x).trim().replace(/^the\\s+/i,'').toLowerCase().replace(/[^a-z0-9]/g,'');
     return n&&e&&r&&f&&norm(n.value)===norm(name)&&e.value.replace(/\\D/g,'')===ein&&/^CH[0-9]+$/.test(r.value)&&(f.value||document.readyState!=='loading'&&f.hasAttribute('readonly')&&document.querySelector('#crsm_fiscalyearenddate')?.hasAttribute('readonly')&&!document.querySelector('#crsm_fiscalyearenddate')?.value);
    }''',arg={'ein':expected_ein,'name':result['matched_registry_name']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['selected_fields_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    fields=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1691:11:evaluate',page.evaluate,locals(), NJ_VISIBLE_FIELDS)
    if (not fields or norm(fields['name'])!=norm(result['matched_registry_name'])
        or re.sub(r'\D','',fields['crsm_federalein'])!=expected_ein
        or (review_credential is not None and fields['accountnumber']!=review_credential)
        or not re.fullmatch(r'CH\d+',fields['accountnumber']) or not fields['crsm_filestanding']
        or not (re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',fields['crsm_fiscalyearenddate_datepicker_description']) or fields['crsm_fiscalyearenddate_datepicker_description']=='' and master.nj_completed_future_detail(page.content(),expected_ein,fields['accountnumber']))):
     fact['outcome']='record_binding_failed';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1696:45:return',None)
    if workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1697:7:evaluate',page.evaluate,locals(), NJ_VISIBLE_GEOMETRY) is not True:fact['outcome']='selected_fields_overlap';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1697:96:return',None)
    text=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1698:9:inner_text',page.inner_text,locals(), 'body',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='source_verification_pending';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1699:150:return',None)
    size=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1700:9:evaluate',page.locator('body').evaluate,locals(), '(el)=>({width:el.scrollWidth,height:el.scrollHeight})')
    if size['width']<=0 or size['height']<=0 or size['width']*size['height']>20000000:fact['outcome']='source_size_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1701:125:return',None)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1702:66:return',None)
    fact['phase']='capture';begin=time.perf_counter();raw=workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1703:58:screenshot',page.screenshot,locals(), type='jpeg',quality=75,full_page=True,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    if page.url!=hint['url'] or workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1705:32:evaluate',page.evaluate,locals(), NJ_VISIBLE_FIELDS)!=fields or workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1705:76:evaluate',page.evaluate,locals(), NJ_VISIBLE_GEOMETRY) is not True or workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1705:126:inner_text',page.inner_text,locals(), 'body',timeout=max(1,int((stop-time.monotonic()-.5)*1000)))!=text:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1705:256:return',None)
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_selected_nj_source:1706:78:return',None)
    # Metadata describes visible original values; source pixels are never redrawn.
    bound_text=text+'\n'+'\n'.join(key+': '+value for key,value in fields.items())
    before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1709:30:document',run.document,locals(), hint['url'],raw,'image',bound_text[:20000])
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if fact['phase']=='selected_fields_ready' and 'selected_fields_ready_ms' not in fact and stop-time.monotonic()>.5:
     try:
      fact['selected_fields_at_failure']=page.locator('html').evaluate("""(root,args)=>{
       const d=root.ownerDocument,get=id=>d.querySelector('#'+id),n=get('name'),e=get('crsm_federalein'),r=get('accountnumber'),f=get('crsm_fiscalyearenddate_datepicker_description'),h=get('crsm_fiscalyearenddate');
       const norm=x=>String(x).trim().replace(/^the\\s+/i,'').toLowerCase().replace(/[^a-z0-9]/g,'');
       return {document_state:d.readyState,name_present:!!n,name_matches:!!n&&norm(n.value)===norm(args.name),ein_present:!!e,ein_matches:!!e&&e.value.replace(/\\D/g,'')===args.ein,registration_present:!!r,registration_valid:!!r&&/^CH[0-9]+$/.test(r.value),fiscal_display_present:!!f,fiscal_display_populated:!!f&&!!f.value,completed_empty_fiscal:!!f&&d.readyState!=='loading'&&f.hasAttribute('readonly')&&!!h&&h.hasAttribute('readonly')&&!h.value};
      }""",{'ein':expected_ein,'name':result['matched_registry_name']},timeout=max(1,int(min(.4,stop-time.monotonic()-.5)*1000)))
     except Exception as probe_error:fact['selected_fields_probe_error']=type(probe_error).__name__
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1712:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1713:27:close',browser.close,locals())
 except Exception as exc:
  fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc)[:800]
  if fact['phase']=='navigation':fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)

 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_selected_nj_source:1718:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)


def wv_pending_navigation_stop(observation, fact, old_stop, deadline, now):
 """Continue one outstanding selected-navigation request, never issue it twice."""
 if fact.get('navigation_continuation') or observation.get('invalid'):return None
 pending=observation.get('pending',[])
 if len(pending)!=1:return None
 req=pending[0]
 if (req.get('host')!='erls.wvsos.gov' or req.get('path') not in
     {'/OnlineCharitiesSearch/Search','/OnlineCharitiesSearch/CharitiesInformation'}
     or req.get('method')!='POST' or req.get('main_document') is not True
     or req.get('responded') is not False):return None
 # Only the exhausted original wait qualifies, not a shorter unrelated timeout.
 if not 0<=old_stop-now<=1.5:return None
 proposed=min(old_stop+15,deadline-1)
 if proposed-now<6:return None
 return proposed


def capture_selected_wv_source(master,result,run,deadline):
 """Use the visible WV ID search and actual organization-ID detail link."""
 if (workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1724:5:get',result.get,locals(), 'state')!='WV' or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1724:54:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1725:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1725:45:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1726:12:get',result.get,locals(), 'matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1726:99:return',None)
 identifier=str(workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1727:16:get',result.get,locals(), 'matched_registry_identifier') or '')
 if not re.fullmatch(r'[A-Z]?\d{1,20}',identifier) or workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1728:54:get',result.get,locals(), 'source_url')!='https://erls.wvsos.gov/OnlineCharitiesSearch/Search':return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1728:134:return',None)
 norm=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
 if any(d[2] in {'image','source_pdf'} and norm(result['matched_registry_name']) in norm(d[3]) and re.search(r'(?<!\w)'+re.escape(identifier)+r'(?!\w)',d[3]) for d in run.documents):return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1730:182:return',None)
 run.selected_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'WV-selected-credential-view','outcome':'not_started','phase':'admission','navigation_ms':0,'credential_search_ms':0,'detail_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 held=False;context=browser=None
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1736:52:return',None)
  stop=time.monotonic()+min(16.0,remaining)
  held=workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1738:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1739:61:return',None)
  with master.checker.sync_playwright() as p:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1741:11:launch_lookup_browser',master.launch_lookup_browser,locals(), p,headless=True)
   try:
    options={'viewport':{'width':1280,'height':900},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1745:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1745:48:new_page',context.new_page,locals());begin=time.perf_counter();fact['phase']='navigation'
    pending_documents={};navigation_observation={'pending':[],'invalid':False}
    def navigation_started(req):
     try:
      if req.resource_type!='document' or req.frame!=page.main_frame:return
      u=urlsplit(req.url)
      pending_documents[req]={'host':u.hostname,'path':u.path,'method':req.method,'main_document':True,'responded':False}
      if len(pending_documents)>4:navigation_observation['invalid']=True
     except Exception:navigation_observation['invalid']=True
    def navigation_response(resp):
     if resp.request in pending_documents:pending_documents[resp.request]['responded']=True
    def navigation_ended(req):pending_documents.pop(req,None)
    page.on('request',navigation_started);page.on('response',navigation_response)
    page.on('requestfinished',navigation_ended);page.on('requestfailed',navigation_ended)
    def continue_pending_navigation(exc):
     nonlocal stop
     if type(exc).__name__!='TimeoutError':raise exc
     navigation_observation['pending']=list(pending_documents.values())
     proposed=wv_pending_navigation_stop(navigation_observation,fact,stop,deadline,time.monotonic())
     fact['navigation_boundary_observation']=navigation_observation.copy()
     if proposed is None:raise exc
     fact['navigation_continuation']={'count':1,'stage':fact['phase'],'extra_cap_seconds':15,
       'extra_granted_seconds':round(proposed-stop,3),'completion_reserve_seconds':5}
     stop=proposed
    def selected_click(stage,control):
     try:workflow_call(stage,control.click,locals(),timeout=max(1,int((stop-time.monotonic()-(5 if fact.get('navigation_continuation') else 1))*1000)))
     except Exception as exc:
      continue_pending_navigation(exc)
      # The caller waits for the original selected row/detail, without another click.
    def wait_selected_navigation():
     def wait():
      workflow_call('deployment/source_visual_adapters.py:WV:selected_detail_navigation',page.wait_for_url,locals(),
       'https://erls.wvsos.gov/OnlineCharitiesSearch/CharitiesInformation',wait_until='domcontentloaded',
       timeout=max(1,int((stop-time.monotonic()-(5 if fact.get('navigation_continuation') else 1))*1000)))
     try:wait()
     except Exception as exc:
      continue_pending_navigation(exc)
      # Continue waiting for the same outstanding document; never submit again.
      wait()
    response=workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1746:13:goto',page.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-(5 if fact.get('navigation_continuation') else 1))*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1748:120:return',None)
    begin=time.perf_counter();fact['phase']='credential_search'
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1750:4:select_option',page.locator('#ddlType').select_option,locals(), '1',timeout=max(1,int((stop-time.monotonic()-(5 if fact.get('navigation_continuation') else 1))*1000)))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1751:4:fill',page.locator('#CharitiesSearch-CharitiesSearch_txtID').fill,locals(), identifier,timeout=max(1,int((stop-time.monotonic()-(5 if fact.get('navigation_continuation') else 1))*1000)))
    selected_click('deployment/source_visual_adapters.py:capture_selected_wv_source:1752:4:click',page.locator('#CharitiesSearch-CharitiesSearch_btnSearch'))
    row=page.locator('#xhtml_grid tr').filter(has=page.locator('a').filter(has_text=re.compile('^'+re.escape(identifier)+'$')))
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1754:4:wait_for',row.wait_for,locals(), state='visible',timeout=max(1,int((stop-time.monotonic()-(5 if fact.get('navigation_continuation') else 1))*1000)))
    if workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1755:7:count',row.count,locals())!=1 or norm(result['matched_registry_name']) not in norm(workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1755:75:inner_text',row.inner_text,locals(), timeout=400)):fact['outcome']='selected_row_binding_failed';return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1755:150:return',None)
    fact['credential_search_ms']=round((time.perf_counter()-begin)*1000,2);fact['visual_credential_queries']=1
    link=row.locator('a')
    if workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1758:7:count',link.count,locals())!=1 or not re.fullmatch(r'NavigateLienInfo\(\d+\)',link.get_attribute('onclick') or ''):fact['outcome']='source_detail_control_changed';return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1758:155:return',None)
    begin=time.perf_counter();fact['phase']='detail'
    selected_click('deployment/source_visual_adapters.py:capture_selected_wv_source:1760:4:click',link)
    wait_selected_navigation()
    workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1762:4:wait_for_function',page.wait_for_function,locals(), '''({id,name})=>{
      const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
      const text=document.body.innerText;
      return norm(text).includes(norm(name))&&new RegExp('ID:\\\\s*'+id+'\\\\s+Initial Registration Date:').test(text)
        &&/Expiration Date:/.test(text)&&/Status:/.test(text)&&!/Please wait\\.\\.\\./i.test(text);
    }''',arg={'id':identifier,'name':result['matched_registry_name']},timeout=max(1,int((stop-time.monotonic()-(5 if fact.get('navigation_continuation') else 1))*1000)))
    fact['detail_ms']=round((time.perf_counter()-begin)*1000,2)
    text=workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1769:9:inner_text',page.inner_text,locals(), 'body',timeout=400)
    if (not re.search(r'\bID:\s*'+re.escape(identifier)+r'\s+Initial Registration Date:',text)
        or norm(result['matched_registry_name']) not in norm(text)
        or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
     fact['outcome']='detail_binding_failed';return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1773:45:return',None)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_selected_wv_source:1774:66:return',None)
    begin=time.perf_counter();fact['phase']='capture';before=len(run.documents)
    previous_capture_stop=getattr(run,'page_capture_stop',None)
    run.page_capture_stop=min(stop,previous_capture_stop) if previous_capture_stop is not None else stop
    try:
     workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1775:80:capture',context.capture,locals())
    finally:
     if previous_capture_stop is None:del run.page_capture_stop
     else:run.page_capture_stop=previous_capture_stop
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1778:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1779:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_selected_wv_source:1782:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)


NJ_PUBLIC_SEARCH='https://charportal.dca.njoag.gov/Charity-Registration/CHR-Public-Search-Page/'
NJ_SEARCH_SELECTOR='#SearchBox28, input[placeholder="Search"], input[aria-label*="partial text" i], input[id^="SearchBox"], input[type="search"]'

def nj_evidence_body_core(text):
 # The source's search-box hover tip disappears during an actual screenshot.
 # Ignore only that observed instructional line, never record/grid/status text.
 tip='To search on partial text, use the asterisk (*) wildcard character.'
 return '\n'.join(line for line in text.splitlines() if line.strip() and line.strip()!=tip)

def nj_empty_response_bound(response,criterion):
 """Bind the original grid's explicit empty response to its actual query."""
 try:
  u=urlsplit(response.url);request=response.request;sent=request.post_data_json
  if (u.scheme!='https' or u.hostname!='charportal.dca.njoag.gov' or u.port not in (None,443)
      or u.username or u.password or u.query or u.fragment
      or not re.fullmatch(r'/_services/entity-grid-data\.json/[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',u.path)
      or request.method!='POST' or response.status!=200 or request.url!=response.url
      or 'json' not in response.headers.get('content-type','').lower()
      or not isinstance(sent,dict) or sent.get('search')!=criterion or type(sent.get('page')) is not int or sent['page']!=1
      or any(sent.get(k) for k in ('filter','metaFilter','odataFilterQuery','nlSearchFilter'))):return False
  data=response.json()
  return (isinstance(data,dict) and type(data.get('ItemCount')) is int and data['ItemCount']==0
          and type(data.get('PageNumber')) is int and data['PageNumber']==1
          and data.get('MoreRecords') is False and data.get('Records')==[]
          and data.get('Success') is not False
          and not any(data.get(k) for k in ('Error','error','ErrorMessage','errorMessage')))
 except Exception:return False

def capture_negative_nj_source(master,result,run,deadline):
 """One final original empty view, separate from the complete search history."""
 if (run is None or run.state!='NJ' or workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1816:39:get',result.get,locals(), 'state')!='NJ'
     or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1817:28:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1818:8:get',result.get,locals(), 'status')!='Not Registered' or workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1818:50:get',result.get,locals(), 'success') is not True
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1819:8:get',result.get,locals(), 'matched_registry_name') or workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1819:47:get',result.get,locals(), 'matched_registry_identifier')
     or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_negative_nj_source:1820:56:return',None)
 run.negative_visual_attempted=True;start=time.perf_counter();held=False;browser=context=None;receipt=None
 fact={'adapter':'NJ-original-completed-empty-search','phase':'admission','outcome':'not_started','extra_registry_queries':0,'navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_nj_source:1825:52:return',None)
  stop=time.monotonic()+min(18.0,remaining);timeout=lambda:max(1,int((stop-time.monotonic()-1)*1000))
  held=workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1827:7:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_negative_nj_source:1828:61:return',None)
  with master.checker.sync_playwright() as pw:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1830:11:launch_lookup_browser',master.launch_lookup_browser,locals(), pw,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1834:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1834:48:new_page',context.new_page,locals());begin=time.perf_counter();fact['phase']='navigation'
    response=workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1835:13:goto',page.goto,locals(), NJ_PUBLIC_SEARCH,wait_until='domcontentloaded',timeout=timeout())
    if response is None or response.status!=200 or page.url!=NJ_PUBLIC_SEARCH:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_nj_source:1836:116:return',None)
    box=page.locator(NJ_SEARCH_SELECTOR).first;workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1837:47:wait_for',box.wait_for,locals(), state='visible',timeout=timeout());fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    from deployment.search_history import begin_source_query
    receipt=begin_source_query('NJ',run.ein,'Public search across charity name, registration number and Federal EIN',NJ_PUBLIC_SEARCH)
    if receipt:receipt.query.pop('name',None);receipt.query['ein']=run.ein
    fact['phase']='visual_EIN_query';begin=time.perf_counter()
    def same_query(r):
     try:return r.request.method=='POST' and urlsplit(r.url).path.startswith('/_services/entity-grid-data.json/') and r.request.post_data_json.get('search')==run.ein
     except Exception:return False
    with page.expect_response(same_query,timeout=timeout()) as pending:
     workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1846:5:fill',box.fill,locals(), run.ein,timeout=timeout());workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1846:41:press',box.press,locals(), 'Enter',timeout=timeout());fact['extra_registry_queries']=1
    if not nj_empty_response_bound(pending.value,run.ein):fact['outcome']='empty_response_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_nj_source:1847:100:return',None)
    grid=page.locator('.public-search-grid');workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1848:45:wait_for',grid.get_by_text('No records to show',exact=True).wait_for,locals(), state='visible',timeout=timeout())
    if workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1849:7:input_value',box.input_value,locals(), timeout=300)!=run.ein or workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1849:48:count',grid.locator('tbody tr[data-id]').count,locals()):fact['outcome']='displayed_query_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_nj_source:1849:133:return',None)
    fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    from deployment.search_observation import complete_browser_query
    complete_browser_query(receipt,pending.value,0,rows=[])
    text=workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1853:9:inner_text',page.inner_text,locals(), 'body',timeout=400);grid_text=workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1853:55:inner_text',grid.inner_text,locals(), timeout=400)
    if re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='source_verification_pending';return trace_return('deployment/source_visual_adapters.py:capture_negative_nj_source:1854:151:return',None)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_nj_source:1855:66:return',None)
    fact['phase']='capture';begin=time.perf_counter();raw=workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1856:58:screenshot',page.screenshot,locals(), type='jpeg',quality=75,full_page=True,timeout=min(1000,timeout()))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    after={'url':page.url,'ein':workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1858:32:input_value',box.input_value,locals(), timeout=300),'grid':workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1858:68:inner_text',grid.inner_text,locals(), timeout=400),'body':workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1858:104:inner_text',page.inner_text,locals(), 'body',timeout=400)}
    before={'url':NJ_PUBLIC_SEARCH,'ein':run.ein,'grid':grid_text,'body':text}
    changed=[key for key in before if (nj_evidence_body_core(before[key])!=nj_evidence_body_core(after[key]) if key=='body' else before[key]!=after[key])]
    if changed:
     import difflib
     fact['outcome']='source_changed_during_capture';fact['changed_components']=changed
     fact['public_body_change']='\n'.join(list(difflib.unified_diff(text.splitlines(),after['body'].splitlines()))[:30])[:1500]
     return trace_return('deployment/source_visual_adapters.py:capture_negative_nj_source:1865:5:return',None)
    before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1866:30:document',run.document,locals(), NJ_PUBLIC_SEARCH,raw,'image',after['body'],note='Original New Jersey completed empty search view for displayed Federal EIN '+run.ein+'. The separate search history records this additional visual query and all earlier attempts; one image does not establish the other searches.')
    if len(run.documents)>before:
     run.nj_validated_empty_images=getattr(run,'nj_validated_empty_images',set());run.nj_validated_empty_images.add(hashlib.sha256(raw).hexdigest());fact['outcome']='captured'
    else:fact['outcome']='image_admission_rejected'
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1871:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1872:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:200]
 finally:
  if receipt:receipt.incomplete()
  if held:workflow_call('deployment/source_visual_adapters.py:capture_negative_nj_source:1876:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)


VA_FINAL_SEARCH='https://vdacs.evokeplatform.com/app/publicPortal/home'

def va_empty_response_bound(response,criterion):
 """Validate the exact anonymous UI request; do not infer zero from a shell."""
 try:
  u=urlsplit(response.url)
  if (u.scheme!='https' or u.hostname!='vdacs.evokeplatform.com' or u.port not in (None,443)
      or u.username or u.password or u.path!='/api/data/objects/entity/instances'
      or response.status!=200 or response.request.method!='GET'):return False
  params=parse_qs(u.query);filters=params.get('filter',[])
  if len(filters)!=1:return False
  plan=json.loads(filters[0]);clauses=plan['where']['and']
  if plan.get('skip')!=0 or plan.get('limit')!=200 or len(clauses)!=2 or clauses[0]!={'and':[{'type':'Business/Organization'},{'status':{'neq':'Excluded'}}]}:return False
  fields=clauses[1]['or']
  if not isinstance(fields,list) or not 1<=len(fields)<=30:return False
  seen=[]
  for item in fields:
   if not isinstance(item,dict) or len(item)!=1:return False
   label,term=next(iter(item.items()))
   if not isinstance(label,str) or term!={'like':criterion,'options':'i'}:return False
   seen.append(label)
  return 'ein' in seen and len(seen)==len(set(seen)) and response.json()==[]
 except (ValueError,KeyError,TypeError,AttributeError):return False

def capture_negative_va_source(master,result,run,deadline):
 if isinstance(result,dict) and workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1905:32:get',result.get,locals(), 'va_entity_evidence'):
  return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1906:2:return',(workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1906:9:capture_va_unregistered_entity',capture_va_unregistered_entity,locals(), master,result,run,deadline)))
 """One original VA global-search view, with a separately recorded EIN term."""
 if (run is None or run.state!='VA' or workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1908:39:get',result.get,locals(), 'state')!='VA'
     or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1909:28:get',result.get,locals(), 'ein','')))!=run.ein
     or workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1910:8:get',result.get,locals(), 'status')!='Not Registered' or workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1910:50:get',result.get,locals(), 'success') is not True
     or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1911:56:return',None)
 run.negative_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None;receipt=None
 fact={'adapter':'VA-original-completed-empty-global-search','phase':'admission','outcome':'not_started','extra_registry_queries':0,'local_visual_budget_ms':16000,'navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1916:52:return',None)
  stop=time.monotonic()+min(16,remaining);held=workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1917:47:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1918:61:return',None)
  criterion=run.ein[:2]+'-'+run.ein[2:]
  with master.checker.sync_playwright() as pw:
   phase_start=time.perf_counter();browser=workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1921:43:launch_lookup_browser',master.launch_lookup_browser,locals(), pw,headless=True);fact['browser_acquire_ms']=round((time.perf_counter()-phase_start)*1000,2)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    phase_start=time.perf_counter();context=workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1925:44:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1925:80:new_page',context.new_page,locals());fact['context_start_ms']=round((time.perf_counter()-phase_start)*1000,2);timeout=lambda:max(1,int((stop-time.monotonic()-1)*1000))
    begin=time.perf_counter();fact['phase']='navigation';response=workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1926:66:goto',page.goto,locals(), VA_FINAL_SEARCH,wait_until='domcontentloaded',timeout=timeout())
    if response is None or response.status!=200 or page.url!=VA_FINAL_SEARCH:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1927:115:return',None)
    field=page.get_by_placeholder('Search...',exact=True);workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1928:58:wait_for',field.wait_for,locals(), state='visible',timeout=timeout());fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    from deployment.search_history import begin_source_query
    receipt=begin_source_query('VA',criterion,'Global search across public fields, including FEIN; case-insensitive term match',VA_FINAL_SEARCH)
    if receipt:receipt.query.pop('name',None);receipt.query['ein']=criterion
    fact['phase']='visual_EIN_query';begin=time.perf_counter()
    def same_query(r):
     if urlsplit(r.url).path!='/api/data/objects/entity/instances':return False
     try:return criterion in parse_qs(urlsplit(r.url).query).get('filter',[''])[0]
     except ValueError:return False
    with page.expect_response(same_query,timeout=timeout()) as pending:
     workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1938:5:fill',field.fill,locals(), criterion,timeout=timeout());workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1938:45:press',field.press,locals(), 'Enter',timeout=timeout());fact['extra_registry_queries']=1
    workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1939:4:wait_for',page.get_by_text('No Data',exact=True).wait_for,locals(), state='visible',timeout=timeout())
    if not va_empty_response_bound(pending.value,criterion):fact['outcome']='empty_response_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1940:102:return',None)
    workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1941:4:wait_for',page.locator('.ag-overlay-loading-center').wait_for,locals(), state='hidden',timeout=timeout())
    workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1942:4:wait_for',page.locator('.ag-center-cols-container .ag-row').first.wait_for,locals(), state='hidden',timeout=timeout())
    fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    if receipt:receipt.complete(0,rows=[])
    text=workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1945:9:inner_text',page.inner_text,locals(), 'body',timeout=400)
    if workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1946:7:input_value',field.input_value,locals(), timeout=300)!=criterion or workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1946:52:count',page.locator('.ag-row').count,locals())!=0 or 'Virginia Department of Agriculture and Consumer Services' not in text:fact['outcome']='displayed_criteria_rejected';return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1946:207:return',None)
    if time.monotonic()+1.5>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1947:68:return',None)
    begin=time.perf_counter();raw=workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1948:34:screenshot',page.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=min(1000,timeout()))
    if page.url!=VA_FINAL_SEARCH or workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1949:36:input_value',field.input_value,locals(), timeout=300)!=criterion or workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1949:81:inner_text',page.inner_text,locals(), 'body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1949:171:return',None)
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_negative_va_source:1950:78:return',None)
    before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1951:30:document',run.document,locals(), VA_FINAL_SEARCH,raw,'image',text,note='Original Virginia empty public global-search view for displayed FEIN term '+criterion+'. The separate history records this additional visual query; this image alone does not establish all name searches.')
    if len(run.documents)>before:
     run.va_validated_empty_images=getattr(run,'va_validated_empty_images',set());run.va_validated_empty_images.add(hashlib.sha256(raw).hexdigest());fact['outcome']='captured'
    else:fact['outcome']='image_admission_rejected'
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
   finally:
    phase_start=time.perf_counter()
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1958:50:close',context.close,locals())
    fact['context_close_ms']=round((time.perf_counter()-phase_start)*1000,2)
    phase_start=time.perf_counter()
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1961:27:close',browser.close,locals())
    fact['browser_close_ms']=round((time.perf_counter()-phase_start)*1000,2)
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:200]
 finally:
  if receipt:receipt.incomplete()
  if held:workflow_call('deployment/source_visual_adapters.py:capture_negative_va_source:1966:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)


def search_wa_with_source_capture(module,org,**kwargs):
 """Clone only this invocation's launcher; do not mutate WA/NM globals."""
 from types import FunctionType
 from deployment.state_snapshots import CURRENT,ContextCaptureProxy
 original=module.search_wa;run=CURRENT.get()
 if run is None or run.state!='WA' or not isinstance(original,FunctionType):
  return original(org,**kwargs)
 launch=original.__globals__.get('launch_context')
 if not callable(launch):return original(org,**kwargs)
 def owned_context(*args,**options):
  browser,context=launch(*args,**options)
  try:return browser,ContextCaptureProxy(context)
  except Exception:
   run.errors.append('WA_optional_context_observer_unavailable')
   return browser,context
 search=FunctionType(original.__code__,{**original.__globals__,'launch_context':owned_context},original.__name__,original.__defaults__,original.__closure__)
 search.__kwdefaults__=original.__kwdefaults__
 return search(org,**kwargs)


"""LOCAL ONLY: original Michigan detail after the retained selected-file lookup."""
import re,time
from urllib.parse import urlsplit

MI_DETAIL_PREFIX='#ctl00_MainContent_fvCSForm_'
def mi_detail_values(page):
    return {key:page.locator(MI_DETAIL_PREFIX+suffix).inner_text(timeout=400).strip() for key,suffix in {
        'identifier':'lblFileNo','name':'lblLegalName','ein':'lblEIN',
        'standing':'lblSolicitationRegistrationStatus'}.items()}

def mi_values_bound(values,result,ein):
    norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
    if (values.get('identifier')!=str(result.get('matched_registry_identifier'))
        or norm(values.get('name'))!=norm(result.get('matched_registry_name'))
        or re.sub(r'\D','',values.get('ein',''))!=ein
        or not values.get('standing')):return False
    expected=re.search(r'(?:License / Registration Expiration|Expiration Date):\s*(\d{1,2})/(\d{1,2})/(\d{4})',result.get('raw_status_text',''),re.I)
    if expected:
        actual=re.search(r'Expiration Date:\s*(\d{1,2})/(\d{1,2})/(\d{4})',values['standing'],re.I)
        if not actual or tuple(map(int,actual.groups()))!=tuple(map(int,expected.groups())):return False
    if re.search(r'Registration Pending',result.get('raw_status_text',''),re.I) and not re.search(r'Registration Pending',values['standing'],re.I):return False
    return True

def mi_explicit_detail_error(page):
    u=urlsplit(page.url)
    return (u.scheme=='https' and u.hostname=='www.ag.state.mi.us' and u.port in (None,443)
            and not u.username and not u.password and not u.fragment
            and u.path=='/CharitableTrust/frmErrorPage.aspx'
            and parse_qsl(u.query)==[('aspxerrorpath','/CharitableTrust/frmSearchResults.aspx')]
            and 'Application Error' in page.inner_text('body',timeout=400))

def mi_selected_grid_values(page,result):
    """Bind original single-file results to the lookup's exact expiration."""
    u=urlsplit(page.url);identifier=str(result.get('matched_registry_identifier',''))
    if (u.scheme!='https' or u.hostname!='www.ag.state.mi.us' or u.port not in (None,443)
        or u.username or u.password or u.query or u.fragment or u.path!='/CharitableTrust/frmSearchResults.aspx'
        or not re.fullmatch(r'\d{3,8}',identifier)):return None
    raw=re.fullmatch(r'License / Registration Expiration: (\d{1,2}/\d{1,2}/\d{4}) \| AG File#: '+re.escape(identifier),str(result.get('raw_status_text','')))
    if not raw:return None
    clean=lambda s:re.sub(r'\s+',' ',s).strip()
    echo=page.locator('#ctl00_MainContent_lblSearchResults')
    grid=page.locator('#ctl00_MainContent_GridView1')
    if echo.count()!=1 or grid.count()!=1:return None
    if clean(echo.inner_text(timeout=400))!='Results for the following input: File No: '+identifier+'; 1 record(s) found':return None
    rows=grid.locator(':scope > tbody > tr')
    if rows.count()!=2:return None
    cells=rows.nth(1).locator(':scope > td')
    if cells.count()!=3:return None
    link=cells.nth(1).get_by_role('link',name=result['matched_registry_name'],exact=True)
    if link.count()!=1 or clean(cells.nth(0).inner_text(timeout=400))!=identifier:return None
    # The selected grid pads month/day; the EIN lookup can omit those zeros.
    # Compare real calendar dates, retaining the exact file/name/single-row guards.
    from datetime import datetime
    displayed=clean(cells.nth(2).inner_text(timeout=400))
    if not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',displayed):return None
    try:
        if datetime.strptime(displayed,'%m/%d/%Y').date()!=datetime.strptime(raw[1],'%m/%d/%Y').date():return None
    except ValueError:return None
    return clean(echo.inner_text(timeout=400)),clean(grid.inner_text(timeout=400))

def capture_mi_error_grid(run,result,search,detail,stop,fact):
    """Only an explicit state application error permits this limited fallback."""
    if search is None or not mi_explicit_detail_error(detail):return False
    fact['phase']='official_detail_error';fact['waiting_for']=''
    values=mi_selected_grid_values(search,result)
    if not values:fact['outcome']='error_grid_not_bound';return True
    if time.monotonic()+1>=stop:fact['outcome']='error_grid_deadline';return True
    search.bring_to_front()
    text=search.inner_text('body',timeout=max(1,int((stop-time.monotonic()-.5)*1000)))
    if re.search(r'verify you are human|access denied|just a moment',text,re.I):fact['outcome']='error_grid_verification';return True
    url=search.url;start=time.perf_counter()
    raw=search.screenshot(type='jpeg',quality=80,full_page=True,timeout=max(1,int((stop-time.monotonic()-.5)*1000)))
    fact['capture_ms']=round((time.perf_counter()-start)*1000,2)
    if search.url!=url or mi_selected_grid_values(search,result)!=values or time.monotonic()>=stop:
        fact['outcome']='error_grid_changed';return True
    before=len(run.documents)
    run.document(url,raw,'image',text,note='Original Michigan single-record results page. The state detail page returned Application Error. This image shows the selected file, name and registration expiration used by the lookup; it does not supply unavailable financial detail.')
    fact['outcome']='captured_original_grid_after_source_error' if len(run.documents)>before else 'capture_failed'
    return True

def prepare_mi_selected_grid(search,result,stop,fact):
    """Retain the exact completed source before opening a potentially slow popup."""
    try:
        values=mi_selected_grid_values(search,result)
        if not values or time.monotonic()+3>=stop:return None
        text=search.inner_text('body',timeout=max(1,int((stop-time.monotonic()-2)*1000)))
        if re.search(r'verify you are human|access denied|just a moment',text,re.I):return None
        url=search.url;started=time.perf_counter()
        raw=search.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(1500,max(1,int((stop-time.monotonic()-2)*1000))))
        fact['capture_ms']+=round((time.perf_counter()-started)*1000,2)
        if search.url!=url or mi_selected_grid_values(search,result)!=values or time.monotonic()>=stop:return None
        binding=tuple(result.get(k) for k in ('ein','matched_registry_identifier','matched_registry_name','raw_status_text'))
        return dict(url=url,raw=raw,text=text,captured_at=time.time(),binding=binding)
    except Exception:return None

def retain_mi_grid_on_popup_timeout(run,result,grid,fact):
    """No substitution after a contradictory detail: only a popup timeout."""
    if not grid or fact.get('phase')!='selected_popup':return False
    binding=tuple(result.get(k) for k in ('ein','matched_registry_identifier','matched_registry_name','raw_status_text'))
    if binding!=grid['binding']:return False
    before=len(run.documents)
    run.document(grid['url'],grid['raw'],'image',grid['text'],note='Original Michigan single-file results page captured before opening the selected detail. The detail popup did not finish within this check. This page shows the exact selected file, organization and registration expiration; it does not supply the unavailable detail or financial fields.')
    if len(run.documents)<=before:return False
    doc=run.documents[-1];run.documents[-1]=(*doc[:4],grid['captured_at'],doc[5])
    fact['outcome']='captured_original_grid_after_detail_timeout'
    return True


def capture_owned_mi_page(run,result,page,context,deadline):
    """One selected-file visual query, original popup pixels, no status mutation."""
    if completed_names_only_result(run,result):return None
    if workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2015:7:get',result.get,locals(), 'status')=='Not Registered':
        return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2016:8:return',(workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2016:15:capture_owned_mi_empty',capture_owned_mi_empty,locals(), run,result,context,deadline)))
    identifier=str(workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2017:19:get',result.get,locals(), 'matched_registry_identifier') or '')
    if (run is None or run.state!='MI' or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2018:42:get',result.get,locals(), 'state')!='MI'
        or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2019:31:get',result.get,locals(), 'ein','')))!=run.ein
        or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2020:11:get',result.get,locals(), 'success') is not True
        or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2021:11:get',result.get,locals(), 'status') in {'Not Registered','Unable to Confirm','Unable to Verify','Site Not Reachable'}
        or not re.fullmatch(r'\d{3,8}',identifier) or not workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2022:58:get',result.get,locals(), 'matched_registry_name')
        or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2023:11:get',result.get,locals(), 'source_url')!='https://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx'
        or getattr(run,'selected_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2024:59:return',None)
    run.selected_visual_attempted=True
    start=time.perf_counter();owned=[];selected_grid=None;detach_observer=lambda:None
    fact={'adapter':'MI-owned-selected-file-detail','phase':'admission','outcome':'not_started',
          'visual_file_queries':0,'capture_ms':0,'total_ms':0,'local_visual_budget_ms':30000}
    run.visual_adapter_facts.append(fact)
    def official(p):
        u=urlsplit(p.url)
        return (u.scheme=='https' and u.hostname=='www.ag.state.mi.us' and u.port in (None,443)
                and not u.username and not u.password and not u.query and not u.fragment
                and u.path=='/CharitableTrust/frmSearchResults.aspx')
    try:
        remaining=deadline-time.monotonic()-1
        if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2037:58:return',None)
        stop=time.monotonic()+min(30,remaining)
        def allowance(reserve=1):return max(1,int((stop-time.monotonic()-reserve)*1000))
        detail=None;search=None;selected_grid=None
        # Reuse a selected detail already produced by the normal browser path.
        for existing in list(context.pages):
            if official(existing) and workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2043:38:count',existing.locator(MI_DETAIL_PREFIX+'lblFileNo').count,locals())==1:
                if mi_values_bound(mi_detail_values(existing),result,run.ein):detail=existing;break
        if detail is None:
            fact['phase']='visual_file_search';search=workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2046:54:new_page',context.new_page,locals());owned.append(search);detach_observer=observe_visual_readiness(search,fact);fact['waiting_for']='search_document_domcontentloaded'
            workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2047:12:goto',search.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=allowance())
            u=urlsplit(search.url)
            if u.scheme!='https' or u.hostname!='www.ag.state.mi.us' or u.path not in {'/CharitableTrust/frmDisclaimer.aspx','/CharitableTrust/frmDefault.aspx'}:
                fact['outcome']='search_navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2050:61:return',None)
            if u.path.endswith('/frmDisclaimer.aspx'):
                fact['waiting_for']='disclaimer_accept'
                workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2053:16:click',search.locator('#ctl00_MainContent_lblYes').click,locals(), timeout=allowance())
            field=search.locator('#ctl00_MainContent_txtFileNo')
            fact['waiting_for']='file_number_field'
            workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2056:12:fill',field.fill,locals(), identifier,timeout=allowance())
            fact['waiting_for']='file_search_click'
            workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2058:12:click',search.locator('#ctl00_MainContent_btnIdSearch').click,locals(), timeout=allowance())
            fact['visual_file_queries']=1
            grid=search.locator('#ctl00_MainContent_GridView1')
            fact['waiting_for']='file_search_grid'
            workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2062:12:wait_for',grid.wait_for,locals(), state='visible',timeout=allowance())
            links=grid.get_by_role('link',name=result['matched_registry_name'],exact=True)
            if workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2064:15:count',links.count,locals())!=1 or not re.search(r'(?<!\d)'+re.escape(identifier)+r'(?!\d)',workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2064:92:inner_text',grid.inner_text,locals(), timeout=400)):
                fact['outcome']='selected_result_not_unique';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2065:61:return',None)
            selected_grid=prepare_mi_selected_grid(search,result,stop,fact)
            fact['phase']='selected_popup';fact['waiting_for']='selected_link_popup'
            with search.expect_popup(timeout=allowance()) as popup:
                workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2068:16:click',links.click,locals(), timeout=allowance())
            detail=popup.value;owned.append(detail)
        # Wait for either the real selected record or the official error page.
        # A completed application error must not spend the rest of the budget
        # waiting for a detail field that this page will never contain.
        detail.wait_for_function("() => !!document.querySelector('#ctl00_MainContent_fvCSForm_lblSolicitationRegistrationStatus') || (location.pathname==='/CharitableTrust/frmErrorPage.aspx' && document.body?.innerText.includes('Application Error'))",timeout=allowance())
        if capture_mi_error_grid(run,result,search,detail,stop,fact):return
        fact['phase']='detail_binding';fact['waiting_for']='selected_status_field'
        workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2071:8:wait_for',detail.locator(MI_DETAIL_PREFIX+'lblSolicitationRegistrationStatus').wait_for,locals(), state='visible',timeout=allowance())
        values=mi_detail_values(detail)
        if not official(detail) or not mi_values_bound(values,result,run.ein):fact['outcome']='selected_detail_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2073:122:return',None)
        text=workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2074:13:inner_text',detail.inner_text,locals(), 'body',timeout=400)
        if re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='verification_pending';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2075:148:return',None)
        size=workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2076:13:evaluate',detail.locator('body').evaluate,locals(), '(b)=>({width:Math.max(b.scrollWidth,document.documentElement.scrollWidth,innerWidth),height:Math.max(b.scrollHeight,document.documentElement.scrollHeight,innerHeight)})',timeout=400)
        if not size or min(size.values())<=0 or size['width']*size['height']>20000000:fact['outcome']='image_size_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2077:124:return',None)
        if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2078:70:return',None)
        fact['phase']='original_image_readiness';fact['waiting_for']='original_images'
        workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2080:8:wait_for_function',detail.wait_for_function,locals(), "() => Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)",timeout=allowance(1))
        if time.monotonic()+1>=stop:fact['outcome']='image_readiness_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2081:78:return',None)
        fact['phase']='capture';fact['waiting_for']='';begin=time.perf_counter();url=detail.url
        raw=workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2083:12:screenshot',detail.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=allowance(.5))
        fact['capture_ms']+=round((time.perf_counter()-begin)*1000,2)
        if detail.url!=url or mi_detail_values(detail)!=values:fact['outcome']='record_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2085:111:return',None)
        if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_page:2086:82:return',None)
        before=len(run.documents)
        workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2088:8:document',run.document,locals(), url,raw,'image',text,note='Original selected Michigan detail, including EIN, solicitation standing and financial period. Retrieved by the already selected AG file number; not a reconstructed report.')
        fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
    except Exception as exc:
        from playwright.sync_api import TimeoutError as BrowserTimeoutError
        if isinstance(exc,BrowserTimeoutError) and retain_mi_grid_on_popup_timeout(run,result,selected_grid,fact):
            fact['detail_error_type']='TimeoutError'
            return
        fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
    finally:
        detach_observer()
        for target in reversed(owned):
            try:workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_page:2095:16:close',target.close,locals())
            except Exception:pass
        run.capture_ms+=fact['capture_ms'];fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def mi_empty_values(page,ein):
    """Bind the original completed grid to the displayed exact EIN criterion."""
    u=urlsplit(page.url)
    if (u.scheme!='https' or u.hostname!='www.ag.state.mi.us' or u.port not in (None,443)
        or u.username or u.password or u.query or u.fragment
        or u.path!='/CharitableTrust/frmSearchResults.aspx'):return None
    echo=page.locator('#ctl00_MainContent_lblSearchResults')
    grid=page.locator('#ctl00_MainContent_GridView1')
    heading=page.locator('#searchResults')
    if echo.count()!=1 or grid.count()!=1 or heading.count()!=1:return None
    clean=lambda s:re.sub(r'\s+',' ',s).strip()
    formatted=ein[:2]+'-'+ein[2:]
    expected='Results for the following input: Organization Type: Charity or Public Safety Organization EIN: '+formatted+'; 0 record(s) found'
    values=(clean(echo.inner_text(timeout=400)),clean(grid.inner_text(timeout=400)),clean(heading.inner_text(timeout=400)))
    return values if values==(expected,'No records found for your search criteria','Search Results') else None

def capture_owned_mi_empty(run,result,context,deadline):
    """Capture one actual EIN result after independently completed status lookup."""
    if (run is None or run.state!='MI' or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2117:42:get',result.get,locals(), 'state')!='MI'
        or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2118:11:get',result.get,locals(), 'status')!='Not Registered' or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2118:53:get',result.get,locals(), 'success') is not True
        or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2119:31:get',result.get,locals(), 'ein','')))!=run.ein
        or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2120:11:get',result.get,locals(), 'completed_exact_ein_empty') is not True
        or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2121:11:get',result.get,locals(), 'matched_registry_name') or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2121:50:get',result.get,locals(), 'matched_registry_identifier')
        or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2122:11:get',result.get,locals(), 'source_url')!='https://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx'
        or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_empty:2123:59:return',None)
    run.negative_visual_attempted=True;run.mi_negative_visual_guard=True;start=time.perf_counter();owned=None;receipt=None;detach_observer=lambda:None
    fact={'adapter':'MI-owned-original-empty-EIN','phase':'admission','outcome':'not_started','visual_EIN_queries':0,'capture_ms':0,'total_ms':0,'local_visual_budget_ms':16000}
    run.visual_adapter_facts.append(fact)
    try:
        remaining=deadline-time.monotonic()-1
        if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_empty:2129:58:return',None)
        stop=time.monotonic()+min(16,remaining)
        def allowance(reserve=1):return max(1,int((stop-time.monotonic()-reserve)*1000))
        detail=next((p for p in list(context.pages) if mi_empty_values(p,run.ein)),None)
        if detail is None:
            fact['phase']='visual_EIN_search';owned=workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2134:52:new_page',context.new_page,locals());detail=owned;detach_observer=observe_visual_readiness(detail,fact);fact['waiting_for']='search_document_domcontentloaded'
            workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2135:12:goto',detail.goto,locals(), result['source_url'],wait_until='domcontentloaded',timeout=allowance())
            if detail.url=='https://www.ag.state.mi.us/CharitableTrust/frmDisclaimer.aspx':
                fact['waiting_for']='disclaimer_accept'
                workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2138:16:click',detail.locator('#ctl00_MainContent_lblYes').click,locals(), timeout=allowance())
            if detail.url!=result['source_url']:fact['outcome']='search_navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_empty:2139:93:return',None)
            fact['waiting_for']='EIN_field'
            workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2141:12:fill',detail.locator('#ctl00_MainContent_txtEIN').fill,locals(), run.ein[:2]+'-'+run.ein[2:],timeout=allowance())
            from deployment.search_history import SourceQueryReceipt
            receipt=SourceQueryReceipt(run,{'state':'MI','operation':'search','ein':run.ein[:2]+'-'+run.ein[2:],'filter_label':'Exact EIN; original public results view','source_kind':'state_portal','url':result['source_url']})
            fact['visual_EIN_queries']=1
            fact['waiting_for']='EIN_search_click_and_response'
            with detail.expect_response(lambda response: response.request.method=='POST' and response.request.url==result['source_url'],timeout=allowance()) as observed_response:
                workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2147:16:click',detail.locator('#ctl00_MainContent_btnTextSearch').click,locals(), timeout=allowance())
            query_response=observed_response.value
            fact['waiting_for']='EIN_result_grid'
            workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2150:12:wait_for',detail.locator('#ctl00_MainContent_GridView1').wait_for,locals(), state='visible',timeout=allowance())
        fact['phase']='empty_binding';values=mi_empty_values(detail,run.ein)
        if not values:
            if receipt:receipt.incomplete();receipt=None
            fact['outcome']='empty_source_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_empty:2154:53:return',None)
        if receipt:
            from deployment.search_observation import complete_browser_query
            complete_browser_query(receipt,query_response,0,[]);receipt=None
        fact['phase']='original_image_readiness';fact['waiting_for']='original_images'
        workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2159:8:wait_for_function',detail.wait_for_function,locals(), "() => Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)",timeout=allowance())
        text=workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2160:13:inner_text',detail.inner_text,locals(), 'body',timeout=400)
        if re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='verification_pending';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_empty:2161:148:return',None)
        if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_empty:2162:70:return',None)
        fact['phase']='capture';fact['waiting_for']='';begin=time.perf_counter()
        raw=workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2164:12:screenshot',detail.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=min(1500,allowance(.5)))
        fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
        if mi_empty_values(detail,run.ein)!=values or workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2166:54:inner_text',detail.inner_text,locals(), 'body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_empty:2166:146:return',None)
        if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_owned_mi_empty:2167:82:return',None)
        import hashlib
        if not hasattr(run,'mi_validated_empty_images'):run.mi_validated_empty_images=set()
        run.mi_validated_empty_images.add(hashlib.sha256(raw).hexdigest())
        before=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2171:34:document',run.document,locals(), detail.url,raw,'image',text,note='Original completed Michigan exact-EIN result. This image documents this search only; the separate search history lists the other submitted queries.')
        fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
    except Exception as exc:
        if receipt:receipt.incomplete()
        fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
    finally:
        detach_observer()
        if owned is not None:
            try:workflow_call('deployment/source_visual_adapters.py:capture_owned_mi_empty:2179:16:close',owned.close,locals())
            except Exception:fact['owned_page_close_error']=True
        run.capture_ms+=fact['capture_ms'];fact['total_ms']=round((time.perf_counter()-start)*1000,2)


def capture_va_unregistered_entity(master,result,run,deadline):
 """Photograph the proven entity, not an empty global search, without changing status."""
 if (run is None or run.state!='VA' or workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2186:39:get',result.get,locals(), 'state')!='VA'
     or workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2187:8:get',result.get,locals(), 'success') is not True or workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2187:45:get',result.get,locals(), 'status') not in {'Not Registered','Suspended'}
     or re.sub(r'\D','',str(workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2188:28:get',result.get,locals(), 'ein','')))!=run.ein
     or getattr(run,'negative_visual_attempted',False)):return trace_return('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2189:56:return',None)
 proof=workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2190:7:get',result.get,locals(), 'va_entity_evidence');identifier=str(workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2190:55:get',result.get,locals(), 'matched_registry_identifier') or '')
 norm=lambda v:re.sub(r'[^a-z0-9]','',str(v).lower())
 if (not isinstance(proof,dict) or not re.fullmatch(r'\d{1,12}',identifier)
     or workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2193:8:get',proof.get,locals(), 'ein')!=run.ein or workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2193:37:get',proof.get,locals(), 'id')!=identifier or workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2193:68:get',proof.get,locals(), 'entity_id')!=identifier
     or not workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2194:12:get',result.get,locals(), 'matched_registry_name') or norm(workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2194:56:get',proof.get,locals(), 'name'))!=norm(result['matched_registry_name'])
     or workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2195:8:get',proof.get,locals(), 'status')!={'Not Registered':'Unregistered','Suspended':'Not Authorized to Solicit'}[result['status']] or type(workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2195:52:get',proof.get,locals(), 'registration_count')) is not int
     or proof['registration_count']!=0 or (result['status']=='Suspended' and result.get('status_reason')!='VA_CONFIRMED_SOLICITATION_RESTRICTION') or workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2196:42:get',result.get,locals(), 'source_url')!=VA_FINAL_SEARCH):return trace_return('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2196:85:return',None)
 selected_restriction=result['status']=='Suspended'
 capture_allowance=30 if selected_restriction else 16
 run.negative_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None
 url='https://vdacs.evokeplatform.com/app/publicPortal/entity/'+identifier
 fact={'adapter':'VA-original-unregistered-entity','phase':'admission','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0,'extra_registry_queries':0,'visual_detail_requests':0,'local_visual_budget_ms':capture_allowance*1000,'budget_class':'selected_record' if selected_restriction else 'negative_entity'};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return trace_return('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2202:52:return',None)
  stop=time.monotonic()+min(capture_allowance,remaining);held=workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2203:47:acquire',master.BROWSER_LOOKUP_SEMAPHORE.acquire,locals(), blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return trace_return('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2204:61:return',None)
  with master.checker.sync_playwright() as pw:
   browser=workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2206:11:launch_lookup_browser',master.launch_lookup_browser,locals(), pw,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1400},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2210:12:new_context',browser.new_context,locals(), **options);page=workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2210:48:new_page',context.new_page,locals());timeout=lambda:max(1,int((stop-time.monotonic()-(3 if selected_restriction else 1))*1000))
    begin=time.perf_counter();fact['phase']='entity_navigation';response=workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2211:73:goto',page.goto,locals(), url,wait_until='commit',timeout=timeout());fact['visual_detail_requests']=1
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=url:fact['outcome']='navigation_rejected';return trace_return('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2213:103:return',None)
    fact['phase']='entity_fields_ready';begin=time.perf_counter()
    workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2215:4:wait_for',page.get_by_role('heading',name='Entity Information',exact=True).wait_for,locals(), state='visible',timeout=timeout())
    panel=page.locator('.formio-form');tab=page.get_by_role('tab',name='Registrations',exact=True)
    empty=page.get_by_text('No Data',exact=True)
    workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2218:4:wait_for',empty.wait_for,locals(), state='visible',timeout=timeout())
    def read_bound():
     if (page.url!=url or workflow_call('deployment/source_visual_adapters.py:read_bound:2220:26:count',panel.count,locals())!=1 or workflow_call('deployment/source_visual_adapters.py:read_bound:2220:46:count',tab.count,locals())!=1 or tab.get_attribute('aria-selected')!='true'
         or workflow_call('deployment/source_visual_adapters.py:read_bound:2221:12:count',empty.count,locals())!=1 or not workflow_call('deployment/source_visual_adapters.py:read_bound:2221:36:is_visible',empty.is_visible,locals()) or workflow_call('deployment/source_visual_adapters.py:read_bound:2221:58:count',page.locator('.ag-center-cols-container .ag-row').count,locals())!=0
         or workflow_call('deployment/source_visual_adapters.py:read_bound:2222:12:count',page.locator('.ag-overlay-loading-center:visible').count,locals())!=0):return trace_return('deployment/source_visual_adapters.py:read_bound:2222:75:return',(None))
     fields={}
     for key,label in [('fullName','Name'),('status','Status'),('ein','FEIN')]:
      el=panel.locator('.formio-component-'+key)
      if workflow_call('deployment/source_visual_adapters.py:read_bound:2226:9:count',el.count,locals())!=1 or not workflow_call('deployment/source_visual_adapters.py:read_bound:2226:30:is_visible',el.is_visible,locals()):return trace_return('deployment/source_visual_adapters.py:read_bound:2226:46:return',(None))
      lines=[line.strip() for line in workflow_call('deployment/source_visual_adapters.py:read_bound:2227:38:inner_text',el.inner_text,locals(), timeout=max(1,int((stop-time.monotonic()-(2 if fact['phase']!='capture' else .1))*1000)) if selected_restriction else 400).splitlines() if line.strip()]
      if len(lines)<2 or lines[0]!=label:return trace_return('deployment/source_visual_adapters.py:read_bound:2228:41:return',(None))
      fields[key]=' '.join(lines[1:])
     if (norm(fields['fullName'])!=norm(proof['name']) or fields['status']!=proof['status']
         or re.sub(r'\D','',fields['ein'])!=run.ein):return trace_return('deployment/source_visual_adapters.py:read_bound:2231:53:return',(None))
     text=workflow_call('deployment/source_visual_adapters.py:read_bound:2232:10:inner_text',page.inner_text,locals(), 'body',timeout=max(1,int((stop-time.monotonic()-(2 if fact['phase']!='capture' else .1))*1000)) if selected_restriction else 400)
     if ('Registration Type' not in text or 'Registration ID' not in text or 'Expiration Date' not in text
         or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):return trace_return('deployment/source_visual_adapters.py:read_bound:2234:110:return',(None))
     return trace_return('deployment/source_visual_adapters.py:read_bound:2235:5:return',(fields,text))
    before=read_bound();fact['selected_fields_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    if before is None:fact['outcome']='entity_not_bound';return trace_return('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2237:57:return',None)
    remaining_capture=stop-time.monotonic()-.5
    if remaining_capture<.25:fact['outcome']='capture_reserve';return trace_return('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2239:63:return',None)
    fact['phase']='capture';begin=time.perf_counter();raw=workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2240:58:screenshot',page.screenshot,locals(), type='jpeg',quality=80,full_page=True,timeout=max(1,int((stop-time.monotonic()-1)*1000)) if selected_restriction else min(1000,max(1,int(remaining_capture*1000))))
    after=read_bound()
    if after is None or after!=before:fact['outcome']='source_changed_during_capture';return trace_return('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2242:86:return',None)
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return trace_return('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2243:78:return',None)
    count=len(run.documents);workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2244:29:document',run.document,locals(), url,raw,'image',before[1],note='Original selected Virginia entity page: explicit '+proof['status']+' standing and empty Registrations table. Same-run exact-EIN lookup confirmed zero registrations; this is not an empty organization search.')
    if len(run.documents)>count:
     digest=hashlib.sha256(raw).hexdigest()
     run.va_validated_empty_images=getattr(run,'va_validated_empty_images',set());run.va_validated_empty_images.add(digest)
     fact['outcome']='captured'
    else:fact['outcome']='image_admission_rejected'
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
   finally:
    if context is not None:context._captured=True;workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2252:50:close',context.close,locals())
    if browser is not None:workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2253:27:close',browser.close,locals())
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:200]
 finally:
  if held:workflow_call('deployment/source_visual_adapters.py:capture_va_unregistered_entity:2256:10:release',master.BROWSER_LOOKUP_SEMAPHORE.release,locals())
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)



def capture_ar_review_page(page,org,candidates,parsed_rows):
    """Retain the original candidate page before the next normal query replaces it."""
    from deployment.state_snapshots import CURRENT,DEADLINE
    run=CURRENT.get()
    if run is None or run.state!='AR' or run.ein!=re.sub(r'\D','',str(getattr(org,'ein',''))):return
    if not isinstance(candidates,list) or not 1<=len(candidates)<=12 or not parsed_rows:return
    u=urlsplit(page.url)
    if u.scheme!='https' or u.hostname!='sos-corp-search.ark.org' or u.path!='/charity/results' or u.fragment:return
    params=parse_qs(u.query)
    if len(params.get('name',[]))!=1 or set(params)-{'name','type'} or ('type' in params and params['type']!=['Charity Registration']):return
    saved=getattr(run,'ar_review_names',set())
    pending=[c for c in candidates if c.get('_identity_outcome')=='possible' and c.get('name') not in saved
             and c.get('url')==page.url and any(r.get('name')==c.get('name') and r.get('status')==c.get('raw_status') and r.get('registration_date')==c.get('initial') for r in parsed_rows)]
    if not pending:return
    used=getattr(run,'ar_review_capture_seconds',0.)
    remaining=min(6.-used,DEADLINE.get()-time.monotonic()-1)
    if remaining<1:return
    start=time.monotonic();stop=start+remaining;url=page.url
    fact={'adapter':'AR-original-review-results','outcome':'not_started','total_ms':0,'capture_ms':0}
    run.visual_adapter_facts.append(fact)
    def allowance():return max(1,int((stop-time.monotonic())*1000))
    try:
        text=page.inner_text('body',timeout=allowance())
        if re.search(r'captcha|verify you are human|access denied|request could not be satisfied',text,re.I):return
        clean=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
        if any(clean(c['name']) not in clean(text) or clean(c['raw_status']) not in clean(text) for c in pending):return
        begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=allowance())
        fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
        if time.monotonic()>=stop or page.url!=url or page.inner_text('body',timeout=allowance())!=text:
            fact['outcome']='source_changed';return
        before=len(run.documents);run.document(url,raw,'image',text,note='Original Arkansas results containing the identity-review candidate, captured before subsequent searches. Identity remains for user decision.')
        if len(run.documents)>before:
            run.ar_review_names=saved|{c['name'] for c in pending};fact['outcome']='captured'
    except Exception as exc:
        fact['outcome']='capture_unavailable';fact['error_type']=type(exc).__name__
    finally:
        elapsed=time.monotonic()-start;run.ar_review_capture_seconds=used+elapsed
        run.capture_ms+=fact['capture_ms'];fact['total_ms']=round(elapsed*1000,2)
