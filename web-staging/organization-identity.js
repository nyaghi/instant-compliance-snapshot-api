/* Reviewed names are local to this run; evidence suggestions never start checks. */
(() => {
  "use strict";
  const panel = document.getElementById("organizationIdentity");
  if (!panel) return;
  const nameInput = document.getElementById("organizationName");
  const einInput = document.getElementById("ein");
  const find = document.getElementById("findAlternateNames");
  const add = document.getElementById("addAlternateName");
  const list = document.getElementById("alternateNameList");
  const message = document.getElementById("identityMessage");
  const review = document.getElementById("identityReview");
  const summary = document.getElementById("identitySummary");
  let revision = 0, reviewedIdentity = "", rows = [], busy = false, controller;
  const identity = () => `${einInput.value.replace(/\D/g, "")}|${nameInput.value.trim()}`;
  const changed = () => window.dispatchEvent(new Event("cc-identity-change"));
  const text = (tag, value, cls) => { const node = document.createElement(tag); node.textContent = value; if (cls) node.className = cls; return node; };
  function invalidate() {
    revision++; controller?.abort(); reviewedIdentity = ""; rows = [];
    list.replaceChildren(); review.hidden = true; find.disabled = busy;
    find.textContent = "1. Find alternate names";
    message.textContent = "We’ll check EIN-linked state and IRS records. Review the names before running your checks.";
    changed();
  }
  [einInput, nameInput].forEach(input => input.addEventListener("input", invalidate));
  function render() {
    list.replaceChildren();
    rows.forEach((row, index) => {
      const box = text("div", "", "rounded-lg border border-slate-200 bg-white p-3");
      const line = text("div", "", "flex items-start gap-2");
      const check = document.createElement("input"); check.type = "checkbox"; check.checked = row.selected;
      check.className = "mt-3"; check.setAttribute("aria-label", `Use alternate name ${index + 1}`);
      check.addEventListener("change", () => { row.selected = check.checked; });
      const input = document.createElement("textarea"); input.rows = 2; input.value = row.name; input.maxLength = 300;
      input.className = "min-w-0 flex-1 rounded border border-slate-300 px-2 py-2 text-sm";
      input.setAttribute("aria-label", `Alternate name ${index + 1}`);
      const remove = text("button", "Remove", "py-2 text-xs underline text-slate-600"); remove.type = "button";
      remove.setAttribute("aria-label", `Remove alternate name ${index + 1}`);
      remove.addEventListener("click", () => { rows.splice(index, 1); render(); });
      const proof = text("p", "", "mt-2 text-xs leading-relaxed text-slate-600");
      const describe = () => {
        proof.replaceChildren();
        if (!row.verified || row.name !== row.original) {
          proof.textContent = "User-entered name — not independently verified."; return;
        }
        proof.append(text("span", row.historical ? "Historical name · EIN verified. " : "EIN verified. "));
        const seen = new Set();
        for (const evidence of row.evidence || []) {
          const key = `${evidence.source}|${evidence.type}`; if (seen.has(key)) continue; seen.add(key);
          const link = text("a", `${evidence.source}: ${evidence.type}`, "underline");
          if (/^https:\/\//.test(evidence.url || "")) { link.href = evidence.url; link.target = "_blank"; link.rel = "noopener noreferrer"; }
          const date = evidence.source_date ? ` · source ${evidence.source_date.slice(0, 10)}` : "";
          const retrieved = evidence.retrieved_at ? ` · checked ${evidence.retrieved_at.slice(0, 10)}` : "";
          proof.append(link, document.createTextNode(`${date}${retrieved}. `));
        }
      };
      input.addEventListener("input", () => { input.value = input.value.replace(/[\r\n\t]+/g, " "); row.name = input.value; describe(); }); describe();
      line.append(check, input, remove); box.append(line, proof); list.append(box);
    });
    add.disabled = busy || rows.length >= 32;
  }
  add.addEventListener("click", () => {
    if (rows.length >= 32 || busy) return;
    rows.push({name: "", original: "", selected: true, verified: false}); render();
    list.lastElementChild?.querySelector('textarea')?.focus();
  });
  find.addEventListener("click", async () => {
    if (busy) return;
    const config = window.CCIdentityConfig?.();
    if (!config) return;
    if (!nameInput.value.trim() || !/^\d{9}$/.test(einInput.value.replace(/\D/g, ""))) {
      message.textContent = "Enter the organization name and nine-digit EIN first."; nameInput.focus(); return;
    }
    if (!config.email || !config.admin_passcode) {
      message.textContent = "Enter your staging email and passcode below, then find alternate names.";
      document.getElementById("email")?.focus(); return;
    }
    const requestIdentity = identity(), requestRevision = ++revision;
    reviewedIdentity = ""; find.disabled = true; find.textContent = "Finding alternate names…";
    nameInput.disabled = true; einInput.disabled = true;
    message.textContent = "Checking EIN-linked records in 15 states and the IRS. Some sources may take longer…"; changed();
    controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 70000);
    const requestedName = nameInput.value.trim(), requestedEin = einInput.value.trim();
    const nyIdentity = window.CCNYConnector?.lookup({organization_name: requestedName, ein: requestedEin,
      email: config.email, admin_passcode: config.admin_passcode, device_id: config.device_id, purpose: "identity",
      onProgress: value => { if (value && requestRevision === revision) message.textContent = value.replace("Other states can continue.", "Finding alternate names; registration checks have not started."); }
    }).catch(() => null);
    try {
      const response = await fetch(`${config.apiBase}/api/discover-names`, {method: "POST", headers: {"Content-Type": "application/json"}, signal: controller.signal,
        body: JSON.stringify({organization_name: requestedName, ein: requestedEin, email: config.email, admin_passcode: config.admin_passcode})});
      const data = await response.json();
      clearTimeout(timeout);
      if (requestRevision !== revision || requestIdentity !== identity()) return;
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) { message.textContent = data.error || "Unlock staging to continue."; return; }
        throw new Error(data.error || "Name discovery did not complete.");
      }
      const ny = await nyIdentity;
      data.names ||= [];
      if (requestRevision !== revision || requestIdentity !== identity()) return;
      if (ny?.identity?.complete) {
        data.sources = (data.sources || []).filter(source => source.source !== "NY").concat({source: "NY", complete: true});
        const key = value => value.toLowerCase().replace(/[’']/g, "").replace(/[^a-z0-9\s]/g, "").replace(/\s+/g, " ").trim().replace(/(?:\s+(?:inc|incorporated|corp|corporation|llc|ltd|limited))+$/, "");
        for (const candidate of ny.identity.names || []) {
          const existing = data.names.find(item => key(item.name) === key(candidate.name));
          if (existing) existing.evidence.push(...candidate.evidence);
          else data.names.push(candidate);
        }
      } else if (ny?.comments) {
        const source = (data.sources || []).find(item => item.source === "NY");
        if (source) source.limitation = "The browser could not confirm New York names. Other confirmed names remain available.";
      }
      rows = (data.names || []).slice(0, 32).map(row => ({...row, original: row.name, selected: true}));
      const limitations = (data.sources || []).filter(source => !source.complete).map(source => `${source.source}: ${source.limitation || "Some records were unavailable."}`);
      if (data.names.length > 32) limitations.push("The first 32 confirmed names are shown. Review these names before continuing.");
      message.textContent = limitations.length ? `Some sources were unavailable. You can review the names found, add names, and continue. ${limitations.join(" ")}` :
        rows.length ? "Review the names below. Keep only names that belong to this organization." : "No additional names were confirmed. You can add names or continue with your entered name.";
      reviewedIdentity = requestIdentity;
    } catch (error) {
      if (requestRevision !== revision || requestIdentity !== identity()) return;
      rows = []; reviewedIdentity = requestIdentity;
      message.textContent = "Alternate-name discovery could not finish. You can enter names manually or continue with your entered name. Registration checks have not started.";
    } finally {
      clearTimeout(timeout);
      nameInput.disabled = busy; einInput.disabled = busy;
      if (requestRevision === revision) {
        find.disabled = busy; find.textContent = "Find names again"; review.hidden = !reviewedIdentity;
        summary.textContent = `${nameInput.value.trim()} · EIN ${einInput.value.trim()}`;
        render(); changed();
      }
    }
  });
  window.CCIdentity = Object.freeze({
    ready: () => !!reviewedIdentity && reviewedIdentity === identity(),
    names: () => rows.filter(row => row.selected && row.name.trim()).map(row => row.name.trim()),
    setBusy(value) {
      busy = value; find.disabled = value; nameInput.disabled = value; einInput.disabled = value;
      panel.querySelectorAll("input, textarea, button").forEach(element => { element.disabled = value; });
      if (!value) add.disabled = rows.length >= 32;
    },
    focus: () => { panel.scrollIntoView({block: "center", behavior: "smooth"}); find.focus(); }
  });
})();
