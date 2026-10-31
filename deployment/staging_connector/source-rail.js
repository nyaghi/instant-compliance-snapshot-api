/* D.C./Wisconsin share the existing two positions; only owned windows are closed. */
const CCSourceRail=(()=>{
 const KEY='ccSourceRailV1',leases=new Set(),waiting=[];
 let initialized=false,readyPromise=null,saving=Promise.resolve();
 const jobs=()=>[...leases].map(x=>x.job);
 const activeSlots=()=>allJobs().filter(j=>isActive(j)&&isDuoJob(j)).map(j=>j.duoSlot);
 const slots=()=>[...leases].map(x=>x.job.duoSlot);
 let revision=0;
 function notify(){revision++;for(const request of waiting)request.wake?.();}
 function pause(request,seen,end){
  if(revision!==seen)return Promise.resolve();
  return new Promise(resolve=>{
   let timer;
   const finish=()=>{clearTimeout(timer);if(request.wake===finish)delete request.wake;resolve();};
   request.wake=finish;
   timer=setTimeout(finish,Math.max(1,end-Date.now()-3000));
  });
 }
 // Wake only requests owned by the origin tab that changed. Revalidate it
 // before granting a slot; waiting must not poll Chrome every fifty ms.
 chrome.tabs.onUpdated.addListener((id,change)=>{
  if(typeof change.url==='string'&&waiting.some(r=>r.originId===id))notify();
 });
 chrome.tabs.onRemoved.addListener(id=>{if(waiting.some(r=>r.originId===id))notify();});
 const persist=()=>{
  const value=[...leases].filter(l=>Number.isInteger(l.windowId)&&Number.isInteger(l.tabId))
   .map(l=>({windowId:l.windowId,tabId:l.tabId,state:l.job.registryState,slot:l.job.duoSlot}));
  saving=saving.catch(()=>{}).then(()=>chrome.storage.session.set({[KEY]:value}));return saving;
 };
 async function ready(){
  if(!readyPromise)readyPromise=(async()=>{
   const saved=(await chrome.storage.session.get(KEY))[KEY]||[];
   if(!Array.isArray(saved)||saved.length>2)throw Error('source_rail_saved_state_invalid');
   for(const r of saved){
    if(!Number.isInteger(r.windowId)||!Number.isInteger(r.tabId)||!['DC','WI'].includes(r.state)||![0,1].includes(r.slot))continue;
    let w;try{w=await chrome.windows.get(r.windowId,{populate:true});}catch{continue;}
    const lease={job:{registryState:r.state,duoSlot:r.slot,sourceRailLease:true},windowId:r.windowId,tabId:r.tabId};leases.add(lease);
    // No live capture survives a worker restart. Close only the saved, sole
    // owned source tab; a user-repurposed window is left intact and reserved.
    const tab=w.tabs?.length===1?w.tabs[0]:null;
    let host='';try{host=new URL(tab?.url).hostname;}catch{}
    if(tab?.id===r.tabId&&host===(r.state==='DC'?'boss.dc.gov':'apps.dfi.wi.gov')){
     try{await chrome.windows.remove(r.windowId);leases.delete(lease);}catch{}
    }
   }
   await persist();initialized=true;
  })();
  return readyPromise;
 }
 // A pending evidence request gets the next free position before another
 // registry job, so polling cannot lose every slot to synchronous admission.
 function admissionSlots(){
  const used=new Set(activeSlots().concat(slots()));
  const held=slots();let count=waiting.filter(x=>x.end>Date.now()+3000).length;
  for(const s of [0,1])if(count>0&&!used.has(s)){held.push(s);count--;}
  return held;
 }
 async function acquire(sender,state,end,runId,signal){
  if(!P.TRIAL_ORIGIN||!sender?.tab||!['DC','WI'].includes(state))return null;
  if(signal?.aborted)throw Error("source_cancelled");
  await ready();
  if(signal?.aborted)throw Error("source_cancelled");
  async function bounded(operation,stage){const began=Date.now();let timer,abort;try{if(signal?.aborted)throw Error("source_cancelled");return await Promise.race([operation,new Promise((_,reject)=>{abort=()=>reject(Error("source_cancelled"));signal?.addEventListener("abort",abort,{once:true});}),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('source_placement_deadline')),Math.max(1,end-Date.now()-3000));})]);}catch(error){error.sourceRailObservation={stage,seconds:(Date.now()-began)/1000,active_registry_slots:activeSlots(),source_slots:slots(),waiting:waiting.length};throw error;}finally{clearTimeout(timer);signal?.removeEventListener("abort",abort);}}
  const origin=await bounded(chrome.tabs.get(sender.tab.id),'origin-tab');
  if(origin.url!==sender.url)throw Error('source_origin_changed');
  if(registryTrialLayout(origin)!=='duo')return null;
  const request={end,originId:origin.id},started=Date.now();waiting.push(request);signal?.addEventListener("abort",notify,{once:true});
  try{
   while(Date.now()<end-3000){
    if(signal?.aborted)throw Error("source_cancelled");
    const seen=revision;
    const occupied=new Set(activeSlots().concat(slots()));
    const slot=waiting[0]===request?[0,1].find(s=>!occupied.has(s)):undefined;
    if(slot!==undefined){
     const job={registryState:state,lookupId:runId,sender,duoSlot:slot,activeExpiresAt:end,sourceRailLease:true};
     const lease={job,windowId:null,tabId:null,options:null};leases.add(lease);
     try{
      lease.options=await bounded(registryTrialWindowOptions(job,origin),'window-options');
      if(Date.now()>=end-3000||!['left','top','width','height'].every(k=>Number.isFinite(lease.options[k])))throw Error('source_placement_unavailable');
      const current=await bounded(chrome.tabs.get(origin.id),'reserved-origin-check');
      if(current.url!==origin.url||current.windowId!==origin.windowId)throw Error('source_origin_changed');
      if(signal?.aborted)throw Error('source_cancelled');
      diagnostic('source-rail-reserved',job,JSON.stringify({slot,wait_seconds:(Date.now()-started)/1000,...lease.options}));
      return lease;
     }catch(e){leases.delete(lease);throw e;}
    }
    const current=await bounded(chrome.tabs.get(origin.id),'waiting-origin-check');
    if(current.url!==origin.url||current.windowId!==origin.windowId)throw Error('source_origin_changed');
    await pause(request,seen,end);
   }
   const error=Error('source_rail_wait_deadline');error.sourceRailObservation={stage:'slot-wait',seconds:(Date.now()-started)/1000,active_registry_slots:activeSlots(),source_slots:slots(),waiting:waiting.length};throw error;
  }finally{signal?.removeEventListener("abort",notify);waiting.splice(waiting.indexOf(request),1);pump();}
 }
 async function release(lease){
  if(lease.creationPending)return;
  if(Number.isInteger(lease.windowId)){try{await chrome.windows.get(lease.windowId);return;}catch{}}
  leases.delete(lease);await persist();pump();
 }
 async function create(lease,options){
  if(!lease)return chrome.windows.create(options);
  lease.creationPending=true;
  try{
   const w=await chrome.windows.create(options);lease.windowId=w.id;lease.tabId=w.tabs?.[0]?.id;
   if(!Number.isInteger(lease.windowId)||!Number.isInteger(lease.tabId)){
    if(Number.isInteger(w.id))await chrome.windows.remove(w.id).catch(()=>{});
    throw Error('source_owned_window_unavailable');
   }
   try{await persist();}catch(e){await chrome.windows.remove(w.id).catch(()=>{});throw e;}
   return w;
  }catch(e){
   if(!Number.isInteger(lease.windowId)){leases.delete(lease);await persist();pump();}
   throw e;
  }finally{lease.creationPending=false;}
 }
 chrome.windows.onRemoved.addListener(id=>{
  let changed=false;for(const lease of leases)if(lease.windowId===id){leases.delete(lease);changed=true;}
  if(changed)persist().then(()=>pump()).catch(()=>{});
 });
 return {acquire,release,create,slots,jobs,ready,notify,admissionSlots,isReady:()=>initialized};
})();
