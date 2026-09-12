importScripts("protocol.js");
const P = CCNYProtocol;
const QUEUE_TTL = 1200000, ACTIVE_TTL = 300000, PACE_MS = 3000;
let active = null, nextStart = 0, pumpTimer = null;
const queue = [];
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
  active = job;
  clearTimeout(job.timer);
  job.timer = setTimeout(() => close(job, "NY_CONNECTOR_TIMEOUT"), ACTIVE_TTL);
  if (job.acquireId) post(job, { id: job.acquireId, ok: true });
  notifyQueue();
}
async function close(job, reason, finishId) {
  if (job.closed) return;
  job.closed = true;
  clearTimeout(job.timer);
  const index = queue.indexOf(job);
  if (index >= 0) queue.splice(index, 1);
  if (reason) post(job, { action: "closed", reason });
  // Await tab creation before handing the slot onward, including origin closure.
  if (job.creating) await job.creating.catch(() => {});
  if (job.tab !== null) await chrome.tabs.remove(job.tab).catch(() => {});
  if (active === job) { active = null; nextStart = Date.now() + PACE_MS; }
  if (finishId) post(job, { id: finishId, ok: true });
  try { job.port.disconnect(); } catch {}
  notifyQueue();
  pump();
}
async function ready(job) {
  const deadline = Date.now() + 15000;
  while (!job.closed && Date.now() < deadline) {
    let state;
    try { state = await chrome.tabs.sendMessage(job.tab, { action: "ready" }, { frameId: 0 }); }
    catch { /* Content script is still loading. */ }
    if (state?.rateLimited) throw new Error("NY_CONNECTOR_RATE_LIMITED");
    if (state?.ready) return;
    await nap(250);
  }
  throw new Error("NY_CONNECTOR_TIMEOUT");
}
async function performSearch(job, query, id) {
  if (job.closed) return;
  if (active !== job || job.pending) { post(job, { id, ok: false, reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); return; }
  job.pending = id;
  let response;
  try {
    if (job.tab === null) {
      // Resolve the origin when its queued turn starts, including a moved tab.
      // Never fall back to Chrome's last-focused window (the user's work).
      job.creating = chrome.tabs.get(job.sender.tab.id).then(origin => {
        if (job.closed) return;
        if (!Number.isInteger(origin.windowId) || origin.windowId < 0) throw new Error("NY_CONNECTOR_INCOMPLETE");
        return chrome.tabs.create({ windowId: origin.windowId, url: P.NY + "/RegistrySearch", active: true })
          .then(tab => { job.tab = tab.id; });
      });
      await job.creating;
      job.creating = null;
    }
    for (;;) {
      if (job.closed) return;
      let documentLimited = false;
      try {
        try { await ready(job); }
        catch (error) { documentLimited = error.message === "NY_CONNECTOR_RATE_LIMITED"; throw error; }
        const current = await chrome.tabs.get(job.tab), url = new URL(current.url);
        if (url.origin !== P.NY || !/^\/RegistrySearch\/?$/.test(url.pathname)) throw new Error("NY_CONNECTOR_INCOMPLETE");
        await chrome.tabs.update(job.tab, { active: true });
        response = await chrome.tabs.sendMessage(job.tab, { action: "search", id, query }, { frameId: 0 });
        if (response?.reason === "NY_CONNECTOR_RATE_LIMITED") throw new Error(response.reason);
        if (!response?.ok || !P.sameQuery(response.evidence?.query, query)) response = { ok: false, reason: response?.reason || "NY_CONNECTOR_INCOMPLETE" };
        break;
      } catch (error) {
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
    response = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(error.message) ? error.message : "NY_CONNECTOR_INCOMPLETE" };
  }
  if (job.closed) return;
  job.pending = null;
  post(job, { id, ...response });
  if (!response.ok) close(job);
}
chrome.tabs.onRemoved.addListener(id => {
  for (const job of [active, ...queue]) {
    if (job && !job.closed && (job.tab === id || job.sender.tab.id === id)) close(job, "NY_CONNECTOR_BROWSER_CLOSED");
  }
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (!allowedSender(sender) || !P.validId(message?.id) || message.action !== "ping") return false;
  respond({ ok: true, version: "0.2.1", capabilities: ["lookup-tab-v1", "verification-retry-v1", "search-verification-retry-v1", "search-schema-errors-v1", "nullable-ein-v1", "queue-v1", "origin-window-v1"] });
  return false;
});
chrome.runtime.onConnect.addListener(port => {
  const prefix = "cc-ny-lookup-v1:";
  if (!allowedSender(port.sender) || !port.name.startsWith(prefix) || !P.validId(port.name.slice(prefix.length))) { port.disconnect(); return; }
  const job = { port, sender: port.sender, tab: null, creating: null, pending: null, acquireId: null, closed: false, timer: null, rateRetries: 0 };
  job.timer = setTimeout(() => close(job, "NY_CONNECTOR_QUEUE_TIMEOUT"), QUEUE_TTL);
  port.onDisconnect.addListener(() => close(job, "NY_CONNECTOR_UNAVAILABLE"));
  port.onMessage.addListener(message => {
    if (job.closed) return;
    if (message?.action === "finish" && P.validId(message.id)) { close(job, null, message.id); return; }
    if (message?.action === "acquire" && P.validId(message.id) && !job.acquireId) {
      job.acquireId = message.id;
      if (active === job) post(job, { id: message.id, ok: true }); else notifyQueue();
      return;
    }
    if (message?.action === "search" && P.validId(message.id) && P.validQuery(message.query)) performSearch(job, message.query, message.id);
    // Heartbeats keep the transport alive without extending either deadline.
  });
  queue.push(job);
  notifyQueue();
  pump();
});
