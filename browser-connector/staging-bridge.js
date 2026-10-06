(() => {
  "use strict";
  const P = CCNYProtocol;
  const ORIGIN = location.origin;
  if (!P.allowedOrigin(ORIGIN) || window !== window.top) return;
  // Read only the current display's usable rectangle, not browsing/session data.
  // A small application window must not disable the isolated collector layout.
  if (P.TRIAL_ORIGIN === ORIGIN) chrome.runtime.onMessage?.addListener((m, sender, respond) => {
    if (m?.action !== 'trial-collector-display' || sender.id !== chrome.runtime.id || sender.tab) return;
    const s = window.screen;
    respond({left:s.availLeft,top:s.availTop,width:s.availWidth,height:s.availHeight});
  });
  let singleActive = null;
  const trialJobs = new Map();
  const reply = (id, response) => window.postMessage({ channel: "cc-ny-staging-v1", direction: "response", ...response, id }, ORIGIN);
  function dispose(job, reason = "NY_CONNECTOR_INTERRUPTED") {
    if (job.closed) return;
    job.closed = true;
    clearInterval(job.heartbeat); clearTimeout(job.timer);
    clearTimeout(job.reconnectTimer);
    for (const id of job.pending.keys()) reply(id, { ok: false, reason });
    job.pending.clear();
    try { job.port.disconnect(); } catch {}
    if(P.TRIAL_ORIGIN) {if(trialJobs.get(job.lookupId)===job)trialJobs.delete(job.lookupId);}
    else if (singleActive === job) singleActive = null;
  }
  function reopen(job) {
    if (job.closed || job.reconnecting) return;
    if (job.finishId && job.pending.has(job.finishId)) {
      const id = job.finishId; job.pending.delete(id); dispose(job); reply(id, { ok: true }); return;
    }
    if (++job.reconnects > 3) { dispose(job); return; }
    job.reconnecting = true;
    for (const id of job.pending.keys()) reply(id, { progress: true, reconnecting: true });
    const retry = () => {
      if (job.closed) return;
      try { openPort(job, true); }
      catch { job.reconnecting = false; reopen(job); }
    };
    if (job.reconnects === 1) retry(); else job.reconnectTimer = setTimeout(retry, 1000 * job.reconnects);
  }
  function openPort(job, resume = false) {
    const port = chrome.runtime.connect({ name: (resume ? "cc-ny-resume-v1:" : job.refreshOnly ? "cc-ny-refresh-v1:" : ["IL","GA","AL","NC","NV","TN","NM","MS"].includes(job.registryState) ? `cc-${job.registryState.toLowerCase()}-lookup-v1:` : "cc-ny-lookup-v1:") + job.lookupId });
    job.port = port;
    port.onMessage.addListener(message => {
      if (job.closed || job.port !== port) return;
      if (message?.action === "resumed") {
        clearTimeout(job.reconnectTimer);
        job.reconnecting = false;
        port.postMessage({ action: "resumed", disconnectReason: job.disconnectReason });
        for (const request of job.pending.values()) port.postMessage(request);
        return;
      }
      if (message?.action === "closed") { dispose(job, message.reason); return; }
      if (message?.progress && job.pending.has(message.id)) { reply(message.id, message); return; }
      if (job.pending.delete(message?.id)) {
        // Release the page's slot before acknowledging completion. Otherwise
        // the caller can start the next job before onDisconnect is delivered.
        if (message.id === job.finishId) dispose(job);
        reply(message.id, message);
      }
    });
    port.onDisconnect.addListener(() => {
      const detail = chrome.runtime.lastError?.message || "port-disconnected";
      if (job.closed || job.port !== port) return;
      job.disconnectReason = detail.slice(0, 180);
      job.reconnecting = false; reopen(job);
    });
    if (resume) job.reconnectTimer = setTimeout(() => {
      if (!job.closed && job.reconnecting && job.port === port) port.disconnect();
    }, 10000);
  }
  function connect(lookupId, refreshOnly = false, registryState = "NY") {
    const job = { port: null, lookupId, refreshOnly, registryState, pending: new Map(), closed: false, reconnects: 0, reconnecting: false };
    if(P.TRIAL_ORIGIN)trialJobs.set(lookupId,job);else singleActive = job;
    openPort(job);
    // Secondary transport health check; the worker owns active-operation life.
    job.heartbeat = setInterval(() => {
      if (job.reconnecting) return;
      try { job.port.postMessage({ action: "heartbeat" }); } catch { reopen(job); }
    }, 20000);
    job.timer = setTimeout(() => dispose(job, "NY_CONNECTOR_QUEUE_TIMEOUT"), 1500000);
    return job;
  }
  window.addEventListener("message", async event => {
    if (event.source !== window || event.origin !== ORIGIN) return;
    const m = event.data;
    if (m?.channel !== "cc-ny-staging-v1" || m.direction !== "request" || !P.validId(m.id)) return;
    if (m.action === "ping") {
      let response;
      try { response = await chrome.runtime.sendMessage({ action: "ping", id: m.id }); }
      catch { response = { ok: false, reason: "NY_CONNECTOR_UNAVAILABLE" }; }
      reply(m.id, response); return;
    }
    if (!P.validId(m.lookup_id)) return;
    const active=P.TRIAL_ORIGIN?trialJobs.get(m.lookup_id):singleActive;
    if (m.action === "finish") {
      if (active?.lookupId === m.lookup_id) {
        active.finishId = m.id;
        const request = { action: "finish", id: m.id };
        active.pending.set(m.id, request);
        try { if (!active.reconnecting) active.port.postMessage(request); }
        catch { reopen(active); }
        return;
      }
      reply(m.id, { ok: true }); return;
    }
    if (!["acquire", "refresh"].includes(m.action) && (m.action !== "search" || !P.validQuery(m.query))) {
      // A rejected command in an admitted trial lookup must not disappear and
      // consume its entire time budget. Keep unrelated unsolicited messages
      // and the mature connector's existing behavior unchanged.
      if (ORIGIN === P.TRIAL_ORIGIN && m.action === "search" && active?.lookupId === m.lookup_id
          && active.registryState === "NV") reply(m.id, {ok:false,reason:"NY_CONNECTOR_INVALID_SEQUENCE"});
      return;
    }
    if (active && active.lookupId !== m.lookup_id) { reply(m.id, { ok: false, reason: "NY_CONNECTOR_BUSY" }); return; }
    try {
      // Acquire chooses the registry; subsequent search messages deliberately
      // omit intent and must retain that admitted registry.
      const state = active?.registryState || (["IL","GA","AL","NC","NV","TN","NM","MS"].includes(m.intent) ? m.intent : "NY");
      if (active && m.intent && m.intent !== state) { reply(m.id,{ok:false,reason:"NY_CONNECTOR_INVALID_SEQUENCE"}); return; }
      if (!P.registryAllowed(state,ORIGIN)) { reply(m.id,{ok:false,reason:"NY_CONNECTOR_INVALID_SEQUENCE"}); return; }
      const job = active || connect(m.lookup_id, m.action === "acquire" && m.intent === "refresh", state);
      const request = { action: m.action, id: m.id, ...(m.query ? { query: m.query } : {}) };
      job.pending.set(m.id, request);
      try { if (!job.reconnecting) job.port.postMessage(request); } catch { reopen(job); }
    } catch {
      if (active) dispose(active);
      reply(m.id, { ok: false, reason: "NY_CONNECTOR_UNAVAILABLE" });
    }
  });
})();
