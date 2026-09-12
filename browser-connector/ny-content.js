(() => {
  "use strict";
  // Relay only our worker's already validated command. Protocol validation runs
  // in the worker and page world; Chrome can deduplicate same-file injections
  // across worlds, so this isolated relay does not depend on that page global.
  const NY = "https://charities-search.ag.ny.gov";
  if (location.origin !== NY || window !== window.top) return;
  let pending = null;
  window.addEventListener("message", event => {
    if (event.source !== window || event.origin !== NY || event.data?.channel !== "cc-ny-page-v1" || event.data.direction !== "response") return;
    if (!pending || event.data.id !== pending.id) return;
    const task = pending; pending = null; clearTimeout(task.timer);
    task.respond(event.data.ok ? { ok: true, evidence: event.data.evidence } : { ok: false, reason: event.data.reason });
  });
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id) return false;
    if (message?.action === "ready") {
      const ready = !!document.querySelector("#ein");
      respond({ ready, rateLimited: !ready && /(?:429\s+Too Many Requests|Too Many Requests\s*429)/i.test(document.body?.innerText || "") });
      return false;
    }
    if (message?.action !== "search" || typeof message.id !== "string" || message.id.length > 80) return false;
    if (pending) { respond({ ok: false, reason: "NY_CONNECTOR_BUSY" }); return false; }
    const timer = setTimeout(() => { if (pending?.id === message.id) { pending = null; respond({ ok: false, reason: "NY_CONNECTOR_TIMEOUT" }); } }, 55000);
    pending = { id: message.id, respond, timer };
    window.postMessage({ channel: "cc-ny-page-v1", direction: "request", id: message.id, query: message.query }, NY);
    return true;
  });
})();
