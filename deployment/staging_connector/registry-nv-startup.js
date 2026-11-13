/* Observe the Nevada portal's own configuration requests without changing them. */
(() => {
  'use strict';
  if (window !== window.top || location.origin !== 'https://orion.nv.gov'
      || location.pathname !== '/portal/public/') return;

  const marker = 'data-cc-nv-config-unavailable';
  const open = XMLHttpRequest.prototype.open;
  let failures = 0;
  let responded = false;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    const result = Reflect.apply(open, this, [method, url, ...rest]);
    if (String(method).toUpperCase() !== 'GET') return result;
    try {
      const request = new URL(url, location.href);
      if (request.origin !== 'https://content.orion.nv.gov' || request.pathname !== '/api/tenants')
        return result;
    } catch {
      return result;
    }
    let networkFailed = false;
    const onError = () => { networkFailed = true; };
    this.addEventListener('error', onError, {once: true});
    this.addEventListener('loadend', () => {
      this.removeEventListener('error', onError);
      if (this.status > 0 && this.status < 500) {
        responded = true;
        document.documentElement?.removeAttribute(marker);
      } else if (!responded && (networkFailed || this.status >= 500) && ++failures >= 2) {
        document.documentElement?.setAttribute(marker, '');
      }
    }, {once: true});
    return result;
  };
})();

/* Observe only the current public search's HTTP outcome. Never alter requests. */
(() => {
  'use strict';
  const origin='https://orion.nv.gov',channel='cc-nv-search-http-v1';
  if(window!==window.top||location.origin!==origin||location.pathname!=='/portal/public/')return;
  const requests=new WeakMap();let active=null;
  const emit=(job,phase,extra={})=>window.postMessage({channel,direction:'response',id:job.id,phase,...extra},origin);
  window.addEventListener('message',event=>{
    const m=event.data;
    if(event.source!==window||event.origin!==origin||m?.channel!==channel||m.direction!=='request'
       ||typeof m.id!=='string'||! /^[a-f0-9-]{36}$/.test(m.id))return;
    if(m.operation==='stop'){if(active?.id===m.id)active=null;return;}
    const businessId = m.business_id ?? '';
    if(m.operation!=='watch'||typeof m.name!=='string'||m.name.length>500
       ||typeof businessId!=='string'
       ||(businessId ? (!/^NV\d+$/.test(businessId)||m.name!==''||m.mode!=='STARTS_WITH') : !m.name.trim())
       ||!['STARTS_WITH','CONTAINS','EXACT_MATCH'].includes(m.mode)
       ||!Number.isFinite(m.budget_ms)||m.budget_ms<=0)return;
    if(active&&active.expires>Date.now()){emit({id:m.id},'unavailable');return;}
    active={id:m.id,name:m.name,mode:m.mode,businessId,expires:Date.now()+Math.min(180000,m.budget_ms),xhr:null};
    emit(active,'ready');
  });
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open=function(method,url,...args){
    let eligible=false;
    try{const u=new URL(url,location.href);eligible=String(method).toUpperCase()==='POST'&&u.origin===origin
      &&u.pathname==='/core/api/_q/v1/nv-sos/public/business/getEntities';}catch{}
    requests.set(this,eligible);return open.call(this,method,url,...args);
  };
  XMLHttpRequest.prototype.send=function(...args){
    const job=active;let bound=false;
    if(job&&Date.now()<job.expires&&!job.xhr&&requests.get(this))try{
      const body=JSON.parse(args[0]),p=body.parameters,g=body.gridInput?.params?.parameters;
      bound=body.pageNo===1&&p?.tabRoute===g?.tabRoute&&[p,g].every(v=>v&&v.entityName===job.name&&v.searchType===job.mode
        &&v.entityNumber===''&&v.nvBusinessId===job.businessId&&['business','business.Miss'].includes(v.tabRoute));
    }catch{}
    if(bound){
      job.xhr=this;emit(job,'started');
      this.addEventListener('loadend',()=>{
        if(active!==job||Date.now()>job.expires)return;
        const http_status=Number.isInteger(this.status)&&this.status>=0&&this.status<=599?this.status:0;
        emit(job,'finished',{http_status});
      },{once:true});
    }
    return send.apply(this,args);
  };
})();
