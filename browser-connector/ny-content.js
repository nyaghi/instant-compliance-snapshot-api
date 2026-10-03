(() => {
  "use strict";
  // Relay only our worker's already validated command. Protocol validation runs
  // in the worker and page world; Chrome can deduplicate same-file injections
  // across worlds, so this isolated relay does not depend on that page global.
  const NY = "https://charities-search.ag.ny.gov";
  if (location.origin !== NY || window !== window.top) return;
  let pending = null;
  let completed = null;
  const documentId = `${Date.now()}:${Math.random()}`;
  const same = (a, b) => a.action === b.action && JSON.stringify(a.query || null) === JSON.stringify(b.query || null);
  function finish(task, response) {
    completed = { id: task.id, attempt: task.attempt, action: task.action, query: task.query, response };
    if (pending === task) pending = null;
    clearTimeout(task.timer);
    for (const respond of task.responders) try { respond(response); } catch { /* Previous worker has exited. */ }
  }
  window.addEventListener("message", event => {
    if (event.source !== window || event.origin !== NY || event.data?.channel !== "cc-ny-page-v1" || event.data.direction !== "response") return;
    if (!pending || event.data.id !== pending.id) return;
    finish(pending, { ...(event.data.ok ? { ok: true, evidence: event.data.evidence } : { ok: false, reason: event.data.reason }), verificationRetryUsed: event.data.verificationRetryUsed === true });
  });
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id) return false;
    if (message?.action === "ready") {
      const ready = !!document.querySelector("#ein") || /^\/RegistrySearch\/[0-9]{2}-[0-9]{2}-[0-9]{2}\/?$/.test(location.pathname);
      respond({ ready, documentId, url: location.href, rateLimited: !ready && /(?:429\s+Too Many Requests|Too Many Requests\s*429)/i.test(document.body?.innerText || "") });
      return false;
    }
    if (message?.action === "back-to-results") {
      if (!/^\/RegistrySearch\/[0-9]{2}-[0-9]{2}-[0-9]{2}\/?$/.test(location.pathname)) {
        respond({ ok: false }); return false;
      }
      respond({ ok: true }); setTimeout(() => window.history.back(), 0); return false;
    }
    if (message?.action === "open-detail") {
      const identifier = message.query?.orgID;
      if (typeof identifier !== "string" || !/^[0-9]{2}-[0-9]{2}-[0-9]{2}$/.test(identifier) || !/^\/RegistrySearch\/?$/.test(location.pathname)) {
        respond({ ok: false, reason: "NY_CONNECTOR_DETAIL_LINK_MISSING" }); return false;
      }
      const link = Array.from(document.querySelectorAll("a")).find(a => a.textContent.trim() === identifier && a.href === NY + "/RegistrySearch/" + identifier);
      if (!link) { respond({ ok: false, reason: "NY_CONNECTOR_DETAIL_LINK_MISSING" }); return false; }
      // Acknowledge before normal full-page navigation destroys this relay.
      respond({ ok: true }); setTimeout(() => link.click(), 0); return false;
    }
    if (!["search", "verify"].includes(message?.action) || typeof message.id !== "string" || message.id.length > 80) return false;
    if (completed?.id === message.id && completed.attempt === message.attempt) { respond(same(completed, message) ? completed.response : { ok: false, reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); return false; }
    if (pending?.id === message.id && pending.attempt === message.attempt && same(pending, message)) { pending.responders.push(respond); return true; }
    if (pending) { respond({ ok: false, reason: "NY_CONNECTOR_BUSY" }); return false; }
    const task = { id: message.id, attempt: message.attempt, action: message.action, query: message.query, responders: [respond], timer: null };
    task.timer = setTimeout(() => { if (pending === task) finish(task, { ok: false, reason: "NY_CONNECTOR_RELAY_TIMEOUT" }); }, 140000);
    pending = task;
    window.postMessage({ channel: "cc-ny-page-v1", direction: "request", id: message.id, action: message.action, query: message.query, verificationRetryUsed: message.verificationRetryUsed === true }, NY);
    return true;
  });
})();
