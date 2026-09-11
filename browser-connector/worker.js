importScripts("protocol.js");
const P = CCNYProtocol;
let active = null;
const nap = ms => new Promise(resolve => setTimeout(resolve, ms));
function allowedSender(sender) {
  try { return sender.id === chrome.runtime.id && sender.frameId === 0 && new URL(sender.url).origin === P.STAGING && Number.isInteger(sender.tab?.id); }
  catch { return false; }
}
async function performSearch(query, id, sender) {
  if (active) return { ok: false, reason: "NY_CONNECTOR_BUSY" };
  const job = { id, tab: null, closed: false }; active = job;
  try {
    const tab = await chrome.tabs.create({ url: P.NY + "/RegistrySearch", active: true });
    job.tab = tab.id;
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      if (job.closed) throw new Error("NY_CONNECTOR_BROWSER_CLOSED");
      try {
        const ready = await chrome.tabs.sendMessage(job.tab, { action: "ready" }, { frameId: 0 });
        if (ready?.ready) break;
      } catch { /* The content script may not have loaded yet. */ }
      await nap(250);
    }
    if (job.closed) throw new Error("NY_CONNECTOR_BROWSER_CLOSED");
    const current = await chrome.tabs.get(job.tab);
    if (new URL(current.url).origin !== P.NY) throw new Error("NY_CONNECTOR_INCOMPLETE");
    const response = await chrome.tabs.sendMessage(job.tab, { action: "search", id, query }, { frameId: 0 });
    if (!response?.ok || !P.sameQuery(response.evidence?.query, query)) return { ok: false, reason: response?.reason || "NY_CONNECTOR_INCOMPLETE" };
    return response;
  } catch (e) {
    return { ok: false, reason: job.closed ? "NY_CONNECTOR_BROWSER_CLOSED" : /^NY_CONNECTOR_[A-Z_]+$/.test(e.message) ? e.message : "NY_CONNECTOR_INCOMPLETE" };
  } finally {
    if (job.tab !== null && !job.closed) await chrome.tabs.remove(job.tab).catch(() => {});
    if (active === job) active = null;
    // Returning focus is limited to the same still-open originating staging tab.
    try { const origin = await chrome.tabs.get(sender.tab.id); if (new URL(origin.url).origin === P.STAGING) await chrome.tabs.update(origin.id, { active: true }); } catch {}
  }
}
chrome.tabs.onRemoved.addListener(id => { if (active?.tab === id) active.closed = true; });
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (!allowedSender(sender) || !P.validId(message?.id)) return false;
  if (message.action === "ping") { respond({ ok: true, version: "0.1.0" }); return false; }
  if (message.action !== "search" || !P.validQuery(message.query)) return false;
  performSearch(message.query, message.id, sender).then(respond);
  return true;
});
