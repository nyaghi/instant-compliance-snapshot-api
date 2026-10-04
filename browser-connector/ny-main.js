/* Runs the normal NY form. Observes only completed public responses, never tokens. */
(() => {
  "use strict";
  const P = CCNYProtocol;
  if (location.origin !== P.NY || window !== window.top) return;
  let active = null;
  let documentDetail = null;
  // Verify and Search share one retry across this page's EIN/name lookup.
  let verificationRetryUsed = false;
  // Trial diagnostics observe existing actions only; no additional requests.
  const note = (stage, event, status = null, payload = null) => {
    if (!P.TRIAL_ORIGIN || !active) return;
    const codes = payload && (payload["error-codes"] || payload.errorCodes);
    active.diagnostics.push(...P.nyDiagnostics([{stage,event,http_status:status,
      elapsed_ms:Date.now()-active.started,verified:payload?.verified,
      payload_type:payload === null ? "non_json" : typeof payload === "object" && !Array.isArray(payload) ? "object" : "other",
      error_codes:codes,visibility:document.visibilityState}]));
    active.diagnostics=active.diagnostics.slice(-32);
    window.postMessage({channel:'cc-ny-page-v1',direction:'diagnostic',id:active.id,
      ny_diagnostics:P.nyDiagnostics(active.diagnostics.slice(-1))},P.NY);
  };
  const xhrMetadata = new WeakMap();
  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  const publish = evidence => {
    const job = active;
    if (!job || !job.waiter || job.waiter.kind !== evidence.kind) return;
    if (["search", "detail"].includes(evidence.kind) && !P.sameQuery(evidence.query, job.query)) return;
    const waiter = job.waiter; job.waiter = null; clearTimeout(waiter.timer); waiter.resolve(evidence);
  };
  const detailFailure = status => !P.TRIAL_ORIGIN ? "NY_CONNECTOR_DETAIL_INCOMPLETE"
    : status === 401 ? "NY_CONNECTOR_DETAIL_UNAUTHORIZED"
    : status === 403 ? "NY_CONNECTOR_DETAIL_FORBIDDEN"
    : status >= 500 && status <= 599 ? "NY_CONNECTOR_DETAIL_SERVER_ERROR"
    : status !== 200 ? "NY_CONNECTOR_DETAIL_HTTP_ERROR" : "NY_CONNECTOR_DETAIL_SCHEMA_INVALID";
  const observe = (request, status, payload, jobId) => {
    if (active?.id === jobId) note(request.kind,"response",status,payload);
    // A normal detail link loads a new document. Its response can finish
    // before the worker reconnects; retain only that document's public fields.
    if (request.kind === "detail" && location.pathname === "/RegistrySearch/" + request.query.orgID) {
      try { documentDetail = { evidence: P.publicResponse(request, status, payload) }; }
      catch { documentDetail = { reason: status === 429 ? "NY_CONNECTOR_RATE_LIMITED" : detailFailure(status) }; }
      if (active?.waiter?.kind === "detail" && P.sameQuery(active.query, request.query)) {
        if (documentDetail.evidence) publish(documentDetail.evidence);
        else rejectRequest(request, active.id, documentDetail.reason);
      }
      return;
    }
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
        ? error.message : request.kind === "detail" ? detailFailure(status) : "NY_CONNECTOR_INCOMPLETE";
      rejectRequest(request, jobId, reason);
    }
  };
  const rejectRequest = (request, jobId, reason) => {
    const job = active;
    if (!job || job.id !== jobId || job.waiter?.kind !== request.kind) return;
    if (["search", "detail"].includes(request.kind) && !P.sameQuery(request.query, job.query)) return;
    const waiter = job.waiter; job.waiter = null; clearTimeout(waiter.timer); waiter.reject(new Error(reason));
  };
  const networkFailure = (request, jobId) => {
    if (active?.id === jobId) note(request.kind,"network_error");
    if (request.kind === "detail" && location.pathname === "/RegistrySearch/" + request.query.orgID) {
      documentDetail = { reason: "NY_CONNECTOR_DETAIL_INCOMPLETE" };
      if (active && P.sameQuery(active.query, request.query)) rejectRequest(request, active.id, documentDetail.reason);
      return;
    }
    rejectRequest(request, jobId, request.kind === "verify" ? "NY_CONNECTOR_VERIFICATION_NETWORK_ERROR" : "NY_CONNECTOR_SEARCH_NETWORK_ERROR");
  };
  XMLHttpRequest.prototype.open = function(method, url, ...args) {
    const request = P.publicRequest(url);
    if (request && ((["search", "detail"].includes(request.kind) && String(method).toUpperCase() === "GET") || (request.kind === "verify" && String(method).toUpperCase() === "POST"))) xhrMetadata.set(this, request);
    else xhrMetadata.delete(this);
    return originalOpen.call(this, method, url, ...args);
  };
  XMLHttpRequest.prototype.send = function(...args) {
    const request = xhrMetadata.get(this), jobId = active?.id;
    if (request && (jobId || request.kind === "detail")) {
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
    catch (error) { if (request && (jobId || request.kind === "detail")) networkFailure(request, jobId); throw error; }
    if (request && (jobId || request.kind === "detail")) response.clone().json().then(data => observe(request, response.status, data, jobId)).catch(() => observe(request, response.status, null, jobId));
    return response;
  };
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const button = name => Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === name);
  async function until(check, ms, reason = "NY_CONNECTOR_FORM_TIMEOUT") {
    const deadline = Date.now() + ms;
    return new Promise((resolve, reject) => {
      let done = false, poll, watchdog, observer;
      const finish = (value, error) => {
        if (done) return;
        done = true; clearTimeout(poll); clearTimeout(watchdog); observer?.disconnect();
        document.removeEventListener?.("input", inspect, true);
        document.removeEventListener?.("change", inspect, true);
        error ? reject(error) : resolve(value);
      };
      const inspect = () => {
        if (done) return;
        if (Date.now() >= deadline) return finish(null, new Error(reason));
        try { const value=check(); if (value) finish(value); }
        catch (error) { finish(null, error); }
      };
      // Chrome throttles polling timers in background registry tabs. Observe
      // the state's normal render/input events before a delayed timer can
      // incorrectly label an already cleared or enabled form as timed out.
      // Evidence first observed after the original deadline is still rejected.
      if (typeof MutationObserver !== "undefined") {
        observer = new MutationObserver(inspect);
        observer.observe(document.documentElement, {childList:true, subtree:true,
          attributes:true, characterData:true});
      }
      document.addEventListener?.("input", inspect, true);
      document.addEventListener?.("change", inspect, true);
      const pollAgain = () => { inspect(); if (!done) poll=setTimeout(pollAgain,100); };
      watchdog=setTimeout(() => finish(null,new Error(reason)),ms);
      pollAgain();
    });
  }
  function waitResponse(kind, ms) {
    return new Promise((resolve, reject) => {
      const job = active;
      const timer = setTimeout(() => { if (job.waiter?.timer === timer) job.waiter = null; if (active === job) note(kind,"timeout"); reject(new Error(kind === "verify" ? "NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT" : kind === "detail" ? "NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT" : "NY_CONNECTOR_SEARCH_RESPONSE_TIMEOUT")); }, ms);
      job.waiter = { kind, resolve, reject, timer };
    });
  }
  async function verifySearch(force = false) {
    for (let attempt = 0; attempt < 2; attempt++) {
      // New York can retain a valid verification across form resets. Its
      // enabled Search button is the normal UI signal; do not require a second
      // Verify click when the page already permits this search.
      if (!force && attempt === 0 && button("Search") && !button("Search").disabled) { note("verify","reuse"); return; }
      const verify = await until(() => { const b = button("Verify"); return b && !b.disabled && b; }, 3000, "NY_CONNECTOR_VERIFY_BUTTON_TIMEOUT");
      // The portal's visible reCAPTCHA frame advertises a 30-second execution
      // allowance. Let that normal flow finish plus its public API response;
      // a matching 30-second observer deadline could expire first.
      const verification = waitResponse("verify", 45000);
      note("verify","click");
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
  async function returnToResults() {
    if (/^\/RegistrySearch\/[0-9]{2}-[0-9]{2}-[0-9]{2}\/?$/.test(location.pathname)) {
      // The state retains the verified result list in browser history.
      window.history.back();
      await until(() => /^\/RegistrySearch\/?$/.test(location.pathname) && document.getElementById("ein"), 10000, "NY_CONNECTOR_RETURN_FORM_TIMEOUT");
    }
  }
  async function runDetail(query) {
    if (location.pathname !== "/RegistrySearch/" + query.orgID) throw new Error("NY_CONNECTOR_DETAIL_LINK_MISSING");
    if (documentDetail?.reason) throw new Error(documentDetail.reason);
    const completed = documentDetail?.evidence || await waitResponse("detail", 30000);
    if (!P.sameQuery(completed.query, query)) throw new Error("NY_CONNECTOR_DETAIL_INCOMPLETE");
    const { kind, ...evidence } = completed;
    return evidence;
  }
  async function run(query, forceVerification = false) {
    if (Object.hasOwn(query, "orgID")) return runDetail(query);
    await returnToResults();
    const reuseVerifiedForm = P.TRIAL_ORIGIN && !forceVerification && button("Search") && !button("Search").disabled;
    if (reuseVerifiedForm) {
      // The enabled form supports same-field reuse. Editing an old EIN to
      // blank and switching to a name produced HTTP400 in the live portal.
      // The worker must obtain a fresh document for that transition; do not
      // clear foreign filters here and mistake a visible blank for a reset.
      const key = Object.keys(query)[0];
      if (["ein", "orgName", "orgID", "city"].some(id => id !== key && document.getElementById(id)?.value))
        throw new Error("NY_CONNECTOR_SEARCH_FORM_CHANGED");
    } else {
      const clear = await until(() => button("Clear fields"), 10000, "NY_CONNECTOR_CLEAR_BUTTON_TIMEOUT");
      clear.click();
    }
    await until(() => ["ein", "orgName", "orgID", "city"].every(id =>
      id === Object.keys(query)[0] && reuseVerifiedForm
        || document.getElementById(id)?.value === ""), 3000, "NY_CONNECTOR_CLEAR_FIELDS_TIMEOUT");
    const [key, value] = Object.entries(query)[0];
    const input = document.getElementById(key);
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await until(() => key === "ein" ? input.value.replace("-", "") === value : input.value === value, 2000, "NY_CONNECTOR_INPUT_BINDING_TIMEOUT");
    await verifySearch(forceVerification);
    // A successful public verification response can precede the portal's
    // rendered button update. Wait for the real enabled control, still bounded.
    const search = await until(() => { const b = button("Search"); return b && !b.disabled && b; }, 15000, "NY_CONNECTOR_SEARCH_BUTTON_TIMEOUT");
    const completed = waitResponse("search", 30000);
    note("search","click");
    search.click();
    const evidence = await completed;
    if (evidence.http_status === 401) {
      if (verificationRetryUsed) throw new Error("NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED");
      verificationRetryUsed = true;
      await pause(1000);
      // Clear the form and repeat its normal Verify/Search flow. The shared
      // budget prevents further recursion or another retry on name fallback.
      return run(query, true);
    }
    if (evidence.http_status !== 200 || evidence.success !== true || evidence.statusCode !== 200) throw new Error("NY_CONNECTOR_INCOMPLETE");
    const { kind, ...publicEvidence } = evidence;
    return publicEvidence;
  }
  window.addEventListener("message", async event => {
    if (event.source !== window || event.origin !== P.NY) return;
    const m = event.data;
    if (m?.channel !== "cc-ny-page-v1" || m.direction !== "request" || !P.validId(m.id) || (m.action !== "verify" && !P.validQuery(m.query)) || active) return;
    const job = { id: m.id, query: m.query, waiter: null, started:Date.now(), diagnostics:[] }; active = job;
    verificationRetryUsed ||= m.verificationRetryUsed === true;
    let reply;
    try {
      if (m.action === "verify") { await verifySearch(true); reply = { ok: true, evidence: { verified: true } }; }
      else reply = { ok: true, evidence: await run(m.query) };
    }
    catch (e) { reply = { ok: false, reason: /^NY_CONNECTOR_[A-Z_]+$/.test(e.message) ? e.message : "NY_CONNECTOR_INCOMPLETE" }; }
    finally { if (job.waiter) clearTimeout(job.waiter.timer); active = null; }
    window.postMessage({ channel: "cc-ny-page-v1", direction: "response", id: m.id, ...reply, verificationRetryUsed, ...(P.TRIAL_ORIGIN ? {ny_diagnostics:P.nyDiagnostics(job.diagnostics)} : {}) }, P.NY);
  });
})();
