/* Scoped Stop-only receipt. Ordinary finish/reuse behavior remains untouched. */

function createStrictStop({close,owned,tabs,safeRegistryTab,allowedSender,forgetResource=()=>{},isTransferred=()=>false,reserveResources=()=>{},timeoutMs=30000}) {
  const pending=new WeakMap(), ledgers=new WeakMap();
  function remember(job) {
    if(!job?.sender?.documentId||typeof job.lookupId!=='string')throw new Error('Resource ownership is unavailable.');
    const resources=ledgers.get(job)||new Set();ledgers.set(job,resources);
    const capture=()=>{if(Number.isInteger(job.tab)&&owned.has(job.tab))resources.add(job.tab);};
    capture();if(job.creating)job.creating.then(capture).catch(()=>{});
  }
  function stop(job,request,sender) {
    if(!allowedSender(sender)||request.lookupId!==job.lookupId||sender.tab?.id!==job.sender.tab.id
      ||!job.sender.documentId||sender.documentId!==job.sender.documentId)
      return Promise.reject(Object.assign(new Error('Stop ownership is unconfirmed.'),{code:'STOP_OWNERSHIP'}));
    if(pending.has(job))return pending.get(job);
    if(job.closed&&!ledgers.has(job))return Promise.reject(Object.assign(new Error('Prior cleanup ownership is unavailable.'),{code:'STOP_UNCONFIRMED'}));
    const resources=ledgers.get(job)||new Set();ledgers.set(job,resources);
    const capture=()=>{if(Number.isInteger(job.tab)&&owned.has(job.tab))resources.add(job.tab);};
    capture();
    // Subscribe before close awaits creation and clears job.tab. The actual
    // close path immediately closes the job, preventing further commands.
    const creation=job.creating?job.creating.then(()=>{capture();job.tab=null;}):Promise.resolve();
    let timer;
    const operation=(async()=>{
      reserveResources(job,[...resources]);
      // Stop owns physical cleanup separately. Detach before logical close so
      // ordinary best-effort removal cannot delete a user-taken/other-state tab.
      // The creation reaction above detaches a late tab before close resumes.
      job.tab=null;
      const closing=close(job,'NY_CONNECTOR_BROWSER_CLOSED');
      await creation;await closing;
      const closedResourceIds=[],transferredResourceIds=[];
      for(const tabId of resources) {
        if(isTransferred(job,tabId)){transferredResourceIds.push(tabId);continue;}
        let tab;
        try {tab=await tabs.get(tabId);}
        catch(error) {if(/No tab with id:/i.test(error.message)){forgetResource(job,tabId);closedResourceIds.push(tabId);continue;}throw error;}
        // A tab taken over by the user is never deleted or called closed.
        if(!safeRegistryTab(job,tab))throw new Error('Owned registry tab changed.');
        await tabs.remove(tabId);
        try {await tabs.get(tabId);throw new Error('Owned registry tab remains open.');}
        catch(error) {if(!/No tab with id:/i.test(error.message))throw error;}
        forgetResource(job,tabId);
        closedResourceIds.push(tabId);
      }
      return {confirmed:true,lookupId:job.lookupId,sourceTabId:sender.tab.id,documentId:sender.documentId,resourceIds:[...resources],closedResourceIds,transferredResourceIds};
    })();
    const result=Promise.race([operation,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Owned cleanup acknowledgement timed out.')),timeoutMs);})])
      .catch(error=>{error.code='STOP_UNCONFIRMED';throw error;}).finally(()=>{clearTimeout(timer);pending.delete(job);});
    pending.set(job,result);return result;
  }
  // Internal lifecycle hook only. No external request may create ownership.
  stop.remember=remember;
  stop.snapshot=job=>ledgers.has(job)?[...ledgers.get(job)]:null;
  stop.restore=(job,ids)=>{
    if(!job?.sender?.documentId||!Array.isArray(ids)||ids.length>100||ids.some(id=>!Number.isInteger(id)||id<0))throw new Error('Stored resource ownership is invalid.');
    ledgers.set(job,new Set(ids));
  };
  return stop;
}

/* Internal ownership ledger. Only the separately scoped Stop message uses it. */

function createOwnedStopRegistry({strictStop,owned,allowedSender,validId,persist=async()=>{},now=()=>Date.now(),maxRecords=200}) {
  const jobs=new Map(),owners=new Map(),ambiguous=new Set();
  function same(a,b){return a?.tab?.id===b?.tab?.id&&a?.documentId===b?.documentId&&a?.url===b?.url;}
  function binding(job){return {lookupId:job.lookupId,sourceTabId:job.sender.tab.id,documentId:job.sender.documentId||''};}
  function equalOwner(a,b){return a?.lookupId===b?.lookupId&&a?.sourceTabId===b?.sourceTabId&&a?.documentId===b?.documentId;}
  function admitted(job){return validId(job?.lookupId)&&allowedSender(job.sender)&&Number.isInteger(job.sender.tab.id);}
  function trim(){
    for(const [id,r] of jobs)if(r.expiresAt<=now()&&r.job.closed)jobs.delete(id);
    if(jobs.size>maxRecords){for(const [id,r] of jobs){if(r.job.closed&&!r.cancelRequested)jobs.delete(id);if(jobs.size<=maxRecords)break;}}
  }
  function remember(job){
    if(!admitted(job))return;
    // Record trusted internal transfer even on an older document context
    // that cannot itself qualify for a strict Stop receipt.
    if(Number.isInteger(job.tab)&&owned.has(job.tab)){owners.set(job.tab,binding(job));ambiguous.delete(job.tab);}
    if(!job.sender.documentId)return;
    const prior=jobs.get(job.lookupId);
    if(prior&&!same(prior.job.sender,job.sender))return;
    strictStop.remember(job);
    const expiresAt=Number.isFinite(job.expiresAt)?job.expiresAt:now()+1200000;
    jobs.set(job.lookupId,{job,expiresAt,cancelRequested:prior?.cancelRequested===true});trim();
  }
  function canAdopt(job,id){const o=owners.get(id),r=jobs.get(o?.lookupId);return !ambiguous.has(id)&&!(r?.cancelRequested&&equalOwner(o,binding(r.job)));}
  function transferred(job,id){
    if(ambiguous.has(id))throw new Error('Stored resource ownership is ambiguous.');
    return owners.has(id)&&!equalOwner(owners.get(id),binding(job));
  }
  function forget(job,id){if(equalOwner(owners.get(id),binding(job)))owners.delete(id);}
  function requested(id,sender){return !!jobs.get(id)?.cancelRequested;}
  async function stop(request,sender){
    if(!allowedSender(sender)||!validId(request.lookupId))throw Object.assign(new Error('Stop ownership is unconfirmed.'),{code:'STOP_OWNERSHIP'});
    const r=jobs.get(request.lookupId);
    if(!r||r.expiresAt<=now()||!same(r.job.sender,sender)||!sender.documentId)
      throw Object.assign(new Error('Lookup ownership is unavailable.'),{code:'STOP_UNCONFIRMED'});
    r.cancelRequested=true;
    await persist();
    return strictStop(r.job,{lookupId:request.lookupId},sender);
  }
  function snapshot(){
    trim();
    return [...jobs.values()].slice(-maxRecords).map(r=>({schema:1,lookupId:r.job.lookupId,registryState:r.job.registryState,
      sourceTabId:r.job.sender.tab.id,documentId:r.job.sender.documentId,sourceUrl:r.job.sender.url,
      expiresAt:r.expiresAt,cancelRequested:r.cancelRequested,resourceIds:strictStop.snapshot(r.job)||[],
      resourceOwners:(strictStop.snapshot(r.job)||[]).map(id=>[id,owners.get(id)||null]),
      ambiguousResourceIds:(strictStop.snapshot(r.job)||[]).filter(id=>ambiguous.has(id))}));
  }
  function restore(records,activeJobs,extensionId){
    if(!Array.isArray(records)||records.length>maxRecords)return;
    for(const r of records){
      if(r?.schema!==1||!validId(r.lookupId)||!Number.isInteger(r.sourceTabId)||r.sourceTabId<0||typeof r.documentId!=='string'||!r.documentId||r.documentId.length>100
        ||!Number.isFinite(r.expiresAt)||r.expiresAt<=now()||r.expiresAt>now()+1200000
        ||!['NY','IL','GA','AL','NC','NV','TN','NM','MS'].includes(r.registryState)
        ||!Array.isArray(r.resourceIds)||r.resourceIds.length>100||r.resourceIds.some(id=>!Number.isInteger(id)||id<0||id===r.sourceTabId)
        ||!Array.isArray(r.resourceOwners)||r.resourceOwners.length!==r.resourceIds.length
        ||new Set(r.resourceIds).size!==r.resourceIds.length
        ||r.resourceOwners.some(entry=>!Array.isArray(entry)||entry.length!==2||!r.resourceIds.includes(entry[0])||(entry[1]!==null&&(!entry[1]||!validId(entry[1].lookupId)||!Number.isInteger(entry[1].sourceTabId)||entry[1].sourceTabId<0||typeof entry[1].documentId!=='string'||entry[1].documentId.length>100)))
        ||new Set(r.resourceOwners.map(entry=>entry[0])).size!==r.resourceIds.length
        ||(r.ambiguousResourceIds!==undefined&&(!Array.isArray(r.ambiguousResourceIds)||r.ambiguousResourceIds.some(id=>!r.resourceIds.includes(id)))))continue;
      const sender={id:extensionId,frameId:0,url:r.sourceUrl,documentId:r.documentId,tab:{id:r.sourceTabId}};
      if(!allowedSender(sender))continue;
      let job=activeJobs.find(j=>j.lookupId===r.lookupId&&same(j.sender,sender));
      if(!job)job={lookupId:r.lookupId,sender,registryState:r.registryState,tab:null,closed:true,expiresAt:r.expiresAt,creating:null};
      strictStop.restore(job,r.resourceIds);jobs.set(r.lookupId,{job,expiresAt:r.expiresAt,cancelRequested:r.cancelRequested===true});
      for(const [id,o] of r.resourceOwners){
        // Null records a prior confirmed removal, not conflicting ownership.
        if(o===null)continue;
        if(!owners.has(id))owners.set(id,o);
        else if(!equalOwner(owners.get(id),o))ambiguous.add(id);
      }
      for(const id of r.ambiguousResourceIds||[])ambiguous.add(id);
    }
    // Active jobs are the current owners after an ordinary idle transfer.
    for(const job of activeJobs)remember(job);
  }
  return {remember,canAdopt,transferred,forget,requested,stop,snapshot,restore};
}

globalThis.CCStopReview={createStrictStop,createOwnedStopRegistry};
