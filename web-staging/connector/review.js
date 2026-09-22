/* Submission test client for the unchanged connector, not a state classifier. */
(() => {
  "use strict";
  const P = globalThis.CCNYProtocol, origin = location.origin;
  if (!P.allowedOrigin(origin) || window !== window.top) return;
  const byId = id => document.getElementById(id), waiting = new Map();
  let busy = false;
  const message = text => { byId("status").textContent = text; };
  const id = () => crypto.randomUUID().replaceAll("-", "");
  window.addEventListener("message", event => {
    const reply = event.data;
    if (event.source !== window || event.origin !== origin || reply?.channel !== "cc-ny-staging-v1" || reply.direction !== "response") return;
    const task = waiting.get(reply.id);
    if (!task) return;
    if (reply.progress) {
      task.progress?.(reply);
      return;
    }
    waiting.delete(reply.id); clearTimeout(task.timer); task.resolve(reply);
  });
  function send(action, lookupId, query, progress, intent) {
    return new Promise(resolve => {
      const requestId = id();
      const ms = action === "ping" ? 5000 : action === "acquire" ? 1205000 : action === "finish" ? 15000 : 290000;
      const timer = setTimeout(() => {
        waiting.delete(requestId);
        resolve({ ok: false, reason: action === "ping" ? "NY_CONNECTOR_UNAVAILABLE" : "NY_CONNECTOR_TIMEOUT" });
      }, ms);
      waiting.set(requestId, { resolve, timer, progress });
      window.postMessage({ channel: "cc-ny-staging-v1", direction: "request", id: requestId, action,
        ...(lookupId ? { lookup_id: lookupId } : {}), ...(query ? { query } : {}), ...(intent ? { intent } : {}) }, origin);
    });
  }
  async function connection() {
    const reply = await send("ping");
    const ready = reply.ok && ["queue-v1", "connection-recovery-v1", "resume-v1"].every(c => reply.capabilities?.includes(c));
    byId("connection").textContent = ready ? `Connected — connector ${reply.version}.` : "Connector unavailable or out of date. Install the submitted extension and reload this page.";
    return ready;
  }
  function setBusy(value) {
    busy = value;
    for (const name of ["search", "refresh", "check", "ein"]) byId(name).disabled = value;
  }
  function progress(reply) {
    message(reply.recovering ? "Recovering the New York connection…" : reply.reconnecting ? "Reconnecting to the connector…" : reply.retrying ? "New York requested a retry; waiting…" : `Waiting for the connector${Number.isInteger(reply.position) ? ` — queue position ${reply.position}` : ""}…`);
  }
  function render(evidence, query) {
    if (!P.sameQuery(evidence?.query, query)) throw new Error("NY_CONNECTOR_INCOMPLETE");
    // Reuse the packaged evidence validator, including row and EIN schema checks.
    const checked = P.publicResponse({ kind: "search", query }, evidence.http_status,
      { success: evidence.success, statusCode: evidence.statusCode, data: evidence.rows });
    const table = document.createElement("table");
    const header = document.createElement("tr");
    for (const label of ["Registry record", "Organization name", "EIN"]) { const cell = document.createElement("th"); cell.textContent = label; header.append(cell); }
    table.append(header);
    for (const row of checked.rows) {
      const tr = document.createElement("tr");
      for (const value of [row.orgID, row.orgName, row.ein || "Not supplied in this search row"]) { const cell = document.createElement("td"); cell.textContent = value; tr.append(cell); }
      table.append(tr);
    }
    byId("results").replaceChildren(table);
    byId("evidence").textContent = JSON.stringify(checked, null, 2);
    byId("details").hidden = false;
    message(checked.rows.length ? `Live registry response received: ${checked.rows.length} record(s). No compliance status is assigned on this review page.` : "The live registry search returned zero rows. This review page does not assign a registration status.");
  }
  async function run(refreshOnly = false) {
    if (busy) return;
    const raw = byId("ein").value.trim();
    const query = { ein: raw.replace("-", "") };
    if (!refreshOnly && (!/^[0-9]{2}-?[0-9]{7}$/.test(raw) || !P.validQuery(query))) { message("Enter a valid nine-digit EIN."); return; }
    setBusy(true);
    const lookupId = id(), started = performance.now();
    let acquired = false;
    byId("results").replaceChildren(); byId("details").hidden = true; byId("evidence").textContent = ""; byId("elapsed").textContent = "";
    try {
      if (!await connection()) { message("Install or enable the submitted connector, then reload this page."); return; }
      message("Waiting for the connector…");
      // Always finish an admitted or timed-out acquire to release the page's job.
      acquired = true;
      const admission = await send("acquire", lookupId, null, progress, refreshOnly ? "refresh" : null);
      if (!admission.ok) throw new Error(admission.reason || "NY_CONNECTOR_INCOMPLETE");
      message(refreshOnly ? "Refreshing New York connection…" : "Searching the live New York registry…");
      const result = await send(refreshOnly ? "refresh" : "search", lookupId, refreshOnly ? null : query, progress);
      if (!result.ok) throw new Error(result.reason || "NY_CONNECTOR_INCOMPLETE");
      if (refreshOnly) message("New York connection refreshed and verification succeeded.");
      else render(result.evidence, query);
    } catch (error) {
      message(`The live check did not complete. No registration conclusion was drawn. ${error.message}`);
    } finally {
      if (acquired) {
        const finished = await send("finish", lookupId);
        if (!finished.ok) message(`${byId("status").textContent} The connector did not acknowledge cleanup; close this review tab before another test.`);
      }
      byId("elapsed").textContent = `Elapsed time: ${((performance.now() - started) / 1000).toFixed(1)} seconds.`;
      setBusy(false);
    }
  }
  byId("lookup").addEventListener("submit", event => { event.preventDefault(); run(); });
  byId("refresh").addEventListener("click", () => run(true));
  byId("check").addEventListener("click", connection);
  connection();
})();
