/* Original Wisconsin detail pixels only. Separate from registry matching lanes. */
(() => {
  'use strict';
  const ORIGIN='https://charityclarity-final-four-29-2.onrender.com';
  const busy=new Set(),pending=new Map();
  const normalize=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
  function valid(d) {
    if(d?.state==='DC')return CCDCSource.valid(d);
    if(!d||d.state!=='WI'||!['detail','empty_search'].includes(d.operation)||!/^\d{9}$/.test(d.ein)
      ||typeof d.name!=='string'||!d.name||d.name.length>300
      ||!/^[a-f0-9]{32}$/.test(d.run_id)||!Number.isFinite(d.issued_at)||Date.now()/1000-d.issued_at< -5||Date.now()/1000-d.issued_at>=600)return false;
    if(Object.hasOwn(d,'deadline_schema')&&d.deadline_schema!==1)return false;
    if(d.deadline_schema===1&&(!Number.isFinite(d.expires_at)||!Number.isFinite(d.issued_at)
      ||d.expires_at<=d.issued_at||d.expires_at-d.issued_at>300.1||Date.now()/1000>=d.expires_at))return false;
    try {const u=new URL(d.url),p=[...u.searchParams];
      if(u.origin!=='https://apps.dfi.wi.gov'||u.hash||u.username||u.password)return false;
      if(d.operation==='empty_search')return u.pathname==='/ice/berg/Registration/OrgCredentialSearchResults.aspx'
        &&p.length===3&&new Set(p.map(x=>x[0])).size===3&&u.searchParams.get('CredentialType')==='800'
        &&u.searchParams.get('LicenseNumber')===''&&u.searchParams.get('FirmName')===d.name;
      return /^\d{1,10}-800$/.test(d.identifier)&&typeof d.raw_status==='string'&&d.raw_status.length>0&&d.raw_status.length<=1000
      &&u.pathname==='/ice/berg/Registration/CredSummaryDetails.aspx'&&!u.hash&&!u.username&&!u.password
      &&p.length===2&&new Set(p.map(x=>x[0])).size===2&&['chid','h'].every(k=>/^\d{1,15}$/.test(u.searchParams.get(k)||''));}catch{return false;}
  }
  function bound(d,m) {
    if(d.operation==='empty_search')return m?.url===d.url&&m.ready==='complete'&&typeof m.text==='string'&&m.text.length<=20000
      &&m.text.includes('Organization Search Results')&&!/verify you are human|user validation required|access denied|just a moment|you have been blocked/i.test(m.text)
      &&m.source_fields?.profession==='Charitable Organization'&&m.source_fields?.name===d.name&&m.source_fields?.visible===true
      &&JSON.stringify(m.source_fields?.rows)===JSON.stringify([['There are no query results.']]);
    if(m?.url!==d.url||m.ready!=='complete'||typeof m.text!=='string'||m.text.length>20000
      ||!/Credential Summary/.test(m.text)||!m.text.includes('CHARITABLE ORGANIZATION (800)')
      ||!normalize(m.text).includes(normalize(d.name))||!new RegExp('(?<!\\d)'+d.identifier+'(?!\\d)').test(m.text)
      ||!normalize(m.text).includes(normalize(d.raw_status.split(';')[0]))
      ||/verify you are human|user validation required|access denied|just a moment|you have been blocked/i.test(m.text))return false;
    const dates=s=>[...s.matchAll(/\b(\d{1,2})\/(\d{1,2})\/(\d{4})\b/g)].map(x=>`${+x[1]}/${+x[2]}/${+x[3]}`);
    const actual=dates(m.text);return dates(d.raw_status).every(x=>actual.includes(x));
  }
  async function capture(d,sender,signal) {
    const start=Date.now(),steps=[];let end=start+20000,tab=null,window=null,attached=false,closed=false,rail=null;
    const owner=sender.tab.id;busy.add(owner);
  let onCancel;
  const cancelled=new Promise((_,reject)=>{onCancel=()=>reject(Error('source_cancelled'));signal?.addEventListener('abort',onCancel,{once:true});});
  // Attach a handler before any source operation so an early cancellation is contained.
  cancelled.catch(()=>{});
  const check=()=>{if(signal?.aborted)throw Error('source_cancelled');};
    function limit(p,label,late) {
      const begin=Date.now();let timer;
      const operation=Promise.resolve(p).then(v=>{if(closed||signal?.aborted){late?.(v);throw Error('closed');}return v;});
      return Promise.race([cancelled,operation,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('timeout:'+label)),Math.max(1,Math.min(label==='create'?end-Date.now()-6000:label==='Page.captureScreenshot'?end-Date.now()-3000:label==='Page.enable'?Math.min(6000,end-Date.now()-10000):3000,end-Date.now())));})])
        .finally(()=>{clearTimeout(timer);steps.push({phase:label,seconds:(Date.now()-begin)/1000});});
    }
    const command=(method,params={})=>{check();return limit(chrome.debugger.sendCommand({tabId:tab.id},method,params),method);};
    const metadata=async()=>{
      const r=await command('Runtime.evaluate',{expression:`JSON.stringify((()=>{
        const table=document.getElementById('ctl00_cphMainContent_OrgCredentialSearch_gvCredentialSearchResults');
        const visible=e=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
        const profession=document.getElementById('ctl00_cphMainContent_lblSearchParam1');
        const name=document.getElementById('ctl00_cphMainContent_lblSearchParam2');
        return {url:location.href,ready:document.readyState,viewport_width:innerWidth,text:document.body?document.body.innerText:'',source_fields:table?{
          profession:profession?.innerText?.replace(/^Profession\\s*:\\s*/, '').trim(),name:name?.innerText?.replace(/^Firm Name\\s*:\\s*/, '').trim(),
          visible:visible(table)&&visible(profession)&&visible(name),rows:Array.from(table.rows).map(r=>Array.from(r.cells).map(c=>c.innerText.trim()))}:null};
      })())`,returnByValue:true});
      return JSON.parse(r.result?.value||'null');
    };
    try {
      // A never-active tab can have a complete DOM but no painted surface.
      // An owned, unfocused window gives its sole tab a surface without
      // selecting a tab in the user's window. Never move the user's window.
      check();
      const queued=Date.now();
      try {rail=await CCSourceRail.acquire(sender,'WI',d.deadline_schema===1?d.expires_at*1000-20000:start+58000,d.run_id,signal);check();}
      finally {steps.push({phase:'queue',seconds:(Date.now()-queued)/1000});}
      end=Math.min(d.deadline_schema===1?d.expires_at*1000:start+75000,Date.now()+20000);if(rail)rail.job.activeExpiresAt=end;
      window=await limit(CCSourceRail.create(rail,{url:d.url,...(rail?.options||{type:'popup',focused:false,width:1000,height:800})}),
        'create',v=>chrome.windows.remove(v.id).catch(()=>{}));
      if(rail)rail.windowId=window.id;
      tab=window?.tabs?.[0];
      if(!Number.isInteger(window?.id)||!Number.isInteger(tab?.id))throw Error('owned_window_unavailable');
      await limit(chrome.debugger.attach({tabId:tab.id},'1.3'),'attach',()=>chrome.debugger.detach({tabId:tab.id}).catch(()=>{}));attached=true;
      await command('Page.enable');
      let m=null;
      while(Date.now()<end-4000) {
        try {m=await metadata();}
        catch(error){
          if(!/Cannot find (?:default execution )?context|Execution context was destroyed|Inspected target navigated/i.test(String(error.message)))throw error;
          await new Promise(resolve=>setTimeout(resolve,200));continue;
        }
        if(bound(d,m))break;
        if(m?.text&&/you have been blocked|verify you are human|user validation required|just a moment/i.test(m.text))throw Error('source_verification_required');
        await new Promise(resolve=>setTimeout(resolve,200));
      }
      if(!bound(d,m))throw Error('selected_detail_unavailable');
      await new Promise(resolve=>setTimeout(resolve,150));
      const before=await metadata();if(JSON.stringify(before)!==JSON.stringify(m))throw Error('source_changed');
      const layout=await command('Page.getLayoutMetrics');const measured=layout.cssContentSize||layout.contentSize;
      // A full-height screenshot can remove the scrollbar and reflow the page.
      // Preserve the original viewport width instead of cropping at the old
      // scrollbar-reduced content width. Only this owned WI capture is affected.
      if(!Number.isFinite(before.viewport_width)||before.viewport_width<1)throw Error('source_size_rejected');
      const rect=measured?{...measured,width:Math.max(measured.width,before.viewport_width)}:null;
      if(!rect||rect.width<1||rect.height<1||rect.width*rect.height>20000000)throw Error('source_size_rejected');
      const shot=await command('Page.captureScreenshot',{format:'jpeg',quality:80,captureBeyondViewport:true,fromSurface:true,clip:{x:0,y:0,width:rect.width,height:rect.height,scale:1}});
      const after=await metadata();check();if(JSON.stringify(before)!==JSON.stringify(after)||!bound(d,after)||Date.now()>=end)throw Error('source_changed');
      return {ok:true,request:d,url:d.url,public_text:after.text,source_fields:after.source_fields,navigation_started_at:start/1000,image:shot.data,captured_at:Date.now()/1000,timing:{seconds:(Date.now()-start)/1000,queue_seconds:steps.find(s=>s.phase==='queue')?.seconds||0,active_seconds:(Date.now()-start)/1000-(steps.find(s=>s.phase==='queue')?.seconds||0),steps}};
    } catch(error) {return {ok:false,reason:String(error.message||'capture_failed').slice(0,150),timing:{seconds:(Date.now()-start)/1000,queue_seconds:steps.find(s=>s.phase==='queue')?.seconds||0,active_seconds:(Date.now()-start)/1000-(steps.find(s=>s.phase==='queue')?.seconds||0),steps,...(error.sourceRailObservation?{placement:error.sourceRailObservation}:{})}};}
    finally {
      closed=true;signal?.removeEventListener("abort",onCancel);
      const cleanup=[];
      if(attached&&tab)cleanup.push(chrome.debugger.detach({tabId:tab.id}).catch(()=>{}));
      if(window)cleanup.push(chrome.windows.remove(window.id).catch(()=>{}));
      let timer;
      await Promise.race([Promise.allSettled(cleanup),new Promise(resolve=>{timer=setTimeout(resolve,500);})]);
      clearTimeout(timer);if(rail)await CCSourceRail.release(rail);busy.delete(owner);
    }
  }
  chrome.runtime.onMessage.addListener((m,sender,respond)=>{
    if(!['cc-owned-source-evidence','cc-owned-source-cancel'].includes(m?.action))return;
    let origin;try{origin=new URL(sender.url).origin;}catch{return;}
    if(sender.id!==chrome.runtime.id||sender.frameId!==0||!sender.tab||origin!==ORIGIN)return;
    const id=typeof m.id==='string'&&/^[a-f0-9-]{36}$/.test(m.id)?m.id:null;
    const requestKey=id?sender.tab.id+':'+id:null;
    if(m.action==='cc-owned-source-cancel'){
      const owned=requestKey&&pending.get(requestKey);
      if(owned&&owned.url===sender.url)owned.controller.abort();
      respond({ok:!!owned&&owned.url===sender.url});return;
    }
    if(!valid(m.request))return;
    const key=m.request.state==='DC'?'DC:'+sender.tab.id:sender.tab.id;
    if(busy.has(key)||(requestKey&&pending.has(requestKey))){respond({ok:false,reason:'source_capture_busy'});return;}
    const controller=new AbortController();busy.add(key);
    if(requestKey)pending.set(requestKey,{controller,url:sender.url});
    boot.then(()=>m.request.state==='DC'?CCDCSource.capture(m.request,sender,controller.signal):capture(m.request,sender,controller.signal))
      .then(respond,()=>respond({ok:false,reason:controller.signal.aborted?'source_cancelled':'source_worker_initialization_failed'}))
      .finally(()=>{busy.delete(key);if(requestKey)pending.delete(requestKey);});return true;
  });
  if(typeof module!=='undefined')module.exports={valid,bound};
})();

