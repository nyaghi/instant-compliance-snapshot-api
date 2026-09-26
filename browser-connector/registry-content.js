/* Public DOM collection only. Identity and status are interpreted by the master. */
(() => {
  "use strict";
  if (window !== window.top) return;
  const IL = location.origin === "https://charitable.illinoisattorneygeneral.gov";
  const GA = location.origin === "https://verify.sos.ga.gov";
  if (!IL && !GA) return;
  const documentId = crypto.randomUUID();
  const text = el => (el?.innerText || "").replace(/\s+/g, " ").trim();
  const visible = el => !!el && el.getClientRects().length > 0;
  const pause = ms => new Promise(r => setTimeout(r, ms));
  async function wait(fn, ms = 25000) {
    const end = Date.now() + ms;
    while (Date.now() < end) { const value = fn(); if (value) return value; await pause(150); }
    throw new Error("REGISTRY_RESPONSE_INCOMPLETE");
  }
  function set(el, value) {
    if (!el) throw new Error("REGISTRY_FORM_CHANGED");
    const descriptor = Object.getOwnPropertyDescriptor(el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype, "value");
    descriptor.set.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    if (el.value !== value) throw new Error("REGISTRY_FILTER_NOT_SET");
  }
  function gaRows() {
    const table = document.querySelector("#datagrid_results");
    if (!table) return null;
    // Georgia exposes both its six-column verification view and a city/state
    // view with an optional complaint link. A changed shape is incomplete
    // evidence; silently skipping its data rows would create false negatives.
    const tableRows = [...table.querySelectorAll(":scope > tbody > tr")];
    const header = tableRows[0], pager = tableRows.at(-1);
    const headings = [...(header?.children || [])].map(el=>text(el).toLowerCase());
    const combined = JSON.stringify(headings) === JSON.stringify(["full name","license #","profession","license type","status","address"]);
    const split = [7,8].includes(headings.length)
      && JSON.stringify(headings.slice(0,7)) === JSON.stringify(["full name","license number","profession","license type","license status","city","state"])
      && (headings.length === 7 || headings[7] === "");
    if ((!combined && !split) || ![...header.children].every(el=>el.tagName === "TH") || tableRows.length < 2)
      throw new Error("REGISTRY_COLUMNS_CHANGED");
    const rows = [];
    for (const tr of tableRows.slice(1,-1)) {
      const cells = [...tr.children];
      if (cells.length !== headings.length || !cells.every(el=>el.tagName === "TD")) throw new Error("REGISTRY_ROW_CHANGED");
      const link = cells[0].querySelector("a"), url = link && new URL(link.href);
      if (!url || url.origin !== location.origin || url.pathname !== "/verification/Details.aspx") throw new Error("REGISTRY_LINK_CHANGED");
      if (text(cells[2]) !== "Charities") throw new Error("REGISTRY_FILTER_CHANGED");
      if (text(cells[3]) === "Paid Solicitor") continue;
      // Legacy exemptions can expose an untranslated type code. Keep their
      // public rows for master identity filtering; this does not classify them.
      if (!["Charity", "Exempt Charity", "Private Foundations", "agency1prof0licType52004"].includes(text(cells[3]))) throw new Error("REGISTRY_FILTER_CHANGED");
      rows.push({name:text(cells[0]), identifier:text(cells[1]), location:combined ? text(cells[5]) : [text(cells[5]),text(cells[6])].filter(Boolean).join(", "), street:"", region:split ? text(cells[6]) : "", postal_code:"", detail_key:url.searchParams.get("result")});
    }
    const current = [...pager.querySelectorAll("span")].map(text).find(v => /^\d+$/.test(v));
    if (!current || pager.children.length !== 1) throw new Error("REGISTRY_PAGINATION_CHANGED");
    const next = [...pager.querySelectorAll("a")].find(a => text(a) === String(Number(current)+1) || text(a) === "...");
    return {rows, page:Number(current), next:!!next};
  }
  async function illinois(query) {
    const inputs = key => document.querySelector(`input[data-val-property-name="${key}"]`);
    const button = await wait(() => [...document.querySelectorAll("button")].find(el => text(el) === "Search" && visible(el) && !el.disabled), 45000);
    for (const key of ["Name","Address","City","StateCode","Zip","County","FEIN","FileNumber"]) set(inputs(key), "");
    const field = query.ein ? "FEIN" : query.identifier ? "FileNumber" : "Name";
    const value = query.ein || query.identifier || query.orgName;
    set(inputs(field), value);
    // Use the normal Search button only after the page enables it. Verification
    // cookies/tokens and Kendo's internal data API are never read or forwarded.
    const grid = document.querySelector('.k-grid[id^="CharitiesPublicSearch_"]');
    if (!grid) throw new Error("REGISTRY_GRID_CHANGED");
    async function changed(action) {
      let mutated = false;
      const observer = new MutationObserver(list => { if (list.some(m => m.type === "childList")) mutated = true; });
      observer.observe(grid, { childList:true, subtree:true });
      try {
        action();
        await wait(() => mutated && ![...grid.querySelectorAll(".k-loading-mask")].some(visible) && grid.querySelector(".k-pager-info"));
      } finally { observer.disconnect(); }
    }
    await changed(() => button.click());
    const collected = [];
    let total = null;
    for (let page=0; page<10; page++) {
      const info = text(grid.querySelector(".k-pager-info"));
      const match = info.match(/(?:of\s+([\d,]+)\s+items)|(?:^No items to display$)/i);
      if (!match) throw new Error("REGISTRY_TOTAL_CHANGED");
      const count = match[1] ? Number(match[1].replaceAll(",","")) : 0;
      if (count > 100 || total !== null && total !== count) throw new Error("REGISTRY_RESULT_LIMIT");
      total = count;
      const headers = [...grid.querySelectorAll(".k-grid-header thead th")].map(h=>h.dataset.field);
      const pageRows = [...grid.querySelectorAll(".k-grid-content tbody > tr[data-uid]")];
      for (const tr of pageRows) {
        const cells = [...tr.children], val = key => text(cells[headers.indexOf(key)]);
        const row = {name:val("Name"), identifier:val("FileNumber"), street:val("Street1"), region:val("State"), postal_code:val("PostalCode"), location:[val("City"),val("State")].filter(Boolean).join(", "), detail_key:""};
        if (query.identifier && row.identifier === query.identifier) {
          tr.querySelector('button[title="View Details"]').click();
          // Identity/status establish a loaded detail. A missing filing date is
          // evidence for the master to interpret, not a transport timeout.
          let dialog;
          try {
            dialog = await wait(() => { const d=document.querySelector("#KendoWindowLevel1"); return visible(d) && d.innerText.includes("CO Number: " + query.identifier) && /FEIN:\s*\d/.test(d.innerText) && /Status:\s*\S/.test(d.innerText) && d; });
          } catch {
            const d=document.querySelector("#KendoWindowLevel1");
            throw new Error(!visible(d) ? "NY_CONNECTOR_IL_DETAIL_NOT_OPENED" : !text(d) ? "NY_CONNECTOR_IL_DETAIL_BLANK" : "NY_CONNECTOR_IL_DETAIL_IDENTITY_INCOMPLETE");
          }
          return {query, complete:true, body:dialog.innerText};
        }
        collected.push(row);
      }
      if (collected.length === total) break;
      const next = grid.querySelector('button[aria-label="Go to the next page"]');
      if (!next || next.getAttribute("aria-disabled") === "true") throw new Error("REGISTRY_PAGINATION_INCOMPLETE");
      await changed(() => next.click());
    }
    if (query.identifier || collected.length !== total) throw new Error("REGISTRY_RESULTS_INCOMPLETE");
    return {query, complete:true, total, rows:collected};
  }
  async function handle(m) {
    if (m.action === "registry-ready") return {ready:document.readyState !== "loading", url:location.href, documentId};
    if (m.action === "registry-il" && IL) return {ok:true, evidence:await illinois(m.query)};
    if (!GA) throw new Error("REGISTRY_WRONG_ORIGIN");
    if (m.action === "registry-ga-form") {
      const profession = [...document.querySelectorAll("select")].find(el=>[...el.options].some(o=>text(o)==="Charities"));
      if (!profession) throw new Error("REGISTRY_FORM_CHANGED");
      const option = [...profession.options].find(o=>text(o)==="Charities");
      if (profession.value !== option.value) { setTimeout(()=>set(profession,option.value), 0); return {ok:true, phase:"profession"}; }
      const name = document.querySelector("#t_web_lookup__full_name");
      set(name, m.query.orgName + "*");
      // New search navigation starts from a fresh blank form, no old filters.
      const search = [...document.querySelectorAll('input[type="submit"],button')].find(el=>/^(Search)$/i.test(el.value || text(el)));
      if (!search) throw new Error("REGISTRY_SEARCH_CHANGED");
      setTimeout(()=>search.click(), 0); return {ok:true, phase:"submitted"};
    }
    if (m.action === "registry-ga-rows") {
      const result = gaRows();
      if (!result) {
        const body = document.body.innerText;
        if (/No records found/i.test(body) && location.pathname === "/verification/SearchResults.aspx") return {ok:true, rows:[], page:1, next:false};
        throw new Error("REGISTRY_RESULTS_INCOMPLETE");
      }
      return {ok:true,...result};
    }
    if (m.action === "registry-ga-next") {
      const table=document.querySelector("#datagrid_results"), pager=[...table.querySelectorAll(":scope > tbody > tr")].at(-1);
      const link=[...pager.querySelectorAll("a")].find(a=>text(a)===String(m.page));
      if (!link) throw new Error("REGISTRY_PAGINATION_INCOMPLETE");
      const id=crypto.randomUUID();
      return new Promise(resolve=>{
        const receive=event=>{
          const r=event.data;
          if(event.source!==window || event.origin!==location.origin || r?.channel!=='cc-ga-public-pager-v1' || r.direction!=='response' || r.id!==id)return;
          clearTimeout(timer);window.removeEventListener('message',receive);resolve({ok:r.ok===true});
        };
        const timer=setTimeout(()=>{window.removeEventListener('message',receive);resolve({ok:false});},3000);
        window.addEventListener('message',receive);
        window.postMessage({channel:'cc-ga-public-pager-v1',direction:'request',id,page:m.page},location.origin);
      });
    }
    if (m.action === "registry-ga-detail") {
      // Serialize only public primary-license spans. Never forward forms,
      // viewstate, cookies, CAPTCHA data or associated paid-solicitor licenses.
      const all=[...document.querySelectorAll('span[id]')];
      const boundary=document.querySelector('#more_details');
      const spans=all.filter(el=>/^_ctl\d+__ctl\d+_(full_name|license_no|profession|license_type|status|issue_date|expiry|last_ren)$/.test(el.id) && (!boundary || !!(el.compareDocumentPosition(boundary)&Node.DOCUMENT_POSITION_FOLLOWING)));
      const escape=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
      const body=spans.map(el=>`<span id="${el.id}">${escape(text(el))}</span>`).join('');
      if (!body || !body.includes(m.query.identifier)) throw new Error("REGISTRY_DETAIL_INCOMPLETE");
      return {ok:true,evidence:{query:m.query,complete:true,body}};
    }
    throw new Error("REGISTRY_COMMAND_INVALID");
  }
  chrome.runtime.onMessage.addListener((m,sender,reply)=>{
    if(sender.id!==chrome.runtime.id || !m?.action?.startsWith('registry-')) return false;
    handle(m).then(reply,error=>{
      const code=error?.message||'';
      const ilReasons={REGISTRY_RESPONSE_INCOMPLETE:'NY_CONNECTOR_IL_RESPONSE_TIMEOUT',REGISTRY_RESULTS_INCOMPLETE:'NY_CONNECTOR_IL_RESULTS_INCOMPLETE',REGISTRY_TOTAL_CHANGED:'NY_CONNECTOR_IL_TOTAL_CHANGED',REGISTRY_RESULT_LIMIT:'NY_CONNECTOR_IL_RESULT_LIMIT',REGISTRY_PAGINATION_INCOMPLETE:'NY_CONNECTOR_IL_PAGINATION_INCOMPLETE'};
      reply({ok:false,reason:/^NY_CONNECTOR_IL_DETAIL_(NOT_OPENED|BLANK|IDENTITY_INCOMPLETE)$/.test(code) ? code : IL && ilReasons[code] || 'NY_CONNECTOR_INCOMPLETE'});
    });
    return true;
  });
})();
