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
  const compatible = response => response?.ok && ["lookup-tab-v1", "verification-retry-v1"].every(capability => response.capabilities?.includes(capability));
  function bridge(action, query, lookupId) {
    return new Promise(resolve => {
      const id = crypto.randomUUID().replaceAll("-", "");
      const timer = setTimeout(() => { waiting.delete(id); resolve({ ok: false, reason: action === "ping" ? "NY_CONNECTOR_UNAVAILABLE" : "NY_CONNECTOR_TIMEOUT" }); }, action === "search" ? 75000 : 1500);
      waiting.set(id, { resolve, timer });
      window.postMessage({ channel: "cc-ny-staging-v1", direction: "request", id, action, ...(query ? { query } : {}), ...(lookupId ? { lookup_id: lookupId } : {}) }, ORIGIN);
    });
  }
  async function setup() {
    const box = document.getElementById("nyConnectorSetup");
    if (!box) return;
    const response = await bridge("ping");
    const ready = !!compatible(response), update = !!response.ok && !ready;
    box.hidden = false;
    const message = box.querySelector("[data-connector-message]");
    message.textContent = ready ? "New York connector is ready. Keep Chrome open while checks run." : update ? "Your New York connector needs an update. Follow the three update steps, then refresh CharityClarity." : "Connect this browser to New York using the three setup steps.";
    document.querySelectorAll("[data-connector-install]").forEach(element => { element.hidden = ready; });
    document.querySelectorAll("[data-connector-first-install]").forEach(element => { element.hidden = ready || update; });
    document.querySelectorAll("[data-connector-update]").forEach(element => { element.hidden = !update; });
    document.querySelectorAll("[data-connector-ready]").forEach(element => { element.hidden = !ready; });
    document.querySelectorAll("[data-connector-setup-link]").forEach(element => { element.textContent = update ? "Update New York in 3 steps" : "Set up New York in 3 steps"; });
    box.dataset.state = ready ? "ready" : update ? "update" : "missing";
  }
  async function lookup({ organization_name, ein, email, admin_passcode, device_id }) {
    const credentials = { email, admin_passcode, device_id };
    let checkToken = "";
    const lookupId = crypto.randomUUID().replaceAll("-", "");
    let connected = false;
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
      if (!compatible(connection) && state.phase === "search") {
        state = await api({ action: "fail", check_token: checkToken, reason: connection.ok ? "NY_CONNECTOR_UPDATE_REQUIRED" : "NY_CONNECTOR_UNAVAILABLE" });
        await setup();
      }
      let count = 0;
      while (state.phase === "search" && count++ < 5) {
        checkToken = state.check_token;
        connected = true;
        const completed = await bridge("search", state.query, lookupId);
        state = completed.ok
          ? await api({ action: "advance", check_token: checkToken, query_id: state.query_id, evidence: completed.evidence })
          : await api({ action: "fail", check_token: checkToken, reason: completed.reason });
      }
      if (state.phase !== "complete" || !state.result || state.result.state !== "NY") throw new Error("New York did not return a complete result.");
      return state.result;
    } finally {
      if (connected) await bridge("finish", null, lookupId);
      if (checkToken) api({ action: "cancel", check_token: checkToken }).catch(() => {});
    }
  }
  window.CCNYConnector = Object.freeze({ setup, lookup });
})();
