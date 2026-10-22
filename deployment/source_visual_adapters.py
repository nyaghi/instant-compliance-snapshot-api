"""Local candidate: photograph proven official detail URLs after status lookup.

No status interpretation, status query planning, page reconstruction or URL guessing.
Positive-record paths only; negative and candidate-review routes remain separate.
"""
import base64,hashlib,json,re,time
from urllib.parse import urlsplit,parse_qsl,parse_qs

def capture_result_visuals(master,result,run,deadline):
 """Measure visual-only requests separately; never alter a completed status."""
 for capture in (capture_selected_source,capture_negative_search):
  try:capture(master,result,run,deadline)
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
  if (u.hostname!='charitableregistration.ohioago.gov' or u.path!='/Charities/OrganizationDetails'
      or not re.fullmatch(r'\d+',identifier) or parse_qsl(u.query,keep_blank_values=True)!=[('Id',identifier)]):return None
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
  from deployment.kansas_row_evidence import capture_selected_kansas
  return capture_selected_kansas(master,result,run,deadline)
 if run is not None and run.state=='CA':return capture_selected_ca_source(master,result,run,deadline)
 if run is not None and run.state=='SC':return capture_selected_sc_source(master,result,run,deadline)
 if run is not None and run.state=='WA':return capture_selected_wa_source(master,result,run,deadline)
 if run is not None and run.state=='VA':return capture_selected_va_source(master,result,run,deadline)
 if run is not None and run.state=='CT':return capture_selected_ct_source(master,result,run,deadline)
 if run is not None and run.state=='LA':return capture_selected_la_source(master,result,run,deadline)
 if run is not None and run.state=='NJ':return capture_selected_nj_source(master,result,run,deadline)
 if run is not None and run.state=='WV':return capture_selected_wv_source(master,result,run,deadline)
 if run is None or run.state not in {'HI','OH','RI','WI','OR'}:return
 if run.state=='OR':
  # This is the existing live-confirmation route, using the validated official
  # export's selected charityID. It never invents an organization/search URL.
  reader=getattr(master,'or_snapshot_row_for_ein',None)
  if not callable(reader):return
  row=reader(run.ein);norm=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
  if (not isinstance(row,list) or len(row)<16 or not re.fullmatch(r'\d+',str(row[0]))
      or norm(str(row[6]).strip('"'))!=norm(result.get('matched_registry_name'))):return
  result={**result,'source_url':'https://justice.oregon.gov/Charities/Charity/details?charityID='+str(row[0])}
 if run.state=='WI':
  hint=getattr(run,'source_detail_hints',{}).get(str(result.get('matched_registry_identifier') or ''))
  norm=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
  if not hint or norm(hint['name'])!=norm(result.get('matched_registry_name')):return
  result={**result,'source_url':hint['url']}
 url=selected_url(run,result)
 if url is None:return
 if getattr(run,'selected_visual_attempted',False):return
 run.selected_visual_attempted=True
 # Existing owned browser captures must remain the first choice.
 if any(d[2] in {'image','source_pdf'} and run.ein in re.sub(r'\D','',d[3])
        and re.sub(r'[^a-z0-9]','',result['matched_registry_name'].lower()) in re.sub(r'[^a-z0-9]','',d[3].lower())
        for d in run.documents):return
 started=time.perf_counter();context=browser=None;held=False
 fact={'adapter':run.state+'-selected-detail','outcome':'not_started','playwright_start_ms':0,'browser_acquire_ms':0,'context_start_ms':0,'navigation_ms':0,'binding_ms':0,'capture_ms':0,'browser_close_ms':0,'playwright_close_ms':0,'total_ms':0}
 facts=getattr(run,'visual_adapter_facts',None)
 if facts is None:run.visual_adapter_facts=[]
 run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1.0
  if remaining<3.0:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(8.0,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  runtime_started=time.perf_counter();runtime_close_started=None
  with master.checker.sync_playwright() as p:
   fact['playwright_start_ms']=round((time.perf_counter()-runtime_started)*1000,2)
   acquire_started=time.perf_counter()
   browser=master.launch_lookup_browser(p,headless=True)
   fact['browser_acquire_ms']=round((time.perf_counter()-acquire_started)*1000,2)
   try:
    context_started=time.perf_counter()
    context_options={'viewport':{'width':1280,'height':900},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):context_options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**context_options)
    page=context.new_page()
    fact['context_start_ms']=round((time.perf_counter()-context_started)*1000,2)
    nav=time.perf_counter()
    response=page.goto(url,wait_until='commit' if run.state=='OR' else 'domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1 if run.state=='OR' else min(5.0,stop-time.monotonic()))*1000)))
    fact['navigation_ms']=round((time.perf_counter()-nav)*1000,2)
    fact['http_status']=response.status if response else None
    fact['url_stable']=page.url==url
    if response is None or response.status!=200 or page.url!=url:
     fact['outcome']='source_navigation_rejected';return
    if run.state=='OR':
     begin=time.perf_counter()
     page.wait_for_function('''({ein,name})=>{
       const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
       const text=document.body.innerText;
       return document.querySelector('#info')&&document.querySelector('#disclaimer')
         &&text.replace(/\\D/g,'').includes(ein)&&norm(text).includes(norm(name))
         &&/Fiscal Year Beginning.*Ending/.test(text)&&/Status:/.test(text);
     }''',arg={'ein':run.ein,'name':result['matched_registry_name']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     fact['selected_view_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    if run.state in {'RI','WI'}:
     begin=time.perf_counter()
     page.wait_for_function('''({name,id})=>{
      const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
      const text=document.body?.innerText||'';
      return norm(text).includes(norm(name)) && text.includes(id)
        && /Charitable Organization/i.test(text) && /Status/i.test(text);
     }''',arg={'name':result['matched_registry_name'],'id':result['matched_registry_identifier']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     fact['selected_view_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    if run.state=='MD':
     search_started=time.perf_counter()
     field=page.locator('#filter-a87e8739-62de-600d-728c-6300bf865f9e')
     field.fill(run.ein[:2]+'-'+run.ein[2:],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     field.press('Enter',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     page.wait_for_function('''({ein,name,id})=>{
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
    text=page.inner_text('body',timeout=max(1,int(min(.6,stop-time.monotonic())*1000)))
    fact['binding_ms']=round((time.perf_counter()-binding_started)*1000,2)
    normalize=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
    identifier=str(result['matched_registry_identifier'])
    identity_visible=(bool(re.search(r'(?<!\w)'+re.escape(identifier)+r'(?!\w)',text,re.I)) if run.state in {'ME','RI','WI'} else run.ein in re.sub(r'\D','',text))
    if run.state=='MD':identity_visible=identity_visible and bool(re.search(r'Charity ID:\s*'+re.escape(identifier)+r'(?![0-9])',text))
    if (not identity_visible or normalize(result['matched_registry_name']) not in normalize(text)
        or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
     fact['outcome']='record_not_ready_or_not_bound';return
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    before=len(run.documents);capture=time.perf_counter()
    # Owned ContextCaptureProxy captures once; its close must not capture again.
    context.capture()
    fact['capture_ms']=round((time.perf_counter()-capture)*1000,2)
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    close_started=time.perf_counter()
    if context is not None:
     # Do not capture a rejected/error page incidentally on close.
     context._captured=True
     context.close()
    if browser is not None:browser.close()
    fact['browser_close_ms']=round((time.perf_counter()-close_started)*1000,2)
    runtime_close_started=time.perf_counter()
  if runtime_close_started is not None:fact['playwright_close_ms']=round((time.perf_counter()-runtime_close_started)*1000,2)
 except Exception:
  fact['outcome']='source_visual_unavailable'
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def remember_ca_selected(run,result):
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

def capture_selected_ca_source(master,result,run,deadline):
 """Photograph the selected actual registration, never the entity Listed label."""
 if (result.get('state')!='CA' or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True or result.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not result.get('matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return
 identifier=str(result.get('matched_registry_identifier') or '')
 hint=getattr(run,'source_detail_hints',{}).get(identifier)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 if not hint or not re.fullmatch(r'(?:CT)?\d+',identifier) or norm(hint.get('name'))!=norm(result['matched_registry_name']):return
 try:
  u=urlsplit(hint['url'])
  if (u.scheme!='https' or u.hostname!='ca-rcf.evokeplatform.com' or u.port not in (None,443)
      or u.username or u.password or u.query or u.fragment
      or not re.fullmatch(r'/app/publicPortal/registrationDetails/\d+',u.path)):return
 except (ValueError,TypeError,KeyError):return
 run.selected_visual_attempted=True
 start=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'CA-selected-registration-detail','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission','local_visual_budget_ms':12000};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  # The observed original app renders in about8s in a fresh context. This
  # CA-only local visual allowance remains inside the original state deadline.
  # It is measured separately and is NOT yet an accepted whole-run speed cost.
  stop=time.monotonic()+min(12.0,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page()
    fact['phase']='navigation';begin=time.perf_counter()
    response=page.goto(hint['url'],wait_until='commit',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=hint['url']:fact['outcome']='navigation_rejected';return
    fact['phase']='selected_fields_ready';begin=time.perf_counter()
    # Source CSP disallows wait_for_function's eval. Visible source locators
    # preserve that policy; no CSP bypass or security setting is used.
    for label in ['Registration Number','Registration Type','Registration Status','Initial Registration Date','Current Expiration Date']:
     page.get_by_text(label,exact=True).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['selected_fields_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    text=page.inner_text('body',timeout=400)
    core=ca_registration_core(text)
    # Validate source labels and selected values, not merely a sidebar/list hit.
    if (not core or not re.search(r'Registration Number\s+'+re.escape(identifier)+r'(?!\d)',core)
        or norm(result['matched_registry_name']) not in norm(text)
        or not re.search(r'Registration Type\s+Charitable Organization',text)
        or not re.search(r'Registration Status\s+\S+',text)
        or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
     fact['outcome']='selected_registration_not_bound';return
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    # Capture the original visible registration panel plus the official page
    # header. Optional filing grids below are not the data used here and may
    # still be loading. Clip original pixels; never hide or redraw the grid.
    panel=page.locator('.formio-form').filter(has=page.locator('.formio-component-registrationNumber'))
    if panel.count()!=1:fact['outcome']='source_panel_not_unique';return
    bounds=panel.bounding_box()
    if not bounds or bounds['width']<=0 or bounds['height']<=0:fact['outcome']='source_panel_not_visible';return
    import math
    height=math.ceil(bounds['y']+bounds['height']+20)
    if height<100 or height>1000:fact['outcome']='source_panel_exceeds_viewport';return
    fact['phase']='capture';begin=time.perf_counter()
    raw=page.screenshot(type='jpeg',quality=80,clip={'x':0,'y':0,'width':1600,'height':height},timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    import io
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as im:
     if im.width*im.height>20000000:fact['outcome']='source_size_rejected';return
    if page.url!=hint['url'] or ca_registration_core(page.inner_text('body',timeout=400))!=core:fact['outcome']='source_changed_during_capture';return
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return
    before=len(run.documents);run.document(hint['url'],raw,'image',core[:20000],note='Original selected registration panel and state header. Optional lower filing grids are outside this captured view.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_selected_sc_source(master,result,run,deadline):
 """One visual selected-name query and the actual bound SC public-ID link."""
 if (result.get('state')!='SC' or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True or result.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not result.get('matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return
 identifier=str(result.get('matched_registry_identifier') or '')
 if not re.fullmatch(r'P\d+',identifier) or result.get('source_url')!='https://search.scsos.com/charities':return
 run.selected_visual_attempted=True
 start=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'SC-selected-original-detail','outcome':'not_started','navigation_ms':0,'search_ms':0,'detail_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission'};run.visual_adapter_facts.append(fact)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(8.0,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1280,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();begin=time.perf_counter();fact['phase']='navigation'
    response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return
    fact['phase']='visual_selected_name_search';begin=time.perf_counter()
    page.locator('#MainContent_dd_CharitySearchOperator').select_option('Contains',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.locator('#MainContent_txt_CharitySearchName').fill(result['matched_registry_name'],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.locator('#MainContent_butt_Search').click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['visual_name_queries']=1;fact['visual_query_name']=result['matched_registry_name'];fact['visual_query_mode']='Contains'
    # A credential can have multiple name rows (actual P2775 has both the
    # current and "The" alias). Match the already selected name as well as ID.
    link=page.locator('a[href="javascript:CharityInfo('+identifier[1:]+')"]').filter(has_text=re.compile(r'^\s*'+re.escape(result['matched_registry_name'])+r'\s*$',re.I))
    link.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if link.count()!=1 or norm(link.inner_text(timeout=400))!=norm(result['matched_registry_name']):fact['outcome']='selected_result_link_not_bound';return
    fact['search_ms']=round((time.perf_counter()-begin)*1000,2)
    fact['phase']='selected_detail';begin=time.perf_counter();link.click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    panel=page.locator('#MainContent_Panel_CharityDetail');panel.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    text=panel.inner_text(timeout=400);heading=panel.locator('h4')
    selected_name_key=norm(re.sub(r'^\s*the\s+','',result['matched_registry_name'],flags=re.I))
    # Actual P2775 links its old name to the same canonical "The" detail.
    # Only this leading article can differ, after the exact name+ID source link.
    detail_name_key=norm(re.sub(r'^\s*the\s+','',heading.inner_text(timeout=400),flags=re.I)) if heading.count()==1 else ''
    if (not detail_name_key or detail_name_key!=selected_name_key
        or not re.search(r'Public Id:\s*'+re.escape(identifier)+r'(?!\w)',text)
        or not re.search(r'Status:\s*\S+',text) or page.url!=result['source_url']):fact['outcome']='selected_detail_not_bound';return
    fact['detail_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    begin=time.perf_counter();fact['phase']='capture';before=len(run.documents);context.capture();fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def wa_summary_core(text):
 parts=re.findall(r'\bORGANIZATION INFORMATION\b[\s\S]*?\bCONTACT INFORMATION\b',text)
 return parts[0] if len(parts)==1 else None

def capture_selected_wa_source(master,result,run,deadline):
 """Original WA summary through renewal date after one exact-EIN UI query."""
 if (result.get('state')!='WA' or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True or result.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not result.get('matched_registry_name') or getattr(run,'selected_visual_attempted',False)
     or result.get('source_url')!='https://ccfs.sos.wa.gov/#/cftSearch'):return
 run.selected_visual_attempted=True;start=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'WA-selected-original-summary','outcome':'not_started','navigation_ms':0,'search_ms':0,'detail_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission','local_visual_budget_ms':24000};run.visual_adapter_facts.append(fact)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 name=result['matched_registry_name'];parts=[norm(part) for part in re.split(r'[()]',name) if norm(part)]
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  # Observed ordinary WA EIN responses take9-16s before detail. The separate
  # local visual allowance is measured, stays inside the existing state
  # deadline, and is NOT an accepted global performance change.
  stop=time.monotonic()+min(24.0,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1280,'height':1800},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();begin=time.perf_counter();fact['phase']='navigation'
    response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return
    fact['phase']='visual_EIN_search';begin=time.perf_counter()
    page.get_by_role('radio',name='FEIN Number',exact=True).check(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.locator('#FEINNoSearchField').fill(run.ein,timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.get_by_role('button',name='Search',exact=True).click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['visual_EIN_queries']=1
    cells=page.get_by_role('cell').filter(has_text=name)
    cells.first.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if cells.count()>20:fact['outcome']='selected_row_not_unique';return
    exact=[cells.nth(i) for i in range(cells.count()) if norm(cells.nth(i).inner_text(timeout=400))==norm(name)]
    if len(exact)!=1:fact['outcome']='selected_row_not_unique';return
    cell=exact[0]
    fact['search_ms']=round((time.perf_counter()-begin)*1000,2)
    fact['phase']='selected_detail';begin=time.perf_counter();cell.click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.get_by_role('heading',name='ORGANIZATION SUMMARY',exact=True).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fein=page.locator('label:visible').filter(has_text=re.compile(r'^\s*FEIN Number:\s*$')).locator('..')
    renewal=page.locator('label:visible').filter(has_text=re.compile(r'^\s*Renewal Date:\s*$')).locator('..')
    renewal.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    # Wait for a populated original field, then reject a foreign FEIN promptly.
    # Waiting for our requested FEIN would disguise a completed mismatch as a
    # long readiness timeout.
    fein.locator('strong').filter(has_text=re.compile(r'\d')).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    text=page.inner_text('body',timeout=400);core=wa_summary_core(text)
    if (page.url!='https://ccfs.sos.wa.gov/#/organization' or not core or fein.count()!=1 or renewal.count()!=1
        or re.sub(r'\D','',fein.inner_text(timeout=400))!=run.ein
        or not all(part in norm(core) for part in parts)
        or not re.search(r'Status:\s*\S+',core)):
     fact['outcome']='selected_summary_not_bound';return
    bounds=renewal.bounding_box()
    if not bounds or bounds['width']<=0 or bounds['height']<=0:fact['outcome']='renewal_not_visible';return
    import math
    height=math.ceil(bounds['y']+bounds['height']+24)
    if height<100 or height>1800:fact['outcome']='summary_exceeds_viewport';return
    fact['detail_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    from deployment.state_snapshots import wa_painted_result_ready
    fact['phase']='painted_result_ready';begin=time.perf_counter()
    if not wa_painted_result_ready(page,max(1,int(min(1,stop-time.monotonic()-2)*1000))):fact['outcome']='source_overlay_visible';return
    fact['painted_result_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    fact['phase']='capture';begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=80,clip={'x':0,'y':0,'width':1280,'height':height},timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    if page.url!='https://ccfs.sos.wa.gov/#/organization' or page.locator('#loaderDiv').is_visible() or wa_summary_core(page.inner_text('body',timeout=400))!=core:fact['outcome']='source_changed_during_capture';return
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return
    before=len(run.documents);run.document(page.url,raw,'image',core[:20000],note='Original organization summary and state header through renewal date; lower financial history is outside this view.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
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
     or not isinstance(kind,dict) or kind.get('name')!='Charity'
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
 if identifier in run.source_detail_hints:run.source_detail_hints[identifier]['source_fields']=expected

def va_registration_core(text):
 return re.split(r'\nSubmissions\n',text,maxsplit=1)[0]

def capture_selected_va_source(master,result,run,deadline):
 """Original selected VA registration: standing, initial/current/expiry dates."""
 if (result.get('state')!='VA' or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True or result.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not result.get('matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return
 identifier=str(result.get('matched_registry_identifier') or '');hint=getattr(run,'source_detail_hints',{}).get(identifier)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 if (not re.fullmatch(r'\d+',identifier) or not hint or norm(hint.get('name'))!=norm(result['matched_registry_name'])
     or hint.get('url')!='https://vdacs.evokeplatform.com/app/publicPortal/registration/'+identifier):return
 run.selected_visual_attempted=True;start=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'VA-selected-original-registration','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission','local_visual_budget_ms':12000};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(12.0,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1400},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();begin=time.perf_counter();fact['phase']='navigation'
    response=page.goto(hint['url'],wait_until='commit',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=hint['url']:fact['outcome']='navigation_rejected';return
    begin=time.perf_counter();fact['phase']='selected_fields_ready'
    page.get_by_role('heading',name='Registration Information',exact=True).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    for label in ['Registration ID','Initial Registration Date','Current Registration Date','Expiration Date']:
     page.get_by_text(label,exact=True).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['selected_fields_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    text=page.inner_text('body',timeout=400);core=va_registration_core(text)
    if (not re.search(r'Registration ID:\s*'+re.escape(identifier)+r'(?!\d)',core)
        or norm(result['matched_registry_name']) not in norm(core) or not re.search(r'Status\s+\S+',core)
        or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
     fact['outcome']='selected_registration_not_bound';return
    panel=page.locator('.formio-form')
    if panel.count()!=1:fact['outcome']='source_panel_not_unique';return
    expected=hint.get('source_fields')
    if not isinstance(expected,dict) or len(expected)!=7:fact['outcome']='source_field_proof_missing';return
    for field,wanted in expected.items():
     component=panel.locator('.formio-component-'+field)
     if component.count()!=1:fact['outcome']='source_field_component_changed';return
     lines=[line.strip() for line in component.inner_text(timeout=400).splitlines() if line.strip()]
     observed=' '.join(lines[1:])
     if observed.casefold()!=wanted.casefold():fact['outcome']='source_fields_changed_since_lookup';return
    bounds=panel.bounding_box()
    if not bounds or bounds['width']<=0 or bounds['height']<=0:fact['outcome']='source_panel_not_visible';return
    import math
    height=math.ceil(bounds['y']+bounds['height']+20);width=min(1600,math.ceil(bounds['x']+bounds['width']+20))
    if height<100 or height>1400 or width<100:fact['outcome']='source_panel_exceeds_viewport';return
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    begin=time.perf_counter();fact['phase']='capture';raw=page.screenshot(type='jpeg',quality=80,clip={'x':0,'y':0,'width':width,'height':height},timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    if page.url!=hint['url'] or va_registration_core(page.inner_text('body',timeout=400))!=core:fact['outcome']='source_changed_during_capture';return
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return
    before=len(run.documents);run.document(hint['url'],raw,'image',core[:20000],note='Original selected registration fields and state header; lower optional submissions grid outside captured view.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def ct_primary_registration_text(text):
 return re.split(r'\nActive Campaign Solicitations\n|\nSolicitation Reports',text,maxsplit=1)[0]

def capture_selected_ct_source(master,result,run,deadline):
 """Fresh credential search and actual source-issued selected detail link."""
 if (result.get('state')!='CT' or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True or result.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not result.get('matched_registry_name') or getattr(run,'selected_visual_attempted',False)
     or result.get('source_url')!='https://www.elicense.ct.gov/lookup/licenselookup.aspx'):return
 identifier=str(result.get('matched_registry_identifier') or '')
 match=re.fullmatch(r'CHR\.(\d{7})',identifier)
 if not match:return
 run.selected_visual_attempted=True;start=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'CT-fresh-selected-original-detail','outcome':'not_started','navigation_ms':0,'search_ms':0,'detail_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission'};run.visual_adapter_facts.append(fact)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(20.0,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1400},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();begin=time.perf_counter();fact['phase']='navigation'
    response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return
    begin=time.perf_counter();fact['phase']='visual_credential_search'
    prefix='#ctl00_MainContentPlaceHolder_ucLicenseLookup_'
    page.locator(prefix+'ctl03_ddCredPrefix').select_option('CHR',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.locator(prefix+'ctl03_tbLicenseNumber').fill(match[1],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.locator(prefix+'btnLookup').click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['visual_credential_queries']=1
    card=page.locator('forge-card').filter(has_text=identifier);card.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if card.count()!=1 or norm(result['matched_registry_name']) not in norm(card.inner_text(timeout=400)):fact['outcome']='selected_card_not_bound';return
    fact['search_ms']=round((time.perf_counter()-begin)*1000,2);begin=time.perf_counter();fact['phase']='selected_detail'
    card.get_by_role('link',name='Details',exact=True).click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    frame=page.locator('#iFrmLicenseDetailPopup[src*="licensedetail.aspx" i]');frame.wait_for(state='attached',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    from urllib.parse import urljoin
    url=urljoin(page.url,frame.get_attribute('src') or '');u=urlsplit(url);pairs=parse_qsl(u.query,keep_blank_values=True)
    if (u.scheme!='https' or u.hostname!='www.elicense.ct.gov' or u.port not in (None,443)
        or u.username or u.password or u.fragment or u.path.lower()!='/lookup/licensedetail.aspx'
        or len(pairs)!=1 or pairs[0][0]!='id' or not 1<=len(pairs[0][1])<=1000):fact['outcome']='source_detail_link_changed';return
    # Use the selected source-issued URL in the same public session.
    # The official iframe can remain blank while this exact URL is readable.
    fact['phase']='selected_direct_detail'
    response=page.goto(url,wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['visual_detail_navigation_attempts']=2
    if response is None or response.status!=200 or page.url!=url:fact['outcome']='selected_direct_navigation_rejected';return
    detail=page
    heading=detail.get_by_text('Registration Information',exact=True);heading.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    text=detail.inner_text('body',timeout=400);core=ct_primary_registration_text(text)
    if (norm(result['matched_registry_name']) not in norm(core)
        or not re.search(r'\bRegistration\s+'+re.escape(identifier)+r'(?![\w.])',core)
        or not re.search(r'Status\s+\S+',core) or 'Expiration Date' not in core
        or re.search('Invalid Request|verify you are human|access denied|just a moment',core,re.I)):
     fact['outcome']='selected_detail_not_bound';return
    panel=heading
    for _ in range(5):
     panel=panel.locator('..');panel_text=panel.inner_text(timeout=400)
     if identifier in panel_text and 'Expiration Date' in panel_text:break
    if identifier not in panel_text or 'Expiration Date' not in panel_text or 'Active Campaign Solicitations' in panel_text:fact['outcome']='primary_registration_panel_changed';return
    bounds=panel.bounding_box()
    if not bounds or bounds['height']<=0 or bounds['width']<=0:fact['outcome']='primary_panel_not_visible';return
    import math
    height=math.ceil(bounds['y']+bounds['height']+8)
    viewport=page.viewport_size
    if (not viewport or height<100 or height>viewport['height']
        or viewport['width']<600 or bounds['x']<0 or bounds['y']<0
        or detail.locator('body').evaluate('(el)=>el.ownerDocument.defaultView.scrollY')!=0):
     fact['outcome']='primary_panel_outside_visible_page';return
    if detail.url!=url:fact['outcome']='selected_page_url_changed';return
    fact['detail_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    clip={'x':0,'y':0,'width':viewport['width'],'height':height}
    begin=time.perf_counter();fact['phase']='capture';raw=page.screenshot(type='jpeg',quality=80,clip=clip,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    if panel.bounding_box()!=bounds:fact['outcome']='source_panel_moved_during_capture';return
    if detail.url!=url or ct_primary_registration_text(detail.inner_text('body',timeout=400))!=core:fact['outcome']='source_changed_during_capture';return
    before=len(run.documents);run.document(url,raw,'image',core[:20000],note='Original selected source-issued detail page and state header through primary registration dates; one direct detail navigation; solicitor campaign records outside this view.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_selected_la_source(master,result,run,deadline,negative=False):
 """Original public publisher row; retain its Registered Through label."""
 if (run is None or run.state!='LA' or result.get('state')!='LA'
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein or result.get('success') is not True
     or (result.get('status')!='Not Registered' if negative else result.get('status') in {'Not Registered','Unable to Confirm','Unable to Verify','Site Not Reachable'})
     or (bool(result.get('matched_registry_name') or result.get('matched_registry_identifier')) if negative else not result.get('matched_registry_name'))
     or getattr(run,'selected_visual_attempted',False)
     or result.get('source_url')!='https://www.ag.state.la.us/Charity/Registration/Listing'
     or result.get('status_reason')!=('LA_EXPORT_NO_SAFE_MATCH' if negative else 'LA_STATUS_FROM_OFFICIAL_EXCEL_EXPORT')):return
 expected=master.parse_due_date(result.get('computed_due_date') or '')
 if not negative and expected is None:return
 query_name=result.get('matched_registry_name')
 if negative:
  evaluated=[r.get('query',{}).get('name') for r in getattr(run,'search_history_receipts',[]) if r.get('outcome')=='Completed official dataset evaluation' and r.get('query',{}).get('source_kind')=='official_dataset' and r.get('query',{}).get('state')=='LA']
  if not evaluated or run.name not in evaluated:return
  query_name=run.name
 run.selected_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'LA-original-publisher-selected-row','phase':'admission','outcome':'not_started','navigation_ms':0,'filter_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(8.0,remaining);held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1500,'height':1100},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();fact['phase']='navigation';begin=time.perf_counter()
    response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)));fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return
    fact['phase']='source_table_filter';begin=time.perf_counter()
    table=page.get_by_role('table')
    if negative:
     from deployment.search_history import SourceQueryReceipt
     receipt=SourceQueryReceipt(run,{'state':'LA','operation':'search','name':query_name,'filter_label':'Original publisher table; client-side contains filter','source_kind':'state_portal','url':result['source_url']})
    page.get_by_role('searchbox',name='Search:',exact=True).fill(query_name,timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if negative:
     try:
      table.get_by_role('cell',name='No matching records found',exact=True).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
      if (table.locator('tbody tr').count()!=1 or not re.search(r'Showing 0 to 0 of 0 entries',page.inner_text('body',timeout=400))):receipt.incomplete();fact['outcome']='not_a_completed_empty_view';return
      receipt.complete(0)
     except Exception:receipt.incomplete();raise
    else:
     row=table.locator('tbody tr').filter(has=page.get_by_role('cell',name=result['matched_registry_name'],exact=True));row.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
     cells=row.get_by_role('cell')
     if (row.count()!=1 or cells.count()!=3 or norm(cells.nth(0).inner_text(timeout=400))!=norm(result['matched_registry_name'])
         or master.parse_due_date(cells.nth(1).inner_text(timeout=400))!=expected
         or table.get_by_role('button',name='Registered Through',exact=True).count()!=1):fact['outcome']='publisher_fields_not_bound';return
    fact['filter_ms']=round((time.perf_counter()-begin)*1000,2);fact['visual_selected_name_filters']=1
    text=page.inner_text('body',timeout=400)
    if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='verification_pending';return
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    fact['phase']='capture';begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    if page.url!=result['source_url'] or page.inner_text('body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return
    before=len(run.documents);run.document(page.url,raw,'image',text[:20000],note=('Original Louisiana public table: completed empty client-side filter of an already evaluated name. The separate search history distinguishes official dataset evaluations from this visual filter.' if negative else 'Original Louisiana public registered-charities table filtered to the already selected source name. Registered Through date agrees with retained official export. No invented EIN/license/detail page.'))
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
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
   return found[0] if len(found)==1 else None
  ein=field('Charity EIN');status=field('Registration Status');year=field('Year Represented')
  if (re.sub(r'\D','',ein or '')!=run.ein or field('Charity ID')!=identifier or not status
      or master.useful_registry_name(entry.get('f_aedd5545-808f-4725-9b1d-5fa61e994a75') or '')!=name):return
  if year not in (None,'') and not re.fullmatch(r'(?:19|20)\d{2}',year):return
  run.remember_detail(identifier,name,'https://onestop.md.gov/detail_views/62f3e17b7f7e3200016a4b6c/entry/'+entry_id)
  if identifier in run.source_detail_hints:run.source_detail_hints[identifier]['source_fields']={'status':status,'year':year or None}
 except (ValueError,TypeError,KeyError,AttributeError):return

def capture_owned_md_page(run,result,page,context,deadline):
 """Original General/Financial tabs in a separate owned source page."""
 if run is None or run.state!='MD':return
 context._captured=True
 if result.get('status')=='Not Registered':return capture_owned_md_empty(run,result,context,deadline)
 if selected_url(run,result) is None or getattr(run,'selected_visual_attempted',False):return
 run.selected_visual_attempted=True;start=time.perf_counter();detail=None
 fact={'adapter':'MD-owned-selected-detail-pair','outcome':'not_started','navigation_ms':0,'general_ms':0,'financial_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission'};run.visual_adapter_facts.append(fact)
 identifier=str(result['matched_registry_identifier']);hint=run.source_detail_hints.get(identifier);norm=lambda s:re.sub(r'[^a-z0-9]','',str(s).lower())
 if not hint or norm(hint.get('name'))!=norm(result['matched_registry_name']) or not isinstance(hint.get('source_fields'),dict):fact['outcome']='selected_source_proof_missing';return
 expected=hint['source_fields'];u=urlsplit(hint['url'])
 if (u.scheme!='https' or u.hostname!='onestop.md.gov' or u.port not in (None,443) or u.username or u.password or u.query or u.fragment
     or not re.fullmatch(r'/detail_views/62f3e17b7f7e3200016a4b6c/entry/[a-f0-9]{24}',u.path)):fact['outcome']='selected_link_rejected';return
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(10.0,remaining)
  detail=context.new_page();detail.set_extra_http_headers({});begin=time.perf_counter();fact['phase']='navigation'
  response=detail.goto(hint['url'],referer=result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200:fact['outcome']='detail_navigation_rejected';return
  def same_record():
   actual=urlsplit(detail.url)
   return actual.scheme=='https' and actual.hostname=='onestop.md.gov' and actual.path==u.path and not actual.username and not actual.password
  begin=time.perf_counter();fact['phase']='general_information'
  general=detail.get_by_role('tabpanel',name='General Information',exact=True);general.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  general.locator('.dvce-model-property').filter(has=detail.get_by_role('heading',name='Charity ID',exact=True)).locator('p').filter(has_text=re.compile(r'\d')).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  def value(panel,label):
   field=panel.locator('.dvce-model-property').filter(has=detail.get_by_role('heading',name=label,exact=True))
   if field.count()!=1:return None
   return field.locator('p').inner_text(timeout=400).strip()
  if (not same_record() or norm(value(general,'Charity Name'))!=norm(result['matched_registry_name'])
      or value(general,'Charity ID')!=identifier or (value(general,'Registration Status') or '').casefold()!=expected['status'].casefold()):fact['outcome']='general_source_fields_not_bound';return
  fact['approval_date_visible']=bool(value(general,'Latest Approval Date'))
  dismiss=detail.get_by_role('button',name='Dismiss alert.',exact=True)
  if dismiss.count()==1 and dismiss.is_visible():
   dismiss.click(timeout=400);dismiss.wait_for(state='hidden',timeout=500)
  general_text=detail.inner_text('body',timeout=400)
  if re.search('verify you are human|user validation required|access denied|just a moment',general_text,re.I):fact['outcome']='source_verification_pending';return
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
  def shot():
   begin_shot=time.perf_counter()
   try:return detail.screenshot(type='jpeg',quality=80,full_page=True,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
   finally:fact['capture_ms']+=round((time.perf_counter()-begin_shot)*1000,2)
  fact['phase']='general_capture';images=[shot()]
  if not same_record() or detail.inner_text('body',timeout=400)!=general_text:fact['outcome']='general_changed_during_capture';return
  fact['general_ms']=round((time.perf_counter()-begin)*1000,2);texts=[general_text]
  if expected.get('year') is not None:
   begin=time.perf_counter();fact['phase']='financial_information'
   detail.get_by_role('tab',name=re.compile(r'^Financial Informati')).click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
   financial=detail.get_by_role('tabpanel',name=re.compile(r'^Financial Informati'));financial.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
   if (not same_record() or value(financial,'Most Recent Fiscal Year')!=expected['year']
       or norm(result['matched_registry_name']) not in norm(detail.inner_text('body',timeout=400))):fact['outcome']='financial_source_fields_not_bound';return
   financial_text=detail.inner_text('body',timeout=400)
   if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
   fact['phase']='financial_capture';images.append(shot())
   if not same_record() or detail.inner_text('body',timeout=400)!=financial_text:fact['outcome']='financial_changed_during_capture';return
   texts.append(financial_text);fact['financial_ms']=round((time.perf_counter()-begin)*1000,2)
  raw=images[0] if len(images)==1 else json.dumps([base64.b64encode(raw).decode('ascii') for raw in images]).encode('utf8')
  if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return
  before=len(run.documents);run.document(detail.url,raw,'image' if len(images)==1 else 'image_pages','\n\n'.join(texts)[:20000],note='Original selected public record General Information and, when a reported year exists, Financial Information. Source standing/year match retained lookup fields. No source reconstruction.')
  fact['original_views']=len(images);fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception as exc:fact['outcome']='owned_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  run.capture_ms+=fact['capture_ms']
  if detail is not None:
   try:detail.close()
   except Exception:fact['owned_page_close_error']=True
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_owned_md_empty(run,result,context,deadline):
 """Original zero-entry EIN filter, using only the existing owned context."""
 if (run is None or run.state!='MD' or result.get('state')!='MD' or result.get('status')!='Not Registered'
     or result.get('success') is not True or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('matched_registry_name') or result.get('matched_registry_identifier')
     or result.get('source_url')!='https://onestop.md.gov/list_views/62f3e1797f7e3200016a3dab'
     or getattr(run,'md_verified_empty',False) is not True or getattr(run,'negative_visual_attempted',False)):return
 run.negative_visual_attempted=True;started=time.perf_counter();detail=None
 fact={'adapter':'MD-owned-original-empty-EIN-view','phase':'admission','outcome':'not_started','navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(10.0,remaining);detail=context.new_page();detail.set_extra_http_headers({});detail.set_viewport_size({'width':1600,'height':1100});begin=time.perf_counter();fact['phase']='navigation'
  response=detail.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)));fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200 or detail.url!=result['source_url']:fact['outcome']='navigation_rejected';return
  table=detail.get_by_role('table');table.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  field_id='a87e8739-62de-600d-728c-6300bf865f9e';field=detail.locator('#filter-'+field_id);criterion=run.ein[:2]+'-'+run.ein[2:];begin=time.perf_counter();fact['phase']='visual_EIN_query'
  from deployment.search_history import SourceQueryReceipt
  receipt=SourceQueryReceipt(run,{'state':'MD','operation':'search','ein':run.ein,'filter_label':'Search by Charity EIN; original public filter','source_kind':'state_portal','url':result['source_url']})
  field.fill(criterion,timeout=max(1,int((stop-time.monotonic()-1)*1000)));field.press('Enter',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  table.get_by_role('cell',name='No results found.',exact=True).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  # The actual source paints its empty row before the aria-live record count.
  # Wait for both original signals; never classify that intermediate view.
  detail.locator('[role="status"]').filter(has_text=re.compile(r'\b0\s+records\b')).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  u=urlsplit(detail.url);pairs=parse_qsl(u.query,keep_blank_values=True);text=detail.inner_text('body',timeout=400)
  fact['empty_binding']={'official_origin':u.scheme=='https' and u.hostname=='onestop.md.gov','path_match':u.path=='/list_views/62f3e1797f7e3200016a3dab','query_keys':[k for k,_ in pairs],'only_EIN_query':pairs==[(field_id,criterion)],'criterion_matches':field.input_value(timeout=400)==criterion,'zero_counter':bool(re.search(r'\b0\s+records\b',text)),'row_count':table.get_by_role('row').count(),'empty_cells':table.get_by_role('cell',name='No results found.',exact=True).count()}
  if (u.scheme!='https' or u.hostname!='onestop.md.gov' or u.path!='/list_views/62f3e1797f7e3200016a3dab'
      or u.username or u.password or u.fragment or pairs!=[(field_id,criterion)]
      or field.input_value(timeout=400)!=criterion or not re.search(r'\b0\s+records\b',text)
      or table.get_by_role('row').count()!=2 or table.get_by_role('cell',name='No results found.',exact=True).count()!=1):receipt.incomplete();fact['outcome']='empty_source_not_bound';return
  receipt.complete(0);fact['visual_EIN_queries']=1;fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
  dismiss=detail.get_by_role('button',name='Dismiss alert.',exact=True)
  if dismiss.count()==1 and dismiss.is_visible():dismiss.click(timeout=400);dismiss.wait_for(state='hidden',timeout=500)
  text=detail.inner_text('body',timeout=400)
  if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='source_verification_pending';return
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
  fact['phase']='capture';begin=time.perf_counter();raw=detail.screenshot(type='jpeg',quality=80,full_page=True,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
  fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
  if detail.url!=u.geturl() or detail.inner_text('body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return
  before=len(run.documents);run.document(detail.url,raw,'image',text[:20000],note='Original completed Maryland zero-result EIN filter. Existing API response independently had zero entries. No name search is claimed; the separate query receipt records the actual visual EIN submission.');fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception as exc:fact['outcome']='owned_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if detail is not None:
   try:detail.close()
   except Exception:fact['owned_page_close_error']=True
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def capture_owned_md_results_view_legacy(run,result,page,context,deadline):
 """Use the existing MD browser; original lookup result/body stay unchanged."""
 if run is None or run.state!='MD' or selected_url(run,result) is None:return
 if getattr(run,'selected_visual_attempted',False):return
 run.selected_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'MD-owned-public-view','outcome':'not_started','navigation_ms':0,'visual_ein_search_ms':0,'capture_ms':0,'total_ms':0}
 run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(6.0,remaining)
  # The existing entries reader leaves AJAX-only headers on this page. They
  # must not accompany the subsequent normal public-page navigation.
  page.set_extra_http_headers({});fact['page_headers_restored']=True
  begin=time.perf_counter()
  response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int(min(3,stop-time.monotonic()-1)*1000)))
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return
  # Static filter inputs precede the live table/event handlers. Wait for its
  # first completed render before entering the one visual-only EIN query.
  begin=time.perf_counter()
  page.wait_for_function('''()=>{
   const text=document.body.innerText,table=document.querySelector('table,[role="table"]');
   return table && table.querySelectorAll('tr,[role="row"]').length>1
    && /\\b[0-9]+ records?\\b/.test(text) && !/Loading\\.\\.\\./i.test(text);
  }''',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['initial_view_ready_ms']=round((time.perf_counter()-begin)*1000,2)
  begin=time.perf_counter();field=page.locator('#filter-a87e8739-62de-600d-728c-6300bf865f9e')
  field.fill(run.ein[:2]+'-'+run.ein[2:],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  field.press('Enter',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  page.wait_for_function('''({ein,name,id})=>{
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
  text=page.inner_text('body',timeout=300)
  norm=lambda value:re.sub(r'[^a-z0-9]','',value.lower())
  if (run.ein not in re.sub(r'\D','',text) or norm(result['matched_registry_name']) not in norm(text)
      or not re.search(r'Charity ID:\s*'+re.escape(str(result['matched_registry_identifier']))+r'(?![0-9])',text)):
   fact['outcome']='record_binding_failed';return
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
  before=len(run.documents);begin=time.perf_counter();context.capture()
  fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
  fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception:fact['outcome']='owned_visual_unavailable'
 finally:fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_owned_me_page(run,result,page,context,deadline):
 """ME redirects its temporary detail key; bind the rendered credential instead."""
 if run is None or run.state!='ME' or selected_url(run,result) is None:return
 if getattr(run,'selected_visual_attempted',False):return
 run.selected_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'ME-owned-selected-detail','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(5.0,remaining)
  begin=time.perf_counter();response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int(min(3,stop-time.monotonic()-1)*1000)))
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  current=urlsplit(page.url)
  if (response is None or response.status!=200 or current.scheme!='https' or current.hostname!='www.pfr.maine.gov'
      or current.path!='/ALMSOnline/ALMSQuery/ShowDetail.aspx'):
   fact['outcome']='navigation_rejected';return
  text=page.inner_text('body',timeout=400)
  norm=lambda value:re.sub(r'[^a-z0-9]','',value.lower())
  if (norm(result['matched_registry_name']) not in norm(text)
      or not re.search(r'License\s+Number:\s*'+re.escape(result['matched_registry_identifier'])+r'(?!\w)',text,re.I)
      or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
   fact['outcome']='record_binding_failed';return
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
  before=len(run.documents);begin=time.perf_counter();context.capture();fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
  fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception:fact['outcome']='owned_visual_unavailable'
 finally:fact['total_ms']=round((time.perf_counter()-start)*1000,2)

def capture_owned_fl_page(master,run,result,page,context,deadline):
 """Photograph the already-selected FL license in the existing owned browser."""
 if run is not None and run.state=='FL' and result.get('status')=='Not Registered':
  return capture_owned_fl_empty(master,run,result,page,deadline)
 if run is None or run.state!='FL' or selected_url(run,result) is None:return
 if getattr(run,'selected_visual_attempted',False):return
 run.selected_visual_attempted=True
 start=time.perf_counter();transport=None;fact={'adapter':'FL-owned-selected-license','outcome':'not_started','navigation_ms':0,'credential_view_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(6.0,remaining)
  begin=time.perf_counter()
  try:response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int(min(3,stop-time.monotonic()-1)*1000)))
  except Exception as exc:
   if 'ERR_CERT_AUTHORITY_INVALID' not in str(exc):raise
   # Preserve the existing verified certificate-chain recovery. Never disable
   # TLS validation, ignore certificate errors or use a different origin.
   transport=master.FloridaVerifiedTransport(page);transport.deadline=stop;transport.enable()
   response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return
  begin=time.perf_counter();field=page.locator('#cpMainContent_LicenseTb')
  field.fill(result['matched_registry_identifier'],timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  page.locator('#cpMainContent_SingleSearchBt').click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  page.wait_for_function('''({name,id})=>{
   const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
   const text=document.body.innerText;
   return norm(text).includes(norm(name)) && text.includes(id)
    && /Charitable Organization/i.test(text) && /Expires/i.test(text);
  }''',arg={'name':result['matched_registry_name'],'id':result['matched_registry_identifier']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
  rows=master.fl_business_candidate_rows(page.content());norm=lambda value:re.sub(r'[^a-z0-9]','',value.lower())
  bound=[r for r in rows if r.get('business_evidence',{}).get('identifier')==result['matched_registry_identifier'] and norm(r['business_evidence']['name'])==norm(result['matched_registry_name'])]
  fact['credential_view_ms']=round((time.perf_counter()-begin)*1000,2)
  if len(bound)!=1:fact['outcome']='credential_binding_failed';return
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
  before=len(run.documents);begin=time.perf_counter();context.capture();fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
  fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
 except Exception:fact['outcome']='owned_visual_unavailable'
 finally:
  if transport is not None:transport.close()
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
 if (run is None or run.state!='FL' or result.get('state')!='FL'
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True or result.get('status')!='Not Registered'
     or not run.name or getattr(run,'negative_visual_attempted',False)):return
 run.negative_visual_attempted=True
 start=time.perf_counter();transport=None
 fact={'adapter':'FL-owned-completed-empty','outcome':'not_started','phase':'admission',
       'navigation_ms':0,'visual_query_count':0,'query_ms':0,'capture_ms':0,'total_ms':0}
 run.visual_adapter_facts.append(fact)
 url='https://csapp.fdacs.gov/CSPublicApp/CheckACharity/CheckACharity.aspx'
 name=run.name
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(6.0,remaining)
  timeout=lambda:max(1,int((stop-time.monotonic()-1)*1000))
  fact['phase']='navigation';begin=time.perf_counter()
  try:response=page.goto(url,wait_until='domcontentloaded',timeout=timeout())
  except Exception as exc:
   if 'ERR_CERT_AUTHORITY_INVALID' not in str(exc):raise
   transport=master.FloridaVerifiedTransport(page);transport.deadline=stop;transport.enable()
   response=page.goto(url,wait_until='domcontentloaded',timeout=timeout())
  fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
  if response is None or response.status!=200 or page.url!=url:
   fact['outcome']='navigation_rejected';return
  initial=page.evaluate(FL_EMPTY_CRITERIA)
  if not initial or any(initial[k] for k in initial if k not in {'BusinessNameTb','warning','results_visible'}):
   fact['outcome']='restricted_or_missing_filter';return
  page.locator('#cpMainContent_BusinessNameTb').fill(name,timeout=timeout())
  fact['phase']='visual_query';begin=time.perf_counter();issued=time.time()
  fact['visual_query_count']=1
  page.locator('#cpMainContent_SingleSearchBt').click(timeout=timeout())
  page.locator('#cpMainContent_NoResultLb').wait_for(state='visible',timeout=timeout())
  fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
  fields=page.evaluate(FL_EMPTY_CRITERIA)
  normalize=lambda value:re.sub(r'\s+',' ',str(value or '')).strip()
  expected='No result found for '+name
  if (page.url!=url or not fields or fields['BusinessNameTb']!=name
      or fields['results_visible'] or normalize(fields['warning'])!=normalize(expected)
      or any(fields[k] for k in fields if k not in {'BusinessNameTb','warning','results_visible'})):
   fact['outcome']='empty_view_not_bound';return
  text=page.inner_text('body',timeout=timeout())
  if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):
   fact['outcome']='source_verification_pending';return
  completed_visual_name_receipt(run,name,url,issued,'Business Name; License blank; all advanced filters blank',0)
  if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
  fact['phase']='capture';begin=time.perf_counter()
  raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(1500,timeout()))
  fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
  if (page.url!=url or page.evaluate(FL_EMPTY_CRITERIA)!=fields
      or page.inner_text('body',timeout=timeout())!=text):
   fact['outcome']='source_changed_during_capture';return
  if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return
  before=len(run.documents);run.document(url,raw,'image',text)
  if len(run.documents)>before:
   run.validated_negative_visual_urls.add(url)
   if not hasattr(run,'fl_validated_empty_images'):run.fl_validated_empty_images=set()
   run.fl_validated_empty_images.add(hashlib.sha256(raw).hexdigest());fact['outcome']='captured'
  else:fact['outcome']='capture_failed'
 except Exception as exc:
  fact['outcome']='owned_empty_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:
  if transport is not None:transport.close()
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
 if run is None or run.state!='OH' or re.sub(r'\D','',str(ein))!=run.ein:return None
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
 return observed

def capture_owned_oh_empty(run,page,observed,deadline):
 """Original already-completed exact-EIN empty table, never an initial blank form."""
 if (run is None or run.state!='OH' or not observed or not observed.get('response_ok')
     or observed.get('receipt') is None or getattr(run,'oh_empty_captured',False)):return
 start=time.perf_counter();fact={'adapter':'OH-existing-completed-EIN-empty','outcome':'not_started',
  'new_queries':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 url='https://charitableregistration.ohioago.gov/Charities/ResearchCharities'
 try:
  if time.monotonic()+3>=deadline:fact['outcome']='deadline_reserve';return
  u=urlsplit(page.url)
  if (u.scheme!='https' or u.netloc!='charitableregistration.ohioago.gov'
      or u.path!='/Charities/ResearchCharities' or u.query or u.fragment not in {'','results'}):
   fact['outcome']='wrong_source';return
  fields=page.evaluate(OH_EMPTY_FIELDS)
  if (not fields or fields['empty'] is not True
      or re.sub(r'\D','',fields['EIN'])!=run.ein or fields['ddlEINFilterCriteriaList']!='3'
      or any(fields[k] for k in fields if k not in {'EIN','ddlEINFilterCriteriaList','empty'})):
   fact['outcome']='empty_criteria_not_bound';return
  text=page.inner_text('body',timeout=400)
  if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):
   fact['outcome']='source_verification_pending';return
  entries=[r for r in getattr(run,'search_history_receipts',[]) if r.get('query_id')==observed['receipt'].query_id]
  if len(entries)!=1:fact['outcome']='issued_receipt_missing';return
  entries[0].update(outcome='Completed source response',completed_at=time.time(),reported_at=time.time(),returned_rows=0,observation_kind='validated_visual_response')
  begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=1000)
  fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
  if page.url!=u.geturl() or page.evaluate(OH_EMPTY_FIELDS)!=fields or page.inner_text('body',timeout=400)!=text:
   fact['outcome']='source_changed_during_capture';return
  if time.monotonic()+1>=deadline:fact['outcome']='capture_completed_too_late';return
  before=len(run.documents);run.document(page.url,raw,'image',text)
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
     or page.url!='https://charity.ehawaii.gov/charity/search.html'):return
 digits=lambda value:re.sub(r'\D','',value)
 if not (fein and digits(fein)==run.ein or not fein and name and name in getattr(run,'known_names',[run.name])):return
 started=time.perf_counter();fact={'adapter':'HI-owned-completed-empty-warning','outcome':'not_started','capture_ms':0,'total_ms':0,'extra_registry_queries':0};run.visual_adapter_facts.append(fact)
 try:
  warning=page.locator('#orgWarning')
  if (page.locator('#name').input_value(timeout=400)!=name or digits(page.locator('#fein').input_value(timeout=400))!=digits(fein)
      or page.locator('#nameFilter').input_value(timeout=400)!='CONTAINS'
      or not page.locator('#searchOrganizationWarning').is_visible() or not warning.is_visible()
      or not warning.inner_text(timeout=400).strip().startswith('The charitable organization you entered is not registered in our system.')
      or page.locator('#org-results-container').is_visible()
      or any(page.locator('#'+field).input_value(timeout=400) for field in ['city','country','state','zipCode','registrationStatus','inactivityReason','registrationType'])):fact['outcome']='empty_query_not_bound';return
  label='Contains; '+('FEIN '+fein if fein else 'FEIN blank')+'; other search filters blank'
  query={'state':'HI','operation':'search','filter_label':label,'source_kind':'state_portal','url':'https://charity.ehawaii.gov/charity/search-charity.json'}
  query.update({'name':name} if name else {'ein':digits(fein)})
  if response is not None:
   from deployment.search_observation import complete_hi_empty_receipt
   complete_hi_empty_receipt(run,response,name,fein,issued)
  else:
   # Upgrade only the actual name transport receipt issued by this same action.
   # EIN-only searches have no passive name receipt; retain their actual issue clock.
   found=[r for r in getattr(run,'search_history_receipts',[]) if r.get('issued_at',0)>=issued and r.get('query',{}).get('name','')==name and (name or r.get('query',{}).get('ein')==digits(fein)) and urlsplit(r.get('query',{}).get('url','')).hostname=='charity.ehawaii.gov']
   if found:
    entry=found[-1];entry['query'].update(query);entry.update(outcome='Completed source response',completed_at=time.time(),reported_at=time.time(),returned_rows=0,observation_kind='validated_visual_response')
   else:
    from deployment.search_history import SourceQueryReceipt
    receipt=SourceQueryReceipt(run,query);receipt.issued=issued;receipt.complete(0)
  if getattr(run,'hi_empty_original_saved',False):fact['outcome']='receipt_validated_original_already_saved';return
  before=len(run.documents);begin=time.perf_counter();run.page(page);fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
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
     or not re.search(r'No records found with your search criteria\.',body,re.I)):return
 started=time.perf_counter();fact={'adapter':'WV-owned-existing-empty-alert','phase':'binding','outcome':'not_started','capture_ms':0,'total_ms':0,'extra_registry_queries':0};run.visual_adapter_facts.append(fact)
 try:
  prefix='#CharitiesSearch-CharitiesSearch_'
  if (page.locator('#ddlType').input_value(timeout=400)!='1' or page.locator(prefix+'txtName').input_value(timeout=400)!=query_name
      or page.get_by_text('No records found with your search criteria.',exact=True).count()!=1
      or not page.get_by_text('No records found with your search criteria.',exact=True).is_visible()
      or any(page.locator(selector).input_value(timeout=400) for selector in [prefix+'txtID','#CharitiesSearch_CharitiesSearch_txtdbaName',prefix+'txtState',prefix+'txtCity',prefix+'txtExpirationStartDate',prefix+'txtExpirationEndDate','#ddlCounty','#ddlStatus','#ddlCharityRatingWV','#ddlCharityRatingNational'])):fact['outcome']='empty_criteria_not_bound';return
  completed_visual_name_receipt(run,query_name,page.url,issued,'Charity Name; Type CHARITABLE ORGANIZATIONS; other filters blank; source name comparison not recorded',0)
  before=len(run.documents);begin=time.perf_counter();fact['phase']='capture';run.page(page);fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
  if len(run.documents)>before:run.wv_empty_original_saved=True;fact['outcome']='captured'
  else:fact['outcome']='capture_failed'
 except Exception as exc:fact['outcome']='owned_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def capture_negative_wv_source(master,result,run,deadline):
 """Actual WV no-record alert, with its original charity/name criteria."""
 if (run is None or run.state!='WV' or result.get('state')!='WV' or result.get('status')!='Not Registered'
     or result.get('success') is not True or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('matched_registry_name') or result.get('matched_registry_identifier')
     or result.get('source_url')!='https://erls.wvsos.gov/OnlineCharitiesSearch/Search'
     or getattr(run,'negative_visual_attempted',False)):return
 if not any(r.get('query',{}).get('name')==run.name and r.get('query',{}).get('state')=='WV' for r in getattr(run,'search_history_receipts',[])):return
 run.negative_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'WV-original-completed-empty-alert','phase':'admission','outcome':'not_started','navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(8.0,remaining);held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1100},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();begin=time.perf_counter();fact['phase']='navigation'
    response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)));fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return
    begin=time.perf_counter();fact['phase']='visual_name_query';prefix='#CharitiesSearch-CharitiesSearch_'
    page.locator('#ddlType').select_option('1',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.locator(prefix+'txtName').fill(run.name,timeout=max(1,int((stop-time.monotonic()-1)*1000)));issued=time.time()
    page.locator(prefix+'btnSearch').click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.get_by_text('No records found with your search criteria.',exact=True).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if (page.url!=result['source_url'] or page.get_by_text('No records found with your search criteria.',exact=True).count()!=1
        or page.locator('#ddlType').input_value(timeout=400)!='1' or page.locator(prefix+'txtName').input_value(timeout=400)!=run.name
        or any(page.locator(selector).input_value(timeout=400) for selector in [prefix+'txtID','#CharitiesSearch_CharitiesSearch_txtdbaName',prefix+'txtState',prefix+'txtCity',prefix+'txtExpirationStartDate',prefix+'txtExpirationEndDate','#ddlCounty','#ddlStatus','#ddlCharityRatingWV','#ddlCharityRatingNational'])):fact['outcome']='empty_criteria_not_bound';return
    completed_visual_name_receipt(run,run.name,result['source_url'],issued,'Charity Name; Type CHARITABLE ORGANIZATIONS; other filters blank; source name comparison not recorded',0)
    fact['visual_name_queries']=1;fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    before=len(run.documents);begin=time.perf_counter();fact['phase']='capture';context.capture();fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def capture_negative_ct_source(master,result,run,deadline):
 """Photograph one actual issued name's original CT zero-result view."""
 if (run is None or run.state!='CT' or result.get('state')!='CT' or result.get('status')!='Not Registered'
     or result.get('success') is not True or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('matched_registry_name') or result.get('matched_registry_identifier')
     or result.get('source_url')!='https://www.elicense.ct.gov/lookup/licenselookup.aspx'
     or getattr(run,'negative_visual_attempted',False)):return
 receipts=[r for r in getattr(run,'search_history_receipts',[]) if r.get('query',{}).get('state')=='CT'
           and r.get('query',{}).get('operation')=='search' and r.get('query',{}).get('source_kind')=='state_portal'
           and r.get('query',{}).get('url')==result['source_url'] and r.get('query',{}).get('name')==run.name]
 if not receipts:return
 run.negative_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'CT-original-completed-empty-view','phase':'admission','outcome':'not_started','navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(8.0,remaining);held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1400},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();fact['phase']='navigation';begin=time.perf_counter()
    response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)));fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return
    prefix='#ctl00_MainContentPlaceHolder_ucLicenseLookup_';fact['phase']='visual_name_query';begin=time.perf_counter()
    page.locator(prefix+'ctl03_ddCredPrefix').select_option('CHR',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.locator(prefix+'ctl03_tbDBA_Contact').fill(run.name,timeout=max(1,int((stop-time.monotonic()-1)*1000)));issued=time.time()
    page.locator(prefix+'btnLookup').click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.get_by_text('Showing 0 result(s).',exact=True).wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if (page.get_by_text('Showing 0 result(s).',exact=True).count()!=1
        or page.locator(prefix+'ctl03_tbDBA_Contact').input_value(timeout=400)!=run.name
        or page.locator(prefix+'ctl03_ddCredPrefix').input_value(timeout=400)!='CHR'
        or page.locator('forge-card').count()!=0):fact['outcome']='empty_view_not_bound';return
    observed=[r for r in getattr(run,'search_history_receipts',[]) if r.get('issued_at',0)>=issued
              and r.get('query',{}).get('name')==run.name and r.get('query',{}).get('url')==result['source_url']]
    if not observed:fact['outcome']='visual_query_receipt_missing';return
    observed[-1].update(outcome='Completed source response',completed_at=time.time(),reported_at=time.time(),returned_rows=0,observation_kind='validated_visual_response')
    observed[-1]['query']['filter_label']='Business Name / DBA / Nickname; License Type CHR; source name comparison not recorded'
    fact['visual_name_queries']=1;fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    text=page.inner_text('body',timeout=400)
    if re.search('verify you are human|user validation required|access denied|just a moment|Searching, please wait',text,re.I):fact['outcome']='source_still_pending';return
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    fact['phase']='capture';before=len(run.documents);begin=time.perf_counter();context.capture();fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
    if len(run.documents)>before:run.validated_negative_visual_urls.update(d[0] for d in run.documents[before:]);fact['outcome']='captured'
    else:fact['outcome']='capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
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
 if (run is None or run.state!='CA' or result.get('state')!='CA'
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('status')!='Not Registered' or result.get('success') is not True
     or getattr(run,'negative_visual_attempted',False)):return
 run.negative_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None;receipt=None
 fact={'adapter':'CA-original-completed-empty-global-search','phase':'admission','outcome':'not_started','extra_registry_queries':0,'navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(18,remaining);held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  criterion=run.ein[:2]+'-'+run.ein[2:]
  with master.checker.sync_playwright() as pw:
   phase_start=time.perf_counter();browser=master.launch_lookup_browser(pw,headless=True);fact['browser_acquire_ms']=round((time.perf_counter()-phase_start)*1000,2)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    phase_start=time.perf_counter();context=browser.new_context(**options);page=context.new_page();fact['context_start_ms']=round((time.perf_counter()-phase_start)*1000,2);timeout=lambda:max(1,int((stop-time.monotonic()-1)*1000))
    begin=time.perf_counter();fact['phase']='navigation';response=page.goto(CA_PUBLIC_SEARCH,wait_until='domcontentloaded',timeout=timeout())
    if response is None or response.status!=200 or page.url!=CA_PUBLIC_SEARCH:fact['outcome']='navigation_rejected';return
    field=page.get_by_placeholder('Search...',exact=True);field.wait_for(state='visible',timeout=timeout());fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    from deployment.search_history import begin_source_query
    receipt=begin_source_query('CA',criterion,'Global search across public fields, including FEIN; case-insensitive term match',CA_PUBLIC_SEARCH)
    if receipt:receipt.query.pop('name',None);receipt.query['ein']=criterion
    fact['phase']='visual_EIN_query';begin=time.perf_counter()
    def same_query(r):
     if urlsplit(r.url).path!='/api/data/objects/entity/instances':return False
     try:return criterion in parse_qs(urlsplit(r.url).query).get('filter',[''])[0]
     except ValueError:return False
    with page.expect_response(same_query,timeout=timeout()) as pending:
     field.fill(criterion,timeout=timeout());field.press('Enter',timeout=timeout());fact['extra_registry_queries']=1
    page.get_by_text('No Data',exact=True).wait_for(state='visible',timeout=timeout())
    if not ca_empty_response_bound(pending.value,criterion):fact['outcome']='empty_response_rejected';return
    page.locator('.ag-overlay-loading-center').wait_for(state='hidden',timeout=timeout())
    fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    if receipt:receipt.complete(0,rows=[])
    text=page.inner_text('body',timeout=400)
    if field.input_value(timeout=300)!=criterion or page.locator('.ag-row').count()!=0 or 'Registry of Charities and Fundraisers' not in text:fact['outcome']='displayed_criteria_rejected';return
    begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(1000,timeout()))
    if page.url!=CA_PUBLIC_SEARCH or field.input_value(timeout=300)!=criterion or page.inner_text('body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return
    before=len(run.documents);run.document(CA_PUBLIC_SEARCH,raw,'image',text,note='Original California empty public global-search view for displayed FEIN term '+criterion+'. The separate history records this additional visual query; this image alone does not establish all name searches.')
    if len(run.documents)>before:
     run.ca_validated_empty_images=getattr(run,'ca_validated_empty_images',set());run.ca_validated_empty_images.add(hashlib.sha256(raw).hexdigest());fact['outcome']='captured'
    else:fact['outcome']='image_admission_rejected'
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
   finally:
    phase_start=time.perf_counter()
    if context is not None:context._captured=True;context.close()
    fact['context_close_ms']=round((time.perf_counter()-phase_start)*1000,2)
    phase_start=time.perf_counter()
    if browser is not None:browser.close()
    fact['browser_close_ms']=round((time.perf_counter()-phase_start)*1000,2)
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:200]
 finally:
  if receipt:receipt.incomplete()
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
  fact['total_ms']=round((time.perf_counter()-started)*1000,2)

def capture_negative_search(master,result,run,deadline):
 if run is not None and run.state=='VA':return capture_negative_va_source(master,result,run,deadline)
 """Known completed-negative source views; never invent a page or zero count."""
 if run is not None and run.state=='CA':return capture_negative_ca_source(master,result,run,deadline)
 if run is not None and run.state=='NJ':return capture_negative_nj_source(master,result,run,deadline)
 if run is not None and run.state=='RI':return capture_negative_ri_source(master,result,run,deadline)
 if run is not None and run.state=='LA':return capture_selected_la_source(master,result,run,deadline,negative=True)
 if run is not None and run.state=='CT':return capture_negative_ct_source(master,result,run,deadline)
 if (run is None or run.state!='WI' or result.get('state')!='WI'
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('status')!='Not Registered' or result.get('success') is not True
     or not getattr(run,'source_search_hint',None) or getattr(run,'negative_visual_attempted',False)):return
 hint=run.source_search_hint;u=urlsplit(hint['url']);pairs=parse_qsl(u.query,keep_blank_values=True);params=dict(pairs)
 if (u.scheme!='https' or u.hostname!='apps.dfi.wi.gov' or u.path!='/ice/berg/Registration/OrgCredentialSearchResults.aspx'
     or len(pairs)!=3 or set(params)!={'CredentialType','LicenseNumber','FirmName'}
     or params['CredentialType']!='800' or params['LicenseNumber'] or params['FirmName']!=hint['name']):return
 run.negative_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'WI-completed-negative-view','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 held=False;context=browser=None
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(8.0,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1280,'height':900},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();begin=time.perf_counter();issued=time.time()
    response=page.goto(hint['url'],wait_until='domcontentloaded',timeout=max(1,int(min(4,stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=hint['url']:fact['outcome']='navigation_rejected';return
    text=page.inner_text('body',timeout=400)
    if (not re.search(r'(?:There are )?no query results',text,re.I)
        or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
     fact['outcome']='not_a_completed_empty_view';return
    # Upgrade only the observed request issued by this exact visual GET.
    receipts=[r for r in getattr(run,'search_history_receipts',[]) if r.get('issued_at',0)>=issued
              and r.get('query',{}).get('name')==hint['name']
              and urlsplit(r.get('query',{}).get('url','')).path==u.path]
    if receipts:
     receipts[-1].update(outcome='Completed source response',completed_at=time.time(),reported_at=time.time(),returned_rows=0,observation_kind='validated_visual_response')
    else:run.search_history_overflow=True
    fact['visual_query_receipt_bound']=bool(receipts)
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    before=len(run.documents);begin=time.perf_counter();context.capture();fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
    if len(run.documents)>before:
     run.validated_negative_visual_urls.update(d[0] for d in run.documents[before:]);fact['outcome']='captured'
    else:fact['outcome']='capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception:fact['outcome']='source_visual_unavailable'
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
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
 if run is None or run.state!='RI' or deadline-time.monotonic()<1:return False
 try:
  req=response.request;payload=req.post_data_json;data=response.json()
  if (response.status!=200 or response.url!=RI_SEARCH_API or req.method!='POST'
      or payload.get('type')!='credential' or payload.get('start')!=0
      or payload.get('rows')!=10 or payload.get('appliedFilters') not in (None,[])
      or payload.get('formRequest',{}).get('values')!={'organizationName':query,'licenseType':'Charitable Organization'}
      or type(data.get('resultCount')) is not int or data['resultCount']!=0 or data.get('results')!=[]
      or data.get('message',{}).get('errors')
      or data.get('appliedFilters')!=['licenseType:Charitable Organization']
      or [x.get('label') for x in data.get('searchChips',[])]!=[query]
      or page.url!=RI_SEARCH_ROOT+'search'):return False
  empty=page.get_by_role('heading',name=RI_EMPTY_MESSAGE,exact=True)
  if empty.count()!=1 or not empty.is_visible():return False
  text=page.inner_text('body',timeout=400)
  if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):return False
  completed_visual_name_receipt(run,query,RI_SEARCH_API,issued,'Organization Name; Credential Type Charitable Organization; other filters blank; source name comparison not recorded',0)
  before=len(run.documents);run.page(page)
  if len(run.documents)==before:return False
  run.validated_negative_visual_urls.update(d[0] for d in run.documents[before:])
  run.ri_validated_empty_images={hashlib.sha256(d[1]).hexdigest() for d in run.documents[before:]}
  return True
 except Exception:return False

def capture_negative_ri_source(master,result,run,deadline):
 """One visual replay of an already completed empty RI name, without status changes."""
 if (run is None or run.state!='RI' or result.get('state')!='RI'
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True or result.get('status')!='Not Registered'
     or getattr(run,'negative_visual_attempted',False)):return
 receipts=[r for r in getattr(run,'search_history_receipts',[]) if r.get('query',{}).get('state')=='RI'
           and r.get('query',{}).get('url')==RI_SEARCH_API
           and isinstance(r.get('query',{}).get('name'),str) and r['query']['name'].strip()
           and r.get('outcome')=='Completed source response' and type(r.get('returned_rows')) is int and r['returned_rows']==0]
 if not receipts:return
 query=receipts[0]['query']['name'];run.negative_visual_attempted=True
 started=time.perf_counter();held=False;browser=context=None
 fact={'adapter':'RI-completed-negative-view','outcome':'not_started','phase':'admission','extra_registry_queries':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(8,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as pw:
   browser=master.launch_lookup_browser(pw,headless=True)
   try:
    options={'viewport':{'width':1280,'height':900},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page()
    timeout=lambda:max(1,int(min(4,stop-time.monotonic()-1)*1000))
    fact['phase']='navigation';response=page.goto(RI_SEARCH_ROOT,wait_until='domcontentloaded',timeout=timeout())
    if response is None or response.status!=200 or page.url!=RI_SEARCH_ROOT:fact['outcome']='navigation_rejected';return
    page.get_by_role('button',name='Search',exact=True).wait_for(timeout=timeout())
    page.get_by_label('Organization Name',exact=True).fill(query,timeout=timeout())
    page.get_by_label('Credential Type',exact=True).fill('Charitable Organization',timeout=timeout())
    page.get_by_role('option',name='Charitable Organization',exact=True).click(timeout=timeout())
    fields=page.evaluate(RI_FORM_FIELDS)
    expected={k:'' for k in ['Last Name','First Name','Organization Name','Board','Credential Type','Credential Number','Credential Status','City','State','Zip Code']}
    expected.update({'Organization Name':query,'Credential Type':'Charitable Organization'})
    if fields!=expected:fact['outcome']='criteria_rejected';return
    fact['phase']='submitted_query';issued=time.time()
    with page.expect_response(lambda r:r.url==RI_SEARCH_API and r.request.method=='POST',timeout=timeout()) as pending:
     page.get_by_role('button',name='Search',exact=True).click(timeout=timeout());fact['extra_registry_queries']=1
    page.get_by_role('heading',name=RI_EMPTY_MESSAGE,exact=True).wait_for(timeout=timeout())
    fact['phase']='binding_and_capture';begin=time.perf_counter()
    ok=capture_ri_completed_empty(run,page,pending.value,query,issued,stop)
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);fact['outcome']='captured' if ok else 'empty_binding_rejected'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
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
 if (result.get('state')!='NJ' or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True or result.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not result.get('matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return
 identifier=str(result.get('matched_registry_identifier') or '')
 hint=getattr(run,'source_detail_hints',{}).get(identifier)
 norm=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
 if not hint or norm(hint.get('name'))!=norm(result['matched_registry_name']):return
 try:
  u=urlsplit(hint['url']);params=parse_qsl(u.query,keep_blank_values=True)
  if (u.scheme!='https' or u.hostname!='charportal.dca.njoag.gov' or u.port not in (None,443)
      or u.username or u.password or u.path!='/CHR-Public-Details-Page/' or u.fragment
      or [k for k,v in params]!=['id','rid']
      or any(not re.fullmatch(r'[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}',value) for key,value in params)
      or identifier!=run.ein):return
 except (ValueError,TypeError,KeyError):return
 run.selected_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'NJ-selected-original-detail','outcome':'not_started','navigation_ms':0,'capture_ms':0,'total_ms':0,'phase':'admission'};run.visual_adapter_facts.append(fact)
 held=False;browser=context=None
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(15.0,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  fact['phase']='playwright_start';begin=time.perf_counter()
  with master.checker.sync_playwright() as p:
   fact['playwright_start_ms']=round((time.perf_counter()-begin)*1000,2)
   fact['phase']='browser_acquire';begin=time.perf_counter();browser=master.launch_lookup_browser(p,headless=True)
   fact['browser_acquire_ms']=round((time.perf_counter()-begin)*1000,2)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    fact['phase']='context_start';begin=time.perf_counter();context=browser.new_context(**options);page=context.new_page()
    fact['context_start_ms']=round((time.perf_counter()-begin)*1000,2);begin=time.perf_counter();fact['phase']='navigation'
    # Required public values are present in the response HTML. Waiting for all
    # document scripts can consume the allowance before those values are read.
    # Readiness below still requires the actual visible selected fields; the
    # original eight-second visual deadline and capture reserve stay intact.
    response=page.goto(hint['url'],wait_until='commit',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=hint['url']:fact['outcome']='navigation_rejected';return
    fact['phase']='selected_fields_ready';begin=time.perf_counter();page.wait_for_function('''({ein,name})=>{
     const n=document.querySelector('#name'),e=document.querySelector('#crsm_federalein'),r=document.querySelector('#accountnumber'),f=document.querySelector('#crsm_fiscalyearenddate_datepicker_description');
     const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
     return n&&e&&r&&f&&norm(n.value)===norm(name)&&e.value.replace(/\\D/g,'')===ein&&/^CH[0-9]+$/.test(r.value)&&f.value;
    }''',arg={'ein':run.ein,'name':result['matched_registry_name']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['selected_fields_ready_ms']=round((time.perf_counter()-begin)*1000,2)
    fields=page.evaluate(NJ_VISIBLE_FIELDS)
    if (not fields or norm(fields['name'])!=norm(result['matched_registry_name'])
        or re.sub(r'\D','',fields['crsm_federalein'])!=run.ein
        or not re.fullmatch(r'CH\d+',fields['accountnumber']) or not fields['crsm_filestanding']
        or not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',fields['crsm_fiscalyearenddate_datepicker_description'])):
     fact['outcome']='record_binding_failed';return
    if page.evaluate(NJ_VISIBLE_GEOMETRY) is not True:fact['outcome']='selected_fields_overlap';return
    text=page.inner_text('body',timeout=400)
    if re.search('verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='source_verification_pending';return
    size=page.locator('body').evaluate('(el)=>({width:el.scrollWidth,height:el.scrollHeight})')
    if size['width']<=0 or size['height']<=0 or size['width']*size['height']>20000000:fact['outcome']='source_size_rejected';return
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    fact['phase']='capture';begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=75,full_page=True,timeout=max(1,int(min(1.5,stop-time.monotonic()-1)*1000)))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    if page.url!=hint['url'] or page.evaluate(NJ_VISIBLE_FIELDS)!=fields or page.evaluate(NJ_VISIBLE_GEOMETRY) is not True or page.inner_text('body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return
    if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return
    # Metadata describes visible original values; source pixels are never redrawn.
    bound_text=text+'\n'+'\n'.join(key+': '+value for key,value in fields.items())
    before=len(run.documents);run.document(hint['url'],raw,'image',bound_text[:20000])
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:
  fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__
  if fact['phase']=='navigation':fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
  fact['total_ms']=round((time.perf_counter()-start)*1000,2)


def capture_selected_wv_source(master,result,run,deadline):
 """Use the visible WV ID search and actual organization-ID detail link."""
 if (result.get('state')!='WV' or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('success') is not True or result.get('status') in {'Not Registered','Unable to Confirm','Site Not Reachable'}
     or not result.get('matched_registry_name') or getattr(run,'selected_visual_attempted',False)):return
 identifier=str(result.get('matched_registry_identifier') or '')
 if not re.fullmatch(r'[A-Z]?\d{1,20}',identifier) or result.get('source_url')!='https://erls.wvsos.gov/OnlineCharitiesSearch/Search':return
 norm=lambda value:re.sub(r'[^a-z0-9]','',str(value).lower())
 if any(d[2] in {'image','source_pdf'} and norm(result['matched_registry_name']) in norm(d[3]) and re.search(r'(?<!\w)'+re.escape(identifier)+r'(?!\w)',d[3]) for d in run.documents):return
 run.selected_visual_attempted=True
 start=time.perf_counter();fact={'adapter':'WV-selected-credential-view','outcome':'not_started','phase':'admission','navigation_ms':0,'credential_search_ms':0,'detail_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 held=False;context=browser=None
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(8.0,remaining)
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as p:
   browser=master.launch_lookup_browser(p,headless=True)
   try:
    options={'viewport':{'width':1280,'height':900},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();begin=time.perf_counter();fact['phase']='navigation'
    response=page.goto(result['source_url'],wait_until='domcontentloaded',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    if response is None or response.status!=200 or page.url!=result['source_url']:fact['outcome']='navigation_rejected';return
    begin=time.perf_counter();fact['phase']='credential_search'
    page.locator('#ddlType').select_option('1',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.locator('#CharitiesSearch-CharitiesSearch_txtID').fill(identifier,timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.locator('#CharitiesSearch-CharitiesSearch_btnSearch').click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    row=page.locator('#xhtml_grid tr').filter(has=page.locator('a').filter(has_text=re.compile('^'+re.escape(identifier)+'$')))
    row.wait_for(state='visible',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    if row.count()!=1 or norm(result['matched_registry_name']) not in norm(row.inner_text(timeout=400)):fact['outcome']='selected_row_binding_failed';return
    fact['credential_search_ms']=round((time.perf_counter()-begin)*1000,2);fact['visual_credential_queries']=1
    link=row.locator('a')
    if link.count()!=1 or not re.fullmatch(r'NavigateLienInfo\(\d+\)',link.get_attribute('onclick') or ''):fact['outcome']='source_detail_control_changed';return
    begin=time.perf_counter();fact['phase']='detail'
    link.click(timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.wait_for_url('https://erls.wvsos.gov/OnlineCharitiesSearch/CharitiesInformation',timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    page.wait_for_function('''({id,name})=>{
      const norm=x=>String(x).toLowerCase().replace(/[^a-z0-9]/g,'');
      const text=document.body.innerText;
      return norm(text).includes(norm(name))&&new RegExp('ID:\\\\s*'+id+'\\\\s+Initial Registration Date:').test(text)
        &&/Expiration Date:/.test(text)&&/Status:/.test(text)&&!/Please wait\\.\\.\\./i.test(text);
    }''',arg={'id':identifier,'name':result['matched_registry_name']},timeout=max(1,int((stop-time.monotonic()-1)*1000)))
    fact['detail_ms']=round((time.perf_counter()-begin)*1000,2)
    text=page.inner_text('body',timeout=400)
    if (not re.search(r'\bID:\s*'+re.escape(identifier)+r'\s+Initial Registration Date:',text)
        or norm(result['matched_registry_name']) not in norm(text)
        or re.search('verify you are human|user validation required|access denied|just a moment',text,re.I)):
     fact['outcome']='detail_binding_failed';return
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    begin=time.perf_counter();fact['phase']='capture';before=len(run.documents);context.capture();fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
    fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__
 finally:
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
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
 if (run is None or run.state!='NJ' or result.get('state')!='NJ'
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('status')!='Not Registered' or result.get('success') is not True
     or result.get('matched_registry_name') or result.get('matched_registry_identifier')
     or getattr(run,'negative_visual_attempted',False)):return
 run.negative_visual_attempted=True;start=time.perf_counter();held=False;browser=context=None;receipt=None
 fact={'adapter':'NJ-original-completed-empty-search','phase':'admission','outcome':'not_started','extra_registry_queries':0,'navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(18.0,remaining);timeout=lambda:max(1,int((stop-time.monotonic()-1)*1000))
  held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  with master.checker.sync_playwright() as pw:
   browser=master.launch_lookup_browser(pw,headless=True)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    context=browser.new_context(**options);page=context.new_page();begin=time.perf_counter();fact['phase']='navigation'
    response=page.goto(NJ_PUBLIC_SEARCH,wait_until='domcontentloaded',timeout=timeout())
    if response is None or response.status!=200 or page.url!=NJ_PUBLIC_SEARCH:fact['outcome']='navigation_rejected';return
    box=page.locator(NJ_SEARCH_SELECTOR).first;box.wait_for(state='visible',timeout=timeout());fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    from deployment.search_history import begin_source_query
    receipt=begin_source_query('NJ',run.ein,'Public search across charity name, registration number and Federal EIN',NJ_PUBLIC_SEARCH)
    if receipt:receipt.query.pop('name',None);receipt.query['ein']=run.ein
    fact['phase']='visual_EIN_query';begin=time.perf_counter()
    def same_query(r):
     try:return r.request.method=='POST' and urlsplit(r.url).path.startswith('/_services/entity-grid-data.json/') and r.request.post_data_json.get('search')==run.ein
     except Exception:return False
    with page.expect_response(same_query,timeout=timeout()) as pending:
     box.fill(run.ein,timeout=timeout());box.press('Enter',timeout=timeout());fact['extra_registry_queries']=1
    if not nj_empty_response_bound(pending.value,run.ein):fact['outcome']='empty_response_rejected';return
    grid=page.locator('.public-search-grid');grid.get_by_text('No records to show',exact=True).wait_for(state='visible',timeout=timeout())
    if box.input_value(timeout=300)!=run.ein or grid.locator('tbody tr[data-id]').count():fact['outcome']='displayed_query_rejected';return
    fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    from deployment.search_observation import complete_browser_query
    complete_browser_query(receipt,pending.value,0,rows=[])
    text=page.inner_text('body',timeout=400);grid_text=grid.inner_text(timeout=400)
    if re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='source_verification_pending';return
    if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
    fact['phase']='capture';begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=75,full_page=True,timeout=min(1000,timeout()))
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
    after={'url':page.url,'ein':box.input_value(timeout=300),'grid':grid.inner_text(timeout=400),'body':page.inner_text('body',timeout=400)}
    before={'url':NJ_PUBLIC_SEARCH,'ein':run.ein,'grid':grid_text,'body':text}
    changed=[key for key in before if (nj_evidence_body_core(before[key])!=nj_evidence_body_core(after[key]) if key=='body' else before[key]!=after[key])]
    if changed:
     import difflib
     fact['outcome']='source_changed_during_capture';fact['changed_components']=changed
     fact['public_body_change']='\n'.join(list(difflib.unified_diff(text.splitlines(),after['body'].splitlines()))[:30])[:1500]
     return
    before=len(run.documents);run.document(NJ_PUBLIC_SEARCH,raw,'image',after['body'],note='Original New Jersey completed empty search view for displayed Federal EIN '+run.ein+'. The separate search history records this additional visual query and all earlier attempts; one image does not establish the other searches.')
    if len(run.documents)>before:
     run.nj_validated_empty_images=getattr(run,'nj_validated_empty_images',set());run.nj_validated_empty_images.add(hashlib.sha256(raw).hexdigest());fact['outcome']='captured'
    else:fact['outcome']='image_admission_rejected'
   finally:
    if context is not None:context._captured=True;context.close()
    if browser is not None:browser.close()
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:200]
 finally:
  if receipt:receipt.incomplete()
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
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
 """One original VA global-search view, with a separately recorded EIN term."""
 if (run is None or run.state!='VA' or result.get('state')!='VA'
     or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
     or result.get('status')!='Not Registered' or result.get('success') is not True
     or getattr(run,'negative_visual_attempted',False)):return
 run.negative_visual_attempted=True;started=time.perf_counter();held=False;browser=context=None;receipt=None
 fact={'adapter':'VA-original-completed-empty-global-search','phase':'admission','outcome':'not_started','extra_registry_queries':0,'navigation_ms':0,'query_ms':0,'capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
 try:
  remaining=deadline-time.monotonic()-1
  if remaining<3:fact['outcome']='deadline_reserve';return
  stop=time.monotonic()+min(12,remaining);held=master.BROWSER_LOOKUP_SEMAPHORE.acquire(blocking=False)
  if not held:fact['outcome']='browser_capacity_unavailable';return
  criterion=run.ein[:2]+'-'+run.ein[2:]
  with master.checker.sync_playwright() as pw:
   phase_start=time.perf_counter();browser=master.launch_lookup_browser(pw,headless=True);fact['browser_acquire_ms']=round((time.perf_counter()-phase_start)*1000,2)
   try:
    options={'viewport':{'width':1600,'height':1000},'locale':'en-US'}
    if getattr(master,'BROWSER_USER_AGENT',None):options['user_agent']=master.BROWSER_USER_AGENT
    phase_start=time.perf_counter();context=browser.new_context(**options);page=context.new_page();fact['context_start_ms']=round((time.perf_counter()-phase_start)*1000,2);timeout=lambda:max(1,int((stop-time.monotonic()-1)*1000))
    begin=time.perf_counter();fact['phase']='navigation';response=page.goto(VA_FINAL_SEARCH,wait_until='domcontentloaded',timeout=timeout())
    if response is None or response.status!=200 or page.url!=VA_FINAL_SEARCH:fact['outcome']='navigation_rejected';return
    field=page.get_by_placeholder('Search...',exact=True);field.wait_for(state='visible',timeout=timeout());fact['navigation_ms']=round((time.perf_counter()-begin)*1000,2)
    from deployment.search_history import begin_source_query
    receipt=begin_source_query('VA',criterion,'Global search across public fields, including FEIN; case-insensitive term match',VA_FINAL_SEARCH)
    if receipt:receipt.query.pop('name',None);receipt.query['ein']=criterion
    fact['phase']='visual_EIN_query';begin=time.perf_counter()
    def same_query(r):
     if urlsplit(r.url).path!='/api/data/objects/entity/instances':return False
     try:return criterion in parse_qs(urlsplit(r.url).query).get('filter',[''])[0]
     except ValueError:return False
    with page.expect_response(same_query,timeout=timeout()) as pending:
     field.fill(criterion,timeout=timeout());field.press('Enter',timeout=timeout());fact['extra_registry_queries']=1
    page.get_by_text('No Data',exact=True).wait_for(state='visible',timeout=timeout())
    if not va_empty_response_bound(pending.value,criterion):fact['outcome']='empty_response_rejected';return
    page.locator('.ag-overlay-loading-center').wait_for(state='hidden',timeout=timeout())
    page.locator('.ag-center-cols-container .ag-row').first.wait_for(state='hidden',timeout=timeout())
    fact['query_ms']=round((time.perf_counter()-begin)*1000,2)
    if receipt:receipt.complete(0,rows=[])
    text=page.inner_text('body',timeout=400)
    if field.input_value(timeout=300)!=criterion or page.locator('.ag-row').count()!=0 or 'Virginia Department of Agriculture and Consumer Services' not in text:fact['outcome']='displayed_criteria_rejected';return
    begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(1000,timeout()))
    if page.url!=VA_FINAL_SEARCH or field.input_value(timeout=300)!=criterion or page.inner_text('body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return
    before=len(run.documents);run.document(VA_FINAL_SEARCH,raw,'image',text,note='Original Virginia empty public global-search view for displayed FEIN term '+criterion+'. The separate history records this additional visual query; this image alone does not establish all name searches.')
    if len(run.documents)>before:
     run.va_validated_empty_images=getattr(run,'va_validated_empty_images',set());run.va_validated_empty_images.add(hashlib.sha256(raw).hexdigest());fact['outcome']='captured'
    else:fact['outcome']='image_admission_rejected'
    fact['capture_ms']=round((time.perf_counter()-begin)*1000,2);run.capture_ms+=fact['capture_ms']
   finally:
    phase_start=time.perf_counter()
    if context is not None:context._captured=True;context.close()
    fact['context_close_ms']=round((time.perf_counter()-phase_start)*1000,2)
    phase_start=time.perf_counter()
    if browser is not None:browser.close()
    fact['browser_close_ms']=round((time.perf_counter()-phase_start)*1000,2)
 except Exception as exc:fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:200]
 finally:
  if receipt:receipt.incomplete()
  if held:master.BROWSER_LOOKUP_SEMAPHORE.release()
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

def capture_owned_mi_page(run,result,page,context,deadline):
    """One selected-file visual query, original popup pixels, no status mutation."""
    if result.get('status')=='Not Registered':
        return capture_owned_mi_empty(run,result,context,deadline)
    identifier=str(result.get('matched_registry_identifier') or '')
    if (run is None or run.state!='MI' or result.get('state')!='MI'
        or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
        or result.get('success') is not True
        or result.get('status') in {'Not Registered','Unable to Confirm','Unable to Verify','Site Not Reachable'}
        or not re.fullmatch(r'\d{3,8}',identifier) or not result.get('matched_registry_name')
        or result.get('source_url')!='https://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx'
        or getattr(run,'selected_visual_attempted',False)):return
    run.selected_visual_attempted=True
    start=time.perf_counter();owned=[]
    fact={'adapter':'MI-owned-selected-file-detail','phase':'admission','outcome':'not_started',
          'visual_file_queries':0,'capture_ms':0,'total_ms':0,'local_visual_budget_ms':12000}
    run.visual_adapter_facts.append(fact)
    def official(p):
        u=urlsplit(p.url)
        return (u.scheme=='https' and u.hostname=='www.ag.state.mi.us' and u.port in (None,443)
                and not u.username and not u.password and not u.query and not u.fragment
                and u.path=='/CharitableTrust/frmSearchResults.aspx')
    try:
        remaining=deadline-time.monotonic()-1
        if remaining<3:fact['outcome']='deadline_reserve';return
        stop=time.monotonic()+min(12,remaining)
        def allowance(reserve=1):return max(1,int((stop-time.monotonic()-reserve)*1000))
        detail=None
        # Reuse a selected detail already produced by the normal browser path.
        for existing in list(context.pages):
            if official(existing) and existing.locator(MI_DETAIL_PREFIX+'lblFileNo').count()==1:
                if mi_values_bound(mi_detail_values(existing),result,run.ein):detail=existing;break
        if detail is None:
            fact['phase']='visual_file_search';search=context.new_page();owned.append(search)
            search.goto(result['source_url'],wait_until='domcontentloaded',timeout=allowance())
            u=urlsplit(search.url)
            if u.scheme!='https' or u.hostname!='www.ag.state.mi.us' or u.path not in {'/CharitableTrust/frmDisclaimer.aspx','/CharitableTrust/frmDefault.aspx'}:
                fact['outcome']='search_navigation_rejected';return
            if u.path.endswith('/frmDisclaimer.aspx'):
                search.locator('#ctl00_MainContent_lblYes').click(timeout=allowance())
            field=search.locator('#ctl00_MainContent_txtFileNo')
            field.fill(identifier,timeout=allowance())
            search.locator('#ctl00_MainContent_btnIdSearch').click(timeout=allowance())
            fact['visual_file_queries']=1
            grid=search.locator('#ctl00_MainContent_GridView1')
            grid.wait_for(state='visible',timeout=allowance())
            links=grid.get_by_role('link',name=result['matched_registry_name'],exact=True)
            if links.count()!=1 or not re.search(r'(?<!\d)'+re.escape(identifier)+r'(?!\d)',grid.inner_text(timeout=400)):
                fact['outcome']='selected_result_not_unique';return
            fact['phase']='selected_popup'
            with search.expect_popup(timeout=allowance()) as popup:
                links.click(timeout=allowance())
            detail=popup.value;owned.append(detail)
        fact['phase']='detail_binding'
        detail.locator(MI_DETAIL_PREFIX+'lblSolicitationRegistrationStatus').wait_for(state='visible',timeout=allowance())
        values=mi_detail_values(detail)
        if not official(detail) or not mi_values_bound(values,result,run.ein):fact['outcome']='selected_detail_not_bound';return
        text=detail.inner_text('body',timeout=400)
        if re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='verification_pending';return
        size=detail.locator('body').evaluate('(b)=>({width:Math.max(b.scrollWidth,document.documentElement.scrollWidth,innerWidth),height:Math.max(b.scrollHeight,document.documentElement.scrollHeight,innerHeight)})',timeout=400)
        if not size or min(size.values())<=0 or size['width']*size['height']>20000000:fact['outcome']='image_size_rejected';return
        if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
        fact['phase']='original_image_readiness'
        detail.wait_for_function("() => Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)",timeout=allowance(1))
        if time.monotonic()+1>=stop:fact['outcome']='image_readiness_reserve';return
        fact['phase']='capture';begin=time.perf_counter();url=detail.url
        raw=detail.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(1500,allowance(.5)))
        fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
        if detail.url!=url or mi_detail_values(detail)!=values:fact['outcome']='record_changed_during_capture';return
        if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return
        before=len(run.documents)
        run.document(url,raw,'image',text,note='Original selected Michigan detail, including EIN, solicitation standing and financial period. Retrieved by the already selected AG file number; not a reconstructed report.')
        fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
    except Exception as exc:
        fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
    finally:
        for target in reversed(owned):
            try:target.close()
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
    if (run is None or run.state!='MI' or result.get('state')!='MI'
        or result.get('status')!='Not Registered' or result.get('success') is not True
        or re.sub(r'\D','',str(result.get('ein','')))!=run.ein
        or result.get('completed_exact_ein_empty') is not True
        or result.get('matched_registry_name') or result.get('matched_registry_identifier')
        or result.get('source_url')!='https://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx'
        or getattr(run,'negative_visual_attempted',False)):return
    run.negative_visual_attempted=True;run.mi_negative_visual_guard=True;start=time.perf_counter();owned=None;receipt=None
    fact={'adapter':'MI-owned-original-empty-EIN','phase':'admission','outcome':'not_started','visual_EIN_queries':0,'capture_ms':0,'total_ms':0,'local_visual_budget_ms':12000}
    run.visual_adapter_facts.append(fact)
    try:
        remaining=deadline-time.monotonic()-1
        if remaining<3:fact['outcome']='deadline_reserve';return
        stop=time.monotonic()+min(12,remaining)
        def allowance(reserve=1):return max(1,int((stop-time.monotonic()-reserve)*1000))
        detail=next((p for p in list(context.pages) if mi_empty_values(p,run.ein)),None)
        if detail is None:
            fact['phase']='visual_EIN_search';owned=context.new_page();detail=owned
            detail.goto(result['source_url'],wait_until='domcontentloaded',timeout=allowance())
            if detail.url=='https://www.ag.state.mi.us/CharitableTrust/frmDisclaimer.aspx':
                detail.locator('#ctl00_MainContent_lblYes').click(timeout=allowance())
            if detail.url!=result['source_url']:fact['outcome']='search_navigation_rejected';return
            detail.locator('#ctl00_MainContent_txtEIN').fill(run.ein[:2]+'-'+run.ein[2:],timeout=allowance())
            from deployment.search_history import SourceQueryReceipt
            receipt=SourceQueryReceipt(run,{'state':'MI','operation':'search','ein':run.ein[:2]+'-'+run.ein[2:],'filter_label':'Exact EIN; original public results view','source_kind':'state_portal','url':result['source_url']})
            fact['visual_EIN_queries']=1
            with detail.expect_response(lambda response: response.request.method=='POST' and response.request.url==result['source_url'],timeout=allowance()) as observed_response:
                detail.locator('#ctl00_MainContent_btnTextSearch').click(timeout=allowance())
            query_response=observed_response.value
            detail.locator('#ctl00_MainContent_GridView1').wait_for(state='visible',timeout=allowance())
        fact['phase']='empty_binding';values=mi_empty_values(detail,run.ein)
        if not values:
            if receipt:receipt.incomplete();receipt=None
            fact['outcome']='empty_source_not_bound';return
        if receipt:
            from deployment.search_observation import complete_browser_query
            complete_browser_query(receipt,query_response,0,[]);receipt=None
        fact['phase']='original_image_readiness'
        detail.wait_for_function("() => Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)",timeout=allowance())
        text=detail.inner_text('body',timeout=400)
        if re.search(r'verify you are human|user validation required|access denied|just a moment',text,re.I):fact['outcome']='verification_pending';return
        if time.monotonic()+1>=stop:fact['outcome']='capture_reserve';return
        fact['phase']='capture';begin=time.perf_counter()
        raw=detail.screenshot(type='jpeg',quality=80,full_page=True,timeout=min(1500,allowance(.5)))
        fact['capture_ms']=round((time.perf_counter()-begin)*1000,2)
        if mi_empty_values(detail,run.ein)!=values or detail.inner_text('body',timeout=400)!=text:fact['outcome']='source_changed_during_capture';return
        if time.monotonic()+.5>=stop:fact['outcome']='capture_completed_too_late';return
        import hashlib
        if not hasattr(run,'mi_validated_empty_images'):run.mi_validated_empty_images=set()
        run.mi_validated_empty_images.add(hashlib.sha256(raw).hexdigest())
        before=len(run.documents);run.document(detail.url,raw,'image',text,note='Original completed Michigan exact-EIN result. This image documents this search only; the separate search history lists the other submitted queries.')
        fact['outcome']='captured' if len(run.documents)>before else 'capture_failed'
    except Exception as exc:
        if receipt:receipt.incomplete()
        fact['outcome']='source_visual_unavailable';fact['error_type']=type(exc).__name__;fact['error_summary']=str(exc).splitlines()[0][:180]
    finally:
        if owned is not None:
            try:owned.close()
            except Exception:fact['owned_page_close_error']=True
        run.capture_ms+=fact['capture_ms'];fact['total_ms']=round((time.perf_counter()-start)*1000,2)
