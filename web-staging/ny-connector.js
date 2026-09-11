/* Staging-only UI integration. Credentials stay between this page and its API. */
(() => {
  "use strict";
  const ORIGIN = "https://staging.compliance-express.com";
  const API = "https://instant-compliance-snapshot-api-staging-8dnk.onrender.com";
  if (location.origin !== ORIGIN) return;
  const waiting = new Map();
  window.addEventListener("message", event => {
    const m = event.data;
    if (event.source !== window || event.origin !== ORIGIN || m?.channel !== "cc-ny-staging-v1" || m.direction !== "response") return;
    const task = waiting.get(m.id); if (!task) return;
    waiting.delete(m.id); clearTimeout(task.timer); task.resolve(m);
  });
  function bridge(action, query) {
    return new Promise(resolve => {
      const id = crypto.randomUUID().replaceAll("-", "");
      const timer = setTimeout(() => { waiting.delete(id); resolve({ ok: false, reason: action === "ping" ? "NY_CONNECTOR_UNAVAILABLE" : "NY_CONNECTOR_TIMEOUT" }); }, action === "ping" ? 1500 : 75000);
      waiting.set(id, { resolve, timer });
      window.postMessage({ channel: "cc-ny-staging-v1", direction: "request", id, action, ...(query ? { query } : {}) }, ORIGIN);
    });
  }
  async function setup() {
    const box = document.getElementById("nyConnectorSetup");
    if (!box) return;
    const response = await bridge("ping");
    box.hidden = false;
    const message = box.querySelector("[data-connector-message]");
    message.textContent = response.ok ? "New York connector is ready. Keep Chrome open while checks run." : "New York needs the staging browser connector. Install it once, then return here and refresh this page.";
    box.querySelector("[data-connector-install]").hidden = !!response.ok;
    box.dataset.state = response.ok ? "ready" : "missing";
  }
  async function lookup({ organization_name, ein, email, admin_passcode, device_id }) {
    const credentials = { email, admin_passcode, device_id };
    let checkToken = "";
    async function api(fields) {
      const response = await fetch(API + "/api/ny-connector", {
        method: "POST", headers: { "Content-Type": "application/json" },
        signal: AbortSignal.timeout(45000), body: JSON.stringify({ ...credentials, ...fields })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "The New York browser check could not be completed.");
      return payload;
    }
    try {
      let state = await api({ action: "start", organization_name, ein });
      checkToken = state.check_token || "";
      const connection = await bridge("ping");
      if (!connection.ok && state.phase === "search") {
        state = await api({ action: "fail", check_token: checkToken, reason: "NY_CONNECTOR_UNAVAILABLE" });
        await setup();
      }
      let count = 0;
      while (state.phase === "search" && count++ < 5) {
        checkToken = state.check_token;
        const completed = await bridge("search", state.query);
        state = completed.ok
          ? await api({ action: "advance", check_token: checkToken, query_id: state.query_id, evidence: completed.evidence })
          : await api({ action: "fail", check_token: checkToken, reason: completed.reason });
      }
      if (state.phase !== "complete" || !state.result || state.result.state !== "NY") throw new Error("New York did not return a complete result.");
      return state.result;
    } finally {
      if (checkToken) api({ action: "cancel", check_token: checkToken }).catch(() => {});
    }
  }
  window.CCNYConnector = Object.freeze({ setup, lookup });
})();
