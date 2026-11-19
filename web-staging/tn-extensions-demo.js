/* Staging only. No live filing automation or IRS gateway. */
(() => {
  'use strict';
  const API='/api/tn-extension-demo';
  const PORTAL='https://tncab.tnsos.gov/portal/portal-login-page';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let context=null,generation=0,current=null,dialog=null,working=false,unknownSend=false,receiptTimer=null,receiptAttempts=0,capturing=false,captureFailed=false,refreshController=null,refreshSerial=0;
  document.addEventListener('submit',event=>{if(event.target.id==='snapshotForm'){refreshController?.abort();generation++;}},true);
  async function request(payload) {
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try {
      const response=await fetch(API,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:controller.signal});
      const data=await response.json();
      if(!response.ok) { const e=new Error(data.error||'The extension check did not complete.');e.signIn=data.sign_in;throw e; }
      return data;
    } finally {clearTimeout(timer);}
  }
  function links(r) {
    return [['application','View submitted test extension'],['acknowledgment','View test acknowledgment'],['confirmation_screen','View captured confirmation screen'],['state_response','View test state review response'],['irs_filed','View test-filed Form 8868'],['irs_acceptance','View test IRS acceptance']].filter(([k])=>r.documents[k])
      .map(([k,label])=>`<a href="${esc(r.documents[k])}" target="_blank" rel="noopener">${label} — Demo only</a>`).join(' · ');
  }
  function dateLabel(value){if(!value)return 'Not verified';const d=new Date(value+'T12:00:00Z');return Number.isNaN(d.getTime())?value:d.toLocaleDateString('en-US',{year:'numeric',month:'long',day:'numeric',timeZone:'UTC'});}
  function eligibilityDetails(data){
    const e=data.eligibility_explanation;if(!e)return '';
    const heading='Eligibility findings';
    return `<div class="tn-eligibility-explanation"><strong>${heading}:</strong><ul>${(e.basis||[]).map(item=>`<li>${esc(item)}</li>`).join('')}</ul><p>${esc(e.summary)}${e.prior_filing_confirmation_required?' Confirm that no renewal or extension is already submitted before preparing the request.':''}</p></div>
      ${e.federal?.deadline?`<p class="tn-small">Federal Form 8868 deadline: ${esc(dateLabel(e.federal.deadline))}. ${esc(e.federal.eligible?'New federal test submission is available after review.':e.federal.reason)}</p>`:''}
      <p class="tn-small">Source checked ${esc(e.checked_at_epoch?new Date(e.checked_at_epoch*1000).toLocaleString():dateLabel(e.checked_at))}. <a href="${esc(e.source)}" target="_blank" rel="noopener">Tennessee extension rule</a> · <a href="${esc(e.registry_source)}" target="_blank" rel="noopener">Registration source</a></p>`;
  }
  function rowPanel(data) {
    if(!context||!context.cell.isConnected)return;
    context.checkData=data;
    let box=context.cell.querySelector('.tn-extension-row');
    if(!box){box=document.createElement('div');box.className='tn-extension-row';context.cell.append(box);}
    const r=context.checked?(data.requests?.find(x=>['Extension submitted','Receipt acknowledged','Submission unconfirmed'].includes(x.status))||data.requests?.[0]):null;
    const pending=data.needs_prior_confirmation&&data.eligibility.reasons.length===1;
    const enabled=context.checked&&(data.eligibility.eligible||pending);
    const ordinal=data.facts?.extension_number===2?'second':'first';
    const pendingLabel=data.facts?.account_check?.requires_period_review?'Matching Tennessee filings need review. Check their fiscal period and correct an existing returned request before creating another.':`May be eligible to request a ${ordinal} extension. Prior filings need your confirmation.`;
    box.innerHTML=`<strong>Tennessee extensions</strong><br><button type="button" id="tnFileExtension" ${enabled?'':'disabled'}>File Extension</button>
      <span>${esc(!context.checked?'Click Check for extensions to assess Tennessee.':pending?pendingLabel:data.eligibility.eligible?`Eligible to prepare a ${ordinal}-extension request based on the reviewed record and your prior-filing answer. Submission is test-only.`:data.eligibility.reasons.join(' '))}</span>
      ${context.checked?eligibilityDetails(data):''}
      ${context.checked?`<details class="tn-account-summary"><summary>Tennessee account: ${esc(data.facts?.account_check?.records?.length?data.facts.account_check.records.map(r=>r.status).join(', '):(data.facts?.account_check?.state||'not checked').replaceAll('_',' '))}</summary>${accountDetails(data.facts)}</details>`:''}
      ${r?`<div class="tn-demo-saved"><strong>Demo only — ${esc(r.status)}</strong><br>${links(r)}
      ${r.confirmation?`<small>${esc(r.confirmation)} · ${esc(new Date((r.acknowledged_at||r.submitted_at)*1000).toLocaleString())}</small>`:''}
      ${['Draft','Submission failed'].includes(r.status)?'':'<button type="button" class="tn-resume">View submitted filing</button>'}</div>`:''}`;
    box.querySelector('.tn-resume')?.addEventListener('click',()=>{current=r;irsAnswer="";showFederal=false;unknownSend=false;openDialog();});
    box.querySelector('#tnFileExtension')?.addEventListener('click',()=>{irsAnswer="";showFederal=false;current=!data.needs_prior_confirmation&&r?.scenario==='verified'&&['Draft','Submission failed'].includes(r.status)&&['coid','period_start','period_end','expiration'].every(k=>r.facts[k]===data.facts[k])?r:null;unknownSend=false;openDialog();});
  }
  async function hydrate(action,quiet=false) {
    if(!context)return;
    const version=generation,ein=context.result.ein;
    const serial=action==='check'?++refreshSerial:refreshSerial;
    try {
      if(action==='check')await refreshPublic(version,ein);
      if(version!==generation||serial!==refreshSerial)return;
      const data=await request({action,ein});
      if(version!==generation||serial!==refreshSerial)return;
      if(action==='check')context.checked=true;
      rowPanel(data);
      if(!quiet)document.getElementById('tnExtensionMessage').textContent=data.facts.refresh_error||'Fresh Tennessee check completed. Other results are unchanged. Test submissions only.';
    } catch(e) {
      if(version!==generation||quiet)return;
      const msg=document.getElementById('tnExtensionMessage');msg.textContent=e.message;
      if(e.signIn){const a=document.createElement('a');a.href=e.signIn;a.textContent=' Sign in to CharityClarity';a.target='_blank';a.rel='noopener';msg.append(a);}
    }
  }
  async function accountRead(facts,nonce,signal){
    if(!facts.coid)return {state:'unavailable',records:[]};
    const id=crypto.randomUUID();
    return new Promise(resolve=>{
      let timer;
      const finish=observation=>{clearTimeout(timer);window.removeEventListener('message',receive);signal?.removeEventListener('abort',abort);resolve(observation);};
      const abort=()=>finish({state:'unavailable',records:[]});
      const receive=event=>{const m=event.data;if(event.source===window&&event.origin===location.origin&&m?.channel==='cc-tn-extension-account-v1'&&m.direction==='response'&&m.id===id&&m.nonce===nonce&&/^[a-p]{32}$/.test(m.extension_id||''))finish(m.observation);};
      window.addEventListener('message',receive);signal?.addEventListener('abort',abort,{once:true});
      timer=setTimeout(()=>finish({state:'connector_update_required',records:[]}),24000);
      window.postMessage({channel:'cc-tn-extension-account-v1',direction:'request',id,nonce,coid:facts.coid,names:[facts.name]},location.origin);
    });
  }
  async function refreshPublic(version,ein){
    context.checked=false;if(context.checkData)rowPanel(context.checkData);
    const message=document.getElementById('tnExtensionMessage');message.textContent='Refreshing Tennessee registration and extension eligibility…';
    const started=await request({action:'begin-check',ein,name:context.result.organization_name});
    refreshController=new AbortController();const signal=AbortSignal.any([refreshController.signal,AbortSignal.timeout(60000)]);
    try{
      if(!window.CCNYConnector?.lookup)throw new Error('Connect the registry connector, then Check for extensions again.');
      const credentials=window.CCIdentityConfig?.();if(!credentials)throw new Error('Unlock CharityClarity before refreshing Tennessee.');
      await window.CCNYConnector.lookup({...credentials,state:'TN',organization_name:started.name,ein,alternate_names:context.aliases,extensionRefresh:started.nonce,signal,onProgress:text=>{if(version===generation&&text)message.textContent=text;}});
      if(version!==generation)return;
      const fresh=await request({action:'status',ein});
      if(!fresh.facts.refresh_error){
        message.textContent='Checking signed-in Tennessee account history…';
        const observation=await accountRead(fresh.facts,started.nonce,signal);
        if(version!==generation)return;
        try{await request({action:'account-observation',ein,nonce:started.nonce,observation});}
        catch{await request({action:'account-observation',ein,nonce:started.nonce,observation:{state:'unavailable',records:[]}});}
      }
    }catch(error){
      if(version!==generation)return;
      const kind=/connector|connection|browser/i.test(error.message||'')?'connector_unavailable':['AbortError','TimeoutError'].includes(error.name)?'timeout':'public_unconfirmed';
      await request({action:'refresh-failed',ein,nonce:started.nonce,kind});
      message.textContent=error.message||'The fresh Tennessee check did not complete. Try Check for extensions again.';
    }finally{refreshController=null;}
  }
  function accountDetails(facts){
    const a=facts?.account_check;if(!a)return '';
    const label={checked:'Account history checked',sign_in_required:'Sign in to Tennessee to check account history',partial:'Account history was only partially checked',unavailable:'Account history could not be checked',busy:'The browser is busy; account history was not checked',connector_update_required:'Account check did not respond. Reload the existing registry connector or review Tennessee manually.',not_checked:'Account history has not been checked'}[a.state]||'Account history needs review';
    return `<section class="tn-workflow-step"><h4>${esc(label)}</h4>${a.checked?`<p class="tn-small">Checked ${esc(new Date(a.checked*1000).toLocaleString())}.</p>`:''}
      ${(a.records||[]).length?`<ul>${a.records.map(r=>`<li>${esc(r.description)} · ${esc(r.coid||'Name match; verify identity')} · tracking ${esc(r.tracking)} · ${esc(r.status)} · ${esc(r.updated)}</li>`).join('')}</ul><p>These records may cover this filing period. Review or correct an existing request before preparing another. The history table does not show its fiscal period.</p>`:a.state==='checked'?'<p>No matching filing was found in the account history checked. Filings in another account or outside that history still need your confirmation.</p>':'<p>Review existing filings in Tennessee and confirm the applicable period before preparing this test request.</p>'}
      <a href="https://tncab.tnsos.gov/portal/my-filings" target="_blank" rel="noopener">Sign in to Tennessee / review filings</a></section>`;
  }
  function render(results) {
    generation++;context=null;
    const old=document.getElementById('tnExtensionActions');if(old)old.remove();
    const index=results.findIndex(r=>r.state==='TN');if(index<0)return;
    const rows=document.querySelectorAll('#resultRows > tr'),row=rows[index];if(!row)return;
    context={result:results[index],cell:row.lastElementChild,checked:false,checkData:null,aliases:Object.freeze([...(window.CCIdentity?.names?.()||[])])};
    const actions=document.createElement('div');actions.id='tnExtensionActions';actions.className='tn-extension-actions';
    actions.innerHTML='<button type="button" id="tnCheckExtensions">Check for extensions</button><span id="tnExtensionMessage" role="status">Tennessee · Separate from the main run · Test submissions only</span>';
    const panel=document.getElementById('resultPanel');panel.append(actions);
    actions.querySelector('#tnCheckExtensions').addEventListener('click',async function(){this.disabled=true;try{await hydrate('check');}finally{this.disabled=false;}});
    // Only read saved account metadata after results render. No registry or main-run request.
    void hydrate('status',true);
  }
  function openDialog() {
    if(!dialog){dialog=document.createElement('dialog');dialog.id='tnExtensionDialog';document.body.append(dialog);dialog.addEventListener('cancel',e=>{if(working)e.preventDefault();});}
    firstChoice=current?.support?.kind==='8868'?'irs':'reason';receiptAttempts=0;captureFailed=false;draw();if(!dialog.open)dialog.showModal();void captureConfirmation();scheduleReceipt();
    if(current?.workflow_version>=2&&["Draft","Submission failed"].includes(current.status)){
      if(current.federal_required&&!current.federal_searched_at)void operate("find-federal",{});
      else if(!current.federal_required&&!current.support)void operate("prepare-first",{});
    }
  }
  function scheduleReceipt(){
    clearTimeout(receiptTimer);receiptTimer=null;
    if(!dialog?.open||working||!current||(!unknownSend&&!['Extension submitted','Submission unconfirmed'].includes(current.status))||receiptAttempts>=6)return;
    receiptTimer=setTimeout(()=>{receiptAttempts++;void operate('receipt',{});},3000);
  }
  async function captureConfirmation(){
    const card=dialog?.querySelector('#tnConfirmationCard');
    if(!dialog?.open||!card||capturing||captureFailed||(current.documents.confirmation_screen&&current.confirmation_capture?.format_version>=2))return;
    capturing=true;const id=current.id;
    try{
      const copy=card.cloneNode(true),originals=[card,...card.querySelectorAll('*')],copies=[copy,...copy.querySelectorAll('*')];
      originals.forEach((element,index)=>{const style=getComputedStyle(element);copies[index].setAttribute('style',Array.from(style).map(key=>`${key}:${style.getPropertyValue(key)};`).join(''));});
      const bounds=card.getBoundingClientRect(),width=Math.ceil(bounds.width),height=Math.ceil(bounds.height)+25;
      if(width<100||height<80)throw new Error('The confirmation must be visible before capture.');
      copy.setAttribute('xmlns','http://www.w3.org/1999/xhtml');copy.style.width=width+'px';copy.style.boxSizing='border-box';copy.style.margin='0';
      const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><foreignObject width="100%" height="100%">${new XMLSerializer().serializeToString(copy)}</foreignObject></svg>`;
      const picture=new Image();await new Promise((resolve,reject)=>{picture.onload=resolve;picture.onerror=reject;picture.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg);});
      const canvas=document.createElement('canvas'),ratio=Math.min(2,1800/height,1800/width);canvas.width=Math.floor(width*ratio);canvas.height=Math.floor(height*ratio);const paint=canvas.getContext('2d');paint.fillStyle='#fff';paint.fillRect(0,0,canvas.width,canvas.height);paint.scale(ratio,ratio);paint.drawImage(picture,0,0);
      const body=canvas.toDataURL('image/png').split(',')[1];
      if(current.id!==id)return;
      const r=await request({action:'capture-confirmation',id,confirmation:current.confirmation,application_sha256:current.application_sha256,body});
      if(current.id===id){current.documents.confirmation_screen=r.documents.confirmation_screen;current.confirmation_capture=r.confirmation_capture;draw();void hydrate('status',true);}
    }catch(e){captureFailed=true;const target=dialog?.querySelector('#tnCaptureMessage');if(target)target.textContent='The test submission is saved, but its confirmation-screen capture did not complete. Use Retry capture; do not resubmit the application.';}
    finally{capturing=false;}
  }
  const federalLabels={name:'Organization name — confirm',ein:'EIN',street:'Street / suite — confirm from prior return',city_state_zip:'City, state, ZIP — confirm',return_type:'Return type — confirm',period_start:'Tax period begins',period_end:'Tax period ends',books:'Books are in the care of *',phone:'Books-in-care-of phone *',tax_a:'Line 3a: tentative tax *',tax_b:'Line 3b: credits/payments *',tax_c:'Line 3c: balance due *'};
  let irsAnswer='',showFederal=false,attachmentReady=false,firstChoice='reason';
  function firstRequestContent(){
    return `<section class="tn-workflow-step"><h4>1. First Tennessee extension — up to 90 days</h4>
      <p>Attach either an existing filed IRS Form 8868 or a document stating the reason for the extension. You do not need a new IRS filing to use the reason-statement route.</p>
      <label>Supporting document<select id="tnFirstSupport"><option value="reason" ${firstChoice==='reason'?'selected':''}>Prepare a reason statement</option><option value="irs" ${firstChoice==='irs'?'selected':''}>Use an already-filed IRS extension</option></select></label>
      ${firstChoice==='reason'?`<label>Reason for extension — review or edit<textarea id="tnFirstReason" maxlength="600" rows="3">${esc(current.fields.reason)}</textarea></label><button type="button" id="tnPrepareFirst">Update reason document</button>${current.support?.kind==='first-request'?`<p class="tn-ready">Reason document prepared for your review.</p><a href="${esc(current.support.url)}" target="_blank" rel="noopener">Review reason document — Demo only</a>`:''}`:
      `${current.support?.kind==='8868'?`<p class="tn-ready">Matching test IRS evidence attached.</p><a href="${esc(current.support.url)}" target="_blank" rel="noopener">Review attached evidence — Demo only</a>`:`<p>This demo checks its saved accepted test evidence. The Tennessee history check does not retrieve attachments or IRS records.</p><label>Upload filed copy and acceptance evidence (test PDF, maximum 2 MB)<input id="tnSupportUpload" type="file" accept="application/pdf"></label><button type="button" id="tnUploadSupport">Validate and attach test PDF</button><details><summary>Demo documents</summary><button type="button" id="tnUseDemoEvidence">Use matching simulated IRS evidence</button></details>`}`}
      <p class="tn-small">Tennessee's portal and returned-filing notice allow a reason document. This test document has not been submitted to or approved by Tennessee.</p></section>
      <section class="tn-workflow-step"><h4>2. Review and submit Tennessee request</h4>
      <p class="tn-small"><a href="${PORTAL}" target="_blank" rel="noopener">Sign in to Tennessee</a> to review actual account filings. Account history is checked read-only when available. The form below sends only to the test service.</p>
      <div id="tnPortalRehearsal" data-demo-only="true"><label>CO number<input id="tnPortalCO" readonly></label><label>Supporting document — Demo only<input id="tnPortalUpload" type="file" accept="application/pdf" disabled></label><p id="tnAttachmentReady" role="status"></p></div>
      <label class="tn-check"><input id="tnReviewed" type="checkbox"> I reviewed the CO number, period and first-extension request.</label>
      <label class="tn-check"><input id="tnAuthorized" type="checkbox"> I am the authorized filer for this test application.</label>
      <button type="button" id="tnSubmitDemo" disabled>Submit to Tennessee test service</button>
      ${responseOptions()}</section>`;
  }
  function responseOptions(){return '<details><summary>Test response options</summary><label>Tennessee test response<select id="tnTestResponse"><option value="immediate">Immediate submission confirmation</option><option value="delayed">Submitted; acknowledgment after 15 seconds</option><option value="timeout">Response timeout; check receipt before retrying</option><option value="returned">Receipt, then returned for correction</option><option value="failed">Confirmed failure; keep draft</option></select></label></details>';}
  function draftContent(locked) {
    const support=current.support,check=current.federal_check;
    if(locked)return `<div class="tn-documents">${links(current)}</div>`;
    if(!current.federal_required)return firstRequestContent();
    return `<p><strong>Tennessee CO number:</strong> ${esc(current.facts.coid)}</p>
      <section class="tn-workflow-step"><h4>1. Second Tennessee extension — IRS evidence required</h4><p class="tn-small">This request is for up to 60 additional days after a verified first extension.</p>
      ${support?`<p class="tn-ready">Attached: ${esc(support.label)} — Demo only</p><a href="${esc(support.url)}" target="_blank" rel="noopener">Review attachment</a>${support.acceptance_url?` · <a href="${esc(support.acceptance_url)}" target="_blank" rel="noopener">View simulated IRS acceptance</a>`:''}`:
      `<p class="tn-small">${esc(check.search_scope)}</p>${!check.eligible?`<p class="tn-disabled-reason">${esc(check.reason)} If an extension was filed on time, upload its filed copy and acceptance evidence. A new federal draft is unavailable in this workflow.</p>`:''}<label>No matching IRS extension was found. Has one already been filed?<select id="tnIRSAnswer"><option value="">Select an answer</option><option value="yes" ${irsAnswer==='yes'?'selected':''}>Yes — upload the filed copy and acceptance evidence</option><option value="no" ${irsAnswer==='no'?'selected':''}>${check.eligible?'No — prepare Form 8868':'No — no timely IRS extension is available'}</option></select></label>
       ${irsAnswer==='yes'?`<p>Upload the filed copy and acceptance evidence. This isolated demo validates only issued test documents; do not upload real tax documents.</p><label>Upload filed copy and acceptance evidence (test PDF, maximum 2 MB)<input id="tnSupportUpload" type="file" accept="application/pdf"></label><button type="button" id="tnUploadSupport">Validate and attach test PDF</button><details><summary>Demo documents</summary><button type="button" id="tnUseDemoEvidence">Use matching simulated IRS evidence</button></details>`:''}
       ${irsAnswer==='no'?`<p class="tn-small">Federal deadline: ${esc(dateLabel(check.deadline))}. ${esc(check.eligible?'Review the prefilled draft below, complete the required fields, then explicitly submit to the IRS test service.':check.reason)}</p>${!check.can_prepare?'<p>Form preparation requires a verified, supported return type and regular annual filing period.</p>':''}`:''}
       `}
      ${showFederal&&check.eligible&&!support?`<section><h4>Form 8868 — draft for authorized review</h4><p class="tn-small">Prefill comes from the dated organization record and prior public Form 990. Confirm the address and return type; complete the books-in-care-of and tax lines. Regular annual 990, 990-EZ and 990-PF only; group/short-year returns are outside this pilot.</p><div class="tn-field-grid">${Object.entries(federalLabels).map(([k,label])=>`<label>${esc(label)}<input data-irs="${k}" id="irs_${k}" value="${esc(current.federal_fields[k])}" ${['ein','return_type','period_start','period_end'].includes(k)?'readonly':''} maxlength="180"></label>`).join('')}</div>
       <label class="tn-check"><input id="tnIRSReviewed" type="checkbox"> I reviewed this federal request and am authorized to submit this test.</label>
       <button type="button" id="tnDownloadDraftIRS">Save and preview draft 8868</button> <button type="button" id="tnSubmitIRS" ${check.eligible?'':'disabled'}>Submit to IRS test service</button>
       ${current.documents.irs_draft?`<a href="${esc(current.documents.irs_draft)}" target="_blank" rel="noopener">View draft Form 8868 — Demo only</a>`:''}</section>`:''}</section>
      <section class="tn-workflow-step"><h4>2. Tennessee request</h4><p class="tn-small">CharityClarity adds the CO number and validated attachment below. This is the test application, not the Tennessee website. A real filing requires Tennessee sign-in; automatic transfer and later portal steps remain unverified.</p>
      <div id="tnPortalRehearsal" data-demo-only="true"><label>CO number<input id="tnPortalCO" readonly placeholder="Added automatically after the attachment is validated"></label><label>IRS Form 8868 or Other Documentation *<input id="tnPortalUpload" type="file" accept="application/pdf" disabled></label><p id="tnAttachmentReady" role="status"></p></div>
      <label class="tn-check"><input id="tnReviewed" type="checkbox" ${current.reviewed?'checked':''}> I reviewed the CO number, period and supporting document.</label>
      <label class="tn-check"><input id="tnAuthorized" type="checkbox" ${current.authorized?'checked':''}> I am the authorized filer for this test application.</label>
      <button type="button" id="tnSubmitDemo" disabled>Submit to Tennessee test service</button>
      <details><summary>Test response options</summary><label>Tennessee test response<select id="tnTestResponse"><option value="immediate">Immediate submission confirmation</option><option value="delayed">Submitted; acknowledgment after 15 seconds</option><option value="timeout">Response timeout; check receipt before retrying</option><option value="failed">Confirmed failure; keep draft</option></select></label></details></section>`;
  }
  function draw(message='') {
    attachmentReady=false;
    const locked=current&&!['Draft','Submission failed'].includes(current.status);
    const hasCompleteCapture=!!(current?.documents.confirmation_screen&&current.confirmation_capture?.format_version>=2);
    dialog.innerHTML=`<div class="tn-dialog-heading"><h2>Tennessee File Extension</h2><button type="button" id="tnClose" aria-label="Close extension demo">×</button></div>
      <p class="tn-demo-banner"><strong>Demo only — no live filings.</strong> Submission uses isolated test services. Applications, acceptance responses and receipts are simulated.</p>
      <div id="tnDemoError" role="alert">${esc(message)}</div>
      ${!current?`<h3>${esc(context.checkData?.facts.name||context.result.organization_name)}</h3>
       <p>EIN ${esc(context.result.ein)} · Tennessee ${esc(context.checkData?.facts.coid)}<br>Filing period ${esc(context.checkData?.facts.period_start)} to ${esc(context.checkData?.facts.period_end)}<br>Registration expires ${esc(context.checkData?.facts.expiration)}</p>
       <p class="tn-small">Public source checked ${esc(dateLabel(context.checkData?.facts.checked_at))}. Pending filings require your confirmation. <a href="${PORTAL}" target="_blank" rel="noopener">Sign in to Tennessee</a> to review your account. Tennessee sign-in is required for real portal filings; this pilot submits only to test services.</p>
       ${accountDetails(context.checkData?.facts)}
       <label>Has a renewal or this extension request already been submitted for this filing period?<select id="tnInitialPrior"><option value="unknown">Select an answer</option><option value="yes">Yes — do not prepare another filing</option><option value="no">No — nothing has been submitted</option></select></label>
       ${context.checkData?.facts.account_check?.requires_period_review?'<label class="tn-check"><input id="tnOtherPeriod" type="checkbox"> I reviewed the listed filings and confirm no submitted request covers this filing period.</label>':''}
       <p id="tnPriorExplanation" role="status"></p><button type="button" id="tnPrepareExtension" disabled>Continue to application</button>`:
      `<h3>${esc(current.fields.name)} — ${esc(current.status)}</h3><p class="tn-small">EIN ${esc(current.ein)} · Filing period ${esc(current.facts.period_start)} to ${esc(current.facts.period_end)} · Registration expiration ${esc(current.facts.expiration)}</p>
       ${eligibilityDetails(current)}
       ${!current.eligibility.eligible?`<p class="tn-disabled-reason">${esc(current.eligibility.reasons.join(' '))}</p>`:''}
       ${draftContent(locked)}
       <section class="tn-workflow-step"><h4>3. Submission and acknowledgment</h4>
       <p><strong>${esc(current.status)} — Demo only</strong></p><p class="tn-small">${esc(current.receipt_method||'The isolated test service supplies simulated responses. No real Tennessee acknowledgment is retrieved.')}</p>
       ${current.state_review?`<p class="tn-disabled-reason"><strong>State review: ${esc(current.state_review.outcome)} — Demo only.</strong> ${esc(current.state_review.reason)}</p><p class="tn-small">Source: ${esc(current.state_review.source)}. Acknowledgment confirms receipt, not approval. Real state email retrieval and correction submission are not connected in this pilot.</p>`:''}
       ${current.failure?`<p class="tn-disabled-reason">${esc(current.failure)}</p>`:''}
       ${['Extension submitted','Receipt acknowledged'].includes(current.status)?`<div id="tnConfirmationCard" style="box-sizing:border-box;max-width:620px;padding:22px;border:1px solid #b9c9df;border-radius:8px;background:#fff;color:#20324a;font:14px/1.5 Arial,sans-serif"><p style="color:#9c1f1f;font-weight:bold">DEMO ONLY — ISOLATED TENNESSEE TEST SERVICE</p><h3 style="font-size:20px;color:#0b2a5b">Thank you for your submission.</h3><p>${current.state_review?'Your test request was received, then returned for correction. Correct the existing filing; this is not approval.':'Your test extension request has been received. Review is pending; this is not approval.'} No email will be sent by this demo.</p><p>${esc(current.fields.name)}<br>EIN ${esc(current.ein)} · ${esc(current.facts.coid)}<br>Period ${esc(current.facts.period_start)} to ${esc(current.facts.period_end)}<br>Confirmation ${esc(current.confirmation)}</p><p style="font-size:11px">Compliance Express · www.compliance-express.com · info@compliance-express.com</p></div><p id="tnCaptureMessage" class="tn-small">${hasCompleteCapture?'Confirmation screen captured and saved with this application.':'Saving the displayed test confirmation screen separately from the application.'}</p>${hasCompleteCapture?'':'<button type="button" id="tnRetryCapture">Retry capture</button>'}`:''}
       ${current.irs_submission?`<p class="tn-small">IRS test service: accepted ${esc(new Date(current.irs_submission.submitted_at*1000).toLocaleString())}. <a href="${esc(current.documents.irs_acceptance)}" target="_blank" rel="noopener">View simulated IRS acceptance</a></p>`:''}
       ${current.acknowledgment_provenance?`<p class="tn-small">Acknowledgment source: ${esc(current.acknowledgment_provenance.source)}. Received ${esc(new Date(current.acknowledgment_provenance.received_at*1000).toLocaleString())}. Matched to this account, organization, filing period, confirmation and exact submitted application.</p>`:''}
       ${unknownSend||['Extension submitted','Submission unconfirmed'].includes(current.status)?'<p class="tn-small">Checking the test service automatically for a matching acknowledgment. You can close this window; a later CharityClarity run will check the saved submission again. Nothing is resubmitted.</p>':''}
       <div class="tn-form-actions"><button type="button" id="tnCheckReceipt" ${unknownSend||['Extension submitted','Submission unconfirmed'].includes(current.status)?'':'disabled'}>Check test acknowledgment</button></div></section>
       ${unknownSend?'<p>Submission unconfirmed. Check for acknowledgment before any retry.</p>':''}
       ${!locked?`<div class="tn-documents">${links(current)}</div>`:''}<p class="tn-small">${esc(current.approval)}${current.confirmation?' · '+esc(current.confirmation):''}${current.submitted_at?' · Submitted '+esc(new Date(current.submitted_at*1000).toLocaleString()):''}${current.acknowledged_at?' · Acknowledged '+esc(new Date(current.acknowledged_at*1000).toLocaleString()):''}</p>`}
      <footer>Compliance Express · www.compliance-express.com · info@compliance-express.com</footer>`;
    dialog.querySelector('#tnClose').onclick=()=>{if(!working){clearTimeout(receiptTimer);dialog.close();}};
    const priorChanged=()=>{const value=dialog.querySelector('#tnInitialPrior').value,other=dialog.querySelector('#tnOtherPeriod');dialog.querySelector('#tnPrepareExtension').disabled=value!=='no'||!!other&&!other.checked;dialog.querySelector('#tnPriorExplanation').textContent=value==='yes'?'Do not create a duplicate. Sign in to Tennessee to review or correct the existing filing, including a returned request.':'';};
    dialog.querySelector('#tnInitialPrior')?.addEventListener('change',priorChanged);
    dialog.querySelector('#tnOtherPeriod')?.addEventListener('change',priorChanged);
    dialog.querySelector('#tnPrepareExtension')?.addEventListener('click',()=>operate('prepare',{ein:context.result.ein,answer:dialog.querySelector('#tnInitialPrior').value,records_not_for_period:dialog.querySelector('#tnOtherPeriod')?.checked===true}));
    dialog.querySelector('#tnIRSAnswer')?.addEventListener('change',function(){irsAnswer=this.value;showFederal=this.value==='no'&&current.federal_check.eligible;draw();});
    dialog.querySelector('#tnFirstSupport')?.addEventListener('change',function(){firstChoice=this.value;draw();if(firstChoice==='irs')void operate('find-federal',{});});
    dialog.querySelector('#tnFirstReason')?.addEventListener('input',()=>{attachmentReady=false;dialog.querySelector('#tnSubmitDemo').disabled=true;dialog.querySelector('#tnAttachmentReady').textContent='Update the reason document, then review the attachment before submitting.';});
    dialog.querySelector('#tnPrepareFirst')?.addEventListener('click',()=>operate('prepare-first',{reason:dialog.querySelector('#tnFirstReason').value}));
    dialog.querySelector('#tnUseDemoEvidence')?.addEventListener('click',()=>operate('attach-demo-evidence',{}));
    dialog.querySelector('#tnPrepareIRS')?.addEventListener('click',()=>{showFederal=true;draw();});
    for(const [id,kind] of [['tnSample8868','8868'],['tnSampleOther','other']])dialog.querySelector('#'+id)?.addEventListener('click',()=>sample(kind));
    dialog.querySelector('#tnUploadSupport')?.addEventListener('click',upload);
    dialog.querySelector('#tnDownloadDraftIRS')?.addEventListener('click',()=>operate('irs-draft',{federal_fields:irsValues()}));
    dialog.querySelector('#tnSubmitIRS')?.addEventListener('click',()=>{if(current.federal_check.eligible)operate('irs-submit',{federal_fields:irsValues(),reviewed:dialog.querySelector('#tnIRSReviewed').checked,authorized:dialog.querySelector('#tnIRSReviewed').checked});});
    dialog.querySelector('#tnSubmitDemo')?.addEventListener('click',()=>{if(attachmentReady)operate('submit',{fields:{coid:current.facts.coid,...(!current.federal_required&&firstChoice==='reason'?{reason:dialog.querySelector('#tnFirstReason').value}:{})},prior_filing:'no',reviewed:dialog.querySelector('#tnReviewed').checked,authorized:dialog.querySelector('#tnAuthorized').checked,test_response:dialog.querySelector('#tnTestResponse').value||'immediate'});});
    dialog.querySelector('#tnCheckReceipt')?.addEventListener('click',()=>operate('receipt',{}));
    dialog.querySelector('#tnRetryCapture')?.addEventListener('click',()=>{captureFailed=false;void captureConfirmation();});
    void captureConfirmation();
    if(current?.support&&!locked)void populateRehearsal(current.id);
  }
  function irsValues(){return Object.fromEntries(Object.keys(federalLabels).map(k=>[k,dialog.querySelector('#irs_'+k).value]));}
  async function populateRehearsal(id) {
    const root=dialog.querySelector('#tnPortalRehearsal');
    try{
      await window.CCTennesseePortalRehearsal.populate(root,current.facts.coid,current.support.url);
      if(current.id!==id||dialog.querySelector('#tnPortalRehearsal')!==root)return;
      attachmentReady=current.federal_required||(firstChoice==='reason'?current.support.kind==='first-request':current.support.kind==='8868');
      dialog.querySelector('#tnAttachmentReady').textContent=attachmentReady?'CO number and matching test attachment added automatically. Review them before submitting.':'Attach the selected supporting document before submitting.';
      dialog.querySelector('#tnSubmitDemo').disabled=!attachmentReady||!current.eligibility.eligible||unknownSend;
    }catch(e){if(current?.id===id)dialog.querySelector('#tnDemoError').textContent=e.message;}
  }
  async function sample(kind){
    try{const d=await request({action:'test-document',id:current.id,kind});dialog.querySelector('#tnTestDownload').innerHTML=`<a href="${esc(d.url)}" download="${esc(d.filename)}" target="_blank" rel="noopener">Download ${esc(d.filename)}</a> — then upload that PDF above.`;}
    catch(e){dialog.querySelector('#tnDemoError').textContent=e.message;}
  }
  async function upload(){
    const file=dialog.querySelector('#tnSupportUpload').files[0];
    if(!file||file.size>2097152){dialog.querySelector('#tnDemoError').textContent='Select a test PDF no larger than 2 MB.';return;}
    const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(const b of bytes)binary+=String.fromCharCode(b);
    await operate('upload-support',{body:btoa(binary)});
  }
  async function operate(action,extra) {
    if(working)return;working=true;dialog.querySelectorAll('button').forEach(b=>b.disabled=true);
    try {
      if(action==='prepare'){
        const checked=await request({action:'confirm-prior',ein:extra.ein,answer:extra.answer,records_not_for_period:extra.records_not_for_period===true});context.checked=true;rowPanel(checked);
      }
      const r=await request({action,...(current?{id:current.id}:{}),...extra});current=r;unknownSend=false;draw();void hydrate('status',true);
    } catch(e) {
      if(current&&extra.federal_fields)current.federal_fields={...current.federal_fields,...extra.federal_fields};
      if(action==='submit'&&(!e.message||e.name==='AbortError'||e.message.includes('fetch')||e.message.includes('temporarily unavailable')))unknownSend=true;
      if(current)draw(e.message);else{dialog.querySelector('#tnDemoError').textContent=e.message;dialog.querySelectorAll('button').forEach(b=>b.disabled=false);}
    } finally{working=false;scheduleReceipt();}
  }
  window.CCTennesseeExtensions={render};
})();
