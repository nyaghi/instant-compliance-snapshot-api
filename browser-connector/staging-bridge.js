(() => {
  "use strict";
  const P = CCNYProtocol;
  if (location.origin !== P.STAGING || window !== window.top) return;
  window.addEventListener("message", async event => {
    if (event.source !== window || event.origin !== P.STAGING) return;
    const m = event.data;
    if (m?.channel !== "cc-ny-staging-v1" || m.direction !== "request" || !P.validId(m.id)) return;
    if (m.action !== "ping" && (m.action !== "search" || !P.validQuery(m.query))) return;
    let response;
    try {
      response = await chrome.runtime.sendMessage({ action: m.action, id: m.id, ...(m.action === "search" ? { query: m.query } : {}) });
    } catch { response = { ok: false, reason: "NY_CONNECTOR_UNAVAILABLE" }; }
    window.postMessage({ channel: "cc-ny-staging-v1", direction: "response", id: m.id, ...response }, P.STAGING);
  });
})();
