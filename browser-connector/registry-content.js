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
  const NM = location.origin === "https://secure.nmdoj.gov";
  if (!IL && !GA && !NV && !TN && !NC && !AL && !NM) return;
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
        // ORION can finish restoring its Business tab/search choice using
        // only attributes. Those are inputs to registryDocumentReady; missing
        // their mutation leaves a complete form waiting until the watchdog.
        attributeFilter:["style", "class", "aria-busy", "disabled", "aria-disabled", "hidden",
          ...(NV ? ["aria-selected", "data-value"] : [])]});
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
      button = await wait(() => {
        const b=searchButton();
        if (b && !b.disabled) return b;
        // Hand the actual hidden verification form to the owned-tab visibility
        // recovery immediately. The widget can arrive after the first DOM
        // inspection; do not spend most of Sales waiting in a hidden tab.
        if (formWaitMs === 0 && verificationPending())
          throw new Error("NY_CONNECTOR_IL_VERIFICATION_PENDING");
        return false;
      }, formWaitMs === 0 ? 45000 : verificationPending() ? formWaitMs : 45000, {trace:phase("form")});
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
  let nvLastSearchMode = 'STARTS_WITH';
  const nvObserved = new Map();
  const nvTrace = (phase, detail={}) => console.info('CharityClarity NV collector', JSON.stringify({phase,...detail}));
  const nvSearchHeaders = ["Entity Name", "NV Business Id #", "Entity No.", "Entity Type", "Registered Agent Name", "Formation Date", "Status"];
  const nvFilingHeaders = ["Filed Date", "Effective Date", "Filing Number", "Filing Type", "Source", "No. of Pages"];
  function nvSearchModeSelected(mode) {
    const label = mode === 'EXACT_MATCH' ? 'Exact Match' : 'Starts With';
    return [...document.querySelectorAll('[role="combobox"]')].some(el => {
      if (text(el).startsWith(label)) return true;
      // ORION can restore the selected public choice using its enum label.
      // Require that choice's DOM identity as well as the displayed label;
      // a partial control or another search mode is not a ready Starts With.
      const selected = el.querySelector?.('.choices__list--single [data-item][aria-selected="true"]');
      return new RegExp('^'+mode+'(?:\\s|$)').test(text(el))
        && selected?.getAttribute('data-value') === mode
        && !!selected.querySelector(`button[aria-label="Remove item: '${mode}'"]`);
    });
  }
  const nvStartsWithSelected = () => nvSearchModeSelected('STARTS_WITH');
  async function nvSelectSearchMode(mode, deadline) {
    if (!['STARTS_WITH','EXACT_MATCH'].includes(mode)) throw new Error('REGISTRY_COMMAND_INVALID');
    if (nvSearchModeSelected(mode)) return;
    const combos=[...document.querySelectorAll('[role="combobox"]')].filter(el=>el.querySelector('select[name="data[searchType]"]'));
    if (combos.length!==1) throw new Error('REGISTRY_NV_FORM_CHANGED');
    const combo=combos[0];
    const option=await wait(()=>{
      const label=mode==='EXACT_MATCH'?'Exact Match':'Starts With';
      const options=[...combo.querySelectorAll('[role="option"]')].filter(el=>el.getAttribute('data-value')===mode
        && (el.textContent||'').replace(/\s+/g,' ').trim()===label && el.getAttribute('aria-disabled')!=='true');
      return options.length===1&&options[0];
    },Math.max(1,Math.min(3000,deadline-Date.now()))).catch(error=>{
      if(error.message==='REGISTRY_RESPONSE_INCOMPLETE')throw new Error('REGISTRY_NV_MODE_MENU_INCOMPLETE');
      throw error;
    });
    // The ordinary public choice is present in the collapsed dropdown's DOM.
    // Choices selects on mousedown; opening its animated menu is unnecessary.
    // A subsequent click can reopen that menu after selection and race the
    // next search. Select the labelled option once and verify the rendered
    // value. No Choices instance, application state or private API is used.
    await wait(()=>nvSearchModeSelected(mode),Math.max(1,Math.min(3000,deadline-Date.now())),{action:()=>{
      option.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,button:0,view:window}));
    },settle:200,sameCandidate:(prior,current)=>prior===current}).catch(error=>{
      if(error.message==='REGISTRY_RESPONSE_INCOMPLETE')throw new Error('REGISTRY_NV_MODE_NOT_SELECTED');
      throw error;
    });
    nvTrace('mode-selected',{mode});
  }
  function nvPublicRow(cells) {
    const [name,businessId,entity_number,entity_type,,,raw_status] = cells;
    const missingId = businessId === '' && /^E\d{7,14}-\d$/.test(entity_number) && !!entity_type;
    const identifier = missingId ? entity_number : businessId;
    const identified = /^NV\d+$/.test(businessId) && !!entity_type
      || /^(?:NR|C)\d{8}-\d+$/.test(businessId) && entity_number === businessId && entity_type === '' || missingId;
    // A completed ORION row can have an explicitly blank Status cell. An
    // issued NV identity and entity type still let the master reject an
    // unrelated company or inspect a matching detail; the blank is no status.
    if (!name || !identified || !raw_status && !(/^NV\d+$/.test(businessId) && !!entity_type))
      throw new Error('REGISTRY_NV_RESULTS_INCOMPLETE');
    return {name,identifier,entity_type,raw_status,
      ...(missingId ? {entity_number,business_identifier_missing:true} : {})};
  }
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
    // A settled public history can contain an unlabelled legacy filing (e.g.
    // a dated, numbered Walk-in filing with a page count). Preserve that row
    // with its blank type; do not invent a CSR or reject the other explicit
    // CSR rows. Placeholder rows still lack the required filing identity.
    if (title === 'Filing History Details' && values.some(cells => !cells[0] || !cells[2]
        || !cells[3] && (!cells[4] || !/^\d+$/.test(cells[5]))))
      throw new Error('REGISTRY_NV_FILINGS_INCOMPLETE');
    if (!rows.length) {
      if (!grid.querySelector('.k-grid-norecords') || grid.getAttribute('aria-rowcount') !== '1' || table.querySelector('kendo-datapager'))
        throw new Error("REGISTRY_NV_EMPTY_INCOMPLETE");
      return {table, rows, values, total:0, page:1, pages:1};
    }
    const info = text(table.querySelector('kendo-datapager-info')).match(/^(\d+)\s*-\s*(\d+) of (\d+) items$/);
    const pager = table.querySelector('kendo-datapager');
    const pages = pager?.getAttribute('aria-label')?.match(/^Page (\d+) of (\d+)$/);
    const maximum = title === 'Search Results' ? 10000 : 500;
    if (!info || !pages || Number(info[2])-Number(info[1])+1 !== rows.length || Number(info[3]) < rows.length || Number(info[3]) > maximum)
      throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
    return {table, rows, values, total:Number(info[3]), page:Number(pages[1]), pages:Number(pages[2])};
  }
  async function nvChanged(action, read, deadline, {requireLoading=false, previous=null, retryNotStarted=null, settle=200, pendingGraceMs=0}={}) {
    let loadingSeen = false, lastParseError = '', retryTimer;
    const responseEnd = Math.min(deadline, Date.now()+35000+pendingGraceMs);
    const loading = () => [...document.querySelectorAll('.app-loader-pane .circle-loader')].some(visible);
    const start = () => {
      action();
      // A fresh ORION form can redraw without submitting the first Search.
      // Retry that read-only action once, only if no loading cycle has begun.
      // Keep observing throughout; never restart a pending request or its budget.
      if (requireLoading && retryNotStarted) retryTimer = setTimeout(() => {
        if (Date.now() >= deadline || loadingSeen || loading()) return;
        try { retryNotStarted(); } catch (error) { lastParseError=error.message; }
      }, Math.min(3000, Math.max(1, deadline-Date.now())));
    };
    const ready = () => {
      loadingSeen ||= loading();
      if (loading() || requireLoading && !loadingSeen) return false;
      try {
        const value = read(); lastParseError = '';
        if (!value || previous !== null && JSON.stringify(value.values) === previous) return false;
        return value;
      } catch (error) { lastParseError = error.message; return false; } // Partial renders are not completed responses.
    };
    const relevant = mutations => {
      loadingSeen ||= loading() || mutations.some(m => [...m.addedNodes].some(n => n.nodeType === 1
        && (n.matches?.('.circle-loader, .app-loader-pane') || n.querySelector?.('.circle-loader'))));
      return mutations.some(m => {
        const el = m.target.nodeType === 1 ? m.target : m.target.parentElement;
        return el?.closest?.('casex-data-table, .app-loader-pane') || [...m.addedNodes, ...m.removedNodes].some(n => n.nodeType === 1
          && (n.matches?.('.circle-loader, .app-loader-pane, casex-data-table') || n.querySelector?.('.circle-loader, casex-data-table')));
      });
    };
    try {
      try { return await wait(ready,Math.max(1,Math.min(35000,deadline-Date.now())),{action:start,settle,relevant}); }
      catch (error) {
        // Only a search that is visibly still loading receives this margin.
        // Observe the same request; do not click again, reset its deadline,
        // extend Sales, or add time to paging and other registry operations.
        if (error.message !== 'REGISTRY_RESPONSE_INCOMPLETE' || !pendingGraceMs
            || !loadingSeen || !loading() || Date.now() >= responseEnd) throw error;
        nvTrace('search-response-grace',{remaining_ms:responseEnd-Date.now()});
        return await wait(ready,responseEnd-Date.now(),{settle,relevant});
      }
    } catch (error) {
      if (error.message !== 'REGISTRY_RESPONSE_INCOMPLETE') throw error;
      throw new Error(lastParseError || (requireLoading && !loadingSeen ? 'REGISTRY_NV_SEARCH_NOT_STARTED'
        : loading() ? 'REGISTRY_NV_RESPONSE_PENDING' : 'REGISTRY_NV_RESPONSE_INCOMPLETE'));
    } finally { clearTimeout(retryTimer); }
  }
  async function nvPages(title, headers, deadline, first) {
    let page = first || nvPage(title, headers);
    if (page.page !== 1) throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
    const total = page.total, collected = [];
    const maximumPages = title === 'Search Results' ? 400 : 20;
    for (let expected=1; expected<=maximumPages; expected++) {
      if (Date.now() >= deadline || page.total !== total || page.page !== expected) throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
      for (let i=0;i<page.values.length;i++) collected.push({cells:page.values[i], node:page.rows[i], page:expected});
      if (expected<=2 || expected===page.pages) nvTrace('page-collected',{page:expected,pages:page.pages,rows:collected.length,total});
      if (collected.length === total && page.page === page.pages) return collected;
      const next = page.table.querySelector('button[aria-label="Go to the next page"]');
      if (collected.length >= total || !next || next.disabled || next.getAttribute('aria-disabled') === 'true')
        throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
      page = await nvChanged(() => next.click(), () => {
        const value=nvPage(title,headers);
        if(value.page!==expected+1 || value.total!==total)throw new Error('REGISTRY_NV_PAGINATION_INCOMPLETE');
        if(title==='Search Results')value.values.forEach(nvPublicRow);
        if(title==='Filing History Details') {
          // ORION updates the pager before replacing all filing rows. An old
          // row on the next page must keep waiting, rather than produce a
          // repeated filing that the master correctly rejects as incomplete.
          const seen=new Set(collected.map(row=>row.cells[2]));
          const nextIds=value.values.map(cells=>cells[2]);
          if(nextIds.some(id=>seen.has(id)) || new Set(nextIds).size!==nextIds.length)
            throw new Error('REGISTRY_NV_FILINGS_INCOMPLETE');
        }
        return value;
      }, deadline, {previous:JSON.stringify(page.values),settle:0});
    }
    throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
  }
  async function nvExpandSearchPage(page, deadline, title='Search Results', headers=nvSearchHeaders) {
    if (page.pages <= 1) return page;
    const selector = 'kendo-datapager [role="combobox"][aria-label="items per page"]';
    const combo = page.table.querySelector(selector);
    if (!combo || !visible(combo)) return page;
    const size = Number(text(combo.querySelector('.k-input-value-text')));
    const wanted = page.total <= 50 ? 50 : 100;
    if (!(title==='Filing History Details' ? [10,25,50,100] : [25,50,100]).includes(size)) throw new Error('REGISTRY_NV_PAGE_SIZE_INCOMPLETE');
    if (size >= wanted) return page;
    // ORION's 25-row pager has returned fewer final-page rows than its total.
    // Use its ordinary larger-page control, then still require every reported
    // row. Never reinterpret a short page as a complete negative search.
    const option = await wait(() => {
      const listId = combo.getAttribute('aria-controls');
      const list = listId && document.getElementById(listId);
      if (!list || !visible(list) || list.getAttribute('role') !== 'listbox') return false;
      const matches = [...list.querySelectorAll('[role="option"]')].filter(el => text(el) === String(wanted) && visible(el));
      return matches.length === 1 && matches[0];
    },Math.max(1,Math.min(3000,deadline-Date.now())),{action:()=>combo.click()}).catch(error=>{
      if(error.message==='REGISTRY_RESPONSE_INCOMPLETE')throw new Error('REGISTRY_NV_PAGE_SIZE_MENU_INCOMPLETE');
      throw error;
    });
    return nvChanged(()=>option.click(),()=>{
      const fresh=nvPage(title,headers), current=fresh.table.querySelector(selector);
      if (!current || Number(text(current.querySelector('.k-input-value-text'))) !== wanted
          || fresh.total !== page.total || fresh.page !== 1 || fresh.pages !== Math.ceil(page.total/wanted)
          || fresh.values.length !== Math.min(wanted,page.total)) return false;
      return fresh;
    },deadline,{previous:JSON.stringify(page.values)});
  }
  async function nvReturnSearch(deadline) {
    const onSearch=()=>location.hash.includes('screen=external-GenericFilingsSearch&tabRoute=business');
    if (!onSearch()) {
      const reservation=location.hash.includes('screen=NameReservationDetails&');
      if (!reservation&&!location.hash.includes('screen=Manage-Business&')) throw new Error('REGISTRY_WRONG_ORIGIN');
      // The ordinary results return preserves the mounted Business form.
      // Return To Search resets ORION's whole search screen, including its
      // loader and asynchronous search-type hydration, for every new alias.
      // A fresh query below still clears all filters and requires its own
      // completed response; restored rows cannot establish a new result.
      const available=[...document.querySelectorAll('button')].filter(el=>visible(el)&&!el.disabled);
      const restored=reservation?[]:available.filter(el=>text(el)==='Return To Results');
      const buttons=restored.length?restored:available.filter(el=>text(el)===(reservation?'Back':'Return To Search'));
      if (buttons.length!==1) throw new Error('REGISTRY_NV_RETURN_SEARCH_MISSING');
      // Follow the public app's own reset/navigation action. Assigning a hash
      // alone can retain a partially restored search form after a detail.
      await wait(()=>onSearch()&&registryDocumentReady(),Math.max(1,deadline-Date.now()),{action:()=>buttons[0].click()}).catch(error=>{
        if(error.message==='REGISTRY_RESPONSE_INCOMPLETE')throw new Error('REGISTRY_NV_RETURN_READY_TIMEOUT');
        throw error;
      });
    } else await wait(()=>registryDocumentReady(),Math.max(1,deadline-Date.now())).catch(error=>{
      if(error.message==='REGISTRY_RESPONSE_INCOMPLETE')throw new Error('REGISTRY_NV_RETURN_READY_TIMEOUT');
      throw error;
    });
    return {ok:true};
  }
  async function nvSearch(query, deadline) {
    if (query?.state !== 'NV' || query.operation !== 'search' || typeof query.name !== 'string' || !query.name.trim() || query.name.length > 500
        || !(['name,operation,state','exact_above,name,operation,state'].includes(Object.keys(query).sort().join(',')))
        || Object.hasOwn(query,'exact_above')&&query.exact_above!==20) throw new Error("REGISTRY_COMMAND_INVALID");
    nvTrace('search-started',{name:query.name});
    const business = [...document.querySelectorAll('[role="tab"]')].find(el => text(el) === 'Business');
    if (business?.getAttribute('aria-selected') !== 'true' || !location.hash.includes('screen=external-GenericFilingsSearch&tabRoute=business'))
      throw new Error("REGISTRY_WRONG_ORIGIN");
    // The worker must open an ordinary fresh search form before this command.
    // Refuse unrecognized filters instead of guessing a potentially narrower query.
    const field = suffix => document.querySelector(`input[id$="-${suffix}"]`);
    const name = field('entityName'), number = field('entityNumber'), id = field('nvBusinessId');
    if (!name || !number || !id || !(nvStartsWithSelected()||nvSearchModeSelected('EXACT_MATCH')))
      throw new Error("REGISTRY_NV_FORM_CHANGED");
    await nvSelectSearchMode('STARTS_WITH',deadline);
    // Form.io redraws Search when filter inputs change. Resolve the current
    // button after that render settles, rather than clicking the old node in
    // the same turn as input/change. Unrelated mask/chat animations must not
    // keep resetting the settle clock for the same button with bound inputs.
    // This stays inside the command deadline and resets on a replaced button.
    const bindSearch = () => wait(() => {
      // Filter changes can replace all three inputs. Rebind only changed
      // values to the current nodes before observing the settled button.
      for (const [suffix,value] of [['entityNumber',''],['nvBusinessId',''],['entityName',query.name]]) {
        const input=field(suffix);
        if(!input)return false;
        if(input.value!==value){set(input,value);return false;}
      }
      if (field('entityName')?.value !== query.name || field('entityNumber')?.value !== '' || field('nvBusinessId')?.value !== '') return false;
      const buttons = [...document.querySelectorAll('button')].filter(el => text(el) === 'Search' && visible(el) && !el.disabled);
      return buttons.length === 1 && buttons[0];
    }, Math.max(1,Math.min(3000,deadline-Date.now())), {settle:200,sameCandidate:(prior,current)=>prior===current,action:()=>{
      for (const [suffix,value] of [['entityNumber',''],['nvBusinessId',''],['entityName',query.name]]) {
        const input=field(suffix);if(!input)throw new Error('REGISTRY_NV_FORM_CHANGED');
        if(input.value!==value)set(input,value);
      }
    }}).catch(error=>{
      if(error.message==='REGISTRY_RESPONSE_INCOMPLETE')throw new Error('REGISTRY_NV_FORM_NOT_SETTLED');
      throw error;
    });
    nvObserved.clear(); nvLastSearch = null;
    let searchMode='STARTS_WITH', broadTotal=null;
    // The initial blank grid and old rows remain visible while ORION searches.
    // A completed loading cycle is mandatory, including for an empty response.
    const submit = async () => {
      const search=await bindSearch();
      nvTrace('search-submitted',{name:query.name,search_mode:searchMode});
      return nvChanged(() => search.click(), () => nvPage('Search Results', nvSearchHeaders), deadline, {
      requireLoading:true, pendingGraceMs:25000, retryNotStarted:()=>{
        // Re-read the current visible controls. A changed query must not be
        // submitted or allowed to inherit the original query's evidence.
        if (field('entityName')?.value !== query.name || field('entityNumber')?.value !== '' || field('nvBusinessId')?.value !== '') return;
        const buttons=[...document.querySelectorAll('button')].filter(el=>text(el)==='Search' && visible(el) && !el.disabled);
        if (business?.getAttribute('aria-selected')==='true'
            && nvSearchModeSelected(searchMode)
            && buttons.length===1) buttons[0].click();
      }
      });
    };
    let first=await submit();
    if (query.exact_above===20 && first.total>query.exact_above) {
      broadTotal=first.total;searchMode='EXACT_MATCH';
      nvTrace('search-narrowed',{name:query.name,broad_total:broadTotal,search_mode:searchMode});
      await nvSelectSearchMode(searchMode,deadline);
      first=await submit();
    }
    first = await nvExpandSearchPage(first,deadline);
    const collected = await nvPages('Search Results', nvSearchHeaders, deadline, first);
    nvTrace('pages-complete',{rows:collected.length});
    const rows = collected.map(({cells,node,page}) => {
      // Keep every completed public row for master identity filtering. An
      // explicit blank business ID uses its visible entity number only as a
      // row key; nvDetail still refuses anything except an observed NV ID.
      const row = nvPublicRow(cells), identifier = row.identifier;
      const prior = nvObserved.get(identifier), signature = JSON.stringify(cells);
      if (prior) {
        // ORION can repeat an identical public record across distinct pages.
        // nvPages has already checked every raw row against the source total,
        // advancing page numbers and non-repeated whole pages. Coalesce only
        // byte-identical cells across pages, never conflicting identities,
        // statuses or same-page repetitions. Preserve the first detail link.
        if (prior.lastPage === page || prior.signature !== signature)
          throw new Error("REGISTRY_NV_RESULTS_INCOMPLETE");
        prior.occurrences += 1;
        prior.lastPage = page;
        return null;
      }
      nvObserved.set(identifier,{...row,node,page,lastPage:page,signature,occurrences:1});
      return row;
    }).filter(Boolean);
    nvLastSearch = {...query};
    nvLastSearchMode = searchMode;
    nvTrace('search-returned',{rows:rows.length});
    return {query,state:'NV',complete:true,verification_pending:false,total:rows.length,rows,
      ...(query.exact_above===20?{search_mode:searchMode,broad_total:broadTotal}:{})};
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
  function nvReservationFields(identifier) {
    if (!location.hash.includes('screen=NameReservationDetails&')) return null;
    const forms=[...document.querySelectorAll('[role="form"]')].filter(el=>[...el.querySelectorAll('h4')].some(h=>text(h)==='Name Reservation Information'));
    if(forms.length!==1)return null;
    const wanted=['Reserved Name','Entity Number','Status','Formation Date','Expiration Date'];
    const fields=Object.create(null);
    let linkedSection=false;
    for(const el of forms[0].querySelectorAll('h4, p')) {
      if(el.tagName==='H4'&&text(el)==='Linked Entity Information') {
        linkedSection=true;
        continue;
      }
      if(linkedSection) {
        if(el.tagName==='H4')break;
        if(el.tagName==='P'&&text(el)){fields['Linked Entity Information']=text(el);break;}
        continue;
      }
      const label=el.querySelector('strong');
      if(label&&wanted.includes(text(label))) {
        if(Object.hasOwn(fields,text(label))||el.nextElementSibling?.tagName!=='P')throw new Error('REGISTRY_NV_DETAIL_CHANGED');
        fields[text(label)]=text(el.nextElementSibling);
      }
    }
    if(!wanted.every(k=>Object.hasOwn(fields,k))||fields['Entity Number']!==identifier||!fields['Reserved Name']||!fields.Status||!fields['Linked Entity Information'])return null;
    return fields;
  }
  async function nvDetail(query, deadline) {
    if (query?.state !== 'NV' || query.operation !== 'detail' || !/^(?:NV\d+|(?:NR|C)\d{8}-\d+)$/.test(query.identifier)
        || Object.keys(query).sort().join(',') !== 'identifier,operation,state') throw new Error("REGISTRY_COMMAND_INVALID");
    const target = nvObserved.get(query.identifier), sourceQuery = nvLastSearch;
    if (!target || !sourceQuery) throw new Error("REGISTRY_NV_DETAIL_NOT_OBSERVED");
    const onSearch=location.hash.includes('screen=external-GenericFilingsSearch&tabRoute=business');
    nvTrace('detail-started',{identifier:query.identifier,on_search:onSearch,page:target.page});
    // Pagination detaches earlier-page rows too. That does not mean we left
    // the search screen. Return from a detail only when actually on a detail
    // route; otherwise navigate to the saved page and revalidate its row.
    if (!target.node.isConnected && !onSearch) {
      const backLabel=location.hash.includes('screen=NameReservationDetails&')?'Back':'Return To Results';
      const back = [...document.querySelectorAll('button')].find(el => text(el) === backLabel && visible(el));
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
      if (field('entityName')?.value !== sourceQuery.name || field('entityNumber')?.value !== '' || field('nvBusinessId')?.value !== ''
          || !nvSearchModeSelected(nvLastSearchMode))
        throw new Error('REGISTRY_NV_RESTORED_QUERY_CHANGED');
      const sourceTotal = [...nvObserved.values()].reduce((total,row)=>total+row.occurrences,0);
      let restored = await wait(() => {
        if ([...document.querySelectorAll('.app-loader-pane .circle-loader')].some(visible)) return false;
        try { const page=nvPage('Search Results',nvSearchHeaders);return page.total===sourceTotal && page; }
        catch { return false; }
      },Math.max(1,Math.min(5000,deadline-Date.now())));
      while (restored.page > 1) {
        const expectedPage=restored.page-1,expectedTotal=restored.total;
        const previous = restored.table.querySelector('button[aria-label="Go to the previous page"]');
        if (!previous || previous.disabled) throw new Error('REGISTRY_NV_PAGINATION_INCOMPLETE');
        restored = await nvChanged(()=>previous.click(),()=>{
          const fresh=nvPage('Search Results',nvSearchHeaders);
          return fresh.page===expectedPage && fresh.total===expectedTotal && fresh;
        },deadline,{previous:JSON.stringify(restored.values),settle:0});
      }
      const rows = await nvPages('Search Results',nvSearchHeaders,deadline,restored), restoredIds = new Map();
      if (rows.length !== sourceTotal) throw new Error('REGISTRY_NV_RESTORED_RESULTS_CHANGED');
      for (const {cells,page} of rows) {
        let row;
        try { row=nvPublicRow(cells); }
        catch { throw new Error('REGISTRY_NV_RESTORED_RESULTS_CHANGED'); }
        const prior = nvObserved.get(row.identifier);
        const occurrence = restoredIds.get(row.identifier);
        if (!prior || prior.signature !== JSON.stringify(cells) || occurrence?.page === page)
          throw new Error('REGISTRY_NV_RESTORED_RESULTS_CHANGED');
        restoredIds.set(row.identifier,{page,count:(occurrence?.count||0)+1});
      }
      if (restoredIds.size !== nvObserved.size || [...restoredIds].some(([id,value])=>value.count!==nvObserved.get(id).occurrences))
        throw new Error('REGISTRY_NV_RESTORED_RESULTS_CHANGED');
      const updated = new Set();
      for (const {cells,node,page} of rows) {
        const identifier=nvPublicRow(cells).identifier;
        if(updated.has(identifier))continue;
        updated.add(identifier);
        nvObserved.set(identifier,{...nvObserved.get(identifier),node,page});
      }
    }
    let current = nvObserved.get(query.identifier);
    if (!current || current.name !== target.name || current.entity_type !== target.entity_type) throw new Error("REGISTRY_NV_DETAIL_CHANGED");
    let page = nvPage('Search Results',nvSearchHeaders);
    while (page.page > current.page) {
      const expectedPage=page.page-1,expectedTotal=page.total;
      const previous = page.table.querySelector('button[aria-label="Go to the previous page"]');
      if (!previous || previous.disabled) throw new Error("REGISTRY_NV_PAGINATION_INCOMPLETE");
      page = await nvChanged(()=>previous.click(),()=>{
        const fresh=nvPage('Search Results',nvSearchHeaders);
        return fresh.page===expectedPage && fresh.total===expectedTotal && fresh;
      },deadline,{previous:JSON.stringify(page.values),settle:0});
    }
    const matches = page.values.map((cells,i)=>({cells,node:page.rows[i]})).filter(row=>row.cells[1]===query.identifier);
    if (matches.length !== 1 || JSON.stringify(matches[0].cells)!==target.signature)
      throw new Error("REGISTRY_NV_DETAIL_NOT_OBSERVED");
    const link = matches[0].node.querySelector('[role="gridcell"] a');
    if (!link || text(link) !== target.name) throw new Error("REGISTRY_NV_DETAIL_NOT_OBSERVED");
    const reservation=/^(?:NR|C)\d{8}-\d+$/.test(query.identifier)&&target.entity_type==='';
    // Keep DOM identities, not values: two organizations can have identical
    // filing dates. A prior detail's table must not qualify the new record.
    const priorFilingTables=new Set([...document.querySelectorAll('casex-data-table')].filter(el=>
      [...el.querySelectorAll('h4')].some(h=>text(h)==='Filing History Details')));
    const priorFilingRows=new Set([...priorFilingTables].flatMap(el=>
      [...(el.querySelector('[role="grid"]')?.querySelectorAll('tbody > tr[role="row"]')||[])]));
    nvTrace('detail-row-confirmed',{identifier:query.identifier,page:page.page});
    let detailRetry, detailStarted=false;
    const loading=()=>[...document.querySelectorAll('.app-loader-pane .circle-loader')].some(visible);
    const detailRoute=()=>!location.hash.includes('screen=external-GenericFilingsSearch&tabRoute=business');
    const readDetail=()=>{
      detailStarted ||= loading() || detailRoute();
      return reservation?nvReservationFields(query.identifier):nvFields(query.identifier);
    };
    let fields;
    try {
      fields=await wait(readDetail,Math.max(1,deadline-Date.now()),{action:()=>{
        link.click();nvTrace('detail-clicked',{identifier:query.identifier});
        // A result row can render before ORION binds its navigation handler.
        // Retry once only while the original, fully confirmed search remains
        // unchanged and no detail navigation/loading has started.
        detailRetry=setTimeout(()=>{
          if(Date.now()>=deadline || detailStarted || loading() || detailRoute())return;
          try {
            const field=s=>document.querySelector(`input[id$="-${s}"]`);
            if(field('entityName')?.value!==sourceQuery.name || field('entityNumber')?.value!==''
                || field('nvBusinessId')?.value!=='' || !nvSearchModeSelected(nvLastSearchMode))return;
            const fresh=nvPage('Search Results',nvSearchHeaders);
            const exact=fresh.values.map((cells,i)=>({cells,node:fresh.rows[i]}))
              .filter(row=>row.cells[1]===query.identifier && JSON.stringify(row.cells)===target.signature);
            if(fresh.page!==target.page || exact.length!==1)return;
            const retry=exact[0].node.querySelector('[role="gridcell"] a');
            if(!retry || text(retry)!==target.name)return;
            retry.click();nvTrace('detail-click-retried',{identifier:query.identifier});
          } catch { /* Changed/incomplete search cannot authorize another click. */ }
        },Math.min(3000,Math.max(1,deadline-Date.now())));
      }});
    } catch(error) {
      if(error.message!=='REGISTRY_RESPONSE_INCOMPLETE')throw error;
      throw new Error(loading()?'REGISTRY_NV_DETAIL_RESPONSE_PENDING'
        : detailRoute()?'REGISTRY_NV_DETAIL_FIELDS_INCOMPLETE':'REGISTRY_NV_DETAIL_NAVIGATION_NOT_STARTED');
    } finally { clearTimeout(detailRetry); }
    nvTrace('detail-returned',{identifier:query.identifier});
    if(reservation) {
      if(fields['Reserved Name']!==target.name)throw new Error('REGISTRY_NV_DETAIL_CHANGED');
      return {query,complete:true,source_url:location.href,fields};
    }
    const evidence = {query,complete:true,source_url:location.href,fields};
    try {
      // ORION mounts the entity fields before its filing-history request has
      // rendered. Reading the table immediately can discard the solicitation
      // statement even though it appears a moment later. Observe the first
      // complete page within the existing detail deadline before paging it.
      let firstFailure = 'REGISTRY_NV_FILINGS_NOT_LOADED';
      let first;
      try { first = await wait(() => {
        if (!nvFields(query.identifier)) { firstFailure='REGISTRY_NV_DETAIL_NOT_READY'; return false; }
        try {
          const page=nvPage('Filing History Details',nvFilingHeaders);
          if (priorFilingTables.has(page.table) || page.rows.some(row=>priorFilingRows.has(row))) {
            firstFailure='REGISTRY_NV_FILINGS_NOT_REFRESHED'; return false;
          }
          // ORION initially renders the normal empty marker while its history
          // request is still loading. That is not evidence of no filings.
          // A complete nonempty table can outlive an unrelated global spinner;
          // zero rows must wait for loading to finish within this same budget.
          if (page.total===0 && loading()) {
            firstFailure='REGISTRY_NV_FILINGS_RESPONSE_PENDING'; return false;
          }
          // ORION's global spinner also covers unrelated detail requests.
          // A new, complete history table bound to the confirmed business ID
          // is usable while that spinner remains. Partial/old grids still wait.
          return page;
        }
        catch (error) { firstFailure=error.message; return false; }
      },Math.max(1,Math.min(35000,deadline-Date.now()))); }
      catch (error) {
        throw new Error(error.message==='REGISTRY_RESPONSE_INCOMPLETE'?firstFailure:error.message);
      }
      // ORION's ten-row history pager can repeat the boundary row and omit
      // another filing with the same date. Use its public 50/100-row choice,
      // as for search results, before paging. Preserve total/identity/unique-
      // filing checks; never accept duplicates or extend the detail deadline.
      first = await nvExpandSearchPage(first,deadline,'Filing History Details',nvFilingHeaders);
      const filings = await nvPages('Filing History Details',nvFilingHeaders,deadline,first);
      evidence.filings = {identifier:query.identifier,name:fields['Entity Name'],complete:true,total:filings.length,
        headers:nvFilingHeaders,rows:filings.map(row=>row.cells)};
    } catch (error) {
      // Optional history failure cannot erase a fully loaded corporate status.
      evidence.filings = {complete:false,failure_code:/^REGISTRY_[A-Z_]+$/.test(error.message)?error.message:'REGISTRY_NV_FILINGS_INCOMPLETE'};
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
      try {
        await wait(()=>!visible(dialog),Math.max(1,deadline-Date.now()),{action:()=>close.click()});
      } catch(error) {
        if(error.message!=='REGISTRY_RESPONSE_INCOMPLETE')throw error;
        throw new Error('REGISTRY_TN_DETAIL_CLOSE_PENDING');
      }
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
    try { Object.assign(fields,await wait(()=>{
      try {return tnFinancials(document.querySelector('#KendoWindowLevel1'));}
      catch(error) {if(error.message==='REGISTRY_TN_FINANCIALS_INCOMPLETE')return null;throw error;}
    },Math.max(1,Math.min(12000,deadline-Date.now())))); }
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
    // NC wires SearchTypeChanged() to change. Do not dispatch it again when
    // the requested Starting With mode is already selected.
    if(words.value!==starts.value)set(words,starts.value);
    set(input,query.name);if(print.checked)print.click();
    // Dispatch the ordinary form action before acknowledging it. A deferred
    // timer in a background tab can be throttled after the worker has already
    // started waiting for the results document. NC's action starts an async
    // request, so the message reply is sent before the resulting navigation.
    button.click();return {ok:true,phase:'submitted'};
  }
  function ncIdleSearch(query) {
    if(query?.state!=='NC'||query.operation!=='search'||typeof query.name!=='string'||!query.name.trim()||query.name.length>500)
      return false;
    if(location.pathname!=='/online_services/search/by_title/search_charities'||!registryDocumentReady())return false;
    const input=document.querySelector('#SearchCriteria'),words=document.querySelector('#Words'),button=document.querySelector('#SubmitButton'),print=document.querySelector('#Print');
    const starts=words&&[...words.options].find(o=>text(o)==='Starting With');
    return !!(input&&input.value===query.name&&starts&&words.value===starts.value&&print&&!print.checked
      &&visible(button)&&!button.disabled&&text(button)==='Search');
  }
  function ncRetry(query) {
    if(query?.state!=='NC'||query.operation!=='search'||typeof query.name!=='string'||!query.name.trim()||query.name.length>500)
      throw new Error('REGISTRY_NC_QUERY_INVALID');
    if(location.pathname!=='/online_services/search/by_title/search_charities'||!registryDocumentReady())
      return {ok:false,phase:'pending'};
    const input=document.querySelector('#SearchCriteria'),words=document.querySelector('#Words'),button=document.querySelector('#SubmitButton'),print=document.querySelector('#Print');
    const starts=words&&[...words.options].find(o=>text(o)==='Starting With');
    if(!input||input.value!==query.name||!starts||words.value!==starts.value||!print||print.checked
        ||!visible(button)||button.disabled||text(button)!=='Search')return {ok:false,phase:'changed'};
    // Ordinary public action only: no reload, challenge action, private
    // request, query rewrite or timer that outlives the worker's deadline.
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
    if(total>100||buttons.length>100)throw new Error('REGISTRY_NC_PAGINATION_INCOMPLETE');
    if(buttons.length<total)throw new Error('REGISTRY_NC_RESULT_COUNT_MISMATCH');
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
    // NC's displayed count can group repeated pending applications by legal
    // name while rendering their distinct profile IDs as separate cards.
    // Retain every fully read card. Accept only this exact grouped-count
    // reconciliation; missing cards, repeated licenses/profiles and arbitrary
    // count changes still fail. No pending application is silently discarded.
    const grouped=new Set(rows.map(row=>row.License||'pending:'+row['CSL Legal Name']));
    // The live Achieving search also groups a pending application with an
    // existing licensed card bearing the exact legal name. Reconcile only
    // that observed relationship; distinct issued licenses stay distinct.
    // Every card still travels to master matching/status selection.
    const licensedNames=new Set(rows.filter(row=>row.License).map(row=>row['CSL Legal Name']));
    const registrationGroups=new Set(rows.filter(row=>row.License||!licensedNames.has(row['CSL Legal Name']))
      .map(row=>row.License||'pending:'+row['CSL Legal Name']));
    if(rows.length!==total&&grouped.size!==total&&registrationGroups.size!==total)throw new Error('REGISTRY_NC_RESULT_COUNT_MISMATCH');
    return {ok:true,evidence:{state:'NC',query,complete:true,verification_pending:false,total:rows.length,rows},
      diagnostics:rows.length===total?[]:[{phase:'pending-count',displayed:total,cards:rows.length,groups:grouped.size}]};
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
    // A completed EX profile explicitly labeled CSL Exempt can omit its
    // entire address block (observed EX009484). Preserve the absence; the
    // master still checks identity and may require a user match decision.
    if(addresses.length===0&&/^EX\d+$/.test(query.identifier)&&fields.Status==='CSL Exempt') {
      fields.Street=fields.City=fields.State=fields.Zip='';
    } else {
      if(addresses.length!==1)throw new Error('REGISTRY_NC_ADDRESS_INCOMPLETE');
      // Read only the nested address block, never outer contact fields.
      const spans=[...addresses[0].parentElement.querySelectorAll(':scope > .para-small > span')].map(text);
      if(spans.length!==4)throw new Error('REGISTRY_NC_ADDRESS_INCOMPLETE');
      [fields.Street,fields.City,fields.State,fields.Zip]=spans;
    }
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
  async function alExpandPage(page, deadline) {
    // Use the registry's public page-size control, not a separate request or
    // a larger time budget. Its published grid supports up to 100 rows.
    const size=page.table.querySelector('tfoot input[aria-label="Page size"][fltr="pageSize"]');
    if (page.pages===1 || !size || !visible(size) || size.disabled) return page;
    const wanted=page.total>50?100:50;
    if (Number(size.value)>=wanted) return page;
    const oldNodes=[...page.table.querySelectorAll('tbody tr.grid_tr')];
    return wait(()=>{
      const table=document.querySelector('table.table.table-responsive.table-bordered');
      const nodes=table?[...table.querySelectorAll('tbody tr.grid_tr')]:[];
      if (!nodes.length || nodes.length===oldNodes.length && nodes.every((r,i)=>r===oldNodes[i])) return null;
      const next=alPage(),fresh=next?.table.querySelector('tfoot input[aria-label="Page size"][fltr="pageSize"]');
      if (!next || !fresh || Number(fresh.value)!==wanted) return null;
      if (next.total!==page.total) throw new Error('REGISTRY_TOTAL_CHANGED');
      if (next.page!==1 || next.from!==1 || next.pages!==Math.ceil(page.total/wanted)
          || next.rows.length!==Math.min(wanted,page.total)) return null;
      return next;
    },Math.max(1,deadline-Date.now()),{action:()=>set(size,String(wanted))});
  }
  let alVerificationImage = null;
  function alImagePixels() {
    const image=document.getElementById('imgcap');
    if (!image || image.tagName!=='IMG' || !image.complete
        || image.naturalWidth<20 || image.naturalHeight<10 || image.naturalWidth>600 || image.naturalHeight>300)
      throw new Error('NY_CONNECTOR_AL_VERIFICATION_REQUIRED');
    // The live image's alt text is "Verification Code image"; its accessible
    // name is "Captcha". Bind to the actual state image endpoint, not either
    // presentation label, while retaining same-origin and dimension checks.
    const source=new URL(image.currentSrc || image.src,location.href);
    if (source.origin!==location.origin || source.pathname!=='/online/Captcha.aspx')
      throw new Error('NY_CONNECTOR_AL_VERIFICATION_REQUIRED');
    const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;
    canvas.getContext('2d').drawImage(image,0,0);
    const pixels=canvas.toDataURL('image/png');
    if(pixels.length>180000)throw new Error('NY_CONNECTOR_AL_VERIFICATION_REQUIRED');
    return pixels;
  }
  function alVerificationRequest(query) {
    // Only the currently displayed public image is sent to the signed master
    // continuation. Never fetch another image, or forward cookies/form state.
    const alert=document.querySelector('#altdialog');
    if(visible(alert)) {
      if(!/verif|captcha|code/i.test(text(alert)))throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
      const ok=[...document.querySelectorAll('.ui-dialog button')].find(b=>visible(b)&&text(b)==='Ok');
      if(!ok)throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
      ok.click();
      if(visible(alert))throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
    }
    const pixels=alImagePixels();
    alVerificationImage={id:crypto.randomUUID(),pixels,name:query.name,created:Date.now()};
    return {state:'AL',query,complete:false,verification_pending:true,
      verification_image:pixels,verification_id:alVerificationImage.id};
  }
  function alApplyVerification(query) {
    const answer=query.verification, pending=alVerificationImage;
    if(!answer || !pending || answer.id!==pending.id || pending.name!==query.name
        || Date.now()-pending.created>45000 || !/^[A-Z0-9]{6}$/.test(answer.code)
        || alImagePixels()!==pending.pixels)throw new Error('NY_CONNECTOR_AL_VERIFICATION_REQUIRED');
    // Consume once. The ordinary Search response still decides acceptance.
    alVerificationImage=null;
    set(document.getElementById('ctl00_cntbdy_txt_verify'),answer.code);
  }
  async function alSearch(query, deadline) {
    if (location.pathname !== '/online/Lookups/Business.aspx') throw new Error('REGISTRY_WRONG_ORIGIN');
    const input = id=>document.getElementById('ctl00_cntbdy_'+id);
    // Verification preparation is separate from source-result acceptance.
    if (!input('txt_verify')?.value.trim()) throw new Error('NY_CONNECTOR_AL_VERIFICATION_REQUIRED');
    const oldAlert = document.querySelector('#altdialog');
    if (visible(oldAlert)) {
      // A rejected code remains in the form. Resubmitting it would create a
      // replacement challenge and can invalidate a verification in progress.
      // Leave that dialog for the person verifying; never recycle its code.
      if (/verif|captcha|code/i.test(text(oldAlert))) throw new Error('NY_CONNECTOR_AL_VERIFICATION_REQUIRED');
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
    let page=await wait(()=>{
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
    page=await alExpandPage(page,deadline);
    const rows=[...page.rows]; let current=page;
    while (current.page < current.pages) {
      if (Date.now()>=deadline) throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
      const target=current.page+1,priorEnd=current.to;
      if (![...current.selector.options].some(o=>o.value===String(target))) throw new Error('REGISTRY_PAGINATION_INCOMPLETE');
      const oldNodes=[...current.table.querySelectorAll('tbody tr.grid_tr')];
      current=await wait(()=>{
        // The selector changes immediately, before the final page's rows and
        // counters. Reject stale rows only after observing a fresh page, so
        // this normal intermediate state cannot fail strict final-page checks.
        const pendingTable=document.querySelector('table.table.table-responsive.table-bordered');
        const pendingNodes=pendingTable?[...pendingTable.querySelectorAll('tbody tr.grid_tr')]:[];
        if (!pendingNodes.length || pendingNodes.length===oldNodes.length && pendingNodes.every((r,i)=>r===oldNodes[i])) return null;
        const next=alPage();
        if (!next || next.page!==target || next.from!==priorEnd+1) return null;
        const nodes=[...next.table.querySelectorAll('tbody tr.grid_tr')];
        if (nodes.length===oldNodes.length && nodes.every((r,i)=>r===oldNodes[i])) return null;
        if (next.total!==page.total || next.pages!==page.pages) throw new Error('REGISTRY_TOTAL_CHANGED');
        return next;
      // Fresh nodes, consecutive boundaries, exact counts and the same total
      // establish page completion. An extra settling timer per page adds
      // background-tab throttling without providing additional evidence.
      },Math.max(1,deadline-Date.now()),{action:()=>set(current.selector,String(target))});
      rows.push(...current.rows);
    }
    // Some public Private Foundation rows have no license number. Preserve
    // those rows for master identity review; blank numbers are not duplicate
    // licenses. Repeated numbered credentials or identical rows still fail.
    const numbered=rows.filter(r=>r[1]).map(r=>r[1]);
    if (rows.length!==page.total || new Set(numbered).size!==numbered.length
        || new Set(rows.map(r=>JSON.stringify(r))).size!==rows.length) throw new Error('REGISTRY_TOTAL_CHANGED');
    return {state:'AL',query,complete:true,verification_pending:false,headers:page.headers,rows,total:page.total};
  }
  function nvReadiness() {
    const tab=[...document.querySelectorAll('[role="tab"]')].find(el=>text(el)==='Business');
    return {
      document_loaded:document.readyState!=='loading',
      search_route:location.hash.includes('screen=external-GenericFilingsSearch&tabRoute=business'),
      business_selected:tab?.getAttribute('aria-selected')==='true',
      loader_clear:![...document.querySelectorAll('.app-loader-pane .circle-loader')].some(visible),
      inputs_present:['entityName','entityNumber','nvBusinessId'].every(s=>document.querySelector(`input[id$="-${s}"]`)),
      search_mode_selected:nvStartsWithSelected()||nvSearchModeSelected('EXACT_MATCH'),
      search_enabled:[...document.querySelectorAll('button')].some(el=>text(el)==='Search'&&visible(el)&&!el.disabled)
    };
  }
  function registryDocumentReady() {
    if (document.readyState === 'loading') return false;
    if(NM)return location.pathname.endsWith('/CharityDetail.aspx')
      ? !!document.querySelector('#MainContent_GridViewStatuses')
      : !!document.querySelector('#MainContent_TextBoxFEIN') && !!document.querySelector('#MainContent_ButtonSearch');
    if (TN) return !!document.querySelector('input[id^="Name_"]')
      && [...document.querySelectorAll('button[id^="Search_"]')].some(el=>visible(el)&&!el.disabled&&text(el)==='Search');
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
    if (NV) {
      // Detail and transitional ORION screens share the public search pathname.
      // A loaded document is not a ready Business search form.
      return Object.values(nvReadiness()).every(value=>value===true);
    }
    return true;
  }
  async function handle(m) {
    if(NM) {
      if(m.action==='registry-ready')return {ready:registryDocumentReady(),url:location.href,documentId,
        ...(text(document.querySelector('h1'))==='New Mexico Charity Search'
          && text(document.querySelector('p'))==='We apologize. An unexpected error has occurred. Please try your request again.'
          ? {source_failure:'REGISTRY_NM_SOURCE_ERROR'} : {})};
      const q=m.query;
      if(q?.state!=='NM')throw new Error('REGISTRY_COMMAND_INVALID');
      if(m.action==='registry-nm-form'&&q.operation==='search') {
        const size=document.querySelector('#MainContent_DropDownListPageSize');
        if(!size)throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
        if(size.value!=='1000'){set(size,'1000');return {ok:true,phase:'page-size',documentId};}
        for(const [id,value] of [['CharityName',q.name],['City',''],['Zip',''],['FEIN',q.name?'':q.ein.slice(0,2)+'-'+q.ein.slice(2)]])
          set(document.querySelector('#MainContent_TextBox'+id),value);
        const state=document.querySelector('select[id*="State"]');if(state)state.selectedIndex=0;
        const button=document.querySelector('#MainContent_ButtonSearch');
        if(!button||button.disabled)throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
        button.click();return {ok:true,documentId};
      }
      if(m.action==='registry-nm-rows'&&q.operation==='search') {
        // Confirm that this postback belongs to the requested search, rather
        // than accepting the preceding page's count while ASP.NET navigates.
        for(const [id,value] of [['CharityName',q.name],['City',''],['Zip',''],['FEIN',q.name?'':q.ein.slice(0,2)+'-'+q.ein.slice(2)]])
          if(document.querySelector('#MainContent_TextBox'+id)?.value!==value)
            throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
        if(document.querySelector('#MainContent_DropDownListPageSize')?.value!=='1000')
          throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
        const count=text(document.querySelector('#MainContent_LabelRecCount')).match(/^Charities Found:\s*(\d+)$/);
        const grid=document.querySelector('#MainContent_GridView1');
        if(!count||!grid)throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
        const rows=[...grid.querySelectorAll('a[href*="CharityDetail.aspx?FEIN="]')].map(a=>{
          const match=text(a).match(/^(.*?)\s*\((\d{2}-\d{7})\)$/);
          const url=new URL(a.href);
          if(!match||url.origin!==location.origin||url.pathname!=='/CharitySearch/CharityDetail.aspx'
              ||url.searchParams.get('FEIN')!==match[2])throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
          return {name:match[1].trim(),ein:match[2].replace('-','')};
        });
        if(rows.length!==Number(count[1])||new Set(rows.map(r=>r.ein)).size!==rows.length)
          throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
        return {ok:true,evidence:{query:q,complete:true,rows,total:Number(count[1])}};
      }
      if(m.action==='registry-nm-detail'&&q.operation==='detail') {
        const heading=text(document.querySelector('#MainContent_FormViewCharityDetail_LabelCharityName'));
        const match=heading.match(/^(.*?)\s*\((\d{2}-\d{7})\)$/);
        if(!match||match[2].replace('-','')!==q.identifier||match[1].trim()!==q.name)
          throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
        const history=document.querySelector('#MainContent_GridViewStatuses');
        const financials=document.querySelector('#MainContent_GridViewFinancials');
        if(!history||!financials)throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
        // Only the public status history and fiscal periods are needed. Do
        // not copy financial amounts, officers, contacts or documents.
        const historyRows=[...history.rows].slice(1).map(r=>{
          if(r.cells.length!==3)throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
          return [...r.cells].map(text);
        });
        const periods=[...financials.rows].slice(1).map(r=>{
          const value=text(r.cells[0]);
          const period=value.match(/^(20\d{2})\s+(\d{1,2}\/\d{1,2}\/\d{4})\s*-\s*(\d{1,2}\/\d{1,2}\/\d{4})\b/);
          if(!period)throw new Error('REGISTRY_RESPONSE_INCOMPLETE');
          return {tax_year:Number(period[1]),period_start:period[2],period_end:period[3]};
        });
        return {ok:true,evidence:{query:q,complete:true,name:match[1].trim(),ein:q.identifier,
          history_rows:historyRows,financial_periods:periods}};
      }
      throw new Error('REGISTRY_COMMAND_INVALID');
    }
    if (AL && m.action==='registry-al') {
      if (m.query?.state!=='AL' || m.query.operation!=='search') throw new Error('REGISTRY_COMMAND_INVALID');
      const query={state:'AL',operation:'search',name:m.query.name};
      try {
        if(m.query.verification)alApplyVerification(m.query);
        return {ok:true,evidence:await alSearch(query,Date.now()+Math.min(45000,Number.isFinite(m.budgetMs)&&m.budgetMs>0?m.budgetMs:45000))};
      } catch(error) {
        if(error.message!=='NY_CONNECTOR_AL_VERIFICATION_REQUIRED' || !m.automaticVerification)throw error;
        return {ok:true,evidence:alVerificationRequest(query)};
      }
    }
    if (m.action === "registry-ready") return {ready:registryDocumentReady(), url:location.href, documentId,
      ...(NV ? {nv_readiness:nvReadiness()} : {}),
      ...(NC ? {verification_pending:/^Just a moment/i.test(document.title||'')
        && /Performing security verification|verifies you are not a bot/i.test(text(document.body)),
        ...(m.query ? {nc_search_idle:ncIdleSearch(m.query)} : {})} : {}),
      ...(TN ? {verification_pending:!!document.querySelector('div[id^="recaptcha_"]') && !registryDocumentReady()} : {})};
    if (NC) {
      if(m.action==='registry-nc-form')return ncForm(m.query);
      if(m.action==='registry-nc-retry')return ncRetry(m.query);
      if(m.action==='registry-nc-rows')return ncRows(m.query,m.budgetMs);
      if(m.action==='registry-nc-profile')return ncProfile(m.query);
      if(m.action==='registry-nc-filings')return ncFilings(m.query);
      throw new Error('REGISTRY_COMMAND_INVALID');
    }
    if (NV && m.action==='registry-nv-return')
      return nvReturnSearch(Date.now()+Math.min(45000,Number.isFinite(m.budgetMs)&&m.budgetMs>0?m.budgetMs:45000));
    if (TN && m.action === 'registry-tn') {
      const deadline=Date.now()+Math.min(45000,Number.isFinite(m.budgetMs)&&m.budgetMs>0?m.budgetMs:45000);
      return {ok:true,evidence:m.query?.operation==='search'?await tnSearch(m.query,deadline):await tnDetail(m.query,deadline)};
    }
    if (NV && m.action === 'registry-nv') {
      const maximum=m.query?.operation==='search'?150000:45000;
      const deadline = Date.now() + Math.min(maximum, Number.isFinite(m.budgetMs) && m.budgetMs > 0 ? m.budgetMs : 45000);
      const evidence = m.query?.operation === 'search' ? await nvSearch(m.query,deadline) : await nvDetail(m.query,deadline);
      return {ok:true,evidence};
    }
    if (m.action === "registry-il" && IL) {
      const diagnostics = [];
      try { return {ok:true, evidence:await illinois(m.query, entry => { if (diagnostics.length < 32) diagnostics.push(entry); }, [0,12000].includes(m.formWaitMs) ? m.formWaitMs : 45000), diagnostics}; }
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
      if (NV) nvTrace('command-failed',{code:/^REGISTRY_[A-Z_]+$/.test(code)?code:'UNEXPECTED_ERROR'});
      const trialReason=(NC||NV||TN) && /^REGISTRY_(?:(?:NC|NV|TN)_[A-Z_]+|WRONG_ORIGIN|COMMAND_INVALID|RESPONSE_INCOMPLETE)$/.test(code)
        ? 'NY_CONNECTOR_'+code : null;
      const ilReasons={REGISTRY_RESPONSE_INCOMPLETE:'NY_CONNECTOR_IL_RESPONSE_TIMEOUT',REGISTRY_RESULTS_INCOMPLETE:'NY_CONNECTOR_IL_RESULTS_INCOMPLETE',REGISTRY_TOTAL_CHANGED:'NY_CONNECTOR_IL_TOTAL_CHANGED',REGISTRY_RESULT_LIMIT:'NY_CONNECTOR_IL_RESULT_LIMIT',REGISTRY_PAGINATION_INCOMPLETE:'NY_CONNECTOR_IL_PAGINATION_INCOMPLETE'};
      reply({ok:false,reason:trialReason || (AL && code==='NY_CONNECTOR_AL_VERIFICATION_REQUIRED' ? code : TN && code==='NY_CONNECTOR_TN_VERIFICATION_OR_FORM_PENDING' ? code : /^NY_CONNECTOR_IL_(?:VERIFICATION_PENDING|FORM_READY_TIMEOUT|FORM_DISABLED|FORM_MISSING|DETAIL_(?:NOT_OPENED|BLANK|IDENTITY_INCOMPLETE|RESPONSE_TIMEOUT))$/.test(code) ? code : IL && ilReasons[code] || 'NY_CONNECTOR_INCOMPLETE'),
        ...(NV ? {nv_readiness:nvReadiness()} : {}),
        ...(IL && error.diagnostics ? {diagnostics:error.diagnostics} : {})});
    });
    return true;
  });
})();
