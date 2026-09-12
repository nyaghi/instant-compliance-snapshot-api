importScripts("protocol.js");
const P = CCNYProtocol;
let active = null;
const nap = ms => new Promise(resolve => setTimeout(resolve, ms));
function allowedSender(sender) {
  try { return sender.id === chrome.runtime.id && sender.frameId === 0 && new URL(sender.url).origin === P.STAGING && Number.isInteger(sender.tab?.id); }
  catch { return false; }
}
function post(job, message) { try { job.port.postMessage(message); } catch {} }
async function close(job, reason, finishId) {
  if (job.closed) return;
  job.closed = true;
  clearTimeout(job.timer);
  if (reason) post(job, { action: "closed", reason });
  if (job.tab !== null) await chrome.tabs.remove(job.tab).catch(() => {});
  // A different lookup cannot acquire the connector until cleanup finishes.
  if (active === job) active = null;
  if (finishId) post(job, { id: finishId, ok: true });
  try { job.port.disconnect(); } catch {}
  try {
    const origin = await chrome.tabs.get(job.sender.tab.id);
    if (new URL(origin.url).origin === P.STAGING) await chrome.tabs.update(origin.id, { active: true });
  } catch {}
}
async function performSearch(job, query, id) {
  if (job.closed) return;
  if (job.pending) { post(job, { id, ok: false, reason: "NY_CONNECTOR_BUSY" }); return; }
  job.pending = id;
  let response;
  try {
    if (job.tab === null) {
      const tab = await chrome.tabs.create({ url: P.NY + "/RegistrySearch", active: true });
      job.tab = tab.id;
      // The originating page may close while tabs.create is still pending.
      if (job.closed) { await chrome.tabs.remove(tab.id).catch(() => {}); return; }
    }
    const deadline = Date.now() + 15000;
    let ready = false;
    while (!job.closed && Date.now() < deadline) {
      try { ready = (await chrome.tabs.sendMessage(job.tab, { action: "ready" }, { frameId: 0 }))?.ready; }
      catch { /* The content script may not have loaded yet. */ }
      if (ready) break;
      await nap(250);
    }
    if (job.closed) return;
    if (!ready) throw new Error("NY_CONNECTOR_TIMEOUT");
    const current = await chrome.tabs.get(job.tab);
    const url = new URL(current.url);
    if (url.origin !== P.NY || !/^\/RegistrySearch\/?$/.test(url.pathname)) throw new Error("NY_CONNECTOR_INCOMPLETE");
    await chrome.tabs.update(job.tab, { active: true });
    response = await chrome.tabs.sendMessage(job.tab, { action: "search", id, query }, { frameId: 0 });
    if (!response?.ok || !P.sameQuery(response.evidence?.query, query)) response = { ok: false, reason: response?.reason || "NY_CONNECTOR_INCOMPLETE" };
  } catch (e) {
    response = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(e.message) ? e.message : "NY_CONNECTOR_INCOMPLETE" };
  }
  if (job.closed) return;
  job.pending = null;
  post(job, { id, ...response });
  if (!response.ok) await close(job);
  // Successful queries retain this lookup's tab for the master's name fallback.
}
chrome.tabs.onRemoved.addListener(id => {
  if (active && !active.closed && (active.tab === id || active.sender.tab.id === id)) close(active, "NY_CONNECTOR_BROWSER_CLOSED");
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (!allowedSender(sender) || !P.validId(message?.id) || message.action !== "ping") return false;
  respond({ ok: true, version: "0.1.4", capabilities: ["lookup-tab-v1", "verification-retry-v1", "search-verification-retry-v1", "search-schema-errors-v1"] });
  return false;
});
chrome.runtime.onConnect.addListener(port => {
  const prefix = "cc-ny-lookup-v1:";
  if (!allowedSender(port.sender) || !port.name.startsWith(prefix) || !P.validId(port.name.slice(prefix.length))) { port.disconnect(); return; }
  const job = { port, sender: port.sender, tab: null, pending: null, closed: false, timer: null };
  if (active) { post(job, { action: "closed", reason: "NY_CONNECTOR_BUSY" }); port.disconnect(); return; }
  active = job;
  // Same maximum lifetime as the master's continuation; heartbeats never extend it.
  job.timer = setTimeout(() => close(job, "NY_CONNECTOR_TIMEOUT"), 300000);
  port.onDisconnect.addListener(() => close(job, "NY_CONNECTOR_UNAVAILABLE"));
  port.onMessage.addListener(message => {
    if (job.closed || active !== job) return;
    if (message?.action === "finish" && P.validId(message.id)) { close(job, null, message.id); return; }
    if (message?.action === "search" && P.validId(message.id) && P.validQuery(message.query)) performSearch(job, message.query, message.id);
    // A heartbeat is transport activity only; it cannot run a query or reset expiry.
  });
});
