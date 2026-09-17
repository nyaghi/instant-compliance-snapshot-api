importScripts("protocol.js", "recovery.js");
const P = CCNYProtocol;
const QUEUE_TTL = 1200000, ACTIVE_TTL = 300000, PACE_MS = 3000;
const REPAIR_INTERVAL = 1200000;
let active = null, nextStart = 0, pumpTimer = null;
const queue = [];
let repair = {}, saving = Promise.resolve();
const owned = new Set();
const rejected = reason => ["NY_CONNECTOR_VERIFICATION_REJECTED", "NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED"].includes(reason);
const recoveryFailure = reason => rejected(reason) ? "NY_CONNECTOR_RECOVERY_REJECTED" :
  typeof reason === "string" && /^NY_CONNECTOR_[A-Z_]+$/.test(reason) ? reason : "NY_CONNECTOR_INCOMPLETE";
const runtimeState = () => ({ ownedTabs: [...owned], queue: [active, ...queue].filter(Boolean).map(j => ({ id: j.lookupId, tabId: j.sender.tab.id, enqueuedAt: j.enqueuedAt, expiresAt: j.expiresAt, active: j === active })) });
function saveRuntime() { const value = runtimeState(); saving = saving.catch(() => {}).then(() => chrome.storage.session.set({ ccnyRuntime: value })); return saving; }
async function saveRepair(value) { await chrome.storage.local.set({ ccnyRepair: value }); repair = value; }
async function removeOwned(tabId) {
  if (tabId === null || !owned.has(tabId)) return;
  owned.delete(tabId);
  try {
    const tab = await chrome.tabs.get(tabId), url = new URL(tab.url);
    if (url.origin === P.NY && /^\/RegistrySearch\/?$/.test(url.pathname)) await chrome.tabs.remove(tabId);
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
  for (const id of previous?.ownedTabs || []) if (Number.isInteger(id)) owned.add(id);
  for (const id of [...owned]) await removeOwned(id);
  if (repair.phase === "repairing") await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_INTERRUPTED" });
  await saveRuntime();
})();
// A failed initialization must fail requests explicitly, never reset the budget.
boot.catch(() => {});
const nap = ms => new Promise(resolve => setTimeout(resolve, ms));
function allowedSender(sender) {
  try { return sender.id === chrome.runtime.id && sender.frameId === 0 && new URL(sender.url).origin === P.STAGING && Number.isInteger(sender.tab?.id); }
  catch { return false; }
}
function post(job, message) { try { job.port.postMessage(message); } catch {} }
function notifyQueue() {
  queue.forEach((job, index) => {
    if (job.acquireId) post(job, { id: job.acquireId, progress: true, position: index + 1 });
  });
}
function pump() {
  if (active || pumpTimer || !queue.length) return;
  const delay = Math.max(0, nextStart - Date.now());
  if (delay) { pumpTimer = setTimeout(() => { pumpTimer = null; pump(); }, delay); return; }
  const job = queue.shift();
  if (job.closed) { pump(); return; }
  if (!job.refreshOnly && repair.phase === "failed" && repair.nextAllowedAt > Date.now()) {
    close(job, repair.reason || "NY_CONNECTOR_RECOVERY_REJECTED"); return;
  }
  active = job;
  clearTimeout(job.timer);
  job.timer = setTimeout(() => close(job, "NY_CONNECTOR_TIMEOUT"), ACTIVE_TTL);
  if (job.acquireId) post(job, { id: job.acquireId, ok: true });
  notifyQueue();
  saveRuntime().catch(() => close(job, "NY_CONNECTOR_INTERRUPTED"));
}
async function close(job, reason, finishId) {
  if (job.closed) return;
  job.closed = true;
  clearTimeout(job.timer);
  const index = queue.indexOf(job);
  if (index >= 0) queue.splice(index, 1);
  if (reason) post(job, { action: "closed", reason });
  // Await tab creation before handing the slot onward, including origin closure.
  let cleanupTimer;
  const cleanup = (async () => {
    if (job.creating) await job.creating.catch(() => {});
    const tabId = job.tab; job.tab = null;
    if (tabId !== null) await removeOwned(tabId);
  })();
  // Browser tab/storage acknowledgements can stall. Finish stays bounded;
  // any late cleanup still refers only to this job's own tab.
  try { await Promise.race([cleanup, new Promise(resolve => { cleanupTimer = setTimeout(resolve, 10000); })]); }
  catch { /* Closing a vanished tab must not strand other organizations. */ }
  finally { clearTimeout(cleanupTimer); }
  if (active === job) { active = null; nextStart = Date.now() + PACE_MS; }
  if (finishId) post(job, { id: finishId, ok: true });
  try { job.port.disconnect(); } catch {}
  notifyQueue();
  pump();
  saveRuntime().catch(() => {});
}
async function lookupTab(job) {
  if (job.tab !== null) return;
  job.creating = chrome.tabs.get(job.sender.tab.id).then(async origin => {
    if (job.closed) return;
    if (!Number.isInteger(origin.windowId) || origin.windowId < 0) throw new Error("NY_CONNECTOR_INCOMPLETE");
    const tab = await chrome.tabs.create({ windowId: origin.windowId, url: P.NY + "/RegistrySearch", active: false });
    job.tab = tab.id; owned.add(tab.id); await saveRuntime();
  });
  await job.creating; job.creating = null;
  // The content script's form check below is authoritative. Unrelated page
  // resources can keep Chrome in "loading" after the search form is usable.
}
async function repairConnection(job, id) {
  if (repair.nextAllowedAt > Date.now()) throw new Error("NY_CONNECTOR_RECOVERY_COOLDOWN");
  await lookupTab(job);
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
    if (error.message === "NY_CONNECTOR_RECOVERY_PAGE_OPEN") await saveRepair(previous);
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
    if (state?.ready) return;
    await nap(250);
  }
  throw new Error("NY_CONNECTOR_TAB_READY_TIMEOUT");
}
async function performSearch(job, query, id) {
  if (job.closed) return;
  if (active !== job || job.pending) { post(job, { id, ok: false, reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); return; }
  job.pending = id;
  let response;
  try {
    let repaired = false;
    for (;;) {
      if (job.closed) return;
      let documentLimited = false;
      try {
        await lookupTab(job);
        try { await ready(job); }
        catch (error) { documentLimited = error.message === "NY_CONNECTOR_RATE_LIMITED"; throw error; }
        const current = await chrome.tabs.get(job.tab), url = new URL(current.url);
        if (url.origin !== P.NY || !/^\/RegistrySearch\/?$/.test(url.pathname)) throw new Error("NY_CONNECTOR_INCOMPLETE");
        const generation = job.generation;
        response = await chrome.tabs.sendMessage(job.tab, { action: "search", id, query, verificationRetryUsed: job.verificationRetryUsed }, { frameId: 0 });
        if (job.closed || generation !== job.generation) return;
        job.verificationRetryUsed ||= response?.verificationRetryUsed === true;
        if (response?.reason === "NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT") throw new Error(response.reason);
        if (response?.reason === "NY_CONNECTOR_RATE_LIMITED") throw new Error(response.reason);
        if (!response?.ok || !P.sameQuery(response.evidence?.query, query)) response = { ok: false, reason: response?.reason || "NY_CONNECTOR_INCOMPLETE" };
        if (rejected(response.reason) && !repaired) {
          if (repair.nextAllowedAt > Date.now()) {
            await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_REJECTED" });
            response = { ok: false, reason: "NY_CONNECTOR_RECOVERY_REJECTED" }; break;
          }
          await repairConnection(job, id); repaired = true; continue;
        }
        if (repaired) {
          await recordRecovery(response);
          if (!response.ok && rejected(response.reason)) response.reason = "NY_CONNECTOR_RECOVERY_REJECTED";
        }
        break;
      } catch (error) {
        if (["NY_CONNECTOR_TAB_READY_TIMEOUT", "NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT"].includes(error.message) && job.timeoutRetries < 1) {
          job.timeoutRetries++;
          post(job, { id, progress: true, retrying: true });
          // Closing the owned tab cancels pending verification and isolates late
          // responses. Carry the used 401 budget across this timeout retry.
          const tabId = job.tab; job.tab = null; job.generation++;
          await removeOwned(tabId);
          if (job.closed) return;
          await nap(1000);
          continue;
        }
        if (error.message !== "NY_CONNECTOR_RATE_LIMITED" || job.rateRetries >= 2) throw error;
        const delay = [5000, 15000][job.rateRetries++];
        post(job, { id, progress: true, retrying: true });
        await nap(delay);
        if (job.closed) return;
        // Reload only an initial rate-limit document. Search/Verify retry on the
        // existing page so the single 401 retry budget cannot be reset.
        if (documentLimited) await chrome.tabs.update(job.tab, { url: P.NY + "/RegistrySearch" });
      }
    }
  } catch (error) {
    if (repair.phase === "repairing") await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_FAILED" });
    response = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : "NY_CONNECTOR_INCOMPLETE" };
  }
  if (job.closed) return;
  job.pending = null;
  post(job, { id, ...response, ...(!response.ok && repair.nextAllowedAt > Date.now() ? { retryAt: repair.nextAllowedAt } : {}) });
  if (!response.ok) close(job);
}
async function performRefresh(job, id) {
  if (job.closed) return;
  if (active !== job || job.pending || !job.refreshOnly) { post(job, { id, ok: false, reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); return; }
  job.pending = id;
  let response;
  try {
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
    if (repair.phase === "repairing") await saveRepair({ ...repair, phase: "failed", reason: "NY_CONNECTOR_RECOVERY_FAILED" });
    response = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : "NY_CONNECTOR_RECOVERY_FAILED" };
  }
  if (job.closed) return;
  job.pending = null; post(job, { id, ...response, ...(!response.ok && repair.nextAllowedAt > Date.now() ? { retryAt: repair.nextAllowedAt } : {}) });
  if (!response.ok) close(job);
}
chrome.tabs.onRemoved.addListener(id => {
  for (const job of [active, ...queue]) {
    if (job && !job.closed && (job.tab === id || job.sender.tab.id === id)) close(job, "NY_CONNECTOR_BROWSER_CLOSED");
  }
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (!allowedSender(sender) || !P.validId(message?.id) || message.action !== "ping") return false;
  boot.then(() => respond({ ok: true, version: "0.3.4", capabilities: ["lookup-tab-v1", "verification-retry-v1", "search-verification-retry-v1", "search-schema-errors-v1", "nullable-ein-v1", "queue-v1", "origin-window-v1", "connection-recovery-v1", "recovery-causes-v1", "cleanup-ack-v1", "timeout-recovery-v1"], recovery: { phase: repair.phase || "idle", nextAllowedAt: repair.nextAllowedAt || 0, verifiedAt: repair.finishedAt || 0 } }), () => respond({ ok: false, reason: "NY_CONNECTOR_INTERRUPTED" }));
  return true;
});
chrome.runtime.onConnect.addListener(port => {
  const prefix = port.name.startsWith("cc-ny-refresh-v1:") ? "cc-ny-refresh-v1:" : "cc-ny-lookup-v1:";
  if (!allowedSender(port.sender) || !port.name.startsWith(prefix) || !P.validId(port.name.slice(prefix.length))) { port.disconnect(); return; }
  const job = { port, sender: port.sender, lookupId: port.name.slice(prefix.length), refreshOnly: prefix === "cc-ny-refresh-v1:", enqueuedAt: Date.now(), expiresAt: Date.now() + QUEUE_TTL, generation: 0, tab: null, creating: null, pending: null, acquireId: null, closed: false, timer: null, rateRetries: 0, timeoutRetries: 0, verificationRetryUsed: false };
  job.timer = setTimeout(() => close(job, "NY_CONNECTOR_QUEUE_TIMEOUT"), QUEUE_TTL);
  port.onDisconnect.addListener(() => close(job, "NY_CONNECTOR_UNAVAILABLE"));
  port.onMessage.addListener(message => { boot.then(() => {
    if (job.closed) return;
    if (message?.action === "finish" && P.validId(message.id)) { close(job, null, message.id); return; }
    if (message?.action === "acquire" && P.validId(message.id) && !job.acquireId) {
      job.acquireId = message.id;
      if (active === job) post(job, { id: message.id, ok: true }); else notifyQueue();
      return;
    }
    if (message?.action === "search" && !job.refreshOnly && P.validId(message.id) && P.validQuery(message.query)) performSearch(job, message.query, message.id);
    if (message?.action === "refresh" && job.refreshOnly && P.validId(message.id)) performRefresh(job, message.id);
    // Heartbeats keep the transport alive without extending either deadline.
  }, () => close(job, "NY_CONNECTOR_INTERRUPTED")); });
  boot.then(() => {
    if (job.closed) return;
    queue.push(job); notifyQueue(); pump();
    saveRuntime().catch(() => close(job, "NY_CONNECTOR_INTERRUPTED"));
  }, () => close(job, "NY_CONNECTOR_INTERRUPTED"));
});
