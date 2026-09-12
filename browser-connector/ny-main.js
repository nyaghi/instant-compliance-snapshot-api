/* Runs the normal NY form. Observes only completed public responses, never tokens. */
(() => {
  "use strict";
  const P = CCNYProtocol;
  if (location.origin !== P.NY || window !== window.top) return;
  let active = null;
  // Verify and Search share one retry across this page's EIN/name lookup.
  let verificationRetryUsed = false;
  const xhrMetadata = new WeakMap();
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  const publish = evidence => {
    const job = active;
    if (!job || !job.waiter || job.waiter.kind !== evidence.kind) return;
    if (evidence.kind === "search" && !P.sameQuery(evidence.query, job.query)) return;
    const waiter = job.waiter; job.waiter = null; clearTimeout(waiter.timer); waiter.resolve(evidence);
  };
  const observe = (request, status, payload, jobId) => {
    if (!active || active.id !== jobId) return;
    if (status === 429) { rejectRequest(request, jobId, "NY_CONNECTOR_RATE_LIMITED"); return; }
    if (request.kind === "search" && status === 401) {
      // Rejections can have a JSON error or HTML body, never a result table.
      publish({ kind: "search", query: request.query, http_status: status });
      return;
    }
    try { publish(P.publicResponse(request, status, payload)); }
    catch (error) {
      const reason = /^NY_CONNECTOR_SEARCH_(HTTP_ERROR|UNSUCCESSFUL|ROWS_INVALID|IDENTITY_INVALID|EIN_MISSING|EIN_NULL|EIN_TYPE|EIN_FORMAT)$/.test(error.message)
        ? error.message : "NY_CONNECTOR_INCOMPLETE";
      rejectRequest(request, jobId, reason);
    }
  };
  const rejectRequest = (request, jobId, reason) => {
    const job = active;
    if (!job || job.id !== jobId || job.waiter?.kind !== request.kind) return;
    if (request.kind === "search" && !P.sameQuery(request.query, job.query)) return;
    const waiter = job.waiter; job.waiter = null; clearTimeout(waiter.timer); waiter.reject(new Error(reason));
  };
  const networkFailure = (request, jobId) => rejectRequest(request, jobId,
    request.kind === "verify" ? "NY_CONNECTOR_VERIFICATION_NETWORK_ERROR" : "NY_CONNECTOR_SEARCH_NETWORK_ERROR");
  XMLHttpRequest.prototype.open = function(method, url, ...args) {
    const request = P.publicRequest(url);
    if (request && ((request.kind === "search" && String(method).toUpperCase() === "GET") || (request.kind === "verify" && String(method).toUpperCase() === "POST"))) xhrMetadata.set(this, request);
    else xhrMetadata.delete(this);
    return originalOpen.call(this, method, url, ...args);
  };
  XMLHttpRequest.prototype.send = function(...args) {
    const request = xhrMetadata.get(this), jobId = active?.id;
    if (request && jobId) {
      for (const event of ["error", "abort", "timeout"]) this.addEventListener(event, () => networkFailure(request, jobId), { once: true });
      this.addEventListener("load", () => {
      let data;
      try { data = this.responseType === "json" ? this.response : JSON.parse(this.responseText); }
      catch { data = null; }
      observe(request, this.status, data, jobId);
      }, { once: true });
    }
    return originalSend.apply(this, args);
  };
  const originalFetch = window.fetch;
  window.fetch = async function(input, init) {
    const request = P.publicRequest(typeof input === "string" || input instanceof URL ? input : input?.url);
    const jobId = active?.id;
    let response;
    try { response = await originalFetch.apply(this, arguments); }
    catch (error) { if (request && jobId) networkFailure(request, jobId); throw error; }
    if (request && jobId) response.clone().json().then(data => observe(request, response.status, data, jobId)).catch(() => observe(request, response.status, null, jobId));
    return response;
  };
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const button = name => Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === name);
  async function until(check, ms) {
    const deadline = Date.now() + ms;
    while (Date.now() < deadline) { const value = check(); if (value) return value; await pause(100); }
    throw new Error("NY_CONNECTOR_TIMEOUT");
  }
  function waitResponse(kind, ms) {
    return new Promise((resolve, reject) => {
      const job = active;
      const timer = setTimeout(() => { if (job.waiter?.timer === timer) job.waiter = null; reject(new Error("NY_CONNECTOR_TIMEOUT")); }, ms);
      job.waiter = { kind, resolve, reject, timer };
    });
  }
  async function verifySearch() {
    for (let attempt = 0; attempt < 2; attempt++) {
      const verify = await until(() => { const b = button("Verify"); return b && !b.disabled && b; }, 3000);
      const verification = waitResponse("verify", 15000);
      verify.click();
      const result = await verification;
      if (result.http_status === 401) {
        if (verificationRetryUsed) throw new Error("NY_CONNECTOR_VERIFICATION_REJECTED");
        verificationRetryUsed = true;
        await pause(1000);
        continue;
      }
      if (result.http_status !== 200 || !result.verified) throw new Error("NY_CONNECTOR_VERIFICATION_REQUIRED");
      return;
    }
  }
  async function run(query) {
    const clear = await until(() => button("Clear fields"), 10000);
    clear.click();
    await until(() => ["ein", "orgName", "orgID", "city"].every(id => document.getElementById(id)?.value === ""), 3000);
    const [key, value] = Object.entries(query)[0];
    const input = document.getElementById(key);
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await until(() => key === "ein" ? input.value.replace("-", "") === value : input.value === value, 2000);
    await verifySearch();
    const search = await until(() => { const b = button("Search"); return b && !b.disabled && b; }, 3000);
    const completed = waitResponse("search", 15000);
    search.click();
    const evidence = await completed;
    if (evidence.http_status === 401) {
      if (verificationRetryUsed) throw new Error("NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED");
      verificationRetryUsed = true;
      await pause(1000);
      // Clear the form and repeat its normal Verify/Search flow. The shared
      // budget prevents further recursion or another retry on name fallback.
      return run(query);
    }
    if (evidence.http_status !== 200 || evidence.success !== true || evidence.statusCode !== 200) throw new Error("NY_CONNECTOR_INCOMPLETE");
    const { kind, ...publicEvidence } = evidence;
    return publicEvidence;
  }
  window.addEventListener("message", async event => {
    if (event.source !== window || event.origin !== P.NY) return;
    const m = event.data;
    if (m?.channel !== "cc-ny-page-v1" || m.direction !== "request" || !P.validId(m.id) || !P.validQuery(m.query) || active) return;
    const job = { id: m.id, query: m.query, waiter: null }; active = job;
    let reply;
    try { reply = { ok: true, evidence: await run(m.query) }; }
    catch (e) { reply = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(e.message) ? e.message : "NY_CONNECTOR_INCOMPLETE" }; }
    finally { if (job.waiter) clearTimeout(job.waiter.timer); active = null; }
    window.postMessage({ channel: "cc-ny-page-v1", direction: "response", id: m.id, ...reply }, P.NY);
  });
})();
