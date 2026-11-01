/* Optional original filing from the already selected, EIN-bound NM detail. */
(() => {
  'use strict';
  if (location.origin !== 'https://secure.nmdoj.gov' || window !== window.top) return;
  const normalize = value => String(value || '').replace(/\s+/g, ' ').trim();
  async function capture(query, budgetMs) {
    const started = Date.now(), deadline = started + Math.max(0, Math.min(6000, Number(budgetMs) || 0));
    const result = {document:null, diagnostic:{outcome:'unavailable',elapsed_ms:0}};
    let timer;
    try {
      const heading = () => normalize(document.querySelector('#MainContent_FormViewCharityDetail_LabelCharityName')?.innerText);
      const expected = `${query.name} (${query.identifier.slice(0,2)}-${query.identifier.slice(2)})`;
      const before = heading(), source = location.href;
      if (query.state !== 'NM' || query.operation !== 'detail' || before !== expected || deadline <= started) return result;
      const history = document.querySelector('#MainContent_GridViewStatuses');
      if (!history) return result;
      const originalHistory=normalize(history.innerText);
      const candidates = [...history.rows].slice(1).flatMap(row => {
        if (row.cells.length !== 3) return [];
        const year = normalize(row.cells[0].innerText), label = normalize(row.cells[1].innerText), date = normalize(row.cells[2].innerText);
        const match = label.match(/^Registration Submitted\s+(\d{10,20})$/), parts = date.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        if (!/^20\d{2}$/.test(year) || !match || !parts) return [];
        return [{year:Number(year),number:match[1],date,rank:Number(parts[3])*10000+Number(parts[1])*100+Number(parts[2]),row,label}];
      });
      candidates.sort((a,b) => b.year-a.year || b.rank-a.rank);
      const selected=candidates[0];
      if (!selected || candidates.some(c=>c.year===selected.year && c.rank===selected.rank && c.number!==selected.number)) return result;
      const links=[...selected.row.cells[1].querySelectorAll('a[href]')].filter(a=>normalize(a.innerText)===selected.number);
      if (links.length!==1) return result;
      const url=new URL(links[0].href), pairs=[...url.searchParams];
      if (url.origin!==location.origin || url.pathname!=='/coros/getregdoc.aspx' || url.hash
          || pairs.length!==1 || pairs[0][0]!=='RegNumber' || pairs[0][1]!==selected.number) return result;
      const controller=new AbortController(); timer=setTimeout(()=>controller.abort(),Math.max(1,deadline-Date.now()));
      const response=await fetch(url.href,{credentials:'same-origin',redirect:'error',signal:controller.signal});
      if (!response.ok || !/application\/pdf/i.test(response.headers.get('content-type')||'')) throw new Error('source_unavailable');
      if (Number(response.headers.get('content-length')||0)>3000000) throw new Error('document_too_large');
      const reader=response.body.getReader(), chunks=[];let size=0;
      while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>3000000){await reader.cancel();throw new Error('document_too_large');}chunks.push(value);}
      if (Date.now()>=deadline || location.href!==source || heading()!==before || normalize(history.innerText)!==originalHistory || !selected.row.isConnected
          || normalize(selected.row.cells[1].innerText)!==selected.label || links[0].href!==url.href) throw new Error('source_changed');
      const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
      if (new TextDecoder().decode(bytes.subarray(0,5))!=='%PDF-') throw new Error('not_pdf');
      let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
      result.document={query:{...query},source_url:url.href,registration_number:selected.number,tax_year:selected.year,
        submitted_on:selected.date,captured_at:Date.now()/1000,content:btoa(binary)};
      result.diagnostic.outcome='captured';
    } catch(error) { result.diagnostic.reason=error?.name==='AbortError'?'deadline':(['source_unavailable','document_too_large','source_changed','not_pdf'].includes(error?.message)?error.message:'download_failed'); }
    finally {clearTimeout(timer);result.diagnostic.elapsed_ms=Date.now()-started;}
    return result;
  }
  window.CCNmRegistrationDocument=Object.freeze({capture});
})();
