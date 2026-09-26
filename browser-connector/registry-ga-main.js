/* Activate only the public GA pager link in its own page context. No data API. */
(() => {
  'use strict';
  const origin='https://verify.sos.ga.gov', channel='cc-ga-public-pager-v1';
  if(window!==window.top || location.origin!==origin || location.pathname!=='/verification/SearchResults.aspx')return;
  window.addEventListener('message',event=>{
    const m=event.data;
    if(event.source!==window || event.origin!==origin || m?.channel!==channel || m.direction!=='request'
       || typeof m.id!=='string' || !/^[a-f0-9-]{36}$/.test(m.id) || !Number.isInteger(m.page) || m.page<2 || m.page>10)return;
    const table=document.querySelector('#datagrid_results');
    const pager=table && [...table.querySelectorAll(':scope > tbody > tr')].at(-1);
    const text=el=>(el?.innerText || '').trim();
    const current=pager && [...pager.querySelectorAll('span')].map(text).find(v=>/^\d+$/.test(v));
    const link=pager && [...pager.querySelectorAll('a')].find(a=>text(a)===String(m.page));
    const ok=!!(current && Number(current)+1===m.page && pager.children.length===1 && link && link.getClientRects().length
      && /^javascript:__doPostBack\('datagrid_results\$[^']+',''\)$/.test(link.getAttribute('href') || ''));
    window.postMessage({channel,direction:'response',id:m.id,ok},origin);
    // The public link uses a javascript: URL. Its normal click needs the page's
    // context; an isolated content-script click can leave page one unchanged.
    if(ok)setTimeout(()=>link.click(),0);
  });
})();
