/* Public TN request lifecycle only. Never submit, alter, or read a response. */
(() => {
  'use strict';
  const origin='https://tncab.tnsos.gov',channel='cc-final-four-tn-phase-v1';
  if(window!==window.top||location.origin!==origin||location.pathname!=='/portal/registered-charities-search')return;
  let active=null;
  const requests=new WeakMap();
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
  window.addEventListener('message',event=>{
    const m=event.data;
    if(event.source!==window||event.origin!==origin||m?.channel!==channel||m.direction!=='request'
      ||typeof m.id!=='string'||! /^[a-f0-9-]{36}$/.test(m.id))return;
    if(m.operation==='stop'){if(active?.id===m.id)active=null;return;}
    if(m.operation!=='watch'||typeof m.identifier!=='string'||!/^CO\d+$/.test(m.identifier)
      ||!Number.isFinite(m.budget_ms)||m.budget_ms<=0)return;
    if(active&&active.expires>Date.now()){emit({id:m.id},'unavailable');return;}
    const id=observedId(m.identifier);
    if(!id){emit({id:m.id},'unavailable');return;}
    active={id:m.id,recordId:id,expires:Date.now()+Math.min(25000,m.budget_ms),xhr:null};
    emit(active,'ready');
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
        emit(job,'finished',{http_status:Number.isInteger(this.status)&&this.status>=0&&this.status<=599?this.status:0});
      },{once:true});
    }
    return send.apply(this,args);
  };
})();
