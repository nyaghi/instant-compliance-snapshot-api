/* Public DOM collection only. Identity and status are interpreted by the master. */
(() => {
  "use strict";
  if (window !== window.top) return;
  const IL = location.origin === "https://charitable.illinoisattorneygeneral.gov";
  const GA = location.origin === "https://verify.sos.ga.gov";
  const NV = location.origin === "https://orion.nv.gov";
  const TN = location.origin === "https://tncab.tnsos.gov";
  const NC = location.origin === "https://www.sosnc.gov";
  const AL = location.origin === "https://ago.igovsolution.net";
  if (!IL && !GA && !NV && !TN && !NC && !AL) return;
  const documentId = crypto.randomUUID();
  const text = el => (el?.innerText || "").replace(/\s+/g, " ").trim();
  const visible = el => !!el && el.getClientRects().length > 0;
  function wait(fn, ms = 25000, {root = document.documentElement, action, relevant, settle = 0, sameCandidate = null, trace = () => {}} = {}) {
    // Observe before acting. Hidden-page timers may wake much later than the
    // DOM update; they are watchdogs, not the sole observers of completion.
    return new Promise((resolve, reject) => {
      const start = Date.now(), end = start + ms;
      let done = false, candidate = null, candidateAt = null, timer, settleTimer;
      const finish = (value, error) => {
        if (done) return;
        done = true; observer.disconnect(); clearTimeout(timer); clearTimeout(settleTimer);
        trace(error ? "incomplete" : "ready", Date.now()-start);
        error ? reject(error) : resolve(value);
      };
      const incomplete = () => finish(null, new Error("REGISTRY_RESPONSE_INCOMPLETE"));
      const settleCandidate = () => {
        if (done) return;
        // Only evidence observed within the original deadline can survive a
        // delayed watchdog. A later mutation invalidates this candidate.
        if (candidateAt === null || candidateAt + settle > end) return incomplete();
        try {
          const current=fn();
          if (!current || sameCandidate && !sameCandidate(candidate,current)) return incomplete();
          if (Date.now()-candidateAt < settle) return;
          finish(candidate);
        } catch (error) { finish(null, error); }
      };
      const inspect = () => {
        if (done) return;
        if (Date.now() > end) return incomplete();
        try {
          const value = fn();
          if (!value) { candidate = null; candidateAt = null; clearTimeout(settleTimer); return; }
          if (candidateAt !== null && sameCandidate?.(candidate, value)) return;
          clearTimeout(settleTimer);
          candidate = value; candidateAt = Date.now();
          trace("observed", candidateAt-start);
          if (!settle) return finish(value);
          settleTimer = setTimeout(settleCandidate, settle);
        } catch (error) { finish(null, error); }
      };
      const observer = new MutationObserver(list => {
        if (done) return;
        try { if (relevant && !relevant(list)) return; }
        catch (error) { return finish(null, error); }
        if (!sameCandidate) { candidate = null; candidateAt = null; clearTimeout(settleTimer); }
        inspect();
      });
      observer.observe(root, {childList:true, subtree:true, attributes:true, characterData:true,
        attributeFilter:["style", "class", "aria-busy", "disabled", "aria-disabled", "hidden"]});
      timer = setTimeout(() => candidateAt === null ? incomplete() : settleCandidate(), ms);
      try { action?.(); inspect(); } catch (error) { finish(null, error); }
    });
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
  async function illinois(query, trace = () => {}, formWaitMs = 45000) {
    const inputs = key => document.querySelector(`input[data-val-property-name="${key}"]`);
    const phase = name => (event, elapsed_ms) => trace({phase:name, event, elapsed_ms,
      visibility:document.visibilityState || "unknown"});
    const searchButton = () => [...document.querySelectorAll("button")].find(el => text(el) === "Search" && visible(el));
    const verificationPending = () => [...document.querySelectorAll("button")].some(el => text(el) === "Search" && !visible(el))
      && !!document.querySelector('div[id^="recaptcha_"]');
    let button;
    try {
      button = await wait(() => { const b=searchButton(); return b && !b.disabled && b; },
        verificationPending() ? formWaitMs : 45000, {trace:phase("form")});
    } catch {
      // Illinois deliberately hides all Kendo buttons until its own
      // verification callback succeeds. Observe only public DOM presence;
      // never read verification values or enable/click a hidden control.
      if (verificationPending())
        throw new Error("NY_CONNECTOR_IL_VERIFICATION_PENDING");
      const b = searchButton();
      throw new Error(!b ? "NY_CONNECTOR_IL_FORM_MISSING" : b.disabled ? "NY_CONNECTOR_IL_FORM_DISABLED" : "NY_CONNECTOR_IL_FORM_READY_TIMEOUT");
    }
    for (const key of ["Name","Address","City","StateCode","Zip","County","FEIN","FileNumber"]) set(inputs(key), "");
    const field = query.ein ? "FEIN" : query.identifier ? "FileNumber" : "Name";
    const value = query.ein || query.identifier || query.orgName;
    set(inputs(field), value);
    // Use the normal Search button only after the page enables it. Verification
    // cookies/tokens and Kendo's internal data API are never read or forwarded.
    const grid = document.querySelector('.k-grid[id^="CharitiesPublicSearch_"]');
    if (!grid) throw new Error("REGISTRY_GRID_CHANGED");
    async function changed(action) {
      let rendered = false, loadingSeen = false;
      const loading = () => [...grid.querySelectorAll(".k-loading-mask")].some(visible);
      await wait(() => {
        if (loading()) { loadingSeen = true; return false; }
        return (rendered || loadingSeen) && !!grid.querySelector(".k-pager-info");
      }, 35000, {root:grid, action, settle:300, trace:phase("results"), relevant:list => {
        // Kendo can reuse the same empty grid and toggle only loading styles.
        // Observe that cycle as well as result rendering, never accept the
        // initial empty grid merely because its pager is already present.
        const isLoading = loading();
        loadingSeen ||= isLoading;
        const contentChanged = list.some(m => ["childList", "characterData"].includes(m.type)
          && (m.target.nodeType === 1 ? m.target : m.target.parentElement)?.closest(".k-grid-content, .k-pager-info, .k-pager-numbers"));
        rendered ||= contentChanged;
        // Attribute-only loading transitions matter; unrelated row styling
        // must not continually restart the response-settling period.
        const loadingChanged = list.some(m => {
          const el = m.target.nodeType === 1 ? m.target : m.target.parentElement;
          return el?.closest(".k-loading-mask") || m.type === "childList" &&
            [...m.addedNodes, ...m.removedNodes].some(n => n.nodeType === 1 && (n.matches(".k-loading-mask") || n.querySelector(".k-loading-mask")));
        });
        return contentChanged || loadingChanged || isLoading;
      }});
    }
    await changed(() => button.click());
    // Use the registry's visible page-size menu to reduce long fallback scans.
    // This is the same public control a reviewer uses, not Kendo's data API.
    const initialInfo = text(grid.querySelector('.k-pager-info'));
    const initialCount = Number(initialInfo.match(/of\s+([\d,]+)\s+items/i)?.[1]?.replaceAll(',', '') || 0);
    if (initialCount > 1000) throw new Error('REGISTRY_RESULT_LIMIT');
    const pageSize = grid.querySelector('[role="combobox"][aria-label="Page sizes drop down"]');
    if (initialCount > 10 && pageSize && text(pageSize).replace(/\u200b/g, '') !== '100') {
      pageSize.click();
      const listId = pageSize.getAttribute('aria-controls');
      const option = await wait(() => {
        const list = listId && document.getElementById(listId);
        return list && [...list.querySelectorAll('[role="option"]')].find(el => visible(el) && text(el).replace(/\u200b/g, '') === '100');
      }, 5000, {trace:phase("page-size")});
      await changed(() => option.click());
      if (!/^1\s*-\s*\d+\s+of\s+[\d,]+\s+items$/i.test(text(grid.querySelector('.k-pager-info'))))
        throw new Error('REGISTRY_PAGINATION_INCOMPLETE');
      const resizedCount = Number(text(grid.querySelector('.k-pager-info')).match(/of\s+([\d,]+)\s+items/i)?.[1]?.replaceAll(',', '') || 0);
      if (resizedCount !== initialCount) throw new Error('REGISTRY_TOTAL_CHANGED');
    }
    const collected = [];
    let total = null;
    for (let page=0; page<100; page++) {
      const info = text(grid.querySelector(".k-pager-info"));
      const match = info.match(/(?:of\s+([\d,]+)\s+items)|(?:^No items to display$)/i);
      if (!match) throw new Error("REGISTRY_TOTAL_CHANGED");
      const count = match[1] ? Number(match[1].replaceAll(",","")) : 0;
      if (count > 1000) throw new Error("REGISTRY_RESULT_LIMIT");
      if (total !== null && total !== count) throw new Error("REGISTRY_TOTAL_CHANGED");
      total = count;
      const headers = [...grid.querySelectorAll(".k-grid-header thead th")].map(h=>h.dataset.field);
      const pageRows = [...grid.querySelectorAll(".k-grid-content tbody > tr[data-uid]")];
      for (const tr of pageRows) {
        const cells = [...tr.children], val = key => text(cells[headers.indexOf(key)]);
        const row = {name:val("Name"), identifier:val("FileNumber"), street:val("Street1"), region:val("State"), postal_code:val("PostalCode"), location:[val("City"),val("State")].filter(Boolean).join(", "), detail_key:""};
        if (query.identifier && row.identifier === query.identifier) {
          // Identity/status establish a loaded detail. A missing filing date is
          // evidence for the master to interpret, not a transport timeout.
          let body;
          const readDetail = () => { const d=document.querySelector("#KendoWindowLevel1"); return visible(d) && d.innerText.includes("CO Number: " + query.identifier) && /FEIN:\s*\d/.test(d.innerText) && /Status:\s*\S/.test(d.innerText) && d.innerText; };
          try {
            body = await wait(readDetail, 25000,
              {action:() => tr.querySelector('button[title="View Details"]').click(), trace:phase("detail")});
          } catch {
            const d=document.querySelector("#KendoWindowLevel1");
            throw new Error(!visible(d) ? "NY_CONNECTOR_IL_DETAIL_NOT_OPENED" : !text(d) ? "NY_CONNECTOR_IL_DETAIL_BLANK" : readDetail() ? "NY_CONNECTOR_IL_DETAIL_RESPONSE_TIMEOUT" : "NY_CONNECTOR_IL_DETAIL_IDENTITY_INCOMPLETE");
          }
          return {query, complete:true, body};
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
  // 29.2 candidate collector. The approved manifest does not activate Nevada.
  // It uses the same DOM observer as IL: no hidden application data, registry
  // requests, verification tokens, or status/identity decisions in the browser.
  let nvLastSearch = null;
  const nvObserved = new Map();
  const nvSearchHeaders = ["Entity Name", "NV Business Id #", "Entity No.", "Entity Type", "Registered Agent Name", "Formation Date", "Status"];
  const nvFilingHeaders = ["Filed Date", "Effective Date", "Filing Number", "Filing Type", "Source", "No. of Pages"];
  function nvTable(title, headers) {
    const tables = [...document.querySelectorAll('casex-data-table')].filter(el =>
      [...el.querySelectorAll('h4')].some(h => text(h) === title));
    if (tables.length !== 1) throw new Error("REGISTRY_NV_TABLE_INCOMPLETE");
    const table = tables[0], grid = table.querySelector('[role="grid"]');
    if (!grid || JSON.stringify([...grid.querySelectorAll('[role="columnheader"]')].map(el => el.getAttribute('aria-label'))) !== JSON.stringify(headers))
      throw new Error("REGISTRY_NV_COLUMNS_CHANGED");
    return {table, grid};
  }
  function nvPage(title, headers) {
    const {table, grid} = nvTable(title, headers);
    const rows = [...grid.querySelectorAll('tbody > tr[role="row"]')].filter(tr => tr.querySelector('[role="gridcell"]'));
    const values = rows.map(tr => {
      const cells = [...tr.querySelectorAll('[role="gridcell"]')];
      if (cells.length !== headers.length) throw new Error("REGISTRY_NV_ROW_CHANGED");
      return cells.map(cell => text(cell.querySelector('.casex-grid-responsive-data') || cell).replace(/^:\s*/, ''));
    });
    if (!rows.length) {
      if (!grid.querySelector('.k-grid-norecords') || grid.getAttribute('aria-rowcount') !== '1' || table.querySelector('kendo-datapager'))
        throw new Error("REGISTRY_NV_EMPTY_INCOMPLETE");
      return {table, rows, values, total:0, page:1, pages:1};
    }
    const info = text(table.querySelector('kendo-datapager-info')).match(/^(\d+)\s*-\s*(\d+) of (\d+) items$/);
    const pager = table.querySelector('kendo-datapager');
    const pages = pager?.getAttribute('aria-label')?.match(/^Page (\d+) of (\d+)$/);
    if (!info || !pages || Number(info[2])-Number(info[1])+1 !== rows.length || Number(info[3]) < rows.length || Number(info[3]) > 500)
      throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
    return {table, rows, values, total:Number(info[3]), page:Number(pages[1]), pages:Number(pages[2])};
  }
  async function nvChanged(action, read, deadline, {requireLoading=false, previous=null}={}) {
    let loadingSeen = false, lastParseError = '';
    const loading = () => [...document.querySelectorAll('.app-loader-pane .circle-loader')].some(visible);
    try { return await wait(() => {
      loadingSeen ||= loading();
      if (loading() || requireLoading && !loadingSeen) return false;
      try {
        const value = read(); lastParseError = '';
        if (!value || previous !== null && JSON.stringify(value.values) === previous) return false;
        return value;
      } catch (error) { lastParseError = error.message; return false; } // Partial renders are not completed responses.
    }, Math.max(1, Math.min(35000, deadline-Date.now())), {action, settle:200, relevant:mutations => {
      loadingSeen ||= loading() || mutations.some(m => [...m.addedNodes].some(n => n.nodeType === 1
        && (n.matches?.('.circle-loader, .app-loader-pane') || n.querySelector?.('.circle-loader'))));
      return mutations.some(m => {
        const el = m.target.nodeType === 1 ? m.target : m.target.parentElement;
        return el?.closest?.('casex-data-table, .app-loader-pane') || [...m.addedNodes, ...m.removedNodes].some(n => n.nodeType === 1
          && (n.matches?.('.circle-loader, .app-loader-pane, casex-data-table') || n.querySelector?.('.circle-loader, casex-data-table')));
      });
    }}); } catch (error) {
      if (error.message !== 'REGISTRY_RESPONSE_INCOMPLETE') throw error;
      throw new Error(lastParseError || (requireLoading && !loadingSeen ? 'REGISTRY_NV_SEARCH_NOT_STARTED'
        : loading() ? 'REGISTRY_NV_RESPONSE_PENDING' : 'REGISTRY_NV_RESPONSE_INCOMPLETE'));
    }
  }
  async function nvPages(title, headers, deadline, first) {
    let page = first || nvPage(title, headers);
    if (page.page !== 1) throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
    const total = page.total, collected = [];
    for (let expected=1; expected<=20; expected++) {
      if (Date.now() >= deadline || page.total !== total || page.page !== expected) throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
      for (let i=0;i<page.values.length;i++) collected.push({cells:page.values[i], node:page.rows[i], page:expected});
      if (collected.length === total && page.page === page.pages) return collected;
      const next = page.table.querySelector('button[aria-label="Go to the next page"]');
      if (collected.length >= total || !next || next.disabled || next.getAttribute('aria-disabled') === 'true')
        throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
      page = await nvChanged(() => next.click(), () => nvPage(title, headers), deadline, {previous:JSON.stringify(page.values)});
    }
    throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
  }
  async function nvSearch(query, deadline) {
    if (query?.state !== 'NV' || query.operation !== 'search' || typeof query.name !== 'string' || !query.name.trim() || query.name.length > 500
        || Object.keys(query).sort().join(',') !== 'name,operation,state') throw new Error("REGISTRY_COMMAND_INVALID");
    const business = [...document.querySelectorAll('[role="tab"]')].find(el => text(el) === 'Business');
    if (business?.getAttribute('aria-selected') !== 'true' || !location.hash.includes('screen=external-GenericFilingsSearch&tabRoute=business'))
      throw new Error("REGISTRY_WRONG_ORIGIN");
    // The worker must open an ordinary fresh search form before this command.
    // Refuse unrecognized filters instead of guessing a potentially narrower query.
    const field = suffix => document.querySelector(`input[id$="-${suffix}"]`);
    const name = field('entityName'), number = field('entityNumber'), id = field('nvBusinessId');
    if (!name || !number || !id || ![...document.querySelectorAll('[role="combobox"]')].some(el => text(el).startsWith('Starts With')))
      throw new Error("REGISTRY_NV_FORM_CHANGED");
    // Form.io redraws Search when filter inputs change. Resolve the current
    // button after that render settles, rather than clicking the old node in
    // the same turn as input/change. Unrelated mask/chat animations must not
    // keep resetting the settle clock for the same button with bound inputs.
    // This stays inside the command deadline and resets on a replaced button.
    const search = await wait(() => {
      if (field('entityName')?.value !== query.name || field('entityNumber')?.value !== '' || field('nvBusinessId')?.value !== '') return false;
      const buttons = [...document.querySelectorAll('button')].filter(el => text(el) === 'Search' && visible(el) && !el.disabled);
      return buttons.length === 1 && buttons[0];
    }, Math.max(1,Math.min(3000,deadline-Date.now())), {settle:200,sameCandidate:(prior,current)=>prior===current,action:()=>{
      if(number.value!=='')set(number,'');if(id.value!=='')set(id,'');if(name.value!==query.name)set(name,query.name);
    }});
    nvObserved.clear(); nvLastSearch = null;
    // The initial blank grid and old rows remain visible while ORION searches.
    // A completed loading cycle is mandatory, including for an empty response.
    const first = await nvChanged(() => search.click(), () => nvPage('Search Results', nvSearchHeaders), deadline, {requireLoading:true});
    const collected = await nvPages('Search Results', nvSearchHeaders, deadline, first);
    const rows = collected.map(({cells,node,page}) => {
      const [name,identifier,,entity_type,,,raw_status] = cells;
      // ORION also returns NR identifiers with an explicitly blank entity type.
      // Preserve these rows for master name filtering; never open them as an
      // issued nonprofit corporation or silently omit a potentially matching row.
      const identified = /^NV\d+$/.test(identifier) && !!entity_type
        || /^NR\d{8}-\d+$/.test(identifier) && entity_type === '';
      if (!name || !identified || !raw_status || nvObserved.has(identifier))
        throw new Error("REGISTRY_NV_RESULTS_INCOMPLETE");
      const row = {name,identifier,entity_type,raw_status};
      nvObserved.set(identifier,{...row,node,page});
      return row;
    });
    nvLastSearch = {...query};
    return {query,state:'NV',complete:true,verification_pending:false,total:rows.length,rows};
  }
  function nvFields(identifier) {
    const fields = Object.create(null);
    const wanted = ['Entity Name','NV Business ID','Entity Status','Entity Type','FEIN','Solicits Charitable Contribution?',
      'IRS Registered Name','Campaign Name','Formation Date in Nevada','Annual Renewal Due Date/Expiration Date'];
    const forms = [...document.querySelectorAll('[role="form"]')].filter(el => [...el.querySelectorAll('h4')].some(h => text(h) === 'Entity Information'));
    if (forms.length !== 1 || !location.hash.includes('screen=Manage-Business&')) return null;
    // Stop at Agent Information. Its duplicate NV Business ID/Status and Las
    // Vegas address must never overwrite nonprofit-corporation identity fields.
    for (const el of forms[0].querySelectorAll('h4, p')) {
      if (el.tagName === 'H4' && text(el) === 'Agent Information') break;
      const label = el.querySelector('strong');
      if (label && wanted.includes(text(label))) {
        if (Object.hasOwn(fields,text(label)) || el.nextElementSibling?.tagName !== 'P') throw new Error("REGISTRY_NV_DETAIL_CHANGED");
        fields[text(label)] = text(el.nextElementSibling);
      }
    }
    if (!wanted.every(k => Object.hasOwn(fields,k)) || fields['NV Business ID'] !== identifier) return null;
    return fields;
  }
  async function nvDetail(query, deadline) {
    if (query?.state !== 'NV' || query.operation !== 'detail' || !/^NV\d+$/.test(query.identifier)
        || Object.keys(query).sort().join(',') !== 'identifier,operation,state') throw new Error("REGISTRY_COMMAND_INVALID");
    const target = nvObserved.get(query.identifier), sourceQuery = nvLastSearch;
    if (!target || !sourceQuery) throw new Error("REGISTRY_NV_DETAIL_NOT_OBSERVED");
    if (!target.node.isConnected) {
      const back = [...document.querySelectorAll('button')].find(el => text(el) === 'Return To Results' && visible(el));
      if (!back) throw new Error("REGISTRY_NV_DETAIL_NOT_OBSERVED");
      // Returning from a detail mounts inputs before the search-type choices.
      // Wait for the same complete form used on initial navigation, within the
      // original command budget, before searching for the next observed record.
      await wait(() => registryDocumentReady(), Math.max(1,deadline-Date.now()), {action:()=>back.click()});
      // ORION restores the completed results and original filters. Repeating
      // Search here needlessly requires a second loading cycle that the page
      // may not emit for the same query. Reuse only the previously observed
      // result set, after checking every restored identity and status.
      const field = suffix => document.querySelector(`input[id$="-${suffix}"]`);
      if (field('entityName')?.value !== sourceQuery.name || field('entityNumber')?.value !== '' || field('nvBusinessId')?.value !== '')
        throw new Error('REGISTRY_NV_RESTORED_QUERY_CHANGED');
      let restored = await wait(() => {
        if ([...document.querySelectorAll('.app-loader-pane .circle-loader')].some(visible)) return false;
        try { const page=nvPage('Search Results',nvSearchHeaders);return page.total===nvObserved.size && page; }
        catch { return false; }
      },Math.max(1,Math.min(5000,deadline-Date.now())));
      while (restored.page > 1) {
        const previous = restored.table.querySelector('button[aria-label="Go to the previous page"]');
        if (!previous || previous.disabled) throw new Error('REGISTRY_NV_PAGINATION_INCOMPLETE');
        restored = await nvChanged(()=>previous.click(),()=>nvPage('Search Results',nvSearchHeaders),deadline,{previous:JSON.stringify(restored.values)});
      }
      const rows = await nvPages('Search Results',nvSearchHeaders,deadline,restored), restoredIds = new Set();
      if (rows.length !== nvObserved.size) throw new Error('REGISTRY_NV_RESTORED_RESULTS_CHANGED');
      for (const {cells} of rows) {
        const prior = nvObserved.get(cells[1]);
        if (!prior || restoredIds.has(cells[1]) || prior.name !== cells[0] || prior.entity_type !== cells[3] || prior.raw_status !== cells[6])
          throw new Error('REGISTRY_NV_RESTORED_RESULTS_CHANGED');
        restoredIds.add(cells[1]);
      }
      for (const {cells,node,page} of rows) nvObserved.set(cells[1],{...nvObserved.get(cells[1]),node,page});
    }
    let current = nvObserved.get(query.identifier);
    if (!current || current.name !== target.name || current.entity_type !== target.entity_type) throw new Error("REGISTRY_NV_DETAIL_CHANGED");
    let page = nvPage('Search Results',nvSearchHeaders);
    while (page.page > current.page) {
      const previous = page.table.querySelector('button[aria-label="Go to the previous page"]');
      if (!previous || previous.disabled) throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
      page = await nvChanged(()=>previous.click(),()=>nvPage('Search Results',nvSearchHeaders),deadline,{previous:JSON.stringify(page.values)});
    }
    const matches = page.values.map((cells,i)=>({cells,node:page.rows[i]})).filter(row=>row.cells[1]===query.identifier);
    if (matches.length !== 1 || matches[0].cells[0] !== target.name || matches[0].cells[3] !== target.entity_type)
      throw new Error("REGISTRY_NV_DETAIL_NOT_OBSERVED");
    const link = matches[0].node.querySelector('[role="gridcell"] a');
    if (!link || text(link) !== target.name) throw new Error("REGISTRY_NV_DETAIL_NOT_OBSERVED");
    const fields = await wait(()=>nvFields(query.identifier),Math.max(1,deadline-Date.now()),{action:()=>link.click()});
    const evidence = {query,complete:true,source_url:location.href,fields};
    try {
      const filings = await nvPages('Filing History Details',nvFilingHeaders,deadline);
      evidence.filings = {identifier:query.identifier,name:fields['Entity Name'],complete:true,total:filings.length,
        headers:nvFilingHeaders,rows:filings.map(row=>row.cells)};
    } catch {
      // Optional history failure cannot erase a fully loaded corporate status.
      evidence.filings = {complete:false};
    }
    return evidence;
  }
  const tnObserved = new Map();
  function tnPage() {
    const grids = [...document.querySelectorAll('.k-grid')].filter(el => el.closest('[id^="SearchResults_"]'));
    if (grids.length !== 1) throw new Error('REGISTRY_TN_GRID_INCOMPLETE');
    const grid = grids[0], table = grid.querySelector('table[role="grid"]');
    if (!table) throw new Error('REGISTRY_TN_GRID_INCOMPLETE');
    const columns = [...table.querySelectorAll('thead th')].map(el=>el.getAttribute('data-field'));
    const required = ['FileNumber','DisplayName','OtherNames','Status','City','StateName','RegistrationDate'];
    if (!required.every(name=>columns.filter(x=>x===name).length===1)) throw new Error('REGISTRY_TN_COLUMNS_CHANGED');
    const rows = [...table.querySelectorAll('tbody > tr')];
    const values = rows.map(tr=>{
      if (tr.children.length !== columns.length) throw new Error('REGISTRY_TN_ROW_CHANGED');
      const get = field => tr.children[columns.indexOf(field)];
      const row = {name:text(get('DisplayName')),identifier:text(get('FileNumber')),city:text(get('City')),region:text(get('StateName')),
        aliases:(get('OtherNames').innerText||'').split(/\r?\n/).map(v=>v.trim()).filter(Boolean),raw_status:text(get('Status')),
        registration_date:text(get('RegistrationDate'))};
      if (!row.name || !/^CO\d+$/.test(row.identifier) || !row.raw_status) throw new Error('REGISTRY_TN_ROW_CHANGED');
      return row;
    });
    const info = text(grid.querySelector('.k-pager-info'));
    const current = text(grid.querySelector('[aria-current="page"]'));
    if (!rows.length) {
      if (info !== 'No items to display' || current !== '0' || !text(grid).includes('No Records Available')) throw new Error('REGISTRY_TN_EMPTY_INCOMPLETE');
      return {grid,rows,values,total:0,page:1};
    }
    const count = info.match(/^(\d+)\s*-\s*(\d+) of (\d+) items$/);
    if (!count || !/^[1-9]\d*$/.test(current) || Number(count[2])-Number(count[1])+1!==rows.length || Number(count[3])>500)
      throw new Error('REGISTRY_TN_PAGINATION_INCOMPLETE');
    return {grid,rows,values,total:Number(count[3]),page:Number(current)};
  }
  async function tnChanged(action, deadline, previous=null) {
    let loadingSeen=false,lastParseError='';
    const loading=()=>[...document.querySelectorAll('[id^="SearchResults_"] .k-loading-mask')].some(visible);
    try { return await wait(()=>{
      loadingSeen ||= loading();
      if (!loadingSeen || loading()) return false;
      try { const page=tnPage();lastParseError='';return previous!==null&&JSON.stringify(page.values)===previous?false:page; }
      catch (error) { lastParseError=error.message;return false; }
    },Math.max(1,Math.min(35000,deadline-Date.now())),{action,settle:200,relevant:mutations=>{
      loadingSeen ||= loading() || mutations.some(m=>[...m.addedNodes].some(n=>n.nodeType===1
        && (n.matches?.('.k-loading-mask') || n.querySelector?.('.k-loading-mask'))));
      return mutations.some(m=>{
        const el=m.target.nodeType===1?m.target:m.target.parentElement;
        return el?.closest?.('[id^="SearchResults_"]') || [...m.addedNodes,...m.removedNodes].some(n=>n.nodeType===1
          && (n.matches?.('[id^="SearchResults_"]') || n.querySelector?.('[id^="SearchResults_"]')));
      });
    }}); } catch (error) {
      if(error.message!=='REGISTRY_RESPONSE_INCOMPLETE')throw error;
      throw new Error(lastParseError || (!loadingSeen ? 'REGISTRY_TN_SEARCH_NOT_STARTED' : loading() ? 'REGISTRY_TN_RESPONSE_PENDING' : 'REGISTRY_TN_RESPONSE_INCOMPLETE'));
    }
  }
  async function tnCloseDetail(deadline) {
    const dialog=document.querySelector('#KendoWindowLevel1');
    if (visible(dialog)) {
      const close=dialog.parentElement.querySelector('button[aria-label="Close"]');
      if (!close) throw new Error('REGISTRY_TN_DETAIL_CHANGED');
      // Kendo closes asynchronously. Do not submit the next alias while its
      // modal is still intercepting the search controls.
      await wait(()=>!visible(dialog),Math.max(1,Math.min(3000,deadline-Date.now())),{action:()=>close.click()});
    }
  }
  async function tnSearch(query,deadline) {
    if (query?.state!=='TN'||query.operation!=='search'||typeof query.name!=='string'||!query.name.trim()||query.name.length>500
        ||Object.keys(query).sort().join(',')!=='name,operation,state') throw new Error('REGISTRY_COMMAND_INVALID');
    await tnCloseDetail(deadline);
    const button=()=>[...document.querySelectorAll('button[id^="Search_"]')].find(el=>visible(el)&&!el.disabled&&text(el)==='Search');
    let search;
    try { search=await wait(button,Math.max(1,Math.min(12000,deadline-Date.now()))); }
    catch { throw new Error('NY_CONNECTOR_TN_VERIFICATION_OR_FORM_PENDING'); }
    // Normal page readiness only: never click verification or read its token.
    set(document.querySelector('input[id^="Name_"]'),query.name);
    set(document.querySelector('input[id^="Filenumber_"]'),'');
    set(document.querySelector('input[id^="City_"]'),'');
    tnObserved.clear();
    let page=await tnChanged(()=>search.click(),deadline),total=page.total;
    const rows=[];
    for(let expected=1;expected<=50;expected++) {
      if(Date.now()>=deadline||page.total!==total||page.page!==expected)throw new Error('REGISTRY_TN_PAGINATION_INCOMPLETE');
      for(let i=0;i<page.values.length;i++) {
        const row=page.values[i];
        if(tnObserved.has(row.identifier))throw new Error('REGISTRY_TN_PAGINATION_INCOMPLETE');
        tnObserved.set(row.identifier,{...row,page:expected});rows.push(row);
      }
      if(rows.length===total)return {query,state:'TN',complete:true,verification_pending:false,total,rows};
      const next=page.grid.querySelector('button[aria-label="Go to the next page"]');
      if(rows.length>total||!next||next.getAttribute('aria-disabled')==='true')throw new Error('REGISTRY_TN_PAGINATION_INCOMPLETE');
      page=await tnChanged(()=>next.click(),deadline,JSON.stringify(page.values));
    }
    throw new Error('REGISTRY_TN_PAGINATION_INCOMPLETE');
  }
  function tnFields(row) {
    const dialog=document.querySelector('#KendoWindowLevel1');
    if(!visible(dialog))return null;
    const fields={Name:text(dialog.querySelector('h2'))};
    for(const el of dialog.querySelectorAll('h4')) {
      const pair=text(el).match(/^(Status|CO Number|Registration Date|Expiration Date):\s*(.*)$/);
      if(pair) { if(Object.hasOwn(fields,pair[1]))throw new Error('REGISTRY_TN_DETAIL_CHANGED');fields[pair[1]]=pair[2]; }
    }
    if(fields['CO Number']!==row.identifier||!fields.Name||!fields.Status||!Object.hasOwn(fields,'Registration Date'))return null;
    // An absent expiration in a completed detail stays blank for master policy.
    fields['Expiration Date'] ||= '';
    const escaped=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    const suffix=new RegExp('\\s'+escaped(row.city)+'\\s+'+escaped(row.region)+'\\s+\\d{5}(?:-\\d{4})?$','i');
    const addresses=[...dialog.querySelectorAll('.col-md-6 > h4')].map(text).filter(s=>suffix.test(s));
    if(addresses.length>1)throw new Error('REGISTRY_TN_ADDRESS_AMBIGUOUS');
    fields.Address=addresses[0]||'';
    return fields;
  }
  function tnFinancials(dialog) {
    const link=[...dialog.querySelectorAll('#DetailsTabStrip > li > a')].find(el=>/^Financials \(\d+\)$/.test(text(el)));
    if(!link)throw new Error('REGISTRY_TN_FINANCIALS_INCOMPLETE');
    const count=Number(text(link).match(/\((\d+)\)/)[1]);
    if(count>500)throw new Error('REGISTRY_TN_FINANCIALS_INCOMPLETE');
    if(link.parentElement.getAttribute('aria-expanded')!=='true')link.click();
    const panel=dialog.querySelector('#DetailsTabStrip-1');
    const table=panel?.querySelector('table[role="grid"]');
    const columns=[...(table?.querySelectorAll('thead th')||[])].map(text);
    const index=columns.indexOf('Fiscal Year End');
    const rows=[...(table?.querySelectorAll('tbody > tr')||[])];
    if(index<0||rows.length!==count||columns.filter(c=>c==='Fiscal Year End').length!==1)throw new Error('REGISTRY_TN_FINANCIALS_INCOMPLETE');
    // Revenue and individual officer/contact information are not collected.
    return {financial_periods:rows.map(row=>{if(row.children.length!==columns.length)throw new Error('REGISTRY_TN_FINANCIALS_INCOMPLETE');return text(row.children[index]);}),financial_count:count};
  }
  async function tnDetail(query,deadline) {
    if(query?.state!=='TN'||query.operation!=='detail'||!/^CO\d+$/.test(query.identifier)
        ||Object.keys(query).sort().join(',')!=='identifier,operation,state')throw new Error('REGISTRY_COMMAND_INVALID');
    const selected=tnObserved.get(query.identifier);
    if(!selected)throw new Error('REGISTRY_TN_DETAIL_NOT_OBSERVED');
    await tnCloseDetail(deadline);
    let page=tnPage();
    while(page.page!==selected.page) {
      const direction=page.page>selected.page?'previous':'next';
      const button=page.grid.querySelector(`button[aria-label="Go to the ${direction} page"]`);
      if(!button||button.getAttribute('aria-disabled')==='true')throw new Error('REGISTRY_TN_PAGINATION_INCOMPLETE');
      page=await tnChanged(()=>button.click(),deadline,JSON.stringify(page.values));
    }
    const indexes=page.values.map((row,index)=>({row,index})).filter(({row})=>row.identifier===selected.identifier);
    if(indexes.length!==1||indexes[0].row.name!==selected.name)throw new Error('REGISTRY_TN_DETAIL_CHANGED');
    const buttons=[...page.rows[indexes[0].index].querySelectorAll('button')].filter(el=>text(el)==='Details');
    if(buttons.length!==1)throw new Error('REGISTRY_TN_DETAIL_NOT_OBSERVED');
    const fields=await wait(()=>tnFields(selected),Math.max(1,Math.min(25000,deadline-Date.now())),{action:()=>buttons[0].click()});
    try { Object.assign(fields,tnFinancials(document.querySelector('#KendoWindowLevel1'))); }
    catch { fields.financial_count=-1;fields.financial_periods=[]; }
    return {query,complete:true,fields};
  }
  function ncLabeled(scope, allowed) {
    const fields={};
    for(const label of scope.querySelectorAll('.para-small > .boldSpan')) {
      const key=text(label).replace(/:$/,'').trim();
      if(!allowed.includes(key))continue;
      if(Object.hasOwn(fields,key))throw new Error('REGISTRY_NC_DUPLICATE_FIELD');
      fields[key]=text(label.parentElement).slice(text(label).length).trim();
    }
    return fields;
  }
  function ncForm(query) {
    if(query?.state!=='NC'||query.operation!=='search'||typeof query.name!=='string'||!query.name.trim()||query.name.length>500)
      throw new Error('REGISTRY_NC_QUERY_INVALID');
    if(location.pathname!=='/online_services/search/by_title/search_charities')throw new Error('REGISTRY_NC_FORM_CHANGED');
    const input=document.querySelector('#SearchCriteria'),words=document.querySelector('#Words'),button=document.querySelector('#SubmitButton'),print=document.querySelector('#Print');
    const starts=words&&[...words.options].find(o=>text(o)==='Starting With');
    if(!input||!starts||!visible(button)||button.disabled||!print)throw new Error('REGISTRY_NC_FORM_CHANGED');
    set(words,starts.value);set(input,query.name);if(print.checked)print.click();
    // Dispatch the ordinary form action before acknowledging it. A deferred
    // timer in a background tab can be throttled after the worker has already
    // started waiting for the results document. NC's action starts an async
    // request, so the message reply is sent before the resulting navigation.
    button.click();return {ok:true,phase:'submitted'};
  }
  async function ncRows(query,budgetMs=45000) {
    const deadline=Date.now()+Math.max(1,Math.min(45000,budgetMs));
    if(location.pathname!=='/online_services/search/Charities_Results')throw new Error('REGISTRY_NC_RESULTS_CHANGED');
    const main=document.querySelector('main'),body=text(main);
    const count=/Records Found:\s*(\d+)\b/.exec(body),searched=/Words:\s*Starting With\s+Organization Name\s+(.+?)\s+Search Time\s/.exec(body);
    if(!count||!searched||searched[1].toLocaleLowerCase()!==query.name.replace(/\s+/g,' ').trim().toLocaleLowerCase())throw new Error('REGISTRY_NC_QUERY_CHANGED');
    const total=Number(count[1]),buttons=[...main.querySelectorAll('#resultsSection .usa-accordion__button')];
    // A larger paginated result is incomplete until every displayed record can
    // be collected. Never infer zero from an absent or partially loaded card.
    if(total>100)throw new Error('REGISTRY_NC_PAGINATION_INCOMPLETE');
    if(buttons.length!==total)throw new Error('REGISTRY_NC_RESULT_COUNT_MISMATCH');
    const rows=[],seen=new Set();
    for(const button of buttons) {
      if(Date.now()>=deadline)throw new Error('REGISTRY_NC_RESPONSE_TIMEOUT');
      const panel=document.getElementById(button.getAttribute('aria-controls'));
      if(!panel)throw new Error('REGISTRY_NC_CARD_CHANGED');
      if(button.getAttribute('aria-expanded')!=='true')button.click();
      await wait(()=>visible(panel)&&panel,Math.max(1,Math.min(3000,deadline-Date.now())));
      const fields=ncLabeled(panel,['CSL Type','Status','License','Expiration Date','Extension End Date']);
      // A license may expose multiple legal names and DBAs. They are identity
      // alternatives, not duplicate scalar status/date fields. Bind the card's
      // displayed name and license to these source-labeled names; the master
      // still decides whether any candidate belongs to the requested entity.
      const legal=[],other=[];
      for(const label of panel.querySelectorAll('.para-small > .boldSpan')) {
        const key=text(label).replace(/:$/,'').trim();
        if(!['CSL Legal Name','CSL DBA Name'].includes(key))continue;
        const value=text(label.parentElement).slice(text(label).length).trim();
        if(!value||value.length>500)throw new Error('REGISTRY_NC_CARD_CHANGED');
        (key==='CSL Legal Name'?legal:other).push(value);
      }
      const headerText=text(button.querySelector('.searchHeader'));
      const pending=fields['CSL Type']==='In-Process'&&fields.Status==='In-Process'&&!fields.License;
      const header=headerText.match(/^(.+?)\s*•\s*\(((?:SL|EX)\d+)\)$/);
      const displayName=pending?headerText:header?.[1].trim();
      const names=[...new Set([...legal,...other])];
      if(!legal.length||names.length>32||(!pending&&(!header||header[2]!==fields.License))||!names.includes(displayName))
        throw new Error('REGISTRY_NC_CARD_CHANGED');
      fields['CSL Legal Name']=legal[0];fields.display_name=displayName;fields.aliases=names.filter(n=>n!==fields.display_name);
      const links=[...panel.querySelectorAll('a[href]')].filter(a=>/^\/online_services\/search\/charities_profile\/\d+$/.test(a.getAttribute('href')));
      if(links.length!==1||!fields['CSL Legal Name']||!fields['CSL Type']||!fields.Status||(!pending&&!fields.License))throw new Error('REGISTRY_NC_CARD_CHANGED');
      const identity=pending?links[0].getAttribute('href'):fields.License;
      if(seen.has(identity))throw new Error('REGISTRY_NC_CARD_CHANGED');
      if(pending)fields.License='';
      if(!Object.hasOwn(fields,'Expiration Date')) {
        if(!pending&&fields['CSL Type']!=='CSL Exempt Organization')throw new Error('REGISTRY_NC_CARD_INCOMPLETE');
        fields['Expiration Date']='';
      }
      fields.profile_url=new URL(links[0].getAttribute('href'),location.origin).href;
      seen.add(identity);rows.push(fields);
    }
    return {ok:true,evidence:{state:'NC',query,complete:true,verification_pending:false,total,rows}};
  }
  function ncProfile(query) {
    if(location.href!==query.url||!/^\/online_services\/search\/charities_profile\/\d+$/.test(location.pathname))throw new Error('REGISTRY_NC_PROFILE_CHANGED');
    const main=document.querySelector('main'),fields=ncLabeled(main,['Name','Status','Registration #','Expiration Date','Last Application Date','Extension End Date']);
    if(!fields.Name||!fields.Status||fields['Registration #']!==query.identifier||!Object.hasOwn(fields,'Last Application Date'))throw new Error('REGISTRY_NC_PROFILE_INCOMPLETE');
    if(!Object.hasOwn(fields,'Expiration Date')) {
      if(!/^EX\d+$/.test(query.identifier))throw new Error('REGISTRY_NC_PROFILE_INCOMPLETE');
      fields['Expiration Date']='';
    }
    const addresses=[...main.querySelectorAll('.para-small > .boldSpan')].filter(el=>text(el)==='Address');
    if(addresses.length!==1)throw new Error('REGISTRY_NC_ADDRESS_INCOMPLETE');
    // The address label is also a direct span inside a .para-small container.
    // Read only the nested address block, never the outer label/contact fields.
    const spans=[...addresses[0].parentElement.querySelectorAll(':scope > .para-small > span')].map(text);
    if(spans.length!==4)throw new Error('REGISTRY_NC_ADDRESS_INCOMPLETE');
    [fields.Street,fields.City,fields.State,fields.Zip]=spans;
    fields.profile_url=location.href;
    const links=[...main.querySelectorAll('a[href]')].filter(a=>a.getAttribute('href')===location.pathname.replace('charities_profile','charities_filings'));
    return {ok:true,evidence:{query,complete:true,fields},filings_url:links.length===1?new URL(links[0].getAttribute('href'),location.origin).href:null};
  }
  function ncFilings(query) {
    if(location.href!==query.url.replace('/charities_profile/','/charities_filings/'))throw new Error('REGISTRY_NC_FILINGS_CHANGED');
    const lists=[...document.querySelectorAll('main article section.usa-section--singleEntry > ul')];
    if(lists.length!==1)throw new Error('REGISTRY_NC_FILINGS_INCOMPLETE');
    const nodes=[...lists[0].children];
    if(nodes.length>500)throw new Error('REGISTRY_NC_FILINGS_LIMIT');
    const rows=nodes.map(node=>{
      const type=[...node.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
      // Some filing rows also contain an "Upload an Attachment" link in a
      // second span. It is not a date, and must not invalidate the whole history.
      const dates=[...node.querySelectorAll(':scope > ul > li > span')].filter(el=>!el.querySelector('a'));
      if(node.tagName!=='LI'||!type||dates.length!==1||!/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(text(dates[0])))throw new Error('REGISTRY_NC_FILINGS_INCOMPLETE');
      return {type,date:text(dates[0])};
    });
    return {ok:true,filings:{url:location.href,complete:true,rows}};
  }
  const alHeaders = ['Name','License/Registration#','Status','Registration Type','Issued Date','Expiration Date','Address','City','State','Zip','Print'];
  function alPage() {
    const table = document.querySelector('table.table.table-responsive.table-bordered');
    if (!table || !visible(table)) return null;
    const headers = [...table.querySelectorAll('thead tr:first-child th')].map(text);
    if (JSON.stringify(headers) !== JSON.stringify(alHeaders)) throw new Error('REGISTRY_COLUMNS_CHANGED');
    if ([...table.querySelectorAll('thead input')].some(input=>input.value.trim())) throw new Error('REGISTRY_FILTER_CHANGED');
    const rows = [...table.querySelectorAll('tbody tr.grid_tr')].map(tr=>{
      const cells = [...tr.children];
      if (cells.length !== headers.length || cells.some(el=>el.tagName !== 'TD')) throw new Error('REGISTRY_ROW_CHANGED');
      return cells.map((el,i)=>i===10?'':text(el));
    });
    const number = id => { const s=text(document.getElementById(id)); if (!/^\d+$/.test(s)) throw new Error('REGISTRY_PAGINATION_INCOMPLETE'); return Number(s); };
    const from=number('pgfrm'),to=number('pgto'),total=number('tot_pgs'),pages=number('totpg');
    const selector=table.querySelector('tfoot select[aria-label="Page"]'),page=Number(selector?.value);
    if (!Number.isInteger(page) || page<1 || page>pages || pages>100 || total>500 || !rows.length || from<1 || to<from
        || to>total || to-from+1!==rows.length || (page===1 && from!==1) || (page===pages && to!==total))
      throw new Error('REGISTRY_PAGINATION_INCOMPLETE');
    return {table,rows,headers,from,to,total,page,pages,selector};
  }
  async function alSearch(query, deadline) {
    if (location.pathname !== '/online/Lookups/Business.aspx') throw new Error('REGISTRY_WRONG_ORIGIN');
    const input = id=>document.getElementById('ctl00_cntbdy_'+id);
    // The connector never reads a challenge image, solves it, supplies a code,
    // or forwards verification material. A user must verify the public page.
    if (!input('txt_verify')?.value.trim()) throw new Error('NY_CONNECTOR_AL_VERIFICATION_REQUIRED');
    const oldAlert = document.querySelector('#altdialog');
    if (visible(oldAlert)) {
      const ok=[...document.querySelectorAll('.ui-dialog button')].find(b=>visible(b) && text(b)==='Ok');
      if (!ok) throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
      ok.click();
      if (visible(oldAlert)) throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
    }
    set(input('txt_linum'),''); set(input('txtcity'),'');
    set(input('ddl_county'),'-1'); set(input('ddl_lictype'),'-1'); set(input('txt_businessname'),query.name);
    const button=input('btn_search');
    if (!button || !visible(button) || button.disabled) throw new Error('REGISTRY_FORM_CHANGED');
    const oldTable=document.querySelector('table.table.table-responsive.table-bordered');
    const oldRows=oldTable?[...oldTable.querySelectorAll('tbody tr.grid_tr')]:[];
    const page=await wait(()=>{
      if (input('txt_businessname')?.value!==query.name || input('txt_linum')?.value || input('txtcity')?.value
          || input('ddl_county')?.value!=='-1' || input('ddl_lictype')?.value!=='-1') throw new Error('REGISTRY_FILTER_CHANGED');
      const alert=document.querySelector('#altdialog');
      if (visible(alert)) {
        const message=text(alert).replace(/^[•\s]+/,'');
        if (message==='No Records Found') return {rows:[],headers:alHeaders,total:0};
        if (/verif|captcha|code/i.test(message)) throw new Error('NY_CONNECTOR_AL_VERIFICATION_REQUIRED');
        throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
      }
      const table=document.querySelector('table.table.table-responsive.table-bordered');
      const currentRows=table?[...table.querySelectorAll('tbody tr.grid_tr')]:[];
      if (!table || (table===oldTable && currentRows.length===oldRows.length && currentRows.every((r,i)=>r===oldRows[i]))) return null;
      return alPage();
    },Math.max(1,deadline-Date.now()),{action:()=>button.click(),settle:150});
    if (!page.total) return {state:'AL',query,complete:true,verification_pending:false,headers:alHeaders,rows:[],total:0};
    const rows=[...page.rows]; let current=page;
    while (current.page < current.pages) {
      if (Date.now()>=deadline) throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
      const target=current.page+1,priorEnd=current.to;
      if (![...current.selector.options].some(o=>o.value===String(target))) throw new Error('REGISTRY_PAGINATION_INCOMPLETE');
      const oldNodes=[...current.table.querySelectorAll('tbody tr.grid_tr')];
      current=await wait(()=>{
        const next=alPage();
        if (!next || next.page!==target || next.from!==priorEnd+1) return null;
        const nodes=[...next.table.querySelectorAll('tbody tr.grid_tr')];
        if (nodes.length===oldNodes.length && nodes.every((r,i)=>r===oldNodes[i])) return null;
        if (next.total!==page.total || next.pages!==page.pages) throw new Error('REGISTRY_TOTAL_CHANGED');
        return next;
      },Math.max(1,deadline-Date.now()),{action:()=>set(current.selector,String(target)),settle:150});
      rows.push(...current.rows);
    }
    if (rows.length!==page.total || new Set(rows.map(r=>r[1])).size!==rows.length) throw new Error('REGISTRY_TOTAL_CHANGED');
    return {state:'AL',query,complete:true,verification_pending:false,headers:page.headers,rows,total:page.total};
  }
  function registryDocumentReady() {
    if (document.readyState === 'loading') return false;
    // A loaded verification/shell document is not a loaded registry form.
    // Observe normal page readiness; do not operate any human challenge.
    if (NC) {
      if (location.pathname === '/online_services/search/by_title/search_charities') {
        // The HTML form can precede the scripts used by its ordinary inline
        // submit action. Do not acknowledge a click against that partial page.
        if (document.readyState !== 'complete') return false;
        const button=document.querySelector('#SubmitButton'),words=document.querySelector('#Words');
        return !!(document.querySelector('#SearchCriteria') && document.querySelector('#Print')
          && words && [...words.options].some(o=>text(o)==='Starting With') && visible(button) && !button.disabled);
      }
      if (location.pathname === '/online_services/search/Charities_Results')
        return /Records Found:\s*\d+\b/.test(text(document.querySelector('main')));
      if (/\/charities_profile\/\d+$/.test(location.pathname))
        return /Registration\s*#\s*:\s*(SL|EX)\d+/.test(text(document.querySelector('main')));
      if (/\/charities_filings\/\d+$/.test(location.pathname))
        return document.querySelectorAll('main article section.usa-section--singleEntry > ul').length===1;
      return false;
    }
    if (NV && location.hash.includes('screen=external-GenericFilingsSearch')) {
      const tab=[...document.querySelectorAll('[role="tab"]')].find(el=>text(el)==='Business');
      return tab?.getAttribute('aria-selected')==='true'
        && ![...document.querySelectorAll('.app-loader-pane .circle-loader')].some(visible)
        && ['entityName','entityNumber','nvBusinessId'].every(s=>document.querySelector(`input[id$="-${s}"]`))
        && [...document.querySelectorAll('[role="combobox"]')].some(el=>text(el).startsWith('Starts With'))
        && [...document.querySelectorAll('button')].some(el=>text(el)==='Search' && visible(el) && !el.disabled);
    }
    return true;
  }
  async function handle(m) {
    if (AL && m.action==='registry-al') {
      if (m.query?.state!=='AL' || m.query.operation!=='search') throw new Error('REGISTRY_COMMAND_INVALID');
      return {ok:true,evidence:await alSearch(m.query,Date.now()+Math.min(45000,Number.isFinite(m.budgetMs)&&m.budgetMs>0?m.budgetMs:45000))};
    }
    if (m.action === "registry-ready") return {ready:registryDocumentReady(), url:location.href, documentId,
      ...(NC ? {verification_pending:/^Just a moment/i.test(document.title||'')
        && /Performing security verification|verifies you are not a bot/i.test(text(document.body))} : {})};
    if (NC) {
      if(m.action==='registry-nc-form')return ncForm(m.query);
      if(m.action==='registry-nc-rows')return ncRows(m.query,m.budgetMs);
      if(m.action==='registry-nc-profile')return ncProfile(m.query);
      if(m.action==='registry-nc-filings')return ncFilings(m.query);
      throw new Error('REGISTRY_COMMAND_INVALID');
    }
    if (TN && m.action === 'registry-tn') {
      const deadline=Date.now()+Math.min(45000,Number.isFinite(m.budgetMs)&&m.budgetMs>0?m.budgetMs:45000);
      return {ok:true,evidence:m.query?.operation==='search'?await tnSearch(m.query,deadline):await tnDetail(m.query,deadline)};
    }
    if (NV && m.action === 'registry-nv') {
      const deadline = Date.now() + Math.min(45000, Number.isFinite(m.budgetMs) && m.budgetMs > 0 ? m.budgetMs : 45000);
      const evidence = m.query?.operation === 'search' ? await nvSearch(m.query,deadline) : await nvDetail(m.query,deadline);
      return {ok:true,evidence};
    }
    if (m.action === "registry-il" && IL) {
      const diagnostics = [];
      try { return {ok:true, evidence:await illinois(m.query, entry => { if (diagnostics.length < 32) diagnostics.push(entry); }, m.formWaitMs === 12000 ? 12000 : 45000), diagnostics}; }
      catch (error) { error.diagnostics = diagnostics; throw error; }
    }
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
      // A blank identifier is a real legacy exemption, but requires the
      // selected public name. Master validates its explicit exemption fields.
      if (!body || (m.query.identifier ? !body.includes(m.query.identifier) : !m.query.record_name || !spans.some(el=>el.id.endsWith('_full_name') && text(el)===m.query.record_name))) throw new Error("REGISTRY_DETAIL_INCOMPLETE");
      return {ok:true,evidence:{query:m.query,complete:true,body}};
    }
    throw new Error("REGISTRY_COMMAND_INVALID");
  }
  chrome.runtime.onMessage.addListener((m,sender,reply)=>{
    if(sender.id!==chrome.runtime.id || !m?.action?.startsWith('registry-')) return false;
    handle(m).then(reply,error=>{
      const code=error?.message||'';
      const trialReason=(NC||NV||TN) && /^REGISTRY_(?:(?:NC|NV|TN)_[A-Z_]+|WRONG_ORIGIN|COMMAND_INVALID|RESPONSE_INCOMPLETE)$/.test(code)
        ? 'NY_CONNECTOR_'+code : null;
      const ilReasons={REGISTRY_RESPONSE_INCOMPLETE:'NY_CONNECTOR_IL_RESPONSE_TIMEOUT',REGISTRY_RESULTS_INCOMPLETE:'NY_CONNECTOR_IL_RESULTS_INCOMPLETE',REGISTRY_TOTAL_CHANGED:'NY_CONNECTOR_IL_TOTAL_CHANGED',REGISTRY_RESULT_LIMIT:'NY_CONNECTOR_IL_RESULT_LIMIT',REGISTRY_PAGINATION_INCOMPLETE:'NY_CONNECTOR_IL_PAGINATION_INCOMPLETE'};
      reply({ok:false,reason:trialReason || (AL && code==='NY_CONNECTOR_AL_VERIFICATION_REQUIRED' ? code : TN && code==='NY_CONNECTOR_TN_VERIFICATION_OR_FORM_PENDING' ? code : /^NY_CONNECTOR_IL_(?:VERIFICATION_PENDING|FORM_READY_TIMEOUT|FORM_DISABLED|FORM_MISSING|DETAIL_(?:NOT_OPENED|BLANK|IDENTITY_INCOMPLETE|RESPONSE_TIMEOUT))$/.test(code) ? code : IL && ilReasons[code] || 'NY_CONNECTOR_INCOMPLETE'),
        ...(IL && error.diagnostics ? {diagnostics:error.diagnostics} : {})});
    });
    return true;
  });
})();
