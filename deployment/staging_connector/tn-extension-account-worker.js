/* Read-only Tennessee account history. Never resumes, creates or files anything. */
(() => {
  'use strict';
  const base='https://tncab.tnsos.gov';
  const paths=['/portal/my-filings','/portal/my-filings-complete'];
  const key=s=>String(s||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toUpperCase().replace(/[^A-Z0-9]+/g,' ').trim();
  function records(snapshot,coid,names,source) {
    const headers=snapshot.headers.map(key),column=name=>headers.indexOf(key(name));
    const tracking=column('Tracking Number'),description=column('Description'),type=column('Filing Type'),status=column('Filing Status'),updated=column('Updated'),co=column('Registration Number');
    if([tracking,description,type,updated].some(i=>i<0))throw new Error('ACCOUNT_TABLE_CHANGED');
    if(['Tracking Number','Description','Filing Type','Updated'].some(n=>headers.filter(h=>h===key(n)).length!==1))throw new Error('ACCOUNT_TABLE_CHANGED');
    const targets=new Set(names.map(key));
    return snapshot.rows.flatMap(cells=>{
      if(cells.length!==headers.length){if(cells.length===1&&/^No (?:records|items)/i.test(cells[0]))return [];throw new Error('ACCOUNT_TABLE_CHANGED');}
      const number=cells[tracking],code=co>=0?cells[co]:'';
      const name=key(cells[description]).replace(/^(FIRST|SECOND) EXTENSION REQUEST FOR /,'');
      if(!/^\d{6,18}$/.test(number)||code&&code!==coid||!code&&!targets.has(name))return [];
      return [{tracking:number,coid:code,description:cells[description].slice(0,300),type:cells[type].slice(0,100),status:status>=0?cells[status].slice(0,100):'Not displayed',updated:cells[updated].slice(0,100),source,identity_method:code?'co_number':'exact_name'}];
    });
  }
  // This expression reads only rendered account tables and a read-only pager.
  // It never reads credentials, executes workflow buttons, or downloads files.
  function snapshotPage(advance=false) {
    const allowed=['/portal/my-filings','/portal/my-filings-complete'];
    if(location.origin!=='https://tncab.tnsos.gov')return {state:'unavailable'};
    if(document.querySelector('#loginButton')||/portal-login-page/.test(location.pathname)||document.body?.innerText.includes('You must be logged in to view this page'))return {state:'sign_in_required'};
    if(!allowed.includes(location.pathname))return {state:'unavailable'};
    const busy=[...document.querySelectorAll('.k-loading-mask')].some(e=>e.getBoundingClientRect().height>0&&getComputedStyle(e).display!=='none');
    const tables=[...document.querySelectorAll('table')].filter(t=>t.querySelector('thead')?.textContent.includes('Tracking Number'));
    if(busy||tables.length!==1)return {state:'loading'};
    const table=tables[0],headers=[...table.querySelectorAll('thead th')].map(e=>e.textContent.trim());
    const rows=[...table.querySelectorAll('tbody tr')].map(row=>[...row.children].map(c=>c.textContent.trim()));
    const empty=/No (?:items to display|records available)/i.test(document.body.innerText);
    if(!rows.length&&!empty)return {state:'loading'};
    const next=document.querySelector('button[aria-label="Go to the next page"]');
    const hasNext=!!next&&!next.disabled&&next.getAttribute('aria-disabled')!=='true'&&!next.classList.contains('k-disabled');
    if(advance){if(hasNext)next.click();return {state:hasNext?'advanced':'last'};}
    return {state:'ready',headers,rows,hasNext,url:location.origin+location.pathname};
  }
  globalThis.CCTNExtensionAccount={records,snapshotPage};
  if(typeof chrome==='undefined'||!chrome.runtime?.onMessage)return;
  let running=false;
  const nap=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  async function inspect(message) {
    if(running||allJobs().some(j=>!j.closed))return {state:'busy',records:[]};
    running=true;const found=[],deadline=Date.now()+20000;
    try {
      for(const path of paths){
        let tab=null,attached=false;
        try {
          tab=await chrome.tabs.create({url:base+path,active:false});
          await chrome.debugger.attach({tabId:tab.id},'1.3');attached=true;
          const evaluate=async advance=>{
            const current=await chrome.tabs.get(tab.id);
            if(current.status!=='complete')return {state:'loading'};
            if(!current.url?.startsWith(base+'/'))return {state:'unavailable'};
            const r=await chrome.debugger.sendCommand({tabId:tab.id},'Runtime.evaluate',{expression:'('+snapshotPage.toString()+')('+!!advance+')',returnByValue:true});
            if(r.exceptionDetails)return {state:'unavailable'};
            return r.result?.value||{state:'loading'};
          };
          let previous='',stable=0,pages=0;
          while(Date.now()<deadline){
            let snap;
            try{snap=await evaluate(false);}catch{await nap(200);continue;}
            if(['sign_in_required','unavailable'].includes(snap.state))return {state:snap.state,records:found};
            if(snap.state!=='ready'){await nap(200);continue;}
            const signature=JSON.stringify(snap.rows);
            if(signature===previous)stable++;else{previous=signature;stable=0;}
            if(stable<1){await nap(250);continue;}
            found.push(...records(snap,message.coid,message.names,base+path));
            if(!snap.hasNext)break;
            if(++pages>=8)return {state:'partial',records:found.slice(0,50)};
            await evaluate(true);stable=0;
            // A page must actually change before it can be counted again.
            while(Date.now()<deadline){await nap(200);const next=await evaluate(false);if(next.state==='ready'&&JSON.stringify(next.rows)!==signature){previous='';break;}}
          }
          if(Date.now()>=deadline)return {state:'partial',records:found.slice(0,50)};
        } finally {
          if(attached)try{await chrome.debugger.detach({tabId:tab.id});}catch{}
          if(tab)try{await chrome.tabs.remove(tab.id);}catch{}
        }
      }
      return {state:found.length>50?'partial':'checked',records:[...new Map(found.map(r=>[r.tracking,r])).values()].slice(0,50)};
    } catch {return {state:'unavailable',records:found.slice(0,50)};}
    finally {running=false;}
  }
  chrome.runtime.onMessage.addListener((m,sender,respond)=>{
    if(m?.type!=='cc-tn-extension-account-v1'||!allowedSender(sender))return false;
    if(!['/','/instant-compliance-snapshot'].includes(new URL(sender.url).pathname)||!/^CO\d{1,15}$/.test(m.coid||'')
      ||!/^[a-f0-9]{48}$/.test(m.nonce||'')||!Array.isArray(m.names)||!m.names.length||m.names.length>20||m.names.some(n=>typeof n!=='string'||!n.trim()||n.length>500)){
      respond({state:'unavailable',records:[]});return false;
    }
    inspect(m).then(respond,()=>respond({state:'unavailable',records:[]}));return true;
  });
})();
