/* Observe public TN request timing and configure the owned detail dialog. */
(() => {
  'use strict';
  const origin='https://tncab.tnsos.gov',channel='cc-final-four-tn-phase-v1';
  if(window!==window.top||location.origin!==origin||location.pathname!=='/portal/registered-charities-search')return;
  let active=null;
  const requests=new WeakMap();
  function retryAfter(xhr){
    try{
      // This one public timing header is the only header observed.
      const value=xhr.getResponseHeader('Retry-After');
      if(typeof value!=='string'||value.length>100)return null;
      if(/^\d+$/.test(value.trim())){
        const ms=Number(value.trim())*1000;
        return Number.isSafeInteger(ms)&&ms>=0?ms:null;
      }
      const date=Date.parse(value);
      return Number.isFinite(date)?Math.max(0,date-Date.now()):null;
    }catch{return null;}
  }
  const emit=(job,phase,extra={})=>window.postMessage({channel,direction:'response',id:job.id,phase,...extra},origin);
  const text=el=>(el?.innerText||'').replace(/\s+/g,' ').trim();
  function observedId(identifier) {
    const tables=[...document.querySelectorAll('[id^="SearchResults_"] table[role="grid"]')];
    if(tables.length!==1)return null;
    const headers=[...tables[0].querySelectorAll('thead th')];
    const column=field=>headers.flatMap((el,index)=>el.getAttribute('data-colkey')===field?[index]:[]);
    const ids=column('Id'),files=column('FileNumber');
    if(ids.length!==1||files.length!==1)return null;
    const rows=[...tables[0].querySelectorAll('tbody > tr')].filter(row=>row.children.length===headers.length
      &&text(row.children[files[0]])===identifier);
    if(rows.length!==1)return null;
    const id=text(rows[0].children[ids[0]]);
    return /^\d{1,15}$/.test(id)?id:null;
  }
  function quietOpening(job) {
    if(!document.hidden) return null;
    const prototype=window.kendo?.ui?.Window?.fn;
    const open=prototype?.open;
    if(typeof open!=='function')return null;
    const restore=()=>{if(prototype.open===openQuietDetail)prototype.open=open;};
    function openQuietDetail(...args) {
      const element=document.getElementById('KendoWindowLevel1');
      if(!element || this.element?.[0]!==element || active!==job || !document.hidden
          || Date.now()>job.expires)return open.apply(this,args);
      restore();
      const options=this.options;
      const original=options?.animation;
      if(!original || typeof original!=='object' || !original.open)return open.apply(this,args);
      const quiet={...original,open:false};
      options.animation=quiet;
      try {
        emit(job,'opening-configured');
        return open.apply(this,args);
      } finally {
        if(this.options===options&&options.animation===quiet)options.animation=original;
      }
    }
    prototype.open=openQuietDetail;
    return restore;
  }
  function stop() {
    const job=active;
    active=null;
    if(!job) return;
    if(job.timer!==undefined)clearTimeout(job.timer);
    job.restoreOpening?.();
  }
  window.addEventListener('message',event=>{
    const m=event.data;
    if(event.source!==window||event.origin!==origin||m?.channel!==channel||m.direction!=='request'
      ||typeof m.id!=='string'||! /^[a-f0-9-]{36}$/.test(m.id))return;
    if(m.operation==='stop'){if(active?.id===m.id)stop();return;}
    if(m.operation!=='watch'||typeof m.identifier!=='string'||!/^CO\d+$/.test(m.identifier)
      ||!Number.isFinite(m.budget_ms)||m.budget_ms<=0)return;
    if(active&&active.expires>Date.now()){emit({id:m.id},'unavailable');return;}
    const id=observedId(m.identifier);
    if(!id){emit({id:m.id},'unavailable');return;}
    stop();
    const budget=Math.min(25000,m.budget_ms);
    active={id:m.id,recordId:id,expires:Date.now()+budget,xhr:null};
    if(m.quiet_detail===true) {
      try { active.restoreOpening=quietOpening(active); } catch { /* Preserve normal behavior if the widget changed. */ }
    }
    if(active.restoreOpening)active.timer=setTimeout(stop,budget);
    emit(active,'ready',active.restoreOpening?{opening_hook_ready:true}:{});
  });
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(method,url,...args){
    let id=null;
    try{
      const parsed=new URL(url,location.href);
      if(String(method).toUpperCase()==='POST'&&parsed.origin===origin
        &&parsed.pathname==='/portal/RegistrationSearch/Details')id=parsed.searchParams.get('id');
    }catch{}
    requests.set(this,id);
    return open.call(this,method,url,...args);
  };
  XMLHttpRequest.prototype.send=function(...args){
    const job=active;
    if(job&&Date.now()<=job.expires&&!job.xhr&&requests.get(this)===job.recordId){
      job.xhr=this;emit(job,'started');
      this.addEventListener('loadend',()=>{
        if(active!==job||Date.now()>job.expires)return;
        const http_status=Number.isInteger(this.status)&&this.status>=0&&this.status<=599?this.status:0;
        const retry_after_ms=http_status===429?retryAfter(this):null;
        emit(job,'finished',{http_status,...(retry_after_ms!==null?{retry_after_ms}:{})});
      },{once:true});
    }
    return send.apply(this,args);
  };
})();
