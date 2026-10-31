(() => {
  "use strict";
  // Relay only our worker's already validated command. Protocol validation runs
  // in the worker and page world; Chrome can deduplicate same-file injections
  // across worlds, so this isolated relay does not depend on that page global.
  const NY = "https://charities-search.ag.ny.gov";
  if (location.origin !== NY || window !== window.top) return;
  let pending = null;
  let completed = null;
  const documentId = `${Date.now()}:${Math.random()}`;
  const same = (a, b) => a.action === b.action && JSON.stringify(a.query || null) === JSON.stringify(b.query || null);
  function finish(task, response) {
    completed = { id: task.id, attempt: task.attempt, action: task.action, query: task.query, response };
    if (pending === task) pending = null;
    clearTimeout(task.timer);
    for (const respond of task.responders) try { respond(response); } catch { /* Previous worker has exited. */ }
  }
  window.addEventListener("message", event => {
    if(event.source===window && event.origin===NY && event.data?.channel==='cc-final-four-ny-page-v1'
        && event.data.direction==='diagnostic' && pending && event.data.id===pending.id) {
      // The worker revalidates sender ownership and sanitizes this payload.
      if(Array.isArray(event.data.ny_diagnostics))chrome.runtime.sendMessage({action:'ny-diagnostic',
        id:pending.id,ny_diagnostics:event.data.ny_diagnostics.slice(-1)}).catch(()=>{});
      return;
    }
    if (event.source !== window || event.origin !== NY || event.data?.channel !== "cc-final-four-ny-page-v1" || event.data.direction !== "response") return;
    if (!pending || event.data.id !== pending.id) return;
    finish(pending, { ...(event.data.ok ? { ok: true, evidence: event.data.evidence } : { ok: false, reason: event.data.reason }), verificationRetryUsed: event.data.verificationRetryUsed === true, ...(Array.isArray(event.data.ny_diagnostics) ? {ny_diagnostics:event.data.ny_diagnostics.slice(-32)} : {}) });
  });
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id) return false;
    if(message?.action==='registry-snapshot-metadata') {
      const roots=[...document.querySelectorAll('main,table,footer')];
      const visible=e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.display!=='none'&&s.visibility==='visible'&&Number(s.opacity)>0&&r.width>0&&r.height>0;};
      const fits=e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;};
      // A table can fit the viewport while an inner scroller hides its columns.
      const horizontallyClipped=roots.some(root=>[root,...root.querySelectorAll('*')].some(e=>visible(e)
        &&/^(auto|scroll|hidden|clip)$/.test(getComputedStyle(e).overflowX)&&e.scrollWidth>e.clientWidth+1));
      const pageFits=!horizontallyClipped&&scrollX===0&&scrollY===0&&roots.length>=3&&roots.some(e=>e.tagName==='MAIN')&&roots.some(e=>e.tagName==='TABLE')&&roots.some(e=>e.tagName==='FOOTER')
        &&roots.every(e=>visible(e)&&fits(e)&&[...e.querySelectorAll('*')].filter(visible).every(fits));
      // Responsive header navigation may appear when the owned viewport widens.
      // Exclude only the exact source menu; retain every record and filing line.
      const publicText=(document.body?.innerText||'').slice(0,20000);
      const menus=[...document.querySelectorAll('header nav.primary-menu')];
      const expected=[['Search Home','/'],['Registrations','/RegistrySearch'],['Transactions','/Transactions'],['Fundraiser Reports','/PenniesForCharities'],['Glossary','/glossary']];
      const menu=menus.length===1?menus[0]:null;
      const menuValid=menu&&JSON.stringify([...menu.querySelectorAll('a')].map(a=>[a.textContent.trim(),a.getAttribute('href')]))===JSON.stringify(expected);
      const menuText=menuValid&&visible(menu)?menu.innerText.trim():'';
      let layoutBody=menuText&&publicText.split(menuText).length===2?publicText.replace(menuText,''):publicText;
      // Narrow source cards repeat labels; wide tables show one header row.
      // Compare complete recognized schemas, preserving ordered field values.
      const schemas=[['Annual filing documents','Fiscal year end'],['Registration documents','Date received'],['Other filed documents','Date received']];
      for(const [title,dateLabel] of schemas){
        const headings=[...document.querySelectorAll('h1')].filter(h=>h.innerText.trim()===title);
        if(headings.length!==1)continue;
        const grid=headings[0].nextElementSibling;
        if(!grid||!visible(grid))continue;
        const raw=grid.innerText,tokens=raw.split(/[\t\r\n]+/).map(t=>t.trim()).filter(Boolean);
        const rows=[];let valid=true,pos=0;
        const mobile=tokens[0]==='Display name:';
        if(!mobile){valid=tokens[0]==='Display name'&&tokens[1]===dateLabel;pos=2;}
        while(valid&&pos<tokens.length){
          let name,date,action;
          if(mobile){
            // The original annual grid may contain an explicitly blank FYE.
            // Preserve it as an empty value, never infer or discard the row.
            const blank=title==='Annual filing documents'&&tokens[pos+3]===':';
            valid=tokens[pos]==='Display name:'&&tokens[pos+2]===dateLabel+':'&&tokens[pos+(blank?3:4)]===':';
            name=tokens[pos+1];date=blank?'':tokens[pos+3];action=tokens[pos+(blank?4:5)];pos+=blank?5:6;
          }else{
            const blank=title==='Annual filing documents'&&['Download','Not available for download'].includes(tokens[pos+1]);
            name=tokens[pos];date=blank?'':tokens[pos+1];action=tokens[pos+(blank?1:2)];pos+=blank?2:3;
          }
          valid=valid&&!!name&&((title==='Annual filing documents'&&date==='')||/^\d{2}\/\d{2}\/\d{4}$/.test(date||''))&&['Download','Not available for download'].includes(action);
          if(valid)rows.push([name,date,action]);
        }
        if(!valid||!rows.length||pos!==tokens.length||!raw||layoutBody.split(raw).length!==2)continue;
        const links=[...grid.querySelectorAll('a[href]')].map(a=>[a.textContent.trim(),a.getAttribute('href')]);
        layoutBody=layoutBody.replace(raw,JSON.stringify({title,columns:['Display name',dateLabel,'Download availability'],rows,links}));
      }
      const layoutText=layoutBody.split('\n').map(line=>line.trim()).filter(Boolean).join('\n');
      respond({url:location.href,document_id:documentId,source_viewport_width:window.innerWidth,source_page_fits:pageFits,source_horizontal_clipped:horizontallyClipped,source_layout_text:layoutText,public_text:(document.body?.innerText||'').slice(0,20000)});return false;
    }
    if (message?.action === "ready") {
      const ready = !!document.querySelector("#ein") || /^\/RegistrySearch\/[0-9]{2}-[0-9]{2}-[0-9]{2}\/?$/.test(location.pathname);
      // Report only which public filters are populated, never their values or
      // verification data. The worker can avoid an invalid EIN/name transition.
      const formFields = ["ein", "orgName", "orgID", "city"].filter(key => document.querySelector("#" + key)?.value);
      respond({ ready, documentId, url: location.href, formFields, page_visibility:document.visibilityState, rateLimited: !ready && /(?:429\s+Too Many Requests|Too Many Requests\s*429)/i.test(document.body?.innerText || "") });
      return false;
    }
    if (message?.action === "back-to-results") {
      if (!/^\/RegistrySearch\/[0-9]{2}-[0-9]{2}-[0-9]{2}\/?$/.test(location.pathname)) {
        respond({ ok: false }); return false;
      }
      respond({ ok: true }); setTimeout(() => window.history.back(), 0); return false;
    }
    if (message?.action === "open-detail") {
      const identifier = message.query?.orgID;
      if (typeof identifier !== "string" || !/^[0-9]{2}-[0-9]{2}-[0-9]{2}$/.test(identifier) || !/^\/RegistrySearch\/?$/.test(location.pathname)) {
        respond({ ok: false, reason: "NY_CONNECTOR_DETAIL_LINK_MISSING" }); return false;
      }
      const link = Array.from(document.querySelectorAll("a")).find(a => a.textContent.trim() === identifier && a.href === NY + "/RegistrySearch/" + identifier);
      if (!link) { respond({ ok: false, reason: "NY_CONNECTOR_DETAIL_LINK_MISSING" }); return false; }
      // Acknowledge before normal full-page navigation destroys this relay.
      respond({ ok: true }); setTimeout(() => link.click(), 0); return false;
    }
    if (!["search", "verify"].includes(message?.action) || typeof message.id !== "string" || message.id.length > 80) return false;
    if (completed?.id === message.id && completed.attempt === message.attempt) { respond(same(completed, message) ? completed.response : { ok: false, reason: "NY_CONNECTOR_INVALID_SEQUENCE" }); return false; }
    if (pending?.id === message.id && pending.attempt === message.attempt && same(pending, message)) { pending.responders.push(respond); return true; }
    if (pending) { respond({ ok: false, reason: "NY_CONNECTOR_BUSY" }); return false; }
    const task = { id: message.id, attempt: message.attempt, action: message.action, query: message.query, responders: [respond], timer: null };
    task.timer = setTimeout(() => { if (pending === task) finish(task, { ok: false, reason: "NY_CONNECTOR_RELAY_TIMEOUT" }); }, 140000);
    pending = task;
    window.postMessage({ channel: "cc-final-four-ny-page-v1", direction: "request", id: message.id, action: message.action, query: message.query, verificationRetryUsed: message.verificationRetryUsed === true }, NY);
    return true;
  });
})();
