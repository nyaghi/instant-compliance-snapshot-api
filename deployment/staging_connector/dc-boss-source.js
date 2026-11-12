/* BOSS visual evidence for a master-selected license; no identity decisions. */
const CCDCSource=(()=>{
 'use strict';
 const SEARCH='https://boss.dc.gov/business/business-license-search';
 const DETAILS=['https://boss.dc.gov/licensing/license-details','https://boss.dc.gov/homepage/license-details'];
 const LABELS=['Licensee','Trade Name','License Category','License Activity','License Number','Premise Address','License Status','Issue Date','Expiration Date'];
 const norm=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
 function articleKey(s){s=String(s||'').trim();const leading=/^THE\s+/i.test(s),trailing=/\(\s*THE\s*\)\s*\.?$/i.test(s);if(leading&&trailing)return norm(s);return norm(leading?s.replace(/^THE\s+/i,''):trailing?s.replace(/,?\s*\(\s*THE\s*\)\s*\.?$/i,''):s);}
 function reconcileRequest(d){return (!Object.hasOwn(d,'prior_renewal_date_type')||d.prior_renewal_date_type==='current_effective_date')&&d.boss_reconcile_schema===1&&!Object.hasOwn(d,'review_candidate')&&['active','current','issued','approved'].includes(String(d.raw_status||'').toLowerCase())&&['charitable solicitation','charitable exempt'].includes(d.expected_activity)&&/^[a-f0-9]{64}$/.test(d.prior_comments_sha256||'')&&/^\d{4}-\d\d-\d\d$/.test(d.prior_renewal_date||'')&&['Current','Upcoming Filing','Delinquent','Exempt'].includes(d.prior_status);}
 function sameName(a,b,d){return norm(a)===norm(b)||reconcileRequest(d)&&articleKey(a)===articleKey(b);}

 function terminalUndated(d){return d?.expiration===''&&['cancelled','canceled','closed','withdrawn','revoked','expired'].includes(String(d.raw_status||'').toLowerCase());}
 function valid(d){return d?.state==='DC'&&d.operation==='detail'&&d.url===SEARCH&&/^\d{9}$/.test(d.ein)&&/^[a-f0-9]{32}$/.test(d.run_id)&&/^\d{5,16}$/.test(d.identifier)&&typeof d.name==='string'&&d.name.length>0&&d.name.length<=300&&typeof d.raw_status==='string'&&d.raw_status.length>0&&d.raw_status.length<=100&&(/^\d{4}-\d\d-\d\d$/.test(d.expiration)||terminalUndated(d))&&Number.isFinite(d.issued_at)&&Number.isFinite(d.expires_at)&&d.expires_at>d.issued_at&&(!Object.hasOwn(d,'deadline_schema')||d.deadline_schema===1)&&d.expires_at-d.issued_at<=(d.deadline_schema===1?300.1:60.1)&&Date.now()/1000>=d.issued_at-5&&Date.now()/1000<d.expires_at&&(!Object.hasOwn(d,'boss_reconcile_schema')||reconcileRequest(d));}
 function fields(url,text,d){
  if(!DETAILS.includes(url)||typeof text!=='string'||text.length>20000||/user validation required|recaptcha timeout|verify you are human|access denied/i.test(text))return null;
  if(text.split('License Information').length!==2||text.split('Licensee Information').length!==2)return null;
  const lines=text.split('License Information')[1].split('Licensee Information')[0].split('\n').map(v=>v.trim()).filter(Boolean);
  if(LABELS.some(k=>lines.filter(v=>v===k).length!==1))return null;
  const pos=LABELS.map(k=>lines.indexOf(k));if(pos.some((v,i)=>i&&v<=pos[i-1]))return null;
  const f=Object.fromEntries(LABELS.map((k,i)=>[k,lines.slice(pos[i]+1,pos[i+1]??lines.length).join(' ')]));
  if(Object.entries(f).some(([k,v])=>!(['Trade Name','Premise Address',...(terminalUndated(d)?['Expiration Date']:[])]).includes(k)&&(!v||v==='N/A')))return null;
  const exp=/^(\d{2})\/(\d{2})\/(\d{4})$/.exec(f['Expiration Date']);
  if(f['License Number']!==d.identifier||!sameName(f.Licensee,d.name,d)||!['charitable solicitation','charitable exempt'].includes(f['License Activity'].toLowerCase())||f['License Status']!==d.raw_status||(!exp&&!(terminalUndated(d)&&f['Expiration Date']==='N/A'))||!/^\d\d\/\d\d\/\d{4}$/.test(f['Issue Date']))return null;
  const expiry=exp?`${exp[3]}-${exp[1]}-${exp[2]}`:'',parts=f['Issue Date'].split('/'),issue=`${parts[2]}-${parts[0]}-${parts[1]}`;
  const validDate=value=>{const parsed=new Date(value+'T00:00:00Z');return Number.isFinite(parsed.valueOf())&&parsed.toISOString().slice(0,10)===value;};
  if((expiry&&!validDate(expiry))||!validDate(issue))return null;
  if(reconcileRequest(d)){
   const observedDay=new Date(d.issued_at*1000).toISOString().slice(0,10);
   if(f['License Activity'].toLowerCase()!==d.expected_activity||expiry<d.expiration||issue>expiry||issue>observedDay||(!(d.prior_renewal_date_type==='current_effective_date'&&expiry===d.expiration)&&(issue<d.prior_renewal_date||(expiry>d.expiration&&issue<=d.prior_renewal_date))))return null;
  }else if(expiry!==d.expiration)return null;
  return f;
 }
 // Executed only in this capture's newly created source tab. Select the exact
 // existing license number AND name, never the first result or business entity.
 function pageStep({phase,d,linkedIdentifier}){
  const visible=e=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
  const text=document.body?.innerText||'';
  const url=location.href;
  if(url==='about:blank'&&phase==='type')return {waiting:true};
  const allowedSearch=['https://boss.dc.gov/business/business-license-search','https://boss.dc.gov/homepage/business-license-search'];
  const allowedDetail=['https://boss.dc.gov/licensing/license-details','https://boss.dc.gov/homepage/license-details'];
  const corporatePhase=['corporate_open','corporate_metadata','corporate_position'].includes(phase);
  if(!allowedSearch.includes(url)&&!allowedDetail.includes(url)&&!(corporatePhase&&url==='https://boss.dc.gov/business/info'))return {error:'unexpected_source_route',url};
  if(/user validation required|recaptcha timeout|verify you are human/i.test(text)||Array.from(document.querySelectorAll('iframe')).some(e=>visible(e)&&/recaptcha.*(?:anchor|bframe)/.test(e.src)))return {error:'source_verification_required',url};
  if(corporatePhase){
   if(phase==='corporate_open'){
    if(!allowedDetail.includes(url)||!/^[A-Z]\d{6,16}$/.test(linkedIdentifier||''))return {error:'invalid_corporate_link'};
    const links=[...document.querySelectorAll('a')].filter(e=>visible(e)&&e.innerText.trim()===linkedIdentifier);
    if(links.length!==1)return {error:'corporate_link_not_unique'};
    links[0].click();return {next:'corporate_metadata'};
   }
   if(url!=='https://boss.dc.gov/business/info'||document.readyState!=='complete'||[...document.querySelectorAll('[role="progressbar"]')].some(visible))return {waiting:true};
   if(phase==='corporate_position'){
    window.scrollTo({left:0,top:0,behavior:'instant'});
    for(const e of document.querySelectorAll('mat-sidenav-content'))e.scrollTo({left:0,top:0,behavior:'instant'});
   }
   const cells=[...document.querySelectorAll('.readonly')].filter(visible);
   const labels=['Record Name','Initial File No.','Entity Type','Entity Status','Street Address','Mailing Address'];
   const fit=labels.every(label=>{const cell=cells.find(e=>e.children[0]?.textContent.trim()===label);if(!cell)return false;
    const r=cell.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth
      &&[...cell.querySelectorAll('p')].every(p=>p.scrollWidth<=p.clientWidth+1&&p.scrollHeight<=p.clientHeight+1);});
   return {url,text:document.querySelector('main')?.innerText||text,ready:document.readyState,fit};
  }
  if(phase==='capture_position') {
   // The SPA can retain search-page scroll. A full-page screenshot then places
   // its fixed navigation bar over record fields. Move only this owned source
   // document and its known content scroller to the start; never rewrite CSS.
   window.scrollTo({left:0,top:0,behavior:'instant'});
   for(const e of document.querySelectorAll('mat-sidenav-content'))e.scrollTo({left:0,top:0,behavior:'instant'});
  }
  // Inspect real rendered text, including clipping by nested source containers.
  // No source text, stylesheet, or field is rewritten.
  const captureFit=()=>{
   const labels=['Licensee','Trade Name','License Category','License Activity','License Number','Premise Address','License Status','Issue Date','Expiration Date'];
   const cells=[...document.querySelectorAll('.readonly')].filter(visible);
   const selected=labels.map(label=>cells.filter(e=>e.children[0]?.textContent.trim()===label));
   if(selected.some(v=>v.length!==1))return {ok:false,reason:'license_field_layout_unrecognized'};
   const clipped=[];
   for(const cell of selected.map(v=>v[0]))for(const child of cell.children){
    const range=document.createRange();range.selectNodeContents(child);
    for(const rect of range.getClientRects()){
     if(!rect.width||!rect.height)continue;
     let fits=rect.left>=-1&&rect.top>=-1&&rect.right<=innerWidth+1&&rect.bottom<=innerHeight+1;
     for(let parent=child;parent&&fits;parent=parent.parentElement){
      const style=getComputedStyle(parent),box=parent.getBoundingClientRect();
      if(/hidden|clip|auto|scroll/.test(style.overflowX)&& (rect.left<box.left-1||rect.right>box.right+1))fits=false;
      if(/hidden|clip|auto|scroll/.test(style.overflowY)&& (rect.top<box.top-1||rect.bottom>box.bottom+1))fits=false;
     }
     if(!fits){clipped.push(cell.children[0].textContent.trim());break;}
    }
   }
   return {ok:clipped.length===0,clipped:[...new Set(clipped)],fields:labels.length};
  };
  if(phase==='metadata'||phase==='capture_position')return {url,text,ready:document.readyState,capture_fit:captureFit(),
   position:{x:scrollX,y:scrollY,width:innerWidth,content:[...document.querySelectorAll('mat-sidenav-content')].map(e=>({x:e.scrollLeft,y:e.scrollTop}))}};
  if(allowedDetail.includes(url))return {next:'metadata'};
  const one=(selector,test)=>{const matches=Array.from(document.querySelectorAll(selector)).filter(e=>visible(e)&&test(e));return matches.length===1?matches[0]:null;};
  const reconcile=d.boss_reconcile_schema===1;
  const searchType='License Number',query=d.identifier,comparison='Exact Match';
  if(phase==='type'){
   const select=document.getElementById('entityApplicantType');
   if(!visible(select))return {waiting:true};
   if(select.innerText.trim()===searchType)return {next:'fill'};
   select.click();return {next:'option'};
  }
  if(phase==='option'){
   const option=one('[role="option"]',e=>e.innerText.trim()===searchType);
   if(!option)return {waiting:true};option.click();return {next:'fill'};
  }
  if(phase==='fill'){
   const input=one('input',e=>e.id.startsWith('searchValue_no_autofill_'));
   const contains=one('input[type="radio"]',e=>e.closest('mat-radio-button')?.innerText.trim()===comparison);
   if(!input||!contains)return {waiting:true};
   Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,query);
   input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
   if(!contains.checked)contains.click();return {next:'submit'};
  }
  if(phase==='submit'){
   const input=one('input',e=>e.id.startsWith('searchValue_no_autofill_'));
   const button=one('button',e=>['Execute Business and License Search','Search records'].includes(e.getAttribute('aria-label')));
   if(!input||input.value!==query||!button||button.disabled)return {waiting:true};
   button.click();return {next:'licensing'};
  }
  if(phase==='licensing'){
   if(Array.from(document.querySelectorAll('[role="progressbar"]')).some(visible))return {waiting:true};
   const tab=one('[role="tab"]',e=>e.innerText.startsWith('Licensing Results'));
   if(!tab)return {waiting:true};
   if(tab.getAttribute('aria-selected')!=='true'){tab.click();return {next:'row'};}
   // When licensing is already selected, inspect its exact row in this same
   // source observation instead of scheduling another browser command.
  }
  if(phase==='row'||phase==='licensing'){
   if(Array.from(document.querySelectorAll('[role="progressbar"]')).some(visible))return {waiting:true};
   if(!Array.from(document.querySelectorAll('.mat-column-licenseNumber')).some(visible))return {waiting:true};
   const clean=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
   const rows=Array.from(document.querySelectorAll('table[aria-label="grid-table"] tr')).filter(r=>visible(r)&&r.querySelector('td.mat-column-licenseNumber'));
   // Angular can paint the column header before the bound result rows. A
   // header alone is not a completed zero-result response. Keep the same cap.
   if(!rows.length)return {waiting:true,selection:{rows:0,identifier_matches:0,matching_rows:0}};
   const canonical=value=>{value=String(value||'').trim();const leading=/^THE\s+/i.test(value),trailing=/\(\s*THE\s*\)\s*\.?$/i.test(value);if(leading&&trailing)return clean(value);return clean(leading?value.replace(/^THE\s+/i,''):trailing?value.replace(/,?\s*\(\s*THE\s*\)\s*\.?$/i,''):value);};
   const activity=r=>{
    const cell=r.querySelector('.mat-column-licenseActivity'),text=cell?.innerText.trim()||'';
    if(['Charitable Solicitation','Charitable Exempt'].includes(text))return text;
    // BOSS appends an accessible "+N more activities" control to its primary
    // activity. Read the actual label; the opened detail must still match it.
    const labels=cell?.querySelectorAll('span')||[],extra=cell?.querySelectorAll('a[aria-label]')||[];
    if(labels.length!==1||extra.length!==1)return '';
    const label=labels[0].innerText.trim(),count=extra[0].innerText.trim();
    if(!['Charitable Solicitation','Charitable Exempt'].includes(label)||!/^\+[1-9]\d*$/.test(count)
       ||extra[0].getAttribute('aria-label')!==count+' more activities'
       ||text.replace(/\s+/g,'')!==(label+count).replace(/\s+/g,''))return '';
    return label;
   };
   const matches=rows.filter(r=>r.querySelector('.mat-column-licenseNumber')?.innerText.trim()===d.identifier&&(clean(r.querySelector('.mat-column-licenseeName')?.innerText)===clean(d.name)||reconcile&&canonical(r.querySelector('.mat-column-licenseeName')?.innerText)===canonical(d.name))&&['Charitable Solicitation','Charitable Exempt'].includes(activity(r))&&(!reconcile||activity(r).toLowerCase()===d.expected_activity));
   const selection={rows:rows.length,identifier_matches:rows.filter(r=>r.querySelector('.mat-column-licenseNumber')?.innerText.trim()===d.identifier).length,matching_rows:matches.length};
   if(matches.length!==1)return {error:'selected_license_not_unique_or_absent',selection};
   const link=matches[0].querySelector('.mat-column-licenseeName a');if(!visible(link))return {error:'selected_license_link_unavailable'};
   link.click();return {next:'metadata',selection};
  }
  return {error:'unknown_source_phase'};
 }
 async function captureOne(d,sender,signal,activeBudgetMs=30000,requireCorporate=false,corporateProof=null){
  const start=Date.now(),steps=[];let end=Math.min(start+activeBudgetMs,d.expires_at*1000),owned=null,tab=null,attached=false,closed=false,rail=null,selection=null;
  let onCancel;
  const cancelled=new Promise((_,reject)=>{onCancel=()=>reject(Error('source_cancelled'));signal?.addEventListener('abort',onCancel,{once:true});});
  // Attach a handler before any source operation so an early cancellation is contained.
  cancelled.catch(()=>{});
  const check=()=>{if(signal?.aborted)throw Error('source_cancelled');};
  function limited(p,label,late,reserve=null){const at=Date.now();let timer;return Promise.race([cancelled,Promise.resolve(p).then(v=>{if(closed||signal?.aborted){late?.(v);throw Error('closed');}return v;}),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('timeout:'+label)),Math.max(1,Math.min(reserve===null?(label==='create'?Math.max(1,end-Date.now()-3000):3000):Math.max(1,end-Date.now()-reserve),end-Date.now())));})]).finally(()=>{clearTimeout(timer);steps.push({phase:label,seconds:(Date.now()-at)/1000});});}
  function captureTiming(finished){const seconds=(finished-start)/1000,queue_seconds=steps.find(s=>s.phase==='queue')?.seconds||0;return {seconds,queue_seconds,active_seconds:seconds-queue_seconds,steps,...(selection?{selection}: {})};}
  const command=(method,params={},reserve=null,label=method)=>{check();return limited(chrome.debugger.sendCommand({tabId:tab.id},method,params),label,null,reserve);};
  // Keep one pending source command; reserve five seconds for image completion.
  // Final binding gets only the same remaining active deadline, never a new clock.
  let linkedIdentifier=null;
  const observe=async (phase,final=false)=>{const r=await command('Runtime.evaluate',{expression:`JSON.stringify((${pageStep.toString()})(${JSON.stringify({phase,d,linkedIdentifier})}))`,returnByValue:true},final?0:5000,'Runtime.evaluate:'+phase+(final?':final':''));if(r.exceptionDetails)throw Error('source_dom_exception');return JSON.parse(r.result?.value||'null');};
  try{
   check();
   if(!valid(d))throw Error('invalid_source_request');
   const queued=Date.now();
   // Queue time is separate from the 30-second active capture allowance. The
   // rail keeps its three-second reserve; retain five more for useful source
   // work without extending the signed request or taking an extra window.
   try {rail=await CCSourceRail.acquire(sender,'DC',d.deadline_schema===1?d.expires_at*1000-30000:Math.min(start+60000,d.expires_at*1000)-5000,d.run_id,signal);check();}
   finally {steps.push({phase:'queue',seconds:(Date.now()-queued)/1000});}
   end=Math.min(d.deadline_schema===1?d.expires_at*1000:start+60000,Date.now()+activeBudgetMs,d.expires_at*1000);if(rail)rail.job.activeExpiresAt=end;
   owned=await limited(CCSourceRail.create(rail,{url:SEARCH,...(rail?.options||{type:'popup',focused:false,width:1280,height:1000})}),'create',w=>chrome.windows.remove(w.id).catch(()=>{}));tab=owned?.tabs?.[0];if(rail)rail.windowId=owned.id;
   if(!Number.isInteger(owned?.id)||!Number.isInteger(tab?.id))throw Error('owned_window_unavailable');
   await limited(chrome.debugger.attach({tabId:tab.id},'1.3'),'attach',()=>chrome.debugger.detach({tabId:tab.id}).catch(()=>{}));attached=true;
   // Initialization may finish after Chrome's generic three-second timer.
   // Spend only this capture's remaining allowance, reserving twenty seconds
   // when available for source search, exact binding and the original image.
   // If creation already consumed that reserve, preserve the prior three-second
   // command allowance without taking the final five-second capture reserve.
   const enableReserve=Math.min(20000,Math.max(5000,end-Date.now()-3000));
   await command('Page.enable',{},enableReserve);
   let phase='type',meta=null;
   while(Date.now()<end-3000){
    let observed;
    try{observed=await observe(phase);}catch(e){if(!/context.*destroyed|Cannot find.*context/i.test(e.message))throw e;await new Promise(r=>setTimeout(r,100));continue;}
    if(observed?.selection)selection=observed.selection;
    if(observed?.error)throw Error(observed.error);
    if(phase==='metadata'&&observed?.ready==='complete'&&fields(observed.url,observed.text,d)&&(!requireCorporate||corporateRecord(observed.text))){meta=observed;break;}
    if(observed?.next){steps.push({phase:'source:'+phase,elapsed_seconds:(Date.now()-start)/1000});phase=observed.next;}
    await new Promise(r=>setTimeout(r,100));
   }
   if(!meta)throw Error('selected_detail_unavailable');
   const before=fields(meta.url,meta.text,d);
   // This tab belongs to this capture and is closed in finally. Give the source
   // a desktop layout and enough viewport height for its internal scroller.
   await command('Emulation.setDeviceMetricsOverride',{width:1280,height:1600,deviceScaleFactor:1,mobile:false},5000);
   const positioned=await observe('capture_position');
   if(!positioned?.capture_fit?.ok)throw Error('selected_detail_fields_clipped');
   const atStart=m=>m?.position?.x===0&&m.position.y===0&&Array.isArray(m.position.content)&&m.position.content.every(e=>e.x===0&&e.y===0);
   if(!atStart(positioned)||JSON.stringify(before)!==JSON.stringify(fields(positioned.url,positioned.text,d)))throw Error('selected_detail_position_changed');
   meta=positioned;
   const layout=await command('Page.getLayoutMetrics',{},4000);const rect=layout.cssContentSize||layout.contentSize;
   if(!rect||rect.width<1||rect.height<1||rect.width*rect.height>20000000)throw Error('source_size_rejected');
   // Capture the complete fitted viewport. CSS-sized clip rectangles are not
   // screenshot pixel dimensions when the browser's page zoom is not 100%.
   const options={format:'jpeg',quality:80,captureBeyondViewport:false,fromSurface:true};
   let shot=await command('Page.captureScreenshot',options,3000);
   if(!shot?.data && Date.now()+5000<end){
    // Only recover a completed empty command. A pending or timed-out CDP
    // operation owns this page until cleanup and is never retried in parallel.
    const fresh=await observe('metadata');
    if(fresh?.url!==meta.url||!fresh.capture_fit?.ok||!atStart(fresh)
        ||JSON.stringify(before)!==JSON.stringify(fields(fresh.url,fresh.text,d)))
      throw Error('selected_detail_changed_before_capture_retry');
    shot=await command('Page.captureScreenshot',options,3000,'Page.captureScreenshot:empty-retry');
   }
   if(!shot?.data)throw Error('source_empty_capture');
   const after=await observe('metadata',true),afterFields=after&&fields(after.url,after.text,d);
   const finished=Date.now();
   check();
   if(requireCorporate&&JSON.stringify(corporateRecord(after?.text||''))!==JSON.stringify(corporateRecord(meta.text)))throw Error('corporate_record_changed');
   if(after?.url!==meta.url||!afterFields||!after.capture_fit?.ok||JSON.stringify(before)!==JSON.stringify(afterFields)||!atStart(after)||after.position.width!==meta.position.width||finished>=end)throw Error('selected_detail_changed');
   const license={ok:true,request:d,url:after.url,public_text:after.text,source_fields:afterFields,image:shot.data,captured_at:finished/1000,navigation_started_at:start/1000,timing:captureTiming(finished)};
   if(!corporateProof)return license;
   linkedIdentifier=corporateRecord(after.text)?.identifier;
   if(!linkedIdentifier)throw Error('corporate_link_missing');
   const opened=await observe('corporate_open');if(opened?.next!=='corporate_metadata')throw Error('corporate_link_unavailable');
   let entity=null;
   while(Date.now()<end-3000){
    const observed=await observe('corporate_metadata');
    if(observed?.error)throw Error(observed.error);
    const f=corporateFields(observed?.url,observed?.text);
    if(f&&f['Initial File No.']===linkedIdentifier){entity=f;break;}
    await new Promise(r=>setTimeout(r,100));
   }
   if(!entity||!corporateProof.names.some(n=>norm(n)===norm(entity['Record Name'])))throw Error('corporate_legal_name_unconfirmed');
   const positionedCorporate=await observe('corporate_position',true);
   if(!positionedCorporate?.fit||JSON.stringify(corporateFields(positionedCorporate.url,positionedCorporate.text))!==JSON.stringify(entity))throw Error('corporate_fields_clipped_or_changed');
   const corporateShot=await command('Page.captureScreenshot',{format:'jpeg',quality:80,captureBeyondViewport:false,fromSurface:true},1000);
   const finalCorporate=await observe('corporate_metadata',true),done=Date.now();
   if(!finalCorporate?.fit||JSON.stringify(corporateFields(finalCorporate.url,finalCorporate.text))!==JSON.stringify(entity)||done>=end)throw Error('corporate_profile_changed');
   return {...license,corporate_detail:{url:finalCorporate.url,public_text:finalCorporate.text,image:corporateShot.data,captured_at:done/1000,linked_identifier:linkedIdentifier},timing:captureTiming(done)};
  }catch(e){return {ok:false,reason:String(e.message||'source_capture_failed').slice(0,150),timing:captureTiming(Date.now())};}
  finally{closed=true;signal?.removeEventListener("abort",onCancel);const cleanup=[];if(attached&&tab)cleanup.push(chrome.debugger.detach({tabId:tab.id}).catch(()=>{}));if(owned)cleanup.push(chrome.windows.remove(owned.id).catch(()=>{}));let timer;await Promise.race([Promise.allSettled(cleanup),new Promise(r=>{timer=setTimeout(r,500);})]);clearTimeout(timer);if(rail)await CCSourceRail.release(rail);}
 }
 function continuityRequest(d){
  const c=d.corporate_continuity_candidate;
  if(d.corporate_continuity_schema!==1||!c||Object.keys(c).sort().join(',')!=='expiration,identifier,name,raw_status'||d.review_candidate||d.boss_reconcile_schema||c.raw_status!=='Active'||norm(c.name)!==norm(d.name)||c.identifier===d.identifier||!/^\d{5,16}$/.test(c.identifier)||!/^\d{4}-\d\d-\d\d$/.test(c.expiration)||c.expiration<=d.expiration)throw Error('invalid_corporate_continuity_request');
  const {corporate_continuity_schema,corporate_continuity_candidate,...base}=d;return {...base,...c};
 }
 function corporateRecord(text){
  if(text.split('Licensee Information').length!==2||text.split('Registered/Resident Agent Information').length!==2)return null;
  const part=text.split('Licensee Information')[1].split('Registered/Resident Agent Information')[0];
  const m=/^\s*Licensee Name\s+(.+?)\s+Record Name\s+([A-Z]\d{6,16})\s+Entity Status\s+(.+?)\s*$/s.exec(part);return m?{name:m[1],identifier:m[2]}:null;
 }
 function corporateFields(url,text){
  if(url!=='https://boss.dc.gov/business/info'||typeof text!=='string'||text.length>80000)return null;
  const lines=text.split(/Jurisdiction of Formation|Biennial Report Information/)[0].split('\n').map(s=>s.trim()).filter(Boolean);
  const labels=['Record Name','Entity Type','Election Type','Initial File No.','Entity Status','Street Address','Mailing Address','Entity Email','File Date','Purpose'];
  if(labels.some(k=>lines.filter(s=>s===k).length!==1))return null;
  const at=labels.map(k=>lines.indexOf(k));if(at.some((v,i)=>i&&v<=at[i-1]))return null;
  const f=Object.fromEntries(labels.slice(0,-1).map((k,i)=>[k,lines.slice(at[i]+1,at[i+1]).join(' ')]));
  return /^[A-Z]\d{6,16}$/.test(f['Initial File No.'])&&f['Record Name']&&f['Entity Type'].includes('Nonprofit')?f:null;
 }
 function linkedRequest(d){
  const c=d.corporate_continuity_candidate,p=d.corporate_link_proof;
  if(d.corporate_continuity_schema!==2||!c||Object.keys(c).sort().join(',')!=='expiration,identifier,name,raw_status'
     ||d.review_candidate||d.boss_reconcile_schema||c.raw_status!=='Active'||c.identifier===d.identifier||!/^\d{5,16}$/.test(c.identifier)
     ||norm(c.name)===norm(d.name)||!/^\d{4}-\d\d-\d\d$/.test(c.expiration)||c.expiration<=d.expiration
     ||!p||!Array.isArray(p.names)||!p.names.length||p.names.length>32||!Array.isArray(p.addresses)||!p.addresses.length||p.addresses.length>12)throw Error('invalid_corporate_link_request');
  const {corporate_continuity_schema,corporate_continuity_candidate,corporate_link_proof,...base}=d;return {...base,...c};
 }
 async function capture(d,sender,signal){
  if(d?.corporate_continuity_schema===2){
   let next;try{next=linkedRequest(d);}catch(e){return {ok:false,reason:e.message};}
   const current=await captureOne(next,sender,signal,30000,true,d.corporate_link_proof);
   if(!current.ok)return current;
   return {...current,request:d,current_license:current,corporate_detail:current.corporate_detail};
  }
  if(!Object.hasOwn(d,'corporate_continuity_schema'))return captureOne(d,sender,signal);
  let next;
  try{next=continuityRequest(d);}catch(e){return {ok:false,reason:e.message};}
  const prior=await captureOne(d,sender,signal,30000,true);if(!prior.ok)return prior;
  const used=prior.timing.active_seconds,remaining=Math.floor((30-used)*1000);
  if(remaining<5000)return {ok:false,reason:'corporate_continuity_deadline',timing:prior.timing};
  const current=await captureOne(next,sender,signal,remaining,true);
  const timing={seconds:prior.timing.seconds+(current.timing?.seconds||0),queue_seconds:prior.timing.queue_seconds+(current.timing?.queue_seconds||0),active_seconds:used+(current.timing?.active_seconds||0),steps:[...prior.timing.steps,...(current.timing?.steps||[])]};
  if(!current.ok)return {...current,timing};
  const a=corporateRecord(prior.public_text),b=corporateRecord(current.public_text);
  if(!a||!b||a.identifier!==b.identifier||norm(a.name)!==norm(d.name)||norm(b.name)!==norm(next.name))return {ok:false,reason:'corporate_identity_not_established',timing};
  return {...current,request:d,prior_license:prior,current_license:current,timing,navigation_started_at:prior.navigation_started_at};
 }
 return {valid,fields,pageStep,capture,continuityRequest,corporateRecord,corporateFields,linkedRequest};
})();
if(typeof module!=='undefined')module.exports=CCDCSource;
