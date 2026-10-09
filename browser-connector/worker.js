importScripts("protocol.js", "recovery.js", "registry-worker.js");
const P = CCNYProtocol;
const QUEUE_TTL = 1200000, ACTIVE_TTL = 300000, PACE_MS = 3000;
const REPAIR_INTERVAL = 1200000;
let active = null, nextStart = 0, pumpTimer = null;
// The approved connector retains its single lane. The isolated trial admits
// one job per registry, so a slow registry cannot strand a different state.
const activeLanes = new Map(), laneStarts = new Map();
const allJobs = () => [...(P.TRIAL_ORIGIN ? activeLanes.values() : [active]), ...queue].filter(Boolean);
const isActive = job => !!job && (P.TRIAL_ORIGIN ? activeLanes.get(job.registryState) === job : active === job);
const queue = [];
let repair = {}, saving = Promise.resolve();
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
  const at=Date.now(), summary=String(detail).slice(0,180);
  diagnostics.push({ at, type, id: job?.lookupId || "", phase: job?.pending ? "search" : isActive(job) ? "active" : "queued", detail: summary });
  if (diagnostics.length > 80) diagnostics.shift();
  if(P.TRIAL_ORIGIN && job && ["GA","MS"].includes(job.registryState)) {
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
const runtimeState = () => ({ schema: 2, nextStart, laneStarts: Object.fromEntries(laneStarts), ownedTabs: [...owned], diagnostics: [...diagnostics], queue: allJobs().filter(j => j && !j.closed).map(j => ({ id: j.lookupId, registryState: j.registryState || "NY", tabId: j.sender.tab.id, documentId: j.sender.documentId || "", enqueuedAt: j.enqueuedAt, expiresAt: j.expiresAt, active: isActive(j), activeExpiresAt: j.activeExpiresAt, tab: j.tab, refreshOnly: j.refreshOnly, generation: j.generation, rateRetries: j.rateRetries, timeoutRetries: j.timeoutRetries, detailRetryUsed: j.detailRetryUsed, detailAuthRetryUsed: j.detailAuthRetryUsed, nyLastSearchQuery: j.nyLastSearchQuery, nyDiagnostics: P.nyDiagnostics(j.nyDiagnostics), retryNotBefore: j.retryNotBefore, reloadAfterRateLimit: j.reloadAfterRateLimit, verificationRetryUsed: j.verificationRetryUsed, command: j.registryState === "AL" ? null : j.command, lastResponse: j.registryState === "AL" ? null : j.lastResponse, queryRepaired: j.queryRepaired, nyFreshPageRecoveryOnly: j.nyFreshPageRecoveryOnly, nvReturnRecoveryUsed: j.nvReturnRecoveryUsed, ...(P.TRIAL_ORIGIN && j.registryState === "NV" ? {nvVisibilityAttempted:j.nvVisibilityAttempted,nvDetailVisibilityChecked:j.nvDetailVisibilityChecked,nvPreviousVisible:j.nvPreviousVisible} : {}) })) });
function saveRuntime() {
  keepAlive();
  if (!allJobs().length && keepAliveTimer) { clearTimeout(keepAliveTimer); keepAliveTimer = null; }
  const value = runtimeState();
  if (P.TRIAL_ORIGIN && trialAlIdle) value.trialAlIdle=trialAlIdle;
  if (P.TRIAL_ORIGIN && trialTnIdle) value.trialTnIdle=trialTnIdle;
  if (P.TRIAL_ORIGIN && trialNyIdle) value.trialNyIdle=trialNyIdle;
  saving = saving.catch(() => {}).then(() => chrome.storage.session.set({ ccnyRuntime: value })); return saving;
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
async function removeOwned(tabId) {
  if (tabId === null || !owned.has(tabId)) return;
  owned.delete(tabId);
  try {
    const tab = await chrome.tabs.get(tabId), url = new URL(tab.url);
    const trialRegistry = P.TRIAL_ORIGIN && ((url.origin === "https://orion.nv.gov" && url.pathname === "/portal/public/")
      || (url.origin === "https://ago.igovsolution.net" && url.pathname === "/online/Lookups/Business.aspx")
      || (url.origin === "https://tncab.tnsos.gov" && url.pathname === "/portal/registered-charities-search")
      || (url.origin === "https://secure.nmdoj.gov" && /^\/CharitySearch\/(?:CharityDetail\.aspx|GenericError\.htm)?$/i.test(url.pathname))
      || (url.origin === "https://charities.sos.ms.gov" && url.pathname === "/online/portal/ch/page/charities-search/Portal.aspx")
      || (url.origin === "https://www.sosnc.gov" && /^\/online_services\/search\/(?:by_title\/search_charities|Charities_Results|charities_(?:profile|filings)\/\d+)$/.test(url.pathname)));
    if (trialRegistry || (["https://charitable.illinoisattorneygeneral.gov", "https://verify.sos.ga.gov"].includes(url.origin)) || url.origin === P.NY && /^\/RegistrySearch(?:\/[0-9]{2}-[0-9]{2}-[0-9]{2})?\/?$/.test(url.pathname)) await chrome.tabs.remove(tabId);
  } catch { /* The tab has already closed or was taken over by the user. */ }
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
  const idle=previous?.trialAlIdle;
  if (P.TRIAL_ORIGIN && Number.isInteger(idle?.id) && owned.has(idle.id) && Number.isFinite(idle.expiresAt)
      && Date.now()<idle.expiresAt && idle.expiresAt<=Date.now()+1800000 && !allJobs().some(j=>j?.tab===idle.id)) {
    try {const tab=await chrome.tabs.get(idle.id);if(tab.url===registryStart('AL')) {trialAlIdle=idle;armTrialAlIdle();}} catch {}
  }
  const tnIdle=previous?.trialTnIdle;
  if (P.TRIAL_ORIGIN && Number.isInteger(tnIdle?.id) && owned.has(tnIdle.id) && Number.isFinite(tnIdle.expiresAt)
      && Date.now()<tnIdle.expiresAt && tnIdle.expiresAt<=Date.now()+300000 && !allJobs().some(j=>j?.tab===tnIdle.id)) {
    try {
      const tab=await chrome.tabs.get(tnIdle.id),source=await chrome.tabs.get(tnIdle.sourceTabId);
      if(tab.url===registryStart('TN') && tab.windowId===tnIdle.windowId && source.windowId===(tnIdle.sourceWindowId??tnIdle.windowId)
          && new URL(source.url).origin===P.TRIAL_ORIGIN && await registryTennesseeOwnedWindow(tab,source)) {trialTnIdle=tnIdle;armTrialTnIdle();}
    } catch {}
  }
  const nyIdle=previous?.trialNyIdle;
  if(P.TRIAL_ORIGIN && Number.isInteger(nyIdle?.id) && owned.has(nyIdle.id) && Number.isFinite(nyIdle.expiresAt)
      && Date.now()<nyIdle.expiresAt && nyIdle.expiresAt<=Date.now()+300000 && !allJobs().some(j=>j?.tab===nyIdle.id)) {
    try {const tab=await chrome.tabs.get(nyIdle.id),source=await chrome.tabs.get(nyIdle.sourceTabId);
      if(nyRegistryPage(tab.url) && new URL(source.url).origin===P.TRIAL_ORIGIN){trialNyIdle=nyIdle;armTrialNyIdle();}
    } catch {}
  }
  for (const id of [...owned]) if (!allJobs().some(j => j?.tab === id) && trialAlIdle?.id!==id && trialTnIdle?.id!==id && trialNyIdle?.id!==id) await removeOwned(id);
  if (repair.phase === "repairing") await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_INTERRUPTED" });
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
  if(P.TRIAL_ORIGIN && ["GA","MS"].includes(job.registryState)
      && (message.action==="closed" || (typeof message.ok==="boolean" && !message.progress)))
    message={...message,trial_diagnostics:[...(job.trialDiagnostics||[])]};
  try { job.port.postMessage(message); } catch {}
}
function notifyQueue() {
  queue.forEach((job, index) => {
    if (job.acquireId) post(job, { id: job.acquireId, progress: true, position: index + 1 });
  });
}
function pump() {
  if (pumpTimer || !queue.length) return;
  const running=P.TRIAL_ORIGIN?activeLanes.size:Number(!!active);
  const cap=P.TRIAL_ORIGIN?8:1;
  if(running>=cap)return;
  let earliest=Infinity,index=-1;
  for(let i=0;i<queue.length;i++) {
    const job=queue[i];
    if(job.closed)continue;
    if(P.TRIAL_ORIGIN && activeLanes.has(job.registryState))continue;
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
  diagnostic('admitted',job,`${job.registryState} queue_ms=${Date.now()-job.enqueuedAt}`);
  // The isolated MS public grid can stall after several negative name probes.
  // Bound its complete collector lane; a partial search remains inconclusive.
  job.activeExpiresAt ??= Date.now()+(P.TRIAL_ORIGIN && job.registryState==='MS' ? 60000 : ACTIVE_TTL);
  arm(job);
  saveRuntime().then(()=>{
    if(job.closed)return;
    if(job.acquireId)post(job,{id:job.acquireId,ok:true});
    notifyQueue();pump();
  }).catch(()=>close(job,'NY_CONNECTOR_INTERRUPTED'));
}
async function close(job, reason, finishId) {
  if (job.closed) return;
  job.closed = true;
  clearTimeout(job.timer);
  clearTimeout(job.reconnectTimer);
  const index = queue.indexOf(job);
  if (index >= 0) queue.splice(index, 1);
  if (reason) post(job, { action: "closed", reason });
  // Await tab creation before handing the slot onward, including origin closure.
  let cleanupTimer;
  const cleanup = (async () => {
    if (job.creating) await job.creating.catch(() => {});
    if (P.TRIAL_ORIGIN && job.registryState==='NV') await registryRestoreNevadaVisibility(job);
    const tabId = job.tab; job.tab = null;
    if (tabId !== null && P.TRIAL_ORIGIN && job.registryState==='AL' && owned.has(tabId) && reason!=='NY_CONNECTOR_BROWSER_CLOSED') {
      try {
        const tab=await chrome.tabs.get(tabId),source=await chrome.tabs.get(job.sender.tab.id);
        if (tab.url===registryStart('AL') && new URL(source.url).origin===P.TRIAL_ORIGIN) {
          trialAlIdle={id:tabId,expiresAt:Date.now()+1800000};armTrialAlIdle();
        } else await removeOwned(tabId);
      } catch {await removeOwned(tabId);}
    } else if (tabId !== null && P.TRIAL_ORIGIN && job.registryState==='TN' && finishId && !reason
        && job.lastResponse?.ok===true && job.finalFourReusableForm && owned.has(tabId)) {
      try {
        const tab=await chrome.tabs.get(tabId),source=await chrome.tabs.get(job.sender.tab.id);
        if(tab.url===registryStart('TN') && new URL(source.url).origin===P.TRIAL_ORIGIN && await registryTennesseeOwnedWindow(tab,source)) {
          trialTnIdle={id:tabId,sourceTabId:source.id,sourceWindowId:source.windowId,windowId:tab.windowId,expiresAt:Date.now()+300000};armTrialTnIdle();
        } else await removeOwned(tabId);
      } catch {await removeOwned(tabId);}
    } else if(tabId!==null && P.TRIAL_ORIGIN && job.registryState==='NY' && finishId && !reason
        && job.lastResponse?.ok===true && !job.verificationRetryUsed && !job.queryRepaired
        && !job.nyFreshPageRecoveryOnly && owned.has(tabId)) {
      try {
        const tab=await chrome.tabs.get(tabId),source=await chrome.tabs.get(job.sender.tab.id);
        const expiresAt=job.nySessionExpiresAt || Date.now()+300000;
        if(nyRegistryPage(tab.url) && expiresAt>Date.now() && new URL(source.url).origin===P.TRIAL_ORIGIN) {
          trialNyIdle={id:tabId,sourceTabId:source.id,expiresAt};armTrialNyIdle();
        } else await removeOwned(tabId);
      } catch {await removeOwned(tabId);}
    } else if (tabId !== null) await removeOwned(tabId);
  })();
  // Browser tab/storage acknowledgements can stall. Finish stays bounded;
  // any late cleanup still refers only to this job's own tab.
  try { await Promise.race([cleanup, new Promise(resolve => { cleanupTimer = setTimeout(resolve, 10000); })]); }
  catch { /* Closing a vanished tab must not strand other organizations. */ }
  finally { clearTimeout(cleanupTimer); }
  if (isActive(job)) {
    if (P.TRIAL_ORIGIN) {activeLanes.delete(job.registryState);laneStarts.set(job.registryState,Date.now()+PACE_MS);}
    else {active=null;nextStart=Date.now()+PACE_MS;}
  }
  if (finishId) post(job, { id: finishId, ok: true });
  try { job.port.disconnect(); } catch {}
  notifyQueue();
  pump();
  saveRuntime().catch(() => {});
}
async function lookupTab(job) {
  if (job.tab !== null) return;
  if(P.TRIAL_ORIGIN && trialNyIdle) {
    const saved=trialNyIdle;trialNyIdle=null;clearTimeout(trialNyIdleTimer);
    try {
      const tab=await chrome.tabs.get(saved.id),source=await chrome.tabs.get(job.sender.tab.id);
      if(!job.refreshOnly && !job.closed && owned.has(saved.id) && saved.expiresAt>Date.now()
          && nyRegistryPage(tab.url) && new URL(source.url).origin===P.TRIAL_ORIGIN) {
        job.tab=saved.id;job.nySessionExpiresAt=saved.expiresAt;
        await registryExposeReusedNyTab(job,source);
        diagnostic('ny-session-reuse',job,'owned successful page; new query and evidence required');
      } else await removeOwned(saved.id);
    } catch {await removeOwned(saved.id);}
    await saveRuntime();
    if(job.tab!==null || job.closed)return;
  }
  job.creating = chrome.tabs.get(job.sender.tab.id).then(async origin => {
    if (job.closed) return;
    if (!Number.isInteger(origin.windowId) || origin.windowId < 0) throw new Error("NY_CONNECTOR_INCOMPLETE");
    await registryCreateOwnedTab(job,P.NY + "/RegistrySearch",origin);
  });
  await job.creating; job.creating = null;
  // The content script's form check below is authoritative. Unrelated page
  // resources can keep Chrome in "loading" after the search form is usable.
}
async function repairConnection(job, id) {
  if (repair.nextAllowedAt > Date.now()) throw new Error("NY_CONNECTOR_RECOVERY_COOLDOWN");
  await lookupTab(job);
  // A newly created tab can still expose about:blank while navigation commits.
  // Wait for its registry origin before attempting origin-scoped cleanup; the
  // form itself need not work for a manual connection refresh to be useful.
  const navigationDeadline = Math.min(Date.now() + 30000, job.activeExpiresAt);
  for (;;) {
    const tab = await chrome.tabs.get(job.tab);
    if (tab.url && new URL(tab.url).origin === P.NY && /^\/RegistrySearch\/?$/.test(new URL(tab.url).pathname)) break;
    if (tab.url && tab.url !== "about:blank") throw new Error("NY_CONNECTOR_INCOMPLETE");
    if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
    if (Date.now() >= navigationDeadline) throw new Error("NY_CONNECTOR_TAB_READY_TIMEOUT");
    await nap(100);
  }
  if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
  const previous = repair;
  await saveRepair({ phase: "repairing", attemptedAt: Date.now(), nextAllowedAt: Date.now() + REPAIR_INTERVAL });
  post(job, { id, progress: true, recovering: true });
  try {
    await CCNYRecovery.clearForTab(job.tab, [...owned], async () => {
      const tabId = job.tab; job.tab = null; job.generation++;
      await removeOwned(tabId);
    });
    if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
    await lookupTab(job);
  } catch (error) {
    if (error.message === "NY_CONNECTOR_RECOVERY_PAGE_OPEN") {
      await saveRepair(previous);
      // An open user registry page forbids origin cleanup. In the isolated
      // trial, retry once using a fresh owned form without changing cookies,
      // storage, the user's page, or the original lookup deadline.
      if (P.TRIAL_ORIGIN && !job.refreshOnly && !job.closed) {
        const tabId = job.tab; job.tab = null; job.generation++;
        await removeOwned(tabId);
        if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
        job.nyFreshPageRecoveryOnly = true;
        await lookupTab(job);
        return;
      }
    }
    else await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_FAILED" });
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
    try { state = await chrome.tabs.sendMessage(job.tab, { action: "ready" }, { frameId: 0 }); }
    catch { /* Content script is still loading. */ }
    if (state?.rateLimited) throw new Error("NY_CONNECTOR_RATE_LIMITED");
    if (state?.ready) { job.nyPageVisibility=state.page_visibility;return; }
    await nap(250);
  }
  throw new Error("NY_CONNECTOR_TAB_READY_TIMEOUT");
}
async function waitForRegistryDocument(job, path, previousDocument = "") {
  const deadline = Math.min(Date.now() + 10000, job.activeExpiresAt);
  while (!job.closed && Date.now() < deadline) {
    const tab = await chrome.tabs.get(job.tab);
    if (tab.url === P.NY + path) {
      try { const state = await chrome.tabs.sendMessage(job.tab, { action: "ready" }, { frameId: 0 });
        if (state?.ready && state.url === tab.url && (!previousDocument || state.documentId && state.documentId !== previousDocument)) return;
      } catch { /* The navigation's new content script is not ready yet. */ }
    }
    await nap(100);
  }
  throw new Error(job.closed ? "NY_CONNECTOR_INTERRUPTED" : "NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT");
}
async function openDetail(job, query) {
  let tab = await chrome.tabs.get(job.tab);
  const path = "/RegistrySearch/" + query.orgID;
  if (tab.url === P.NY + path) return;
  if (/^\/RegistrySearch\/[0-9]{2}-[0-9]{2}-[0-9]{2}\/?$/.test(new URL(tab.url).pathname)) {
    const returned = await chrome.tabs.sendMessage(job.tab, { action: "back-to-results" }, { frameId: 0 });
    if (!returned?.ok) throw new Error("NY_CONNECTOR_DETAIL_LINK_MISSING");
    await waitForRegistryDocument(job, "/RegistrySearch");
  }
  if (job.closed) throw new Error("NY_CONNECTOR_INTERRUPTED");
  const opened = await chrome.tabs.sendMessage(job.tab, { action: "open-detail", query }, { frameId: 0 });
  if (!opened?.ok) throw new Error(opened?.reason || "NY_CONNECTOR_DETAIL_LINK_MISSING");
  await waitForRegistryDocument(job, path);
}
async function prepareNySearchForm(job, query) {
  if (!P.TRIAL_ORIGIN || Object.hasOwn(query, "orgID")) return;
  const key=Object.keys(query)[0],tab=await chrome.tabs.get(job.tab);
  if (job.closed || Date.now()>=job.activeExpiresAt) throw new Error("NY_CONNECTOR_INTERRUPTED");
  const url=new URL(tab.url);
  if (!owned.has(tab.id) || url.origin!==P.NY || !/^\/RegistrySearch\/?$/.test(url.pathname)) throw new Error("NY_CONNECTOR_INCOMPLETE");
  const before=await chrome.tabs.sendMessage(tab.id,{action:"ready"},{frameId:0});
  job.nyPageVisibility=before?.page_visibility;
  if (!Array.isArray(before?.formFields) || !before.formFields.some(field=>field!==key)) return;
  if (!before.documentId) throw new Error("NY_CONNECTOR_SEARCH_FORM_CHANGED");
  // A fresh normal page resets the state's form model, unlike changing its
  // prior EIN input to an empty string. Do not reset cookies, retry allowances,
  // or the lookup deadline. Same-field searches retain the verified document.
  const current=await chrome.tabs.get(tab.id);
  if(job.closed || Date.now()>=job.activeExpiresAt)throw new Error("NY_CONNECTOR_INTERRUPTED");
  if(job.tab!==tab.id || !owned.has(tab.id) || current.url!==tab.url)throw new Error("NY_CONNECTOR_SEARCH_FORM_CHANGED");
  await chrome.tabs.reload(tab.id);job.generation++;
  await waitForRegistryDocument(job,url.pathname,before.documentId);
  if (job.closed || Date.now()>=job.activeExpiresAt) throw new Error("NY_CONNECTOR_INTERRUPTED");
  const after=await chrome.tabs.sendMessage(tab.id,{action:"ready"},{frameId:0});
  job.nyPageVisibility=after?.page_visibility;
  if (after?.formFields?.some(field=>field!==key)) throw new Error("NY_CONNECTOR_SEARCH_FORM_CHANGED");
  diagnostic("ny-form-transition",job,"new normal document for a different search field");
  await saveRuntime();
}
async function performSearch(job, query, id) {
  if (job.closed) return;
  if (job.command?.id === id && !P.sameQuery(job.command.query, query)) { post(job, { id, ok: false, reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); return; }
  if (job.lastResponse?.id === id && P.sameQuery(job.command?.query, query)) { post(job, job.lastResponse); return; }
  if (job.pending === id && P.sameQuery(job.command?.query, query)) { post(job, { id, progress: true, reconnecting: true }); return; }
  if (!isActive(job) || job.pending) { post(job, { id, ok: false, reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); return; }
  if (job.command?.id !== id) { job.queryRepaired = false; job.lastResponse = null; }
  job.command = { id, query };
  job.pending = id;
  let response;
  try {
    await saveRuntime();
    if (job.registryState !== "NY") {
      response = await performRegistryQuery(job, query);
    } else {
    let repaired = job.queryRepaired;
    for (;;) {
      if (job.retryNotBefore > Date.now()) await nap(job.retryNotBefore - Date.now());
      if (job.closed) return;
      if (job.reloadAfterRateLimit) {
        await chrome.tabs.update(job.tab, { url: P.NY + "/RegistrySearch" });
        job.reloadAfterRateLimit = false; await saveRuntime();
      }
      let documentLimited = false;
      try {
        if(P.TRIAL_ORIGIN)post(job,{id,progress:true,ny_phase:"opening_page"});
        await lookupTab(job);
        if(P.TRIAL_ORIGIN)post(job,{id,progress:true,ny_phase:"waiting_for_form"});
        try { await ready(job); }
        catch (error) { documentLimited = error.message === "NY_CONNECTOR_RATE_LIMITED"; throw error; }
        const current = await chrome.tabs.get(job.tab), url = new URL(current.url);
        if (url.origin !== P.NY || !/^\/RegistrySearch(?:\/[0-9]{2}-[0-9]{2}-[0-9]{2})?\/?$/.test(url.pathname)) throw new Error("NY_CONNECTOR_INCOMPLETE");
        if (Object.hasOwn(query, "orgID")) await openDetail(job, query);
        else if(P.TRIAL_ORIGIN && /^\/RegistrySearch\/[0-9]{2}-[0-9]{2}-[0-9]{2}\/?$/.test(url.pathname)) {
          // Navigate before delivering the next command: full-page Back would
          // otherwise destroy the content relay waiting to return its result.
          const returned=await chrome.tabs.sendMessage(job.tab,{action:'back-to-results'},{frameId:0});
          if(!returned?.ok)throw new Error('NY_CONNECTOR_RETURN_FORM_TIMEOUT');
          await waitForRegistryDocument(job,'/RegistrySearch');
        }
        if(P.TRIAL_ORIGIN)post(job,{id,progress:true,ny_phase:"preparing_query"});
        await prepareNySearchForm(job,query);
        if (job.closed) return;
        const generation = job.generation;
        // Stable across reconnection, distinct for an already permitted retry.
        const attempt = `${job.generation}:${job.rateRetries}`;
        if(P.TRIAL_ORIGIN)post(job,{id,progress:true,ny_phase:"query_sent"});
        response = await chrome.tabs.sendMessage(job.tab, { action: "search", id, attempt, query, verificationRetryUsed: job.verificationRetryUsed }, { frameId: 0 });
        if (job.closed || generation !== job.generation) return;
        collectNyDiagnostics(job,response);
        job.verificationRetryUsed ||= response?.verificationRetryUsed === true;
        await saveRuntime();
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
          await saveRuntime();
          const returned = await chrome.tabs.sendMessage(job.tab, {action:"back-to-results"}, {frameId:0});
          if (!returned?.ok) break;
          await waitForRegistryDocument(job, "/RegistrySearch");
          if (job.closed || Date.now() >= job.activeExpiresAt) return;
          const formTab = job.tab;
          const priorForm = await chrome.tabs.sendMessage(formTab, {action:"ready"}, {frameId:0});
          if (job.closed || job.tab !== formTab || !owned.has(formTab) || Date.now() >= job.activeExpiresAt) return;
          if (!priorForm?.documentId) throw new Error("NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT");
          await chrome.tabs.reload(formTab);
          await waitForRegistryDocument(job, "/RegistrySearch", priorForm.documentId);
          if (job.closed || Date.now() >= job.activeExpiresAt) return;
          const verified = await chrome.tabs.sendMessage(job.tab, {action:"verify", id,
            attempt:`${attempt}:detail-auth`, verificationRetryUsed:true}, {frameId:0});
          if (job.closed || generation !== job.generation) return;
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
          const restored = await chrome.tabs.sendMessage(job.tab, {action:"search", id,
            attempt:`${attempt}:detail-results`, query:job.nyLastSearchQuery,
            verificationRetryUsed:true}, {frameId:0});
          if (job.closed || generation !== job.generation) return;
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
            await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_REJECTED" });
            response = { ok: false, reason: "NY_CONNECTOR_RECOVERY_REJECTED" }; break;
          }
          job.queryRepaired = true; await saveRuntime();
          await repairConnection(job, id); repaired = true; continue;
        }
        if (repaired && !job.nyFreshPageRecoveryOnly) {
          await recordRecovery(response);
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
          const tab = await chrome.tabs.get(job.tab);
          const previous = await chrome.tabs.sendMessage(job.tab, { action: "ready" }, { frameId: 0 });
          if (tab.url !== P.NY + path || !previous?.documentId) throw error;
          job.detailRetryUsed = true; job.generation++;
          await saveRuntime(); post(job, { id, progress: true, retrying: true });
          await chrome.tabs.reload(job.tab);
          await waitForRegistryDocument(job, path, previous.documentId);
          continue;
        }
        if (["NY_CONNECTOR_TAB_READY_TIMEOUT", "NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT", "NY_CONNECTOR_SEARCH_RESPONSE_TIMEOUT"].includes(error.message) && job.timeoutRetries < 1) {
          job.timeoutRetries++;
          job.retryNotBefore = Date.now() + 1000;
          post(job, { id, progress: true, retrying: true });
          // Closing the owned tab cancels pending verification and isolates late
          // responses. Carry the used 401 budget across this timeout retry.
          const tabId = job.tab; job.tab = null; job.generation++;
          await removeOwned(tabId);
          if (job.closed) return;
          continue;
        }
        if (error.message !== "NY_CONNECTOR_RATE_LIMITED" || job.rateRetries >= 2) throw error;
        const delay = [5000, 15000][job.rateRetries++];
        job.retryNotBefore = Date.now() + delay;
        job.reloadAfterRateLimit = documentLimited;
        await saveRuntime();
        post(job, { id, progress: true, retrying: true });
        // Reload only an initial rate-limit document. Search/Verify retry on the
        // existing page so the single 401 retry budget cannot be reset.
      }
    }
    }
  } catch (error) {
    diagnostic("lookup-error", job, /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : error.name);
    if (repair.phase === "repairing") await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_FAILED" });
    response = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : "NY_CONNECTOR_INCOMPLETE" };
  }
  if (job.closed) return;
  job.pending = null;
  if (P.TRIAL_ORIGIN && job.registryState === "NY" && response.ok && !Object.hasOwn(query, "orgID")) {
    job.nyLastSearchQuery = {...query};
  }
  if(P.TRIAL_ORIGIN&&job.registryState==='NV'&&job.nvReadiness)response.nv_readiness={...job.nvReadiness,
    visibility_recovery:job.nvVisibilityOutcome||'not_requested',visibility_attempted:job.nvVisibilityAttempted===true};
  if(P.TRIAL_ORIGIN&&job.registryState==='NY')response.ny_diagnostics=P.nyDiagnostics(job.nyDiagnostics);
  if(P.TRIAL_ORIGIN&&job.registryState==='NY'&&['visible','hidden'].includes(job.nyPageVisibility))response.page_visibility=job.nyPageVisibility;
  if(P.TRIAL_ORIGIN&&job.registryState==='NY'&&!response.ok&&rejected(job.nyFailureCause)) {
    response.ny_failure_cause=job.nyFailureCause;
    response.ny_reset_cooldown=job.nyResetCooldown===true;
  }
  if(P.TRIAL_ORIGIN&&job.registryState==='NC'&&job.ncSubmissionObservations)response.nc_submission=job.ncSubmissionObservations;
  job.lastResponse = { id, ...response, ...(!response.ok && repair.nextAllowedAt > Date.now() ? { retryAt: repair.nextAllowedAt } : {}) };
  try { await saveRuntime(); } catch { close(job, "NY_CONNECTOR_INTERRUPTED"); return; }
  post(job, job.lastResponse);
  if (!response.ok) close(job);
}
async function performRefresh(job, id) {
  if (job.closed) return;
  if (job.refreshOnly && job.lastResponse?.id === id) { post(job, job.lastResponse); return; }
  if (job.refreshOnly && job.pending === id) { post(job, { id, progress: true, reconnecting: true }); return; }
  if (!isActive(job) || job.pending || !job.refreshOnly) { post(job, { id, ok: false, reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); return; }
  job.command = { id, action: "refresh" };
  job.pending = id;
  let response;
  try {
    await saveRuntime();
    // Requests already waiting when a repair finished share that operation.
    if (repair.phase === "verified" && job.enqueuedAt <= repair.finishedAt) {
      response = { ok: true, verified: true, verifiedAt: repair.finishedAt };
    } else {
      await repairConnection(job, id); await ready(job);
      const generation = job.generation;
      const checked = await chrome.tabs.sendMessage(job.tab, { action: "verify", id }, { frameId: 0 });
      if (job.closed || generation !== job.generation) return;
      response = checked?.ok && checked.evidence?.verified === true
        ? { ok: true, verified: true, verifiedAt: Date.now() }
        : { ok: false, reason: recoveryFailure(checked?.reason) };
      await recordRecovery(response);
    }
  } catch (error) {
    diagnostic("lookup-error", job, /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : error.name);
    if (repair.phase === "repairing") await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_FAILED" });
    response = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : "NY_CONNECTOR_RECOVERY_FAILED" };
  }
  if (job.closed) return;
  job.pending = null;
  job.lastResponse = { id, ...response, ...(!response.ok && repair.nextAllowedAt > Date.now() ? { retryAt: repair.nextAllowedAt } : {}) };
  try { await saveRuntime(); } catch { close(job, "NY_CONNECTOR_INTERRUPTED"); return; }
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
  boot.then(() => respond({ ok: true, version: chrome.runtime.getManifest().version, capabilities: ["lookup-tab-v1", "verification-retry-v1", "search-verification-retry-v1", "search-schema-errors-v1", "nullable-ein-v1", "queue-v1", "origin-window-v1", "connection-recovery-v1", "recovery-causes-v1", "cleanup-ack-v1", "timeout-recovery-v1", "resume-v1", "verified-detail-v1", "detail-navigation-v1", "il-ga-public-dom-v1", "ga-exempt-record-v1", "ga-legacy-rows-v1", "il-ga-complete-search-v2", "il-session-reuse-v1", "il-large-pages-v1", "il-dom-events-v1", "il-verification-visibility-v1", ...(P.TRIAL_ORIGIN ? ["final-four-public-v1"] : [])], recovery: { phase: repair.phase || "idle", nextAllowedAt: repair.nextAllowedAt || 0, verifiedAt: repair.finishedAt || 0 } }), () => respond({ ok: false, reason: "NY_CONNECTOR_INTERRUPTED" }));
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
      if (!job || job.closed || job.port !== port) return;
      job.port = null; diagnostic("disconnected", job, detail);
      // Allow a hidden page to reconnect even if its timer is throttled. Neither
      // this grace nor a worker restart extends the original job deadline.
      awaitReconnect(job);
      saveRuntime().catch(() => close(job, "NY_CONNECTOR_INTERRUPTED"));
    }).catch(() => {});
  });
  port.onMessage.addListener(message => { bound.then(job => {
    if (!job || job.closed || job.port !== port) return;
    if (message?.action === "resumed") { diagnostic("bridge-reconnected", job, message.disconnectReason || "port-disconnected"); saveRuntime().catch(() => {}); return; }
    if (message?.action === "finish" && P.validId(message.id)) { close(job, null, message.id); return; }
    if (message?.action === "acquire" && P.validId(message.id)) {
      job.acquireId = message.id;
      if (isActive(job)) saveRuntime().then(() => { if (!job.closed) post(job, { id: message.id, ok: true }); }).catch(() => close(job, "NY_CONNECTOR_INTERRUPTED")); else notifyQueue();
      return;
    }
    if (message?.action === "search" && !job.refreshOnly && P.validId(message.id) && P.validQuery(message.query)) performSearch(job, message.query, message.id);
    if (message?.action === "refresh" && job.refreshOnly && P.validId(message.id)) performRefresh(job, message.id);
    // Heartbeats keep the transport alive without extending either deadline.
  }).catch(() => {}); });
});
