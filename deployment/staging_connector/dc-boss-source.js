/* BOSS visual evidence for a master-selected license; no identity decisions. */
const CCDCSource=(()=>{
 'use strict';
 const SEARCH='https://boss.dc.gov/business/business-license-search';
 const DETAILS=['https://boss.dc.gov/licensing/license-details','https://boss.dc.gov/homepage/license-details'];
 const LABELS=['Licensee','Trade Name','License Category','License Activity','License Number','Premise Address','License Status','Issue Date','Expiration Date'];
 const norm=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
 function valid(d){return d?.state==='DC'&&d.operation==='detail'&&d.url===SEARCH&&/^\d{9}$/.test(d.ein)&&/^[a-f0-9]{32}$/.test(d.run_id)&&/^\d{5,16}$/.test(d.identifier)&&typeof d.name==='string'&&d.name.length>0&&d.name.length<=300&&typeof d.raw_status==='string'&&d.raw_status.length>0&&d.raw_status.length<=100&&/^\d{4}-\d\d-\d\d$/.test(d.expiration)&&Number.isFinite(d.issued_at)&&Number.isFinite(d.expires_at)&&d.expires_at>d.issued_at&&(!Object.hasOwn(d,'deadline_schema')||d.deadline_schema===1)&&d.expires_at-d.issued_at<=(d.deadline_schema===1?300.1:60.1)&&Date.now()/1000>=d.issued_at-5&&Date.now()/1000<d.expires_at;}
 function fields(url,text,d){
  if(!DETAILS.includes(url)||typeof text!=='string'||text.length>20000||/user validation required|recaptcha timeout|verify you are human|access denied/i.test(text))return null;
  if(text.split('License Information').length!==2||text.split('Licensee Information').length!==2)return null;
  const lines=text.split('License Information')[1].split('Licensee Information')[0].split('\n').map(v=>v.trim()).filter(Boolean);
  if(LABELS.some(k=>lines.filter(v=>v===k).length!==1))return null;
  const pos=LABELS.map(k=>lines.indexOf(k));if(pos.some((v,i)=>i&&v<=pos[i-1]))return null;
  const f=Object.fromEntries(LABELS.map((k,i)=>[k,lines.slice(pos[i]+1,pos[i+1]??lines.length).join(' ')]));
  if(Object.entries(f).some(([k,v])=>!['Trade Name','Premise Address'].includes(k)&&(!v||v==='N/A')))return null;
  const exp=/^(\d{2})\/(\d{2})\/(\d{4})$/.exec(f['Expiration Date']);
  if(f['License Number']!==d.identifier||norm(f.Licensee)!==norm(d.name)||!['charitable solicitation','charitable exempt'].includes(f['License Activity'].toLowerCase())||f['License Status']!==d.raw_status||!exp||`${exp[3]}-${exp[1]}-${exp[2]}`!==d.expiration||!/^\d\d\/\d\d\/\d{4}$/.test(f['Issue Date']))return null;
  return f;
 }
 // Executed only in this capture's newly created source tab. Select the exact
 // existing license number AND name, never the first result or business entity.
 function pageStep({phase,d}){
  const visible=e=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
  const text=document.body?.innerText||'';
  const url=location.href;
  if(url==='about:blank'&&phase==='type')return {waiting:true};
  const allowedSearch=['https://boss.dc.gov/business/business-license-search','https://boss.dc.gov/homepage/business-license-search'];
  const allowedDetail=['https://boss.dc.gov/licensing/license-details','https://boss.dc.gov/homepage/license-details'];
  if(!allowedSearch.includes(url)&&!allowedDetail.includes(url))return {error:'unexpected_source_route',url};
  if(/user validation required|recaptcha timeout|verify you are human/i.test(text)||Array.from(document.querySelectorAll('iframe')).some(e=>visible(e)&&/recaptcha.*(?:anchor|bframe)/.test(e.src)))return {error:'source_verification_required',url};
  if(phase==='capture_position') {
   // The SPA can retain search-page scroll. A full-page screenshot then places
   // its fixed navigation bar over record fields. Move only this owned source
   // document and its known content scroller to the start; never rewrite CSS.
   window.scrollTo({left:0,top:0,behavior:'instant'});
   for(const e of document.querySelectorAll('mat-sidenav-content'))e.scrollTo({left:0,top:0,behavior:'instant'});
  }
  if(phase==='metadata'||phase==='capture_position')return {url,text,ready:document.readyState,
   position:{x:scrollX,y:scrollY,width:innerWidth,content:[...document.querySelectorAll('mat-sidenav-content')].map(e=>({x:e.scrollLeft,y:e.scrollTop}))}};
  if(allowedDetail.includes(url))return {next:'metadata'};
  const one=(selector,test)=>{const matches=Array.from(document.querySelectorAll(selector)).filter(e=>visible(e)&&test(e));return matches.length===1?matches[0]:null;};
  if(phase==='type'){
   const select=document.getElementById('entityApplicantType');
   if(!visible(select))return {waiting:true};
   if(select.innerText.trim()==='Business Name')return {next:'fill'};
   select.click();return {next:'option'};
  }
  if(phase==='option'){
   const option=one('[role="option"]',e=>e.innerText.trim()==='Business Name');
   if(!option)return {waiting:true};option.click();return {next:'fill'};
  }
  if(phase==='fill'){
   const input=one('input',e=>e.id.startsWith('searchValue_no_autofill_'));
   const contains=one('input[type="radio"]',e=>e.closest('mat-radio-button')?.innerText.trim()==='Contains');
   if(!input||!contains)return {waiting:true};
   Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,d.name);
   input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
   if(!contains.checked)contains.click();return {next:'submit'};
  }
  if(phase==='submit'){
   const input=one('input',e=>e.id.startsWith('searchValue_no_autofill_'));
   const button=one('button',e=>['Execute Business and License Search','Search records'].includes(e.getAttribute('aria-label')));
   if(!input||input.value!==d.name||!button||button.disabled)return {waiting:true};
   button.click();return {next:'licensing'};
  }
  if(phase==='licensing'){
   if(Array.from(document.querySelectorAll('[role="progressbar"]')).some(visible))return {waiting:true};
   const tab=one('[role="tab"]',e=>e.innerText.startsWith('Licensing Results'));
   if(!tab)return {waiting:true};
   if(tab.getAttribute('aria-selected')!=='true')tab.click();return {next:'row'};
  }
  if(phase==='row'){
   if(Array.from(document.querySelectorAll('[role="progressbar"]')).some(visible))return {waiting:true};
   if(!Array.from(document.querySelectorAll('.mat-column-licenseNumber')).some(visible))return {waiting:true};
   const clean=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
   const rows=Array.from(document.querySelectorAll('table[aria-label="grid-table"] tr')).filter(visible);
   const matches=rows.filter(r=>r.querySelector('.mat-column-licenseNumber')?.innerText.trim()===d.identifier&&clean(r.querySelector('.mat-column-licenseeName')?.innerText)===clean(d.name)&&['Charitable Solicitation','Charitable Exempt'].includes(r.querySelector('.mat-column-licenseActivity')?.innerText.trim()));
   if(matches.length!==1)return {error:'selected_license_not_unique_or_absent'};
   const link=matches[0].querySelector('.mat-column-licenseeName a');if(!visible(link))return {error:'selected_license_link_unavailable'};
   link.click();return {next:'metadata'};
  }
  return {error:'unknown_source_phase'};
 }
 async function capture(d,sender,signal){
  const start=Date.now(),steps=[];let end=Math.min(start+30000,d.expires_at*1000),owned=null,tab=null,attached=false,closed=false,rail=null;
  let onCancel;
  const cancelled=new Promise((_,reject)=>{onCancel=()=>reject(Error('source_cancelled'));signal?.addEventListener('abort',onCancel,{once:true});});
  // Attach a handler before any source operation so an early cancellation is contained.
  cancelled.catch(()=>{});
  const check=()=>{if(signal?.aborted)throw Error('source_cancelled');};
  function limited(p,label,late,reserve=null){const at=Date.now();let timer;return Promise.race([cancelled,Promise.resolve(p).then(v=>{if(closed||signal?.aborted){late?.(v);throw Error('closed');}return v;}),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('timeout:'+label)),Math.max(1,Math.min(reserve===null?(label==='create'?Math.max(1,end-Date.now()-3000):3000):Math.max(1,end-Date.now()-reserve),end-Date.now())));})]).finally(()=>{clearTimeout(timer);steps.push({phase:label,seconds:(Date.now()-at)/1000});});}
  function captureTiming(finished){const seconds=(finished-start)/1000,queue_seconds=steps.find(s=>s.phase==='queue')?.seconds||0;return {seconds,queue_seconds,active_seconds:seconds-queue_seconds,steps};}
  const command=(method,params={},reserve=null,label=method)=>{check();return limited(chrome.debugger.sendCommand({tabId:tab.id},method,params),label,null,reserve);};
  // Keep one pending source command; reserve five seconds for image completion.
  // Final binding gets only the same remaining active deadline, never a new clock.
  const observe=async (phase,final=false)=>{const r=await command('Runtime.evaluate',{expression:`JSON.stringify((${pageStep.toString()})(${JSON.stringify({phase,d})}))`,returnByValue:true},final?0:5000,'Runtime.evaluate:'+phase+(final?':final':''));if(r.exceptionDetails)throw Error('source_dom_exception');return JSON.parse(r.result?.value||'null');};
  try{
   check();
   if(!valid(d))throw Error('invalid_source_request');
   const queued=Date.now();
   // Queue time is separate from the 30-second active capture allowance. The
   // rail keeps its three-second reserve; retain five more for useful source
   // work without extending the signed request or taking an extra window.
   try {rail=await CCSourceRail.acquire(sender,'DC',d.deadline_schema===1?d.expires_at*1000-30000:Math.min(start+60000,d.expires_at*1000)-5000,d.run_id,signal);check();}
   finally {steps.push({phase:'queue',seconds:(Date.now()-queued)/1000});}
   end=Math.min(d.deadline_schema===1?d.expires_at*1000:start+60000,Date.now()+30000,d.expires_at*1000);if(rail)rail.job.activeExpiresAt=end;
   owned=await limited(CCSourceRail.create(rail,{url:SEARCH,...(rail?.options||{type:'popup',focused:false,width:1280,height:1000})}),'create',w=>chrome.windows.remove(w.id).catch(()=>{}));tab=owned?.tabs?.[0];if(rail)rail.windowId=owned.id;
   if(!Number.isInteger(owned?.id)||!Number.isInteger(tab?.id))throw Error('owned_window_unavailable');
   await limited(chrome.debugger.attach({tabId:tab.id},'1.3'),'attach',()=>chrome.debugger.detach({tabId:tab.id}).catch(()=>{}));attached=true;await command('Page.enable');
   let phase='type',meta=null;
   while(Date.now()<end-3000){
    let observed;
    try{observed=await observe(phase);}catch(e){if(!/context.*destroyed|Cannot find.*context/i.test(e.message))throw e;await new Promise(r=>setTimeout(r,100));continue;}
    if(observed?.error)throw Error(observed.error);
    if(phase==='metadata'&&observed?.ready==='complete'&&fields(observed.url,observed.text,d)){meta=observed;break;}
    if(observed?.next){steps.push({phase:'source:'+phase,elapsed_seconds:(Date.now()-start)/1000});phase=observed.next;}
    await new Promise(r=>setTimeout(r,100));
   }
   if(!meta)throw Error('selected_detail_unavailable');
   const before=fields(meta.url,meta.text,d);
   const positioned=await observe('capture_position');
   const atStart=m=>m?.position?.x===0&&m.position.y===0&&Array.isArray(m.position.content)&&m.position.content.every(e=>e.x===0&&e.y===0);
   if(!atStart(positioned)||JSON.stringify(before)!==JSON.stringify(fields(positioned.url,positioned.text,d)))throw Error('selected_detail_position_changed');
   meta=positioned;
   const layout=await command('Page.getLayoutMetrics',{},4000);const rect=layout.cssContentSize||layout.contentSize;
   if(!rect||rect.width<1||rect.height<1||rect.width*rect.height>20000000)throw Error('source_size_rejected');
   const shot=await command('Page.captureScreenshot',{format:'jpeg',quality:80,captureBeyondViewport:true,fromSurface:true,clip:{x:0,y:0,width:rect.width,height:rect.height,scale:1}},3000);
   const after=await observe('metadata',true),afterFields=after&&fields(after.url,after.text,d);
   const finished=Date.now();
   check();
   if(after?.url!==meta.url||!afterFields||JSON.stringify(before)!==JSON.stringify(afterFields)||!atStart(after)||after.position.width!==meta.position.width||finished>=end)throw Error('selected_detail_changed');
   return {ok:true,request:d,url:after.url,public_text:after.text,source_fields:afterFields,image:shot.data,captured_at:finished/1000,navigation_started_at:start/1000,timing:captureTiming(finished)};
  }catch(e){return {ok:false,reason:String(e.message||'source_capture_failed').slice(0,150),timing:captureTiming(Date.now())};}
  finally{closed=true;signal?.removeEventListener("abort",onCancel);const cleanup=[];if(attached&&tab)cleanup.push(chrome.debugger.detach({tabId:tab.id}).catch(()=>{}));if(owned)cleanup.push(chrome.windows.remove(owned.id).catch(()=>{}));let timer;await Promise.race([Promise.allSettled(cleanup),new Promise(r=>{timer=setTimeout(r,500);})]);clearTimeout(timer);if(rail)await CCSourceRail.release(rail);}
 }
 return {valid,fields,pageStep,capture};
})();
if(typeof module!=='undefined')module.exports=CCDCSource;
