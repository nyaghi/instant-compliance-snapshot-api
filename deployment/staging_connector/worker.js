importScripts("protocol.js", "workflow-observation.js", "recovery.js", "registry-worker.js", "state-snapshot-worker.js", "dc-boss-source.js", "source-rail.js", "desktop-source-worker.js");
const P = CCNYProtocol;
// Public diagnostic correlation only; never a credential or authorization key.
const nvHandoffWorkerTag=Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,10);
function nvHandoffDiagnostic(job,message) {
  if(!P.TRIAL_ORIGIN || job?.registryState!=='NV' || typeof message.ok!=='boolean' || message.progress)return wfReturn(job,"worker.js:nvHandoffDiagnostic:6:103:return",(message));
  const operation=job.command?.query?.operation;
  return wfReturn(job,"worker.js:nvHandoffDiagnostic:8:2:return",({...message,nv_readiness:{...message.nv_readiness,handoff:{
    build:'evidence-policy-placement-1',extension_id:chrome.runtime.id,worker_tag:nvHandoffWorkerTag,
    active:isActive(job),pending:!!job.pending,search_complete:job.finalFourSearchComplete===true,
    pending_matches_reply:job.pending===message.id,
    command_matches_reply:job.command?.id===message.id,
    operation:['search','detail'].includes(operation)?operation:'none',
    capture:(job.trialDiagnostics||[]).filter(entry=>entry.type==='source-snapshot-phase').slice(-24)
  }}}));
}
const QUEUE_TTL = 1200000, ACTIVE_TTL = 300000, PACE_MS = 3000;
const REPAIR_INTERVAL = 1200000;
let active = null, nextStart = 0, pumpTimer = null;
// The approved connector retains its single lane. The isolated trial admits
// one job per registry, so a slow registry cannot strand a different state.
const activeLanes = new Map(), laneStarts = new Map();
const duoStates = new Set(['NV','NY','IL','NC','TN','MS','AL','GA','NM']);
const isDuoJob = job => !!job && duoStates.has(job.registryState)
  && registryTrialLayout({url:job.sender.url})==='duo';
const allJobs = () => [...(P.TRIAL_ORIGIN ? activeLanes.values() : [active]), ...queue].filter(Boolean);
const isActive = job => !!job && (P.TRIAL_ORIGIN ? activeLanes.get(job.registryState) === job : active === job);
const queue = [];
let repair = {}, saving = Promise.resolve();
let runtimeCheckpointSequence = 0, runtimeCheckpointPending = 0;
const owned = new Set();
let keepAliveTimer = null;
let trialAlIdle = null, trialAlIdleTimer = null;
let trialTnIdle = null, trialTnIdleTimer = null;
let trialNyIdle = null, trialNyIdleTimer = null;
const nyRegistryPage = url => {
  try {const u=new URL(url);return u.origin===P.NY && /^\/RegistrySearch(?:\/[0-9]{2}-[0-9]{2}-[0-9]{2})?\/?$/.test(u.pathname);}
  catch {return false;}
};
function armTrialNyIdle() {
  clearTimeout(trialNyIdleTimer);
  if (!P.TRIAL_ORIGIN || !trialNyIdle) return;
  const saved=trialNyIdle;
  trialNyIdleTimer=setTimeout(()=>{
    if(trialNyIdle===saved){trialNyIdle=null;removeOwned(saved.id).catch(()=>{});}
  },Math.max(0,saved.expiresAt-Date.now()));
}
function armTrialTnIdle() {
  clearTimeout(trialTnIdleTimer);
  if (!P.TRIAL_ORIGIN || !trialTnIdle) return;
  const saved=trialTnIdle;
  trialTnIdleTimer=setTimeout(()=>{
    if (trialTnIdle===saved) {trialTnIdle=null;removeOwned(saved.id).catch(()=>{});}
  },Math.max(0,saved.expiresAt-Date.now()));
}
function armTrialAlIdle() {
  clearTimeout(trialAlIdleTimer);
  if (!P.TRIAL_ORIGIN || !trialAlIdle) return;
  const saved=trialAlIdle;
  trialAlIdleTimer=setTimeout(()=>{
    if (trialAlIdle===saved) {trialAlIdle=null;removeOwned(saved.id).catch(()=>{});}
  },Math.max(0,saved.expiresAt-Date.now()));
}
const diagnostics = [];
function diagnostic(type, job, detail = "") {
  if(type==='source-snapshot-phase')wfCaptureFact(job,detail);
  const at=Date.now(), summary=String(detail).slice(0,180);
  diagnostics.push({ at, type, id: job?.lookupId || "", phase: job?.pending ? "search" : isActive(job) ? "active" : "queued", detail: summary });
  if (diagnostics.length > 80) diagnostics.shift();
  if(P.TRIAL_ORIGIN && job && ["GA","MS","NC","TN","NV","AL","IL","NM","NY"].includes(job.registryState)) {
    job.trialDiagnostics ||= [];
    job.trialDiagnostics.push({at,type,detail:String(detail).slice(0,600)});
    if(job.trialDiagnostics.length>120)job.trialDiagnostics.shift();
  }
}
function keepAlive() {
  if (keepAliveTimer || !allJobs().some(j => j && !j.closed)) return;
  keepAliveTimer = setTimeout(async () => {
    keepAliveTimer = null;
    if (!allJobs().some(j => j && !j.closed)) return;
    // A bounded active operation must not depend on timers in hidden pages.
    try { await chrome.storage.session.get("ccnyRuntime"); } catch (e) { diagnostic("keepalive-error", active, e.message); }
    keepAlive();
  }, 20000);
}
const rejected = reason => ["NY_CONNECTOR_VERIFICATION_REJECTED", "NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED"].includes(reason);
const recoveryFailure = reason => rejected(reason) ? "NY_CONNECTOR_RECOVERY_REJECTED" :
  typeof reason === "string" && /^NY_CONNECTOR_[A-Z_]+$/.test(reason) ? reason : "NY_CONNECTOR_INCOMPLETE";
function collectNyDiagnostics(job, response) {
  if(P.TRIAL_ORIGIN && job.registryState === "NY")
    job.nyDiagnostics=P.nyDiagnostics([...(job.nyDiagnostics||[]),...P.nyDiagnostics(response?.ny_diagnostics)]);
}
const runtimeState = () => ({ schema: 2, nextStart, laneStarts: Object.fromEntries(laneStarts), ...(P.TRIAL_ORIGIN?{tnTraffic:registryTnTrafficSnapshot()}:{}), ownedTabs: [...owned], diagnostics: [...diagnostics], queue: allJobs().filter(j => j && !j.closed).map(j => ({ id: j.lookupId, registryState: j.registryState || "NY", tabId: j.sender.tab.id, documentId: j.sender.documentId || "", enqueuedAt: j.enqueuedAt, trialDisplay: j.trialDisplay, expiresAt: j.expiresAt, active: isActive(j), activeExpiresAt: j.activeExpiresAt, duoSlot: j.duoSlot, tab: j.tab, refreshOnly: j.refreshOnly, generation: j.generation, rateRetries: j.rateRetries, timeoutRetries: j.timeoutRetries, ...(P.TRIAL_ORIGIN && j.registryState === "TN" ? {tnCheckboxAttempted:j.tnCheckboxAttempted===true} : {}), detailRetryUsed: j.detailRetryUsed, detailAuthRetryUsed: j.detailAuthRetryUsed, nyLastSearchQuery: j.nyLastSearchQuery, nyDiagnostics: P.nyDiagnostics(j.nyDiagnostics), retryNotBefore: j.retryNotBefore, reloadAfterRateLimit: j.reloadAfterRateLimit, verificationRetryUsed: j.verificationRetryUsed, command: j.registryState === "AL" ? null : j.command, lastResponse: j.registryState === "AL" ? null : withoutSourcePixels(j.lastResponse), snapshotCaptures: j.snapshotCaptures || 0, ...(P.TRIAL_ORIGIN?{ilSnapshotSpentMs:j.ilSnapshotSpentMs,tnSnapshotSpentMs:j.tnSnapshotSpentMs,nmSnapshotSpentMs:j.nmSnapshotSpentMs,ncSnapshotSpentMs:j.ncSnapshotSpentMs,nySnapshotSpentMs:j.nySnapshotSpentMs,msSnapshotSpentMs:j.msSnapshotSpentMs,gaDetailSnapshotSpentByRecord:j.gaDetailSnapshotSpentByRecord,requiredCaptureSpentByState:j.requiredCaptureSpentByState}:{}), ...(P.TRIAL_ORIGIN&&j.registryState==='AL'?{alEmptySnapshotSaved:j.alEmptySnapshotSaved===true}:{}), queryRepaired: j.queryRepaired, nyFreshPageRecoveryOnly: j.nyFreshPageRecoveryOnly, nvReturnRecoveryUsed: j.nvReturnRecoveryUsed, ...(P.TRIAL_ORIGIN && j.registryState === "AL" ? {alFinalEmptyProtocol:j.alFinalEmptyProtocol,alFinalEmptyUsed:j.alFinalEmptyUsed,alSnapshotSpentMs:j.alSnapshotSpentMs,snapshotCaptures:j.snapshotCaptures}:{}), ...(P.TRIAL_ORIGIN && j.registryState === "NV" ? {nvVisibilityAttempted:j.nvVisibilityAttempted,nvDetailVisibilityChecked:j.nvDetailVisibilityChecked,nvPreviousVisible:j.nvPreviousVisible} : {}) })) });
/* Capture the last completed empty AL page in place; no search or verification. */
async function performAlFinalEmpty(job,query,id) {
  const admitted=P.TRIAL_ORIGIN&&job.registryState==='AL'&&job.alFinalEmptyProtocol===true
    &&!job.closed&&isActive(job)&&owned.has(job.tab)&&Date.now()<job.activeExpiresAt&&P.validId(id);
  if(admitted&&job.command?.action==='capture_empty'&&job.command.id===id&&P.sameQuery(job.command.query,query)) {
    if(job.lastResponse?.id===id){post(job,job.lastResponse);return wfReturn(job,"worker.js:performAlFinalEmpty:97:61:return",undefined);}
    if(job.pending===id){post(job,{id,progress:true,reconnecting:true});return wfReturn(job,"worker.js:performAlFinalEmpty:98:72:return",undefined);}
  }
  const prior=job.lastResponse;
  const valid=P.TRIAL_ORIGIN&&job.registryState==='AL'&&job.alFinalEmptyProtocol===true
    &&!job.closed&&isActive(job)&&!job.pending&&!job.alFinalEmptyUsed
    &&owned.has(job.tab)&&Date.now()<job.activeExpiresAt&&P.validId(id)
    &&P.validQuery(query)&&Object.keys(query).sort().join(',')==='name,operation,state'
    &&query.state==='AL'&&query.operation==='search'&&prior?.ok===true
    &&prior.evidence?.complete===true&&prior.evidence.verification_pending===false
    &&prior.evidence.total===0&&Array.isArray(prior.evidence.rows)&&prior.evidence.rows.length===0
    &&P.sameQuery(prior.evidence.query,query);
  if(!valid){post(job,{id,ok:false,reason:'NY_CONNECTOR_INVALID_SEQUENCE'});return wfReturn(job,"worker.js:performAlFinalEmpty:109:76:return",undefined);}
  job.alFinalEmptyUsed=true;job.command={id,action:'capture_empty',query};job.pending=id;
  let snapshot=null;
  try{snapshot=await wfAwait(job,"worker.js:performAlFinalEmpty:112:15:await",()=>(captureStateSnapshot(job,query,id,{kind:'al-final-empty',command_id:id,query})));}
  catch{} // Optional evidence failure must not alter the settled registration result.
  if(job.closed)return wfReturn(job,"worker.js:performAlFinalEmpty:114:16:return",undefined);
  job.pending=null;job.lastResponse={id,ok:true,...(snapshot?{state_snapshot:snapshot}:{})};
  try{await wfAwait(job,"worker.js:performAlFinalEmpty:116:6:await",()=>(saveRuntime()));}catch{}
  post(job,job.lastResponse);
}

function withoutSourcePixels(value) { if(!value)return value; const {state_snapshot,...rest}=value; return rest; }
function saveRuntime() {
  keepAlive();
  if (!allJobs().length && keepAliveTimer) { clearTimeout(keepAliveTimer); keepAliveTimer = null; }
  const value = runtimeState();
  if (P.TRIAL_ORIGIN && trialAlIdle) value.trialAlIdle=trialAlIdle;
  if (P.TRIAL_ORIGIN && trialTnIdle) value.trialTnIdle=trialTnIdle;
  if (P.TRIAL_ORIGIN && trialNyIdle) value.trialNyIdle=trialNyIdle;
  if (!P.TRIAL_ORIGIN) {
    saving = saving.catch(() => {}).then(() => chrome.storage.session.set({ ccnyRuntime: value })); return saving;
  }
  const enqueued = Date.now(), owners = allJobs().filter(j => j && !j.closed);
  const sequence = ++runtimeCheckpointSequence, depth = ++runtimeCheckpointPending;
  const record = (invoked, outcome) => {
    runtimeCheckpointPending--;
    try {
      const finished = Date.now();
      const sample = {sequence, enqueued_epoch_ms:enqueued, invoked_epoch_ms:invoked,
        finished_epoch_ms:finished, queue_ms:invoked-enqueued, api_ms:finished-invoked,
        pending_at_enqueue:depth, outcome};
      for (const job of owners) {
        if (!job.workflowObservation) continue;
        const samples = job.workflowObservation.runtime_checkpoints ||= [];
        samples.push(sample); if(samples.length>32)samples.shift();
      }
    } catch { /* Observation must never change a checkpoint result. */ }
  };
  saving = saving.catch(() => {}).then(() => {
    const invoked = Date.now();
    try {
      return Promise.resolve(chrome.storage.session.set({ccnyRuntime:value})).then(
        result => {record(invoked,'returned');return result;},
        error => {record(invoked,'rejected');throw error;});
    } catch(error) {record(invoked,'threw');throw error;}
  });
  return saving;
}
function newJob(sender, id, refreshOnly, saved = {}) {
  return { port: null, sender, lookupId: id, refreshOnly, registryState: "NY", enqueuedAt: Date.now(), expiresAt: Date.now() + QUEUE_TTL, activeExpiresAt: null, generation: 0, tab: null, creating: null, pending: null, acquireId: null, closed: false, timer: null, reconnectTimer: null, rateRetries: 0, timeoutRetries: 0, detailAuthRetryUsed: false, retryNotBefore: 0, verificationRetryUsed: false, command: null, lastResponse: null, queryRepaired: false, ...saved };
}
function arm(job) {
  clearTimeout(job.timer);
  const running = job.activeExpiresAt !== null;
  job.timer = setTimeout(() => close(job, running ? "NY_CONNECTOR_TIMEOUT" : "NY_CONNECTOR_QUEUE_TIMEOUT"), Math.max(0, (running ? job.activeExpiresAt : job.expiresAt) - Date.now()));
}
function awaitReconnect(job) {
  clearTimeout(job.reconnectTimer);
  job.reconnectTimer = setTimeout(() => { if (!job.port) close(job, "NY_CONNECTOR_INTERRUPTED"); }, Math.max(0, Math.min(90000, (job.activeExpiresAt ?? job.expiresAt) - Date.now())));
}
async function saveRepair(value) { await chrome.storage.local.set({ ccnyRepair: value }); repair = value; }
const ownedCleanupRetries = new Map();
async function removeOwned(tabId) {
  if (tabId === null || !owned.has(tabId)) return;
  try {
    const tab = await chrome.tabs.get(tabId), url = new URL(tab.url);
    const trialRegistry = P.TRIAL_ORIGIN && ((url.origin === "https://orion.nv.gov" && url.pathname === "/portal/public/")
      || (url.origin === "https://ago.igovsolution.net" && url.pathname === "/online/Lookups/Business.aspx")
      || (url.origin === "https://tncab.tnsos.gov" && url.pathname === "/portal/registered-charities-search")
      || (url.origin === "https://secure.nmdoj.gov" && /^\/CharitySearch\/(?:CharityDetail\.aspx|GenericError\.htm)?$/i.test(url.pathname))
      || (url.origin === "https://charities.sos.ms.gov" && url.pathname === "/online/portal/ch/page/charities-search/Portal.aspx")
      || (url.origin === "https://www.sosnc.gov" && /^\/online_services\/search\/(?:by_title\/search_charities|Charities_Results|charities_(?:profile|filings)\/\d+)$/.test(url.pathname)));
    if (trialRegistry || (["https://charitable.illinoisattorneygeneral.gov", "https://verify.sos.ga.gov"].includes(url.origin)) || url.origin === P.NY && /^\/RegistrySearch(?:\/[0-9]{2}-[0-9]{2}-[0-9]{2})?\/?$/.test(url.pathname)) await chrome.tabs.remove(tabId);
    owned.delete(tabId);
    ownedCleanupRetries.delete(tabId);
  } catch (error) {
    if (!P.TRIAL_ORIGIN) owned.delete(tabId);
    else if (/No tab with id|Invalid tab ID/i.test(String(error))) {
      owned.delete(tabId);ownedCleanupRetries.delete(tabId);
    } else {
      diagnostic('owned-tab-cleanup-pending',null,'Owned tab closure not acknowledged');
      if (!ownedCleanupRetries.has(tabId)) {
        ownedCleanupRetries.set(tabId,true);
        setTimeout(()=>{if(owned.has(tabId))removeOwned(tabId).catch(()=>{});},1000);
      }
    }
  }
  await saveRuntime();
}
const boot = (async () => {
  await chrome.storage.session.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });
  // Older supported Chrome releases expose this method on session only. Local
  // storage contains repair timing/reason only; no queries, tokens or tab IDs.
  if (chrome.storage.local.setAccessLevel) await chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" });
  repair = (await chrome.storage.local.get("ccnyRepair")).ccnyRepair || {};
  const previous = (await chrome.storage.session.get("ccnyRuntime")).ccnyRuntime;
  if (previous?.schema === 2) {
    diagnostics.push(...(previous.diagnostics || []).slice(-70));
    registryTnTrafficRestore(previous.tnTraffic);
    nextStart = Number(previous.nextStart) || 0;
    for (const [state, start] of Object.entries(previous.laneStarts || {})) if (Number.isFinite(start)) laneStarts.set(state,start);
    for (const saved of previous.queue || []) {
      if (!P.validId(saved.id) || !Number.isInteger(saved.tabId) || !Number.isFinite(saved.expiresAt)) continue;
      let sourceTab;
      try { sourceTab = await chrome.tabs.get(saved.tabId); } catch { continue; }
      // Revalidate the live source tab after restart; never manufacture an
      // authorized staging origin for a tab that has navigated elsewhere.
      const sourceSender = { id: chrome.runtime.id, frameId: 0, url: sourceTab.url, documentId: saved.documentId, tab: { id: saved.tabId } };
      if (!allowedSender(sourceSender) || !P.registryAllowed(saved.registryState || "NY",new URL(sourceTab.url).origin)) continue;
      const { id, tabId, documentId, active: wasActive, ...state } = saved;
      const job = newJob(sourceSender, id, !!saved.refreshOnly, state);
      if (wasActive && P.TRIAL_ORIGIN && !activeLanes.has(job.registryState)) activeLanes.set(job.registryState,job);
      else if (wasActive && !P.TRIAL_ORIGIN && !active) active=job; else queue.push(job);
      arm(job);
      awaitReconnect(job);
    }
  }
  for (const id of previous?.ownedTabs || []) if (Number.isInteger(id)) owned.add(id);
  // Completed trial windows are no longer retained between checks.
  for (const id of [...owned]) if (!allJobs().some(j => j?.tab === id) && trialAlIdle?.id!==id && trialTnIdle?.id!==id && trialNyIdle?.id!==id) {
    await removeOwned(id);
    while(P.TRIAL_ORIGIN && owned.has(id)) { await nap(1000); await removeOwned(id); }
  }
  if (repair.phase === "repairing") await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_INTERRUPTED" });
  await CCSourceRail.ready();
  diagnostic("worker-start", active, `restored=${allJobs().filter(Boolean).length}`);
  await saveRuntime();
})();
// A failed initialization must fail requests explicitly, never reset the budget.
boot.catch(() => {});
const nap = ms => new Promise(resolve => setTimeout(resolve, ms));
function allowedSender(sender) {
  try { return sender.id === chrome.runtime.id && sender.frameId === 0 && P.allowedOrigin(new URL(sender.url).origin) && Number.isInteger(sender.tab?.id); }
  catch { return false; }
}
function post(job, message) {
  message=nvHandoffDiagnostic(job,message);
  if(P.TRIAL_ORIGIN)message={...message,workflow_observation:wfExport(job)};
  if(P.TRIAL_ORIGIN && ["GA","MS","NC","TN","AL","IL","NM"].includes(job.registryState)
      && (message.action==="closed" || (typeof message.ok==="boolean" && !message.progress)))
    message={...message,trial_diagnostics:[...(job.trialDiagnostics||[])]};
  if(P.TRIAL_ORIGIN && job.registryState==='IL' && typeof message.ok==='boolean' && !message.progress)
    message={...message,trial_diagnostics:[...(message.trial_diagnostics||[]).slice(-118),{
      at:Date.now(),type:'il-handoff-worker',detail:JSON.stringify({build:'il-handoff-observation-1',
        extension_id:chrome.runtime.id,worker_tag:nvHandoffWorkerTag,
        active:isActive(job),pending:!!job.pending,pending_matches_reply:job.pending===message.id,
        command_matches_reply:job.command?.id===message.id,
        operation:job.command?.query?.identifier?'detail':'search'})}]};
  try {
    if(P.TRIAL_ORIGIN)message={...message,workflow_delivery:{schema:1,worker_post_epoch_seconds:Date.now()/1000}};
    job.port.postMessage(message);
  } catch {}
}
function notifyQueue() {
  queue.forEach((job, index) => {
    if (job.acquireId) post(job, { id: job.acquireId, progress: true, position: index + 1 });
  });
}
function pump() {
  CCSourceRail.notify();
  if(!CCSourceRail.isReady())return;
  if (pumpTimer || !queue.length) return;
  const running=P.TRIAL_ORIGIN?activeLanes.size:Number(!!active);
  const cap=P.TRIAL_ORIGIN?8:1;
  if(running>=cap)return;
  const usedDuoSlots=new Set([...activeLanes.values()].filter(isDuoJob).map(j=>j.duoSlot).concat(CCSourceRail.admissionSlots()));
  let earliest=Infinity,index=-1;
  for(let i=0;i<queue.length;i++) {
    const job=queue[i];
    if(job.closed)continue;
    if(P.TRIAL_ORIGIN && activeLanes.has(job.registryState))continue;
    if(isDuoJob(job) && usedDuoSlots.size>=2)continue;
    // Preserve FIFO within a registry, even while its old page reconnects.
    if(P.TRIAL_ORIGIN && queue.slice(0,i).some(j=>!j.closed&&j.registryState===job.registryState))continue;
    if(!job.port)continue;
    const start=P.TRIAL_ORIGIN?(laneStarts.get(job.registryState)||0):nextStart;
    if(start<=Date.now()){index=i;break;}
    earliest=Math.min(earliest,start);
    if(!P.TRIAL_ORIGIN)break;
  }
  if(index<0) {
    if(Number.isFinite(earliest))pumpTimer=setTimeout(()=>{pumpTimer=null;pump();},Math.max(0,earliest-Date.now()));
    return;
  }
  const job=queue.splice(index,1)[0];
  // In the isolated trial, a failed origin reset pauses further resets, not
  // normal fresh-page lookups. Otherwise one transient rejection makes later
  // organizations inconclusive without consulting a source that has recovered.
  // performQuery still enforces this same persisted reset cooldown on rejection.
  if(!P.TRIAL_ORIGIN&&job.registryState==='NY'&&!job.refreshOnly&&repair.phase==='failed'&&repair.nextAllowedAt>Date.now()){
    close(job,repair.reason||'NY_CONNECTOR_RECOVERY_REJECTED');return;
  }
  if(P.TRIAL_ORIGIN)activeLanes.set(job.registryState,job);else active=job;
  if(isDuoJob(job))job.duoSlot=[0,1].find(slot=>!usedDuoSlots.has(slot));
  diagnostic('admitted',job,`${job.registryState} queue_ms=${Date.now()-job.enqueuedAt}`);
  job.activeExpiresAt ??= Date.now()+ACTIVE_TTL;
  arm(job);
  saveRuntime().then(()=>{
    if(job.closed)return;
    if(job.acquireId)post(job,{id:job.acquireId,ok:true});
    notifyQueue();pump();
  }).catch(()=>close(job,'NY_CONNECTOR_INTERRUPTED'));
}
async function close(job, reason, finishId) {
  if (job.closed) return wfReturn(job,"worker.js:close:283:18:return",undefined);
  job.closed = true;
  clearTimeout(job.timer);
  clearTimeout(job.reconnectTimer);
  const index = queue.indexOf(job);
  if (index >= 0) queue.splice(index, 1);
  if (reason) post(job, { action: "closed", reason });
  // Await tab creation before handing the slot onward, including origin closure.
  let cleanupTimer, cleanupDone=false;
  const cleanup = (async () => {
    if (job.creating) await wfAwait(job,"worker.js:close:293:22:await",()=>(job.creating.catch(() => {})));
    if (P.TRIAL_ORIGIN && job.registryState==='NV') try { await wfAwait(job,"worker.js:close:294:52:await",()=>(registryRestoreNevadaVisibility(job))); } catch { diagnostic('visibility-restore-failed',job,'Continuing owned-page cleanup'); }
    const tabId = job.tab; job.tab = null;
    if (tabId !== null) await wfAwait(job,"worker.js:close:321:31:await",()=>(removeOwned(tabId)));
    // A failed Chrome remove acknowledgement retains ownership. Keep the slot
    // reserved while retrying only that same owned tab; never open a replacement.
    while (P.TRIAL_ORIGIN && tabId !== null && owned.has(tabId)) {
      await new Promise(resolve=>setTimeout(resolve,1000));
      await removeOwned(tabId);
    }
  })();
  // Returning from finish and releasing a physical slot are separate events.
  // Late cleanup may free this job's slot, but cannot free a newer owner's slot.
  const release = () => {
    cleanupDone=true;
    if (isActive(job)) {
      if (P.TRIAL_ORIGIN) {activeLanes.delete(job.registryState);laneStarts.set(job.registryState,Date.now()+PACE_MS);}
      else {active=null;nextStart=Date.now()+PACE_MS;}
    }
    notifyQueue();pump();saveRuntime().catch(()=>{});
  };
  cleanup.then(release,()=>diagnostic('owned-slot-cleanup-pending',job,'Slot retained until cleanup is acknowledged'));
  // Browser tab/storage acknowledgements can stall. Finish stays bounded;
  // any late cleanup still refers only to this job's own tab.
  try { await wfAwait(job,"worker.js:close:325:8:await",()=>(Promise.race([cleanup, new Promise(resolve => { cleanupTimer = setTimeout(resolve, 10000); })]))); }
  catch { /* Closing a vanished tab must not strand other organizations. */ }
  finally { clearTimeout(cleanupTimer); }
  if (finishId) post(job, { id: finishId, ok: true, cleanup_complete: cleanupDone });
  try { job.port.disconnect(); } catch {}
  notifyQueue();
  pump();
  saveRuntime().catch(() => {});
}
async function lookupTab(job) {
  if (job.tab !== null) return wfReturn(job,"worker.js:lookupTab:339:24:return",undefined);
  if(P.TRIAL_ORIGIN && trialNyIdle) {
    const saved=trialNyIdle;trialNyIdle=null;clearTimeout(trialNyIdleTimer);
    try {
      const tab=await wfAwait(job,"worker.js:lookupTab:343:16:await",()=>(chrome.tabs.get(saved.id))),source=await wfAwait(job,"worker.js:lookupTab:343:55:await",()=>(chrome.tabs.get(job.sender.tab.id)));
      if(!job.refreshOnly && !job.closed && owned.has(saved.id) && saved.expiresAt>Date.now()
          && nyRegistryPage(tab.url) && new URL(source.url).origin===P.TRIAL_ORIGIN) {
        job.tab=saved.id;job.nySessionExpiresAt=saved.expiresAt;
        await wfAwait(job,"worker.js:lookupTab:347:8:await",()=>(registryExposeReusedNyTab(job,source)));
        diagnostic('ny-session-reuse',job,'owned successful page; new query and evidence required');
      } else await wfAwait(job,"worker.js:lookupTab:349:13:await",()=>(removeOwned(saved.id)));
    } catch {await wfAwait(job,"worker.js:lookupTab:350:13:await",()=>(removeOwned(saved.id)));}
    await wfAwait(job,"worker.js:lookupTab:351:4:await",()=>(saveRuntime()));
    if(job.tab!==null || job.closed)return wfReturn(job,"worker.js:lookupTab:352:36:return",undefined);
  }
  job.creating = chrome.tabs.get(job.sender.tab.id).then(async origin => {
    if (job.closed) return wfReturn(job,"worker.js:lookupTab:355:20:return",undefined);
    if (!Number.isInteger(origin.windowId) || origin.windowId < 0) throw new Error("NY_CONNECTOR_INCOMPLETE");
    await wfAwait(job,"worker.js:lookupTab:357:4:await",()=>(registryCreateOwnedTab(job,P.NY + "/RegistrySearch",origin)));
  });
  await wfAwait(job,"worker.js:lookupTab:359:2:await",()=>(job.creating)); job.creating = null;
  // The content script's form check below is authoritative. Unrelated page
  // resources can keep Chrome in "loading" after the search form is usable.
}
async function repairConnection(job, id) {
  if (repair.nextAllowedAt > Date.now()) throw new Error("NY_CONNECTOR_RECOVERY_COOLDOWN");
  await wfAwait(job,"worker.js:repairConnection:365:2:await",()=>(lookupTab(job)));
  // A newly created tab can still expose about:blank while navigation commits.
  // Wait for its registry origin before attempting origin-scoped cleanup; the
  // form itself need not work for a manual connection refresh to be useful.
  const navigationDeadline = Math.min(Date.now() + 30000, job.activeExpiresAt);
  for (;;) {
    const tab = await wfAwait(job,"worker.js:repairConnection:371:16:await",()=>(chrome.tabs.get(job.tab)));
    if (tab.url && new URL(tab.url).origin === P.NY && /^\/RegistrySearch\/?$/.test(new URL(tab.url).pathname)) break;
    if (tab.url && tab.url !== "about:blank") throw new Error("NY_CONNECTOR_INCOMPLETE");
    if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
    if (Date.now() >= navigationDeadline) throw new Error("NY_CONNECTOR_TAB_READY_TIMEOUT");
    await wfAwait(job,"worker.js:repairConnection:376:4:await",()=>(nap(100)));
  }
  if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
  const previous = repair;
  await wfAwait(job,"worker.js:repairConnection:380:2:await",()=>(saveRepair({ phase: "repairing", attemptedAt: Date.now(), nextAllowedAt: Date.now() + REPAIR_INTERVAL })));
  post(job, { id, progress: true, recovering: true });
  try {
    await wfAwait(job,"worker.js:repairConnection:383:4:await",async ()=>(CCNYRecovery.clearForTab(job.tab, [...owned], async () => {
      const tabId = job.tab; job.tab = null; job.generation++;
      await wfAwait(job,"worker.js:repairConnection:385:6:await",()=>(removeOwned(tabId)));
    })));
    if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
    await wfAwait(job,"worker.js:repairConnection:388:4:await",()=>(lookupTab(job)));
  } catch (error) {
    if (error.message === "NY_CONNECTOR_RECOVERY_PAGE_OPEN") {
      await wfAwait(job,"worker.js:repairConnection:391:6:await",()=>(saveRepair(previous)));
      // An open user registry page forbids origin cleanup. In the isolated
      // trial, retry once using a fresh owned form without changing cookies,
      // storage, the user's page, or the original lookup deadline.
      if (P.TRIAL_ORIGIN && !job.refreshOnly && !job.closed) {
        const tabId = job.tab; job.tab = null; job.generation++;
        await wfAwait(job,"worker.js:repairConnection:397:8:await",()=>(removeOwned(tabId)));
        if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
        job.nyFreshPageRecoveryOnly = true;
        await wfAwait(job,"worker.js:repairConnection:400:8:await",()=>(lookupTab(job)));
        return wfReturn(job,"worker.js:repairConnection:401:8:return",undefined);
      }
    }
    else await wfAwait(job,"worker.js:repairConnection:404:9:await",()=>(saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_FAILED" })));
    throw error;
  }
}
async function recordRecovery(response) {
  if (response.ok) await saveRepair({ ...repair, phase: "verified", finishedAt: Date.now() });
  else await saveRepair({ ...repair, phase: "failed", finishedAt: Date.now(), reason: recoveryFailure(response.reason) });
}
async function ready(job) {
  const deadline = Date.now() + 30000;
  while (!job.closed && Date.now() < deadline) {
    let state;
    try { state = await wfAwait(job,"worker.js:ready:416:18:await",()=>(chrome.tabs.sendMessage(job.tab, { action: "ready" }, { frameId: 0 }))); }
    catch { /* Content script is still loading. */ }
    if (state?.rateLimited) throw new Error("NY_CONNECTOR_RATE_LIMITED");
    if (state?.ready) { job.nyPageVisibility=state.page_visibility;return wfReturn(job,"worker.js:ready:419:67:return",undefined); }
    await wfAwait(job,"worker.js:ready:420:4:await",()=>(nap(250)));
  }
  throw new Error("NY_CONNECTOR_TAB_READY_TIMEOUT");
}
async function waitForRegistryDocument(job, path, previousDocument = "") {
  const deadline = Math.min(Date.now() + 10000, job.activeExpiresAt);
  while (!job.closed && Date.now() < deadline) {
    const tab = await wfAwait(job,"worker.js:waitForRegistryDocument:427:16:await",()=>(chrome.tabs.get(job.tab)));
    if (tab.url === P.NY + path) {
      try { const state = await wfAwait(job,"worker.js:waitForRegistryDocument:429:26:await",()=>(chrome.tabs.sendMessage(job.tab, { action: "ready" }, { frameId: 0 })));
        if (state?.ready && state.url === tab.url && (!previousDocument || state.documentId && state.documentId !== previousDocument)) return wfReturn(job,"worker.js:waitForRegistryDocument:430:135:return",undefined);
      } catch { /* The navigation's new content script is not ready yet. */ }
    }
    await wfAwait(job,"worker.js:waitForRegistryDocument:433:4:await",()=>(nap(100)));
  }
  throw new Error(job.closed ? "NY_CONNECTOR_INTERRUPTED" : "NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT");
}
async function openDetail(job, query) {
  let tab = await wfAwait(job,"worker.js:openDetail:438:12:await",()=>(chrome.tabs.get(job.tab)));
  const path = "/RegistrySearch/" + query.orgID;
  if (tab.url === P.NY + path) return wfReturn(job,"worker.js:openDetail:440:31:return",undefined);
  if (/^\/RegistrySearch\/[0-9]{2}-[0-9]{2}-[0-9]{2}\/?$/.test(new URL(tab.url).pathname)) {
    const returned = await wfAwait(job,"worker.js:openDetail:442:21:await",()=>(chrome.tabs.sendMessage(job.tab, { action: "back-to-results" }, { frameId: 0 })));
    if (!returned?.ok) throw new Error("NY_CONNECTOR_DETAIL_LINK_MISSING");
    await wfAwait(job,"worker.js:openDetail:444:4:await",()=>(waitForRegistryDocument(job, "/RegistrySearch")));
  }
  if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
  const opened = await wfAwait(job,"worker.js:openDetail:447:17:await",()=>(chrome.tabs.sendMessage(job.tab, { action: "open-detail", query }, { frameId: 0 })));
  if (!opened?.ok) throw new Error(opened?.reason || "NY_CONNECTOR_DETAIL_LINK_MISSING");
  await wfAwait(job,"worker.js:openDetail:449:2:await",()=>(waitForRegistryDocument(job, path)));
}
async function prepareNySearchForm(job, query) {
  if (!P.TRIAL_ORIGIN || Object.hasOwn(query, "orgID")) return wfReturn(job,"worker.js:prepareNySearchForm:452:56:return",undefined);
  const key=Object.keys(query)[0],tab=await wfAwait(job,"worker.js:prepareNySearchForm:453:38:await",()=>(chrome.tabs.get(job.tab)));
  if (job.closed || Date.now()>=job.activeExpiresAt) throw new Error("NY_CONNECTOR_INTERRUPTED");
  const url=new URL(tab.url);
  if (!owned.has(tab.id) || url.origin!==P.NY || !/^\/RegistrySearch\/?$/.test(url.pathname)) throw new Error("NY_CONNECTOR_INCOMPLETE");
  const before=await wfAwait(job,"worker.js:prepareNySearchForm:457:15:await",()=>(chrome.tabs.sendMessage(tab.id,{action:"ready"},{frameId:0})));
  job.nyPageVisibility=before?.page_visibility;
  if (!Array.isArray(before?.formFields) || !before.formFields.some(field=>field!==key)) return wfReturn(job,"worker.js:prepareNySearchForm:459:89:return",undefined);
  if (!before.documentId) throw new Error("NY_CONNECTOR_SEARCH_FORM_CHANGED");
  // A fresh normal page resets the state's form model, unlike changing its
  // prior EIN input to an empty string. Do not reset cookies, retry allowances,
  // or the lookup deadline. Same-field searches retain the verified document.
  const current=await wfAwait(job,"worker.js:prepareNySearchForm:464:16:await",()=>(chrome.tabs.get(tab.id)));
  if(job.closed || Date.now()>=job.activeExpiresAt)throw new Error("NY_CONNECTOR_INTERRUPTED");
  if(job.tab!==tab.id || !owned.has(tab.id) || current.url!==tab.url)throw new Error("NY_CONNECTOR_SEARCH_FORM_CHANGED");
  await wfAwait(job,"worker.js:prepareNySearchForm:467:2:await",()=>(chrome.tabs.reload(tab.id)));job.generation++;
  await wfAwait(job,"worker.js:prepareNySearchForm:468:2:await",()=>(waitForRegistryDocument(job,url.pathname,before.documentId)));
  if (job.closed || Date.now()>=job.activeExpiresAt) throw new Error("NY_CONNECTOR_INTERRUPTED");
  const after=await wfAwait(job,"worker.js:prepareNySearchForm:470:14:await",()=>(chrome.tabs.sendMessage(tab.id,{action:"ready"},{frameId:0})));
  job.nyPageVisibility=after?.page_visibility;
  if (after?.formFields?.some(field=>field!==key)) throw new Error("NY_CONNECTOR_SEARCH_FORM_CHANGED");
  diagnostic("ny-form-transition",job,"new normal document for a different search field");
  await wfAwait(job,"worker.js:prepareNySearchForm:474:2:await",()=>(saveRuntime()));
}
async function awaitSnapshotCleanup(job,id) {
  if(!job.snapshotCleanupBusy)return;
  const completion=job.snapshotCleanupCompletion;
  const tab=job.tab,generation=job.generation,deadline=job.activeExpiresAt;
  const remaining=deadline-Date.now();
  if(!completion||typeof completion.then!=='function'||remaining<=0)
    throw new Error('NY_CONNECTOR_INCOMPLETE');
  let timer;
  diagnostic('capture-cleanup-wait',job,'Waiting for original owned capture cleanup');
  try {
    await Promise.race([completion,new Promise((_,reject)=>{
      timer=setTimeout(()=>reject(new Error('NY_CONNECTOR_INCOMPLETE')),remaining);
    })]);
  } finally {clearTimeout(timer);}
  if(job.closed||!isActive(job)||job.pending!==id||job.command?.id!==id
    ||job.tab!==tab||job.generation!==generation||job.activeExpiresAt!==deadline
    ||Date.now()>=deadline||job.snapshotCleanupBusy)
    throw new Error('NY_CONNECTOR_INCOMPLETE');
}
async function performSearch(job, query, id) {
  if (job.closed) return wfReturn(job,"worker.js:performSearch:477:18:return",undefined);
  if (job.command?.id === id && !P.sameQuery(job.command.query, query)) { post(job, { id, ...registryNvSequenceFailure(job,query,"worker-command-changed") }); return wfReturn(job,"worker.js:performSearch:478:159:return",undefined); }
  if (job.lastResponse?.id === id && P.sameQuery(job.command?.query, query)) { post(job, job.lastResponse); return wfReturn(job,"worker.js:performSearch:479:108:return",undefined); }
  if (job.pending === id && P.sameQuery(job.command?.query, query)) { post(job, { id, progress: true, reconnecting: true }); return wfReturn(job,"worker.js:performSearch:480:125:return",undefined); }
  if (!isActive(job) || job.pending) { post(job, { id, ...registryNvSequenceFailure(job,query,"worker-inactive-or-pending") }); return wfReturn(job,"worker.js:performSearch:481:128:return",undefined); }
  if (job.command?.id !== id) { job.queryRepaired = false; job.lastResponse = null; }
  job.command = { id, query };
  job.pending = id;
  let response;
  try {
    await wfAwait(job,"worker.js:performSearch:487:4:await",()=>(saveRuntime()));
    await wfAwait(job,"capture-cleanup-command-handoff",()=>awaitSnapshotCleanup(job,id));
    if (job.registryState !== "NY") {
      response = await wfAwait(job,"worker.js:performSearch:489:17:await",()=>(performRegistryQuery(job, query)));
    } else {
    let repaired = job.queryRepaired;
    for (;;) {
      if (job.retryNotBefore > Date.now()) await wfAwait(job,"worker.js:performSearch:493:43:await",()=>(nap(job.retryNotBefore - Date.now())));
      if (job.closed) return wfReturn(job,"worker.js:performSearch:494:22:return",undefined);
      if (job.reloadAfterRateLimit) {
        await wfAwait(job,"worker.js:performSearch:496:8:await",()=>(chrome.tabs.update(job.tab, { url: P.NY + "/RegistrySearch" })));
        job.reloadAfterRateLimit = false; await wfAwait(job,"worker.js:performSearch:497:42:await",()=>(saveRuntime()));
      }
      let documentLimited = false;
      try {
        if(P.TRIAL_ORIGIN)post(job,{id,progress:true,ny_phase:"opening_page"});
        await wfAwait(job,"worker.js:performSearch:502:8:await",()=>(lookupTab(job)));
        if(P.TRIAL_ORIGIN)post(job,{id,progress:true,ny_phase:"waiting_for_form"});
        try { await wfAwait(job,"worker.js:performSearch:504:14:await",()=>(ready(job))); }
        catch (error) { documentLimited = error.message === "NY_CONNECTOR_RATE_LIMITED"; throw error; }
        const current = await wfAwait(job,"worker.js:performSearch:506:24:await",()=>(chrome.tabs.get(job.tab))), url = new URL(current.url);
        if (url.origin !== P.NY || !/^\/RegistrySearch(?:\/[0-9]{2}-[0-9]{2}-[0-9]{2})?\/?$/.test(url.pathname)) throw new Error("NY_CONNECTOR_INCOMPLETE");
        if (Object.hasOwn(query, "orgID")) await wfAwait(job,"worker.js:performSearch:508:43:await",()=>(openDetail(job, query)));
        else if(P.TRIAL_ORIGIN && /^\/RegistrySearch\/[0-9]{2}-[0-9]{2}-[0-9]{2}\/?$/.test(url.pathname)) {
          // Navigate before delivering the next command: full-page Back would
          // otherwise destroy the content relay waiting to return its result.
          const returned=await wfAwait(job,"worker.js:performSearch:512:25:await",()=>(chrome.tabs.sendMessage(job.tab,{action:'back-to-results'},{frameId:0})));
          if(!returned?.ok)throw new Error('NY_CONNECTOR_RETURN_FORM_TIMEOUT');
          await wfAwait(job,"worker.js:performSearch:514:10:await",()=>(waitForRegistryDocument(job,'/RegistrySearch')));
        }
        if(P.TRIAL_ORIGIN)post(job,{id,progress:true,ny_phase:"preparing_query"});
        await wfAwait(job,"worker.js:performSearch:517:8:await",()=>(prepareNySearchForm(job,query)));
        if (job.closed) return wfReturn(job,"worker.js:performSearch:518:24:return",undefined);
        const generation = job.generation;
        // Stable across reconnection, distinct for an already permitted retry.
        const attempt = `${job.generation}:${job.rateRetries}`;
        if(P.TRIAL_ORIGIN)post(job,{id,progress:true,ny_phase:"query_sent"});
        response = await wfAwait(job,"worker.js:performSearch:523:19:await",()=>(chrome.tabs.sendMessage(job.tab, { action: "search", id, attempt, query, verificationRetryUsed: job.verificationRetryUsed }, { frameId: 0 })));
        if (job.closed || generation !== job.generation) return wfReturn(job,"worker.js:performSearch:524:57:return",undefined);
        collectNyDiagnostics(job,response);
        job.verificationRetryUsed ||= response?.verificationRetryUsed === true;
        await wfAwait(job,"worker.js:performSearch:527:8:await",()=>(saveRuntime()));
        if (["NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT", "NY_CONNECTOR_SEARCH_RESPONSE_TIMEOUT", "NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT"].includes(response?.reason)) throw new Error(response.reason);
        if (response?.reason === "NY_CONNECTOR_RATE_LIMITED") throw new Error(response.reason);
        if (!response?.ok || !P.sameQuery(response.evidence?.query, query)) response = { ok: false, reason: response?.reason || "NY_CONNECTOR_INCOMPLETE" };
        if (P.TRIAL_ORIGIN && response?.reason === "NY_CONNECTOR_DETAIL_UNAUTHORIZED"
            && Object.hasOwn(query, "orgID") && !job.detailAuthRetryUsed && !job.verificationRetryUsed
            && job.activeExpiresAt - Date.now() > 15000) {
          // A successful search can be followed by an expired detail session.
          // Return to its observed result list, renew the owned form, click
          // normal Verify once, and reopen the same public ID link. Browser
          // Back restores a "Verified" form whose Verify button is absent.
          // Never erase cookies/user pages,
          // reset the shared verification budget, or retry another rejection.
          job.detailAuthRetryUsed = true; job.verificationRetryUsed = true;
          await wfAwait(job,"worker.js:performSearch:541:10:await",()=>(saveRuntime()));
          const returned = await wfAwait(job,"worker.js:performSearch:542:27:await",()=>(chrome.tabs.sendMessage(job.tab, {action:"back-to-results"}, {frameId:0})));
          if (!returned?.ok) break;
          await wfAwait(job,"worker.js:performSearch:544:10:await",()=>(waitForRegistryDocument(job, "/RegistrySearch")));
          if (job.closed || Date.now() >= job.activeExpiresAt) return wfReturn(job,"worker.js:performSearch:545:63:return",undefined);
          const formTab = job.tab;
          const priorForm = await wfAwait(job,"worker.js:performSearch:547:28:await",()=>(chrome.tabs.sendMessage(formTab, {action:"ready"}, {frameId:0})));
          if (job.closed || job.tab !== formTab || !owned.has(formTab) || Date.now() >= job.activeExpiresAt) return wfReturn(job,"worker.js:performSearch:548:109:return",undefined);
          if (!priorForm?.documentId) throw new Error("NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT");
          await wfAwait(job,"worker.js:performSearch:550:10:await",()=>(chrome.tabs.reload(formTab)));
          await wfAwait(job,"worker.js:performSearch:551:10:await",()=>(waitForRegistryDocument(job, "/RegistrySearch", priorForm.documentId)));
          if (job.closed || Date.now() >= job.activeExpiresAt) return wfReturn(job,"worker.js:performSearch:552:63:return",undefined);
          const verified = await wfAwait(job,"worker.js:performSearch:553:27:await",()=>(chrome.tabs.sendMessage(job.tab, {action:"verify", id,
            attempt:`${attempt}:detail-auth`, verificationRetryUsed:true}, {frameId:0})));
          if (job.closed || generation !== job.generation) return wfReturn(job,"worker.js:performSearch:555:59:return",undefined);
          collectNyDiagnostics(job,verified);
          if (!verified?.ok || verified.evidence?.verified !== true) {
            response = {ok:false, reason:verified?.reason || "NY_CONNECTOR_VERIFICATION_REQUIRED"}; break;
          }
          // Reload removed the result links. Re-run only the successful query
          // that produced this detail, then open its observed link again.
          // Verification and the original job deadline remain shared.
          if (!job.nyLastSearchQuery) {
            response = {ok:false, reason:"NY_CONNECTOR_DETAIL_LINK_MISSING"}; break;
          }
          const restored = await wfAwait(job,"worker.js:performSearch:566:27:await",()=>(chrome.tabs.sendMessage(job.tab, {action:"search", id,
            attempt:`${attempt}:detail-results`, query:job.nyLastSearchQuery,
            verificationRetryUsed:true}, {frameId:0})));
          if (job.closed || generation !== job.generation) return wfReturn(job,"worker.js:performSearch:569:59:return",undefined);
          collectNyDiagnostics(job,restored);
          if (!restored?.ok || !P.sameQuery(restored.evidence?.query, job.nyLastSearchQuery)) {
            response = {ok:false, reason:restored?.reason || "NY_CONNECTOR_INCOMPLETE"}; break;
          }
          diagnostic("ny-detail-session", job, "normal verification and original results restored; same observed ID reopened");
          continue;
        }
        if (P.TRIAL_ORIGIN && rejected(response.reason)) {
          // Keep the source failure distinct from a refused origin reset.
          // These two static codes contain no verification material.
          job.nyFailureCause=response.reason;
          job.nyResetCooldown=repair.nextAllowedAt>Date.now();
        }
        if (rejected(response.reason) && !repaired) {
          if (repair.nextAllowedAt > Date.now()) {
            await wfAwait(job,"worker.js:performSearch:585:12:await",()=>(saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_REJECTED" })));
            response = { ok: false, reason: "NY_CONNECTOR_RECOVERY_REJECTED" }; break;
          }
          job.queryRepaired = true; await wfAwait(job,"worker.js:performSearch:588:36:await",()=>(saveRuntime()));
          await wfAwait(job,"worker.js:performSearch:589:10:await",()=>(repairConnection(job, id))); repaired = true; continue;
        }
        if (repaired && !job.nyFreshPageRecoveryOnly) {
          await wfAwait(job,"worker.js:performSearch:592:10:await",()=>(recordRecovery(response)));
          if (!response.ok && rejected(response.reason)) response.reason = "NY_CONNECTOR_RECOVERY_REJECTED";
        }
        if (repaired && job.nyFreshPageRecoveryOnly && !response.ok && rejected(response.reason)) {
          // The fresh owned form did not resolve the rejection, and another
          // NY page still prevents the origin-scoped refresh. Preserve that
          // actionable cause instead of hiding it behind a generic 401.
          response.reason = "NY_CONNECTOR_RECOVERY_PAGE_OPEN";
        }
        break;
      } catch (error) {
        if (error.message === "NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT" && Object.hasOwn(query, "orgID") && !job.detailRetryUsed && job.activeExpiresAt - Date.now() > 45000) {
          // Retry only the exact detail page already opened from an observed
          // result link. Require a new document so a cached timeout cannot win.
          const path = "/RegistrySearch/" + query.orgID;
          const tab = await wfAwait(job,"worker.js:performSearch:607:22:await",()=>(chrome.tabs.get(job.tab)));
          const previous = await wfAwait(job,"worker.js:performSearch:608:27:await",()=>(chrome.tabs.sendMessage(job.tab, { action: "ready" }, { frameId: 0 })));
          if (tab.url !== P.NY + path || !previous?.documentId) throw error;
          job.detailRetryUsed = true; job.generation++;
          await wfAwait(job,"worker.js:performSearch:611:10:await",()=>(saveRuntime())); post(job, { id, progress: true, retrying: true });
          await wfAwait(job,"worker.js:performSearch:612:10:await",()=>(chrome.tabs.reload(job.tab)));
          await wfAwait(job,"worker.js:performSearch:613:10:await",()=>(waitForRegistryDocument(job, path, previous.documentId)));
          continue;
        }
        if (["NY_CONNECTOR_TAB_READY_TIMEOUT", "NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT", "NY_CONNECTOR_SEARCH_RESPONSE_TIMEOUT"].includes(error.message) && job.timeoutRetries < 1) {
          job.timeoutRetries++;
          job.retryNotBefore = Date.now() + 1000;
          post(job, { id, progress: true, retrying: true });
          // Closing the owned tab cancels pending verification and isolates late
          // responses. Carry the used 401 budget across this timeout retry.
          const tabId = job.tab; job.tab = null; job.generation++;
          await wfAwait(job,"worker.js:performSearch:623:10:await",()=>(removeOwned(tabId)));
          if (job.closed) return wfReturn(job,"worker.js:performSearch:624:26:return",undefined);
          continue;
        }
        if (error.message !== "NY_CONNECTOR_RATE_LIMITED" || job.rateRetries >= 2) throw error;
        const delay = [5000, 15000][job.rateRetries++];
        job.retryNotBefore = Date.now() + delay;
        job.reloadAfterRateLimit = documentLimited;
        await wfAwait(job,"worker.js:performSearch:631:8:await",()=>(saveRuntime()));
        post(job, { id, progress: true, retrying: true });
        // Reload only an initial rate-limit document. Search/Verify retry on the
        // existing page so the single 401 retry budget cannot be reset.
      }
    }
    }
  } catch (error) {
    diagnostic("lookup-error", job, /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : error.name);
    if (repair.phase === "repairing") await wfAwait(job,"worker.js:performSearch:640:38:await",()=>(saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_FAILED" })));
    response = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : "NY_CONNECTOR_INCOMPLETE", ...(error.nvSequence?{nv_readiness:error.nvSequence}:{}) };
  }
  if (job.closed) return wfReturn(job,"worker.js:performSearch:643:18:return",undefined);
  // This optional local metadata is never forwarded or persisted as a reply
  // field; capture independently validates its command, age, URL and document.
  const preparedNvMetadata=response?.nv_snapshot_metadata;
  if(response&&Object.hasOwn(response,'nv_snapshot_metadata')) {
    const {nv_snapshot_metadata,...publicResponse}=response;response=publicResponse;
  }
  // NV positive searches need the observed detail, not an offscreen result
  // list. Reserve the original four-capture allowance for those detail pages.
  const nvPositiveSearch=P.TRIAL_ORIGIN&&job.registryState==='NV'&&query.operation==='search'
    &&response.ok===true&&response.evidence?.complete===true&&response.evidence.total>0
    &&Array.isArray(response.evidence.rows)&&response.evidence.rows.length>0;
  if(nvPositiveSearch)diagnostic('source-snapshot-phase',job,JSON.stringify({operation:'search',phase:'positive-search-detail-required'}));
  // AL verification replies are not completed public registry evidence.
  // Never take or forward a state screenshot of a verification challenge.
  const alCompletedSource=job.registryState!=='AL'||(response.evidence?.complete===true
    &&response.evidence.verification_pending===false
    &&P.sameQuery(response.evidence.query,{state:'AL',operation:'search',name:query.name}));
  // One original empty AL search is enough when paired with the full query
  // history. Preserve the existing four slots for records found by later names.
  const alEmptySource=job.registryState==='AL'&&alCompletedSource
    &&response.evidence.total===0&&Array.isArray(response.evidence.rows)&&response.evidence.rows.length===0;
  const alRepeatedEmpty=alEmptySource&&(job.alEmptySnapshotSaved===true||job.alFinalEmptyProtocol===true);
  const selectedDetailOnly=P.TRIAL_ORIGIN && (
    (job.registryState==='IL'&&!Object.hasOwn(query,'identifier')) ||
    (job.registryState==='NY'&&!Object.hasOwn(query,'orgID')) ||
    (job.registryState==='MS'&&query.operation==='search'));
  // Completed empty searches publish the actual names-searched report. Do not
  // spend a capture slot or attach a debugger to an empty source grid. A found
  // record (including Unregistered/Exempt), detail, or incomplete result keeps
  // the existing capture path. The source's complete/query/count proof is
  // required; an absent image or empty DOM is never proof of no registration.
  const completedEmptySearch=P.TRIAL_ORIGIN && response.ok===true
    && (query.operation==='search' || job.registryState==='GA'&&Object.hasOwn(query,'orgName'))
    && query.state===job.registryState && P.sameQuery(response.evidence?.query,query)
    && response.evidence?.complete===true && response.evidence.verification_pending!==true
    && response.evidence.total===0 && Array.isArray(response.evidence.rows)
    && response.evidence.rows.length===0;
  if(completedEmptySearch)diagnostic('source-snapshot-phase',job,JSON.stringify({operation:'search',phase:'completed-empty-history-only'}));
  if (response.ok && alCompletedSource && !alRepeatedEmpty && !nvPositiveSearch && !selectedDetailOnly && !completedEmptySearch && typeof captureStateSnapshot === 'function') {
    const preparedNc=job.ncProfileSnapshot;
    delete job.ncProfileSnapshot;
    const useNc=job.registryState==='NC' && query.operation==='detail' && preparedNc
      && preparedNc.commandId===id && preparedNc.generation===job.generation
      && P.sameQuery(preparedNc.query,query) && !job.closed && isActive(job)
      && job.pending===id && job.command?.id===id && Date.now()<job.activeExpiresAt;
    // A failed profile capture is not retried against the later filings page.
    const snapshot=useNc?preparedNc.snapshot:await wfAwait(job,"worker.js:performSearch:674:45:await",()=>(captureStateSnapshot(job,query,id,job.registryState==='AL'&&alCompletedSource&&Number.isInteger(response.evidence.total)&&response.evidence.total>0&&Array.isArray(response.evidence.rows)&&response.evidence.rows.length===response.evidence.total?{kind:'al-completed-record',command_id:id,query}:preparedNvMetadata)));
    if(snapshot){
      response.state_snapshot=snapshot;
      if(alEmptySource)job.alEmptySnapshotSaved=true;
    }
  }
  if (job.closed) return wfReturn(job,"worker.js:performSearch:680:18:return",undefined);
  job.pending = null;
  if (P.TRIAL_ORIGIN && job.registryState === "NY" && response.ok && !Object.hasOwn(query, "orgID")) {
    job.nyLastSearchQuery = {...query};
  }
  if(P.TRIAL_ORIGIN&&job.registryState==='NV'&&job.nvReadiness)response.nv_readiness={...job.nvReadiness,
    visibility_recovery:job.nvVisibilityOutcome||'not_requested',visibility_attempted:job.nvVisibilityAttempted===true,visibility_blocker:job.nvVisibilityBlocker||null,...response.nv_readiness};
  if(P.TRIAL_ORIGIN&&job.registryState==='NY')response.ny_diagnostics=P.nyDiagnostics(job.nyDiagnostics);
  if(P.TRIAL_ORIGIN&&job.registryState==='NY'&&['visible','hidden'].includes(job.nyPageVisibility))response.page_visibility=job.nyPageVisibility;
  if(P.TRIAL_ORIGIN&&job.registryState==='NY'&&!response.ok&&rejected(job.nyFailureCause)) {
    response.ny_failure_cause=job.nyFailureCause;
    response.ny_reset_cooldown=job.nyResetCooldown===true;
  }
  if(P.TRIAL_ORIGIN&&job.registryState==='NC'&&job.ncSubmissionObservations)response.nc_submission=job.ncSubmissionObservations;
  job.lastResponse = { id, ...response, ...(!response.ok && repair.nextAllowedAt > Date.now() ? { retryAt: repair.nextAllowedAt } : {}) };
  try { await wfAwait(job,"worker.js:performSearch:695:8:await",()=>(saveRuntime())); } catch { close(job, "NY_CONNECTOR_INTERRUPTED"); return wfReturn(job,"worker.js:performSearch:695:79:return",undefined); }
  post(job, job.lastResponse);
  if (!response.ok) close(job);
}
async function performRefresh(job, id) {
  if (job.closed) return wfReturn(job,"worker.js:performRefresh:700:18:return",undefined);
  if (job.refreshOnly && job.lastResponse?.id === id) { post(job, job.lastResponse); return wfReturn(job,"worker.js:performRefresh:701:85:return",undefined); }
  if (job.refreshOnly && job.pending === id) { post(job, { id, progress: true, reconnecting: true }); return wfReturn(job,"worker.js:performRefresh:702:102:return",undefined); }
  if (!isActive(job) || job.pending || !job.refreshOnly) { post(job, { id, ok: false, reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); return wfReturn(job,"worker.js:performRefresh:703:130:return",undefined); }
  job.command = { id, action: "refresh" };
  job.pending = id;
  let response;
  try {
    await wfAwait(job,"worker.js:performRefresh:708:4:await",()=>(saveRuntime()));
    // Requests already waiting when a repair finished share that operation.
    if (repair.phase === "verified" && job.enqueuedAt <= repair.finishedAt) {
      response = { ok: true, verified: true, verifiedAt: repair.finishedAt };
    } else {
      await wfAwait(job,"worker.js:performRefresh:713:6:await",()=>(repairConnection(job, id))); await wfAwait(job,"worker.js:performRefresh:713:39:await",()=>(ready(job)));
      const generation = job.generation;
      const checked = await wfAwait(job,"worker.js:performRefresh:715:22:await",()=>(chrome.tabs.sendMessage(job.tab, { action: "verify", id }, { frameId: 0 })));
      if (job.closed || generation !== job.generation) return wfReturn(job,"worker.js:performRefresh:716:55:return",undefined);
      response = checked?.ok && checked.evidence?.verified === true
        ? { ok: true, verified: true, verifiedAt: Date.now() }
        : { ok: false, reason: recoveryFailure(checked?.reason) };
      await wfAwait(job,"worker.js:performRefresh:720:6:await",()=>(recordRecovery(response)));
    }
  } catch (error) {
    diagnostic("lookup-error", job, /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : error.name);
    if (repair.phase === "repairing") await wfAwait(job,"worker.js:performRefresh:724:38:await",()=>(saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_FAILED" })));
    response = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : "NY_CONNECTOR_RECOVERY_FAILED" };
  }
  if (job.closed) return wfReturn(job,"worker.js:performRefresh:727:18:return",undefined);
  job.pending = null;
  job.lastResponse = { id, ...response, ...(!response.ok && repair.nextAllowedAt > Date.now() ? { retryAt: repair.nextAllowedAt } : {}) };
  try { await wfAwait(job,"worker.js:performRefresh:730:8:await",()=>(saveRuntime())); } catch { close(job, "NY_CONNECTOR_INTERRUPTED"); return wfReturn(job,"worker.js:performRefresh:730:79:return",undefined); }
  post(job, job.lastResponse);
  if (!response.ok) close(job);
}
chrome.tabs.onRemoved.addListener(id => {
  if (trialNyIdle?.id===id || trialNyIdle?.sourceTabId===id) {
    const saved=trialNyIdle;trialNyIdle=null;clearTimeout(trialNyIdleTimer);
    if(saved?.id!==id)removeOwned(saved.id).catch(()=>{});else owned.delete(id);
    saveRuntime().catch(()=>{});
  }
  if (trialTnIdle?.id===id || trialTnIdle?.sourceTabId===id) {
    const saved=trialTnIdle;trialTnIdle=null;clearTimeout(trialTnIdleTimer);
    if(saved?.id!==id)removeOwned(saved.id).catch(()=>{});else owned.delete(id);
    saveRuntime().catch(()=>{});
  }
  if (trialAlIdle?.id===id) {trialAlIdle=null;owned.delete(id);clearTimeout(trialAlIdleTimer);saveRuntime().catch(()=>{});}
  for (const job of allJobs()) {
    if (job && !job.closed && (job.tab === id || job.sender.tab.id === id)) close(job, "NY_CONNECTOR_BROWSER_CLOSED");
  }
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if(['tn-checkbox-permission','tn-checkbox-outcome','tn-checkbox-observation'].includes(message?.action)){
    boot.then(()=>registryTnCheckboxMessage(message,sender)).then(respond,()=>respond({allowed:false}));
    return true;
  }
  if(P.TRIAL_ORIGIN && message?.action==='nv-diagnostic') {
    if(sender.id!==chrome.runtime.id || sender.frameId!==0 || !P.validId(message.id)
        || !sender.url?.startsWith('https://orion.nv.gov/portal/public/'))return false;
    const job=allJobs().find(job=>isActive(job)&&!job.closed&&job.registryState==='NV'
      && job.tab===sender.tab?.id && owned.has(job.tab) && job.pending===message.id);
    const value=message.nv_diagnostic;
    const phases=['search-started','mode-selected','search-submitted','search-narrowed','page-collected',
      'pages-complete','search-returned','detail-started','detail-row-confirmed','detail-clicked',
      'detail-click-retried','detail-returned','filings-started','filings-incomplete','filings-first-page','filings-page-size-ready','filings-complete'];
    if(!job || !phases.includes(value?.phase))return false;
    const detail={visibility:['visible','hidden'].includes(value.visibility)?value.visibility:'unknown'};
    for(const key of ['page','pages','rows','total','on_search'])
      if(typeof value[key]==='boolean' || Number.isFinite(value[key]))detail[key]=value[key];
    registryNevadaDiagnostic(job,value.phase,detail);return false;
  }
  if(P.TRIAL_ORIGIN && message?.action==='ny-diagnostic') {
    if(sender.id!==chrome.runtime.id || sender.frameId!==0 || !nyRegistryPage(sender.url)
        || !P.validId(message.id))return false;
    const job=allJobs().find(job=>isActive(job)&&!job.closed&&job.registryState==='NY'
      && job.tab===sender.tab?.id && owned.has(job.tab) && job.pending===message.id);
    if(!job)return false;
    const entries=P.nyDiagnostics(message.ny_diagnostics).slice(-1);
    if(job.nyDiagnosticCommand!==message.id){job.nyDiagnosticCommand=message.id;job.nyDiagnosticCount=0;}
    if(entries.length && job.nyDiagnosticCount++<32)post(job,{id:message.id,progress:true,ny_diagnostics:entries});
    return false;
  }
  if (!allowedSender(sender) || !P.validId(message?.id) || message.action !== "ping") return false;
  boot.then(() => respond({ ok: true, version: chrome.runtime.getManifest().version, capabilities: ["lookup-tab-v1", "verification-retry-v1", "search-verification-retry-v1", "search-schema-errors-v1", "nullable-ein-v1", "queue-v1", "origin-window-v1", "connection-recovery-v1", "recovery-causes-v1", "cleanup-ack-v1", "timeout-recovery-v1", "resume-v1", "verified-detail-v1", "detail-navigation-v1", "il-ga-public-dom-v1", "ga-exempt-record-v1", "ga-legacy-rows-v1", "il-ga-complete-search-v2", "il-session-reuse-v1", "il-large-pages-v1", "il-dom-events-v1", "il-verification-visibility-v1", ...(P.TRIAL_ORIGIN ? ["final-four-public-v1","al-final-empty-v1"] : [])], recovery: { phase: repair.phase || "idle", nextAllowedAt: repair.nextAllowedAt || 0, verifiedAt: repair.finishedAt || 0 } }), () => respond({ ok: false, reason: "NY_CONNECTOR_INTERRUPTED" }));
  return true;
});
chrome.runtime.onConnect.addListener(port => {
  const resume = port.name.startsWith("cc-ny-resume-v1:");
  const registryState = port.name.startsWith("cc-il-lookup-v1:") ? "IL" : port.name.startsWith("cc-ga-lookup-v1:") ? "GA" : port.name.startsWith("cc-al-lookup-v1:") ? "AL" : port.name.startsWith("cc-nc-lookup-v1:") ? "NC" : port.name.startsWith("cc-nv-lookup-v1:") ? "NV" : port.name.startsWith("cc-tn-lookup-v1:") ? "TN" : port.name.startsWith("cc-nm-lookup-v1:") ? "NM" : port.name.startsWith("cc-ms-lookup-v1:") ? "MS" : "NY";
  if (!allowedSender(port.sender) || (!resume && !P.registryAllowed(registryState,new URL(port.sender.url).origin))) { port.disconnect(); return; }
  const prefix = registryState !== "NY" ? `cc-${registryState.toLowerCase()}-lookup-v1:` : resume ? "cc-ny-resume-v1:" : port.name.startsWith("cc-ny-refresh-v1:") ? "cc-ny-refresh-v1:" : "cc-ny-lookup-v1:";
  if (!allowedSender(port.sender) || !port.name.startsWith(prefix) || !P.validId(port.name.slice(prefix.length))) { port.disconnect(); return; }
  let disconnected = false;
  const bound = boot.then(async () => {
    if (disconnected) return null;
    const id = port.name.slice(prefix.length);
    let job = allJobs().find(j => j && !j.closed && j.lookupId === id);
    if (resume) {
      if (!job || !P.registryAllowed(job.registryState,new URL(port.sender.url).origin)
          || job.sender.tab.id !== port.sender.tab.id || (job.sender.documentId && job.sender.documentId !== port.sender.documentId)) {
        port.postMessage({ action: "closed", reason: "NY_CONNECTOR_INTERRUPTED" }); port.disconnect(); return null;
      }
      clearTimeout(job.reconnectTimer);
      const oldPort = job.port; job.port = port;
      if (oldPort && oldPort !== port) try { oldPort.disconnect(); } catch {}
      diagnostic("reconnected", job);
      await saveRuntime();
      if (job.closed) return null;
      const deadline = job.activeExpiresAt ?? job.expiresAt;
      if (Date.now() >= deadline) { close(job, job.activeExpiresAt ? "NY_CONNECTOR_TIMEOUT" : "NY_CONNECTOR_QUEUE_TIMEOUT"); return null; }
      if (job.registryState === "NY" && !job.lastResponse?.ok && repair.phase === "failed" && repair.nextAllowedAt > Date.now()) { close(job, repair.reason || "NY_CONNECTOR_RECOVERY_FAILED"); return null; }
      post(job, { action: "resumed" });
    } else {
      if (job) { port.postMessage({ action: "closed", reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); port.disconnect(); return null; }
      job = newJob(port.sender, id, prefix === "cc-ny-refresh-v1:", {registryState}); job.port = port;
      arm(job); queue.push(job); await saveRuntime();
    }
    notifyQueue(); pump(); return job;
  });
  bound.catch(() => { try { port.postMessage({ action: "closed", reason: "NY_CONNECTOR_INTERRUPTED" }); port.disconnect(); } catch {} });
  port.onDisconnect.addListener(() => {
    const detail = chrome.runtime.lastError?.message || "port-disconnected";
    disconnected = true;
    bound.then(job => {
      if (!job || job.closed || job.port !== port) return wfReturn(job,"worker.js:null:823:51:return",undefined);
      job.port = null; diagnostic("disconnected", job, detail);
      // Allow a hidden page to reconnect even if its timer is throttled. Neither
      // this grace nor a worker restart extends the original job deadline.
      awaitReconnect(job);
      saveRuntime().catch(() => close(job, "NY_CONNECTOR_INTERRUPTED"));
    }).catch(() => {});
  });
  port.onMessage.addListener(message => { bound.then(job => {
    if (!job || job.closed || job.port !== port) return wfReturn(job,"worker.js:null:832:49:return",undefined);
    if (message?.action === "resumed") { diagnostic("bridge-reconnected", job, message.disconnectReason || "port-disconnected"); saveRuntime().catch(() => {}); return wfReturn(job,"worker.js:null:833:160:return",undefined); }
    if (message?.action === "finish" && P.validId(message.id)) { close(job, null, message.id); return wfReturn(job,"worker.js:null:834:95:return",undefined); }
    if (message?.action === "acquire" && P.validId(message.id)) {
      job.acquireId = message.id;
      if(P.TRIAL_ORIGIN && job.registryState === "AL" && message.evidence_protocol === "al-final-empty-v1")job.alFinalEmptyProtocol=true;
      if(P.TRIAL_ORIGIN && !job.trialDisplay && message.display
          && [message.display.viewportWidth,message.display.outerWidth,message.display.outerHeight,
              message.display.chromeInsetTop].every(Number.isFinite)
          && message.display.viewportWidth>=320 && message.display.viewportWidth<=16384
          && message.display.outerWidth>=320 && message.display.outerWidth<=16384
          && message.display.outerHeight>=320 && message.display.outerHeight<=16384
          && message.display.chromeInsetTop>=0 && message.display.chromeInsetTop<=200)
        job.trialDisplay={...message.display};
      if (isActive(job)) saveRuntime().then(() => { if (!job.closed) post(job, { id: message.id, ok: true }); }).catch(() => close(job, "NY_CONNECTOR_INTERRUPTED")); else notifyQueue();
      return wfReturn(job,"worker.js:null:847:6:return",undefined);
    }
    if (message?.action === "capture_empty" && !job.refreshOnly)performAlFinalEmpty(job,message.query,message.id);
    if (message?.action === "search" && !job.refreshOnly && P.validId(message.id) && P.validQuery(message.query)) performSearch(job, message.query, message.id);
    if (message?.action === "refresh" && job.refreshOnly && P.validId(message.id)) performRefresh(job, message.id);
    // Heartbeats keep the transport alive without extending either deadline.
  }).catch(() => {}); });
});
