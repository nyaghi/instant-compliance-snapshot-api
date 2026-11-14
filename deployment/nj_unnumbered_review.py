"""Preserve one complete unnumbered NJ exemption for identity review and pixels."""
import hashlib,re,time
from deployment.state_snapshots import CURRENT,DEADLINE
URL='https://charportal.dca.njoag.gov/Charity-Registration/CHR-Public-Search-Page/'
KEYS=('name','accountnumber','crsm_filestanding','crsm_federalein','crsm_addressline1','crsm_mailingcity','crsm_mailingstate','crsm_mailingzip')
REASON='NJ_UNNUMBERED_EXEMPTION_REVIEW'

def candidate(master,org,row,identity):
    if identity not in {'accepted','possible','conflict'} or row.get('address_evidence',{}).get('decision')=='different_ein':
        return None
    row={**row,'url':URL,'_identity_outcome':'conflict'if identity=='conflict'else'possible',
         'license_category':'Unnumbered charitable exemption','expiration':''}
    result=master.scope_identity_review_result(org,'NJ',[row],False,URL)
    if not getattr(result,'_cc_identity_review',None):return None
    result.reason_code=REASON
    result.source_note+=' The public exemption row has no registration number.'
    if not row.get('ein'):result.source_note+=' It does not display an EIN.'
    return result

VIEW=r"""({expected,query,prepare})=>{
 const input=document.querySelector('input[placeholder="Search"]');
 const grids=[...document.querySelectorAll('[role="grid"]')];
 if(grids.length!==1||!input||input.value!==query)return null;
 const rows=[...grids[0].querySelectorAll('[role="row"][data-item-index]')];
 if(rows.length!==1)return null;
 const row=rows[0],norm=x=>String(x??'').replace(/\s+/g,' ').trim(),fields={};
 for(const key of Object.keys(expected)){
  const cells=row.querySelectorAll('[data-automation-key="'+key+'"]');
  if(cells.length!==1)return null;
  fields[key]=norm(cells[0].innerText);
  if(fields[key]!==expected[key])return null;
 }
 const name=row.querySelector('[data-automation-key="name"]'),button=name.querySelector('button');
 if(!button)return null;
 if(prepare){
  // Reflow only the existing name; retain all public text, values and columns.
  for(const node of [row,row.querySelector('[data-automationid="DetailsRowFields"]'),name]){
   if(node){node.style.height='auto';node.style.minHeight='80px';node.style.maxHeight='none';}
  }
  for(const node of [name,button]){node.style.whiteSpace='normal';node.style.overflow='visible';node.style.textOverflow='clip';}
  button.style.maxWidth='100%';button.style.height='auto';button.style.overflowWrap='anywhere';
 }
 const box=button.getBoundingClientRect(),cell=name.getBoundingClientRect(),r=row.getBoundingClientRect();
 const fits=box.height>0&&box.bottom<=r.bottom+1&&box.right<=cell.right+1&&button.scrollWidth<=button.clientWidth+1&&button.scrollHeight<=button.clientHeight+1;
 return {fields,query:input.value,url:location.href,name_fits:fits};
}"""

def capture(master,page,org,data,*,candidate=None):
    run=CURRENT.get()
    if (run is None or run.state!='NJ' or run.ein!=master.canonical_ein_digits(org.ein)
            or not isinstance(data,dict) or type(data.get('ItemCount'))is not int or data['ItemCount']!=1
            or type(data.get('PageNumber'))is not int or data['PageNumber']!=1 or data.get('MoreRecords')is not False
            or data.get('Success')is False or any(data.get(k)for k in ('Error','error','ErrorMessage','errorMessage'))
            or not isinstance(data.get('Records'),list)or len(data['Records'])!=1 or not isinstance(data['Records'][0],dict)
            or getattr(page,'_cc_nj_query_incomplete',True)is not False or getattr(page,'_cc_nj_completed_data',None)is not data):return
    attrs=data['Records'][0].get('Attributes',[])
    if not isinstance(attrs,list)or any(not isinstance(a,dict)or not isinstance(a.get('Name'),str)for a in attrs):return
    values={a['Name']:a.get('DisplayValue')for a in attrs}
    if len(values)!=len(attrs):return
    fields={k:re.sub(r'\s+',' ',str(values.get(k)or '')).strip()for k in KEYS}
    if fields['accountnumber']or fields['crsm_filestanding']!='Exempt'or not fields['name']:return
    field_ein=master.canonical_ein_digits(fields['crsm_federalein'])
    signed_legacy=(field_ein=='000000000' and isinstance(candidate,dict)
                   and candidate.get('match',{}).get('reason')=='NJ_LEGACY_SUFFIX_INITIALS'
                   and candidate.get('name')==fields['name'] and candidate.get('raw_status')=='Exempt'
                   and not candidate.get('ein') and candidate.get('identifier')=='')
    evidence_ein='' if field_ein=='000000000' else fields['crsm_federalein']
    if evidence_ein and field_ein!=run.ein:return
    if not signed_legacy and master.score_candidate(org.organization_name,org.ein,{'name':fields['name'],'ein':evidence_ein})['decision']=='rejected':return
    query=getattr(page,'_cc_nj_query_diagnostic',{}).get('query')
    if not isinstance(query,str)or not query or page.url!=URL:return
    run.nj_unnumbered_capture_guard=True
    if not hasattr(run,'nj_unnumbered_image_bindings'):run.nj_unnumbered_image_bindings={}
    start=time.perf_counter();fact={'adapter':'NJ-unnumbered-original-grid','outcome':'not_started','capture_ms':0,'total_ms':0};run.visual_adapter_facts.append(fact)
    stop=min(DEADLINE.get()-1,master.NJ_NAME_QUERY_DEADLINE.get())
    try:
        if stop-time.monotonic()<.1:fact['outcome']='deadline_reserve';return
        expected={'expected':fields,'query':query,'prepare':True}
        before=page.evaluate(VIEW,expected)
        if not before or not before['name_fits']or before['url']!=URL:fact['outcome']='source_binding_or_geometry_failed';return
        for attempt in (1,2):
            if stop-time.monotonic()<.1:fact['outcome']='deadline_reserve';return
            if attempt==2:
                # Discard the first image. Rebind the same completed response and
                # exact public row before taking another, inside the original stop.
                if (getattr(page,'_cc_nj_query_incomplete',True) is not False
                        or getattr(page,'_cc_nj_completed_data',None) is not data
                        or page.url!=URL or page.evaluate(VIEW,expected)!=before):
                    fact['outcome']='source_changed';return
            size=page.locator('body').evaluate('(el)=>({width:el.scrollWidth,height:el.scrollHeight})',
                                             timeout=max(1,int(min(1,stop-time.monotonic())*1000)))
            if size['width']<=0 or size['height']<=0 or size['width']*size['height']>20_000_000:fact['outcome']='source_size_rejected';return
            if stop-time.monotonic()<.1:fact['outcome']='deadline_reserve';return
            fact['capture_attempts']=attempt
            begin=time.perf_counter();raw=page.screenshot(type='jpeg',quality=75,full_page=True,timeout=max(1,int(min(5,stop-time.monotonic())*1000)))
            elapsed=round((time.perf_counter()-begin)*1000,2)
            fact['capture_ms']=round(fact['capture_ms']+elapsed,2);run.capture_ms+=elapsed
            if time.monotonic()>=stop:fact['outcome']='capture_late';return
            after=page.evaluate(VIEW,{**expected,'prepare':False})
            if time.monotonic()>=stop:fact['outcome']='capture_late';return
            text=page.locator('body').inner_text(timeout=max(1,int(min(1,stop-time.monotonic())*1000)))
            if time.monotonic()>=stop or re.search(r'verify you are human|access denied|just a moment',text,re.I):fact['outcome']='source_unavailable';return
            if before==after:break
        else:
            fact['outcome']='source_changed';return
        before_documents=len(run.documents)
        run.nj_unnumbered_image_bindings[hashlib.sha256(raw).hexdigest()]=(fields['name'],'')
        run.document(URL,raw,'image',text,note='Original NJ unnumbered exemption row; source name wrapped to fit, public values unchanged. Identity confirmation is separate.')
        fact['outcome']='captured'if len(run.documents)>before_documents else'capture_failed'
    except Exception as exc:fact.update(outcome='capture_unavailable',error_type=type(exc).__name__)
    finally:fact['total_ms']=round((time.perf_counter()-start)*1000,2)
