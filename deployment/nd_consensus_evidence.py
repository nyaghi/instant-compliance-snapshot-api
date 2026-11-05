"""Bind the original ND results grid to an already-decided inactive consensus."""
import hashlib,re,time

URL='https://firststop.sos.nd.gov/search/charitable'

def capture(page,records,result,lookup_deadline):
    from deployment.state_snapshots import CURRENT,DEADLINE
    run=CURRENT.get()
    if run is None or run.state!='ND' or result.status_reason!='ND_MATCHING_RECORDS_INACTIVE':return
    selected=[{'id':str(r.get('RECORD_NUM') or r.get('ID') or ''),
               'name':str((r.get('TITLE') or [''])[0]),'status':str(r.get('STATUS') or '')} for r in records]
    if (not 2<=len(selected)<=10 or len({r['id'] for r in selected})!=len(selected)
            or any(not re.fullmatch(r'\d{10}',r['id']) or not r['name']
                   or not re.fullmatch(r'inactive(?:\s*[-–—]\s*(?:involuntary|voluntary))?',r['status'],re.I) for r in selected)):
        return
    identifier=', '.join(r['id'] for r in selected)
    if result.matched_registry_identifier!=identifier:return
    start=time.monotonic();stop=min(start+8,DEADLINE.get()-1,start+max(0,lookup_deadline-time.perf_counter()))
    fact={'adapter':'ND-existing-inactive-results','outcome':'not_started','record_count':len(selected)}
    run.visual_adapter_facts.append(fact)
    def ms(reserve=0):
        remaining=stop-time.monotonic()-reserve
        if remaining<=0:raise TimeoutError('ND_consensus_capture_reserve')
        return max(1,int(remaining*1000))
    check=r'''wanted=>{
      const norm=s=>(s||'').replace(/\s+/g,' ').trim();
      const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
      if(/verify you are human|access denied|just a moment/i.test(document.body.innerText))return null;
      const rows=[...document.querySelectorAll('table tr')].filter(visible);
      const actual=[];
      for(const record of wanted){
        const found=rows.filter(r=>[...r.cells].some(c=>norm(c.innerText)===record.id));
        if(found.length!==1)return null;
        const cells=[...found[0].cells].map(c=>norm(c.innerText));
        if(!cells.some(c=>c===norm(record.name))||!cells.some(c=>c===norm(record.status)))return null;
        actual.push({id:record.id,name:record.name,status:record.status});
      }
      return actual;
    }'''
    try:
        if page.url!=URL or stop-start<3:fact['outcome']='deadline_or_route';return
        page.wait_for_function(check,arg=selected,timeout=ms(2))
        before=page.evaluate(check,selected)
        text=page.inner_text('body',timeout=ms(1))
        raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=ms(.5))
        if page.url!=URL or not before or page.evaluate(check,selected)!=before or time.monotonic()>=stop:
            fact['outcome']='source_changed';return
        digest=hashlib.sha256(raw).hexdigest()
        binding=(result.matched_registry_name,identifier,result.raw_status_text)
        run.nd_consensus_image_bindings={digest:binding}
        run.document(URL,raw,'image',text,note='Original North Dakota results showing every inactive registration used in this conclusion.')
        fact['outcome']='captured' if any(hashlib.sha256(d[1]).hexdigest()==digest for d in run.documents) else 'document_rejected'
        if fact['outcome']!='captured':run.nd_consensus_image_bindings={}
    except Exception as exc:fact.update(outcome='unavailable',error_type=type(exc).__name__)
    finally:
        fact['total_ms']=round((time.monotonic()-start)*1000,2);run.capture_ms+=fact['total_ms']

def image_bound(run,row,url,raw,kind):
    return bool(kind=='image' and url==URL and row.get('state')=='ND'
        and row.get('status_reason')=='ND_MATCHING_RECORDS_INACTIVE'
        and row.get('status')=='Closed / Withdrawn / Canceled'
        and getattr(run,'nd_consensus_image_bindings',{}).get(hashlib.sha256(raw).hexdigest())
        ==(row.get('matched_registry_name'),row.get('matched_registry_identifier'),row.get('raw_status_text')))
