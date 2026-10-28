"""Retain an already-open ND review detail before later queries replace it."""
import hashlib,re,time

def capture(page, selected, fields, lookup_deadline):
    from deployment.state_snapshots import CURRENT,DEADLINE
    run=CURRENT.get()
    if run is None or run.state!='ND':return
    name=str((selected.get('TITLE') or [''])[0]).strip()
    identifier=str(selected.get('RECORD_NUM') or '')
    if not name or not re.fullmatch(r'\d{10}',identifier) or not fields.get('Status'):return
    url='https://firststop.sos.nd.gov/search/charitable'
    start=time.monotonic()
    # Share one visual reserve across all review candidates, inside the existing
    # lookup and task deadlines. No extra search, navigation or retry.
    stop=min(start+max(0,lookup_deadline-time.perf_counter()),DEADLINE.get()-1,
             getattr(run,'nd_review_capture_stop',start+10))
    run.nd_review_capture_stop=stop
    fact={'adapter':'ND-existing-review-detail','identifier':identifier,'outcome':'not_started'}
    run.visual_adapter_facts.append(fact)
    def ms(reserve=0):
        remaining=stop-time.monotonic()-reserve
        if remaining<=0:raise TimeoutError('ND_review_capture_reserve')
        return max(1,int(remaining*1000))
    expected={k:str(v).strip() for k,v in fields.items() if k in {'Status','Principal Address','Registration Date','AR Due Date','AR Extended Due Date','Inactive Date'}}
    # The original table identifies the selected record; its visible drawer
    # must independently show that record's name and returned detail fields.
    check="""({name,id,fields})=>{
      const norm=x=>(x||'').replace(/\\s+/g,' ').trim();
      const visible=e=>!!(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
      const ds=[...document.querySelectorAll('.drawer.show')].filter(visible);
      if(ds.length!==1||norm(ds[0].querySelector('h4')?.innerText)!==norm(name))return null;
      const rows=[...document.querySelectorAll('table tr')].filter(r=>visible(r)&&[...r.cells].some(c=>norm(c.innerText)===id));
      if(rows.length!==1||!rows[0].innerText.includes(name))return null;
      // ND marks the selected registration row independently of its name-only
      // drawer. Require that exact highlighted ID, including same-name cases.
      const selectedRows=[...document.querySelectorAll('table tr.selected')].filter(visible);
      if(selectedRows.length!==1||selectedRows[0]!==rows[0])return null;
      const actual=Object.fromEntries([...ds[0].querySelectorAll('tr')].filter(r=>r.cells.length===2).map(r=>[norm(r.cells[0].innerText),norm(r.cells[1].innerText)]));
      if(Object.entries(fields).some(([k,v])=>actual[k]!==norm(v)))return null;
      if(/verify you are human|access denied|just a moment/i.test(document.body.innerText))return null;
      return {name,id,fields:actual};
    }"""
    args={'name':name,'id':identifier,'fields':expected}
    try:
        if page.url!=url or stop-start<3:fact['outcome']='deadline_or_route';return
        page.wait_for_function(check,arg=args,timeout=ms(2))
        before=page.evaluate(check,args)
        text=page.inner_text('body',timeout=ms(1))
        raw=page.screenshot(type='jpeg',quality=80,full_page=True,timeout=ms(.5))
        after=page.evaluate(check,args)
        if page.url!=url or not before or before!=after or time.monotonic()>=stop:
            fact['outcome']='source_changed';return
        digest=hashlib.sha256(raw).hexdigest()
        bindings=getattr(run,'nd_review_image_bindings',{})
        run.nd_review_image_bindings=bindings;bindings[digest]=(name,identifier)
        run.document(url,raw,'image',text,note='Original North Dakota candidate detail captured before continuing existing searches; identity remains for user review.')
        fact['outcome']='captured' if any(hashlib.sha256(d[1]).hexdigest()==digest for d in run.documents) else 'document_rejected'
        if fact['outcome']!='captured':bindings.pop(digest,None)
    except Exception as exc:
        fact.update(outcome='unavailable',error_type=type(exc).__name__,error_summary=str(exc).splitlines()[0][:180])
    finally:
        fact['total_ms']=round((time.monotonic()-start)*1000,2)
        run.capture_ms+=fact['total_ms']
