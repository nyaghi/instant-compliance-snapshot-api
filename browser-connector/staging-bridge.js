(() => {
  "use strict";
  const P = CCNYProtocol;
  if (location.origin !== P.STAGING || window !== window.top) return;
  let active = null;
  const reply = (id, response) => window.postMessage({ channel: "cc-ny-staging-v1", direction: "response", ...response, id }, P.STAGING);
  function dispose(job, reason = "NY_CONNECTOR_UNAVAILABLE") {
    if (job.closed) return;
    job.closed = true;
    clearInterval(job.heartbeat); clearTimeout(job.timer);
    for (const id of job.pending) reply(id, { ok: false, reason });
    job.pending.clear();
    try { job.port.disconnect(); } catch {}
    if (active === job) active = null;
  }
  function connect(lookupId) {
    const port = chrome.runtime.connect({ name: "cc-ny-lookup-v1:" + lookupId });
    const job = { port, lookupId, pending: new Set(), closed: false };
    active = job;
    port.onMessage.addListener(message => {
      if (job.closed) return;
      if (message?.action === "closed") { dispose(job, message.reason); return; }
      if (message?.progress && job.pending.has(message.id)) { reply(message.id, message); return; }
      if (job.pending.delete(message?.id)) reply(message.id, message);
    });
    port.onDisconnect.addListener(() => { void chrome.runtime.lastError; dispose(job); });
    // Messages keep MV3 alive only during this bounded lookup (Chrome 114+).
    job.heartbeat = setInterval(() => {
      try { port.postMessage({ action: "heartbeat" }); } catch { dispose(job); }
    }, 20000);
    job.timer = setTimeout(() => dispose(job, "NY_CONNECTOR_QUEUE_TIMEOUT"), 1500000);
    return job;
  }
  window.addEventListener("message", async event => {
    if (event.source !== window || event.origin !== P.STAGING) return;
    const m = event.data;
    if (m?.channel !== "cc-ny-staging-v1" || m.direction !== "request" || !P.validId(m.id)) return;
    if (m.action === "ping") {
      let response;
      try { response = await chrome.runtime.sendMessage({ action: "ping", id: m.id }); }
      catch { response = { ok: false, reason: "NY_CONNECTOR_UNAVAILABLE" }; }
      reply(m.id, response); return;
    }
    if (!P.validId(m.lookup_id)) return;
    if (m.action === "finish") {
      if (active?.lookupId === m.lookup_id) {
        active.pending.add(m.id);
        try { active.port.postMessage({ action: "finish", id: m.id }); }
        catch { dispose(active); }
        return;
      }
      reply(m.id, { ok: true }); return;
    }
    if (m.action !== "acquire" && (m.action !== "search" || !P.validQuery(m.query))) return;
    if (active && active.lookupId !== m.lookup_id) { reply(m.id, { ok: false, reason: "NY_CONNECTOR_BUSY" }); return; }
    try {
      const job = active || connect(m.lookup_id);
      job.pending.add(m.id);
      job.port.postMessage({ action: m.action, id: m.id, ...(m.query ? { query: m.query } : {}) });
    } catch {
      if (active) dispose(active);
      reply(m.id, { ok: false, reason: "NY_CONNECTOR_UNAVAILABLE" });
    }
  });
})();
