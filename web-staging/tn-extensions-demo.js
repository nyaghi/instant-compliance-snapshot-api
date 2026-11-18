/* Staging only. No live filing automation or IRS gateway. */
(() => {
  'use strict';
  const API='/api/tn-extension-demo';
  const PORTAL='https://tncab.tnsos.gov/portal/portal-login-page';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let context=null,generation=0,current=null,dialog=null,working=false,unknownSend=false;
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
    return [['application','View submitted extension'],['acknowledgment','View acknowledgment']].filter(([k])=>r.documents[k])
      .map(([k,label])=>`<a href="${esc(r.documents[k])}" target="_blank" rel="noopener">${label} — Demo only</a>`).join(' · ');
  }
  function rowPanel(data) {
    if(!context||!context.cell.isConnected)return;
    let box=context.cell.querySelector('.tn-extension-row');
    if(!box){box=document.createElement('div');box.className='tn-extension-row';context.cell.append(box);}
    const r=data.requests?.find(x=>['Extension submitted','Receipt acknowledged','Submission unconfirmed'].includes(x.status))||data.requests?.[0];
    box.innerHTML=`<strong>Tennessee extension pilot</strong><br><button type="button" disabled>File Extension</button>
      <span>${esc(data.eligibility.reasons.join(' '))}</span>
      ${r?`<div class="tn-demo-saved"><strong>Demo only — ${esc(r.status)}</strong><br>${links(r)}
      ${r.confirmation?`<small>${esc(r.confirmation)} · ${esc(new Date((r.acknowledged_at||r.submitted_at)*1000).toLocaleString())}</small>`:''}
      <button type="button" class="tn-resume">${r.status==='Draft'?'Resume demo draft':'View demo filing'}</button></div>`:''}`;
    box.querySelector('.tn-resume')?.addEventListener('click',()=>{current=r;unknownSend=false;openDialog();});
  }
  async function hydrate(action,quiet=false) {
    if(!context)return;
    const version=generation,ein=context.result.ein;
    try {
      const data=await request({action,ein});
      if(version!==generation)return;
      rowPanel(data);
      if(!quiet)document.getElementById('tnExtensionMessage').textContent='Tennessee checked. Other results are unchanged. This pilot does not submit live filings.';
    } catch(e) {
      if(version!==generation||quiet)return;
      const msg=document.getElementById('tnExtensionMessage');msg.textContent=e.message;
      if(e.signIn){const a=document.createElement('a');a.href=e.signIn;a.textContent=' Sign in to CharityClarity';a.target='_blank';a.rel='noopener';msg.append(a);}
    }
  }
  function render(results) {
    generation++;context=null;
    const old=document.getElementById('tnExtensionActions');if(old)old.remove();
    const index=results.findIndex(r=>r.state==='TN');if(index<0)return;
    const rows=document.querySelectorAll('#resultRows > tr'),row=rows[index];if(!row)return;
    context={result:results[index],cell:row.lastElementChild};
    const actions=document.createElement('div');actions.id='tnExtensionActions';actions.className='tn-extension-actions';
    actions.innerHTML='<button type="button" id="tnCheckExtensions">Check for extensions</button> <button type="button" id="tnTryDemo">Try Tennessee demo</button><span id="tnExtensionMessage" role="status">Tennessee pilot · Separate from the main run · Test submissions only</span>';
    const panel=document.getElementById('resultPanel');panel.append(actions);
    actions.querySelector('#tnCheckExtensions').addEventListener('click',async function(){this.disabled=true;try{await hydrate('check');}finally{this.disabled=false;}});
    actions.querySelector('#tnTryDemo').addEventListener('click',()=>{current=null;unknownSend=false;openDialog();});
    // Only read saved account metadata after results render. No registry or main-run request.
    void hydrate('status',true);
  }
  function openDialog() {
    if(!dialog){dialog=document.createElement('dialog');dialog.id='tnExtensionDialog';document.body.append(dialog);dialog.addEventListener('cancel',e=>{if(working)e.preventDefault();});}
    draw();if(!dialog.open)dialog.showModal();
  }
  const labels={name:'Organization legal name',coid:'Tennessee CO number',address:'Mailing address',phone:'Phone',website:'Website',contact:'Authorized filer name',contact_email:'Filer email',title:'Filer title',reason:'Reason for extension',requested_days:'Days requested (1–90)'};
  function draw(message='') {
    const locked=current&&!['Draft','Submission failed'].includes(current.status);
    dialog.innerHTML=`<div class="tn-dialog-heading"><h2>Tennessee File Extension</h2><button type="button" id="tnClose" aria-label="Close extension demo">×</button></div>
      <p class="tn-demo-banner"><strong>Demo only.</strong> No submission is sent to Tennessee or the IRS. Synthetic eligibility is evaluated as of November 18, 2026.</p>
      <p class="tn-small">First extension: request up to 90 days; state approval is separate. An IRS extension is not a prerequisite for this first request. Second extensions are outside this pilot.</p>
      <p class="tn-small">The signed-in portal menu was inspected. Its later form steps and acknowledgment format are unverified. <a href="${PORTAL}" target="_blank" rel="noopener">Sign in to Tennessee</a> if you need to review your actual filings.</p>
      <div id="tnDemoError" role="alert">${esc(message)}</div>
      ${!current?`<label>Test case<select id="tnDemoScenario"><option value="open">Open window — synthetic</option><option value="closed">Closed window</option><option value="already-filed">Renewal or extension already filed</option><option value="unverified">Unverified filing period</option></select></label>
       <p>Prefill identity from the Tennessee result for <strong>${esc(context.result.organization_name)}</strong>, EIN ${esc(context.result.ein)}. The demo period and deadline are test data, not a finding of real eligibility.</p>
       <button type="button" id="tnCreateDraft">Prepare test application</button>`:
      `<h3>${esc(current.fields.name)} — ${esc(current.status)}</h3>
       <p class="tn-small">Test period ${esc(current.facts.period_start)} to ${esc(current.facts.period_end)} · Test expiration ${esc(current.facts.expiration)}</p>
       ${!current.eligibility.eligible?`<p class="tn-disabled-reason">${esc(current.eligibility.reasons.join(' '))}</p>`:''}
       <form id="tnExtensionForm"><div class="tn-field-grid">${Object.entries(labels).map(([k,label])=>`<label>${label}${!['phone','website'].includes(k)?' *':''}<input name="${k}" value="${esc(current.fields[k])}" ${locked?'disabled':''} ${k==='contact_email'?'type="email"':k==='requested_days'?'type="number" min="1" max="90"':'type="text"'} maxlength="600"></label>`).join('')}</div>
       <label>Has a renewal or extension already been submitted for this filing period?<select id="tnPriorFiling" ${locked?'disabled':''}><option value="unknown" ${current.prior_filing==='unknown'?'selected':''}>Select an answer</option><option value="yes" ${current.prior_filing==='yes'?'selected':''}>Yes — do not prepare another filing</option><option value="no" ${current.prior_filing==='no'?'selected':''}>No — confirmed by authorized user (test case)</option></select></label>
       <label class="tn-check"><input id="tnReviewed" type="checkbox" ${current.reviewed?'checked':''} ${locked?'disabled':''}> I reviewed the organization, period, deadline and request.</label>
       <label class="tn-check"><input id="tnAuthorized" type="checkbox" ${current.authorized?'checked':''} ${locked?'disabled':''}> I am the authorized filer for this test application.</label>
       <div class="tn-form-actions">${!locked?`<button type="button" id="tnSaveDraft">Save draft</button><label>Test response<select id="tnTestResponse"><option value="delayed">Delayed acknowledgment (15 seconds)</option><option value="immediate">Immediate acknowledgment</option><option value="timeout">Timeout after acceptance — prevent duplicate</option><option value="failed">Definite failure — retain draft</option></select></label><button type="button" id="tnSubmitDemo" ${!current.eligibility.eligible||current.prior_filing!=='no'||unknownSend?'disabled':''}>Submit test extension</button>`:''}
       <button type="button" id="tnCheckReceipt">Check for acknowledgment</button></div></form>
       ${unknownSend?'<p>Submission unconfirmed. Check for acknowledgment before any retry.</p>':''}
       <div class="tn-documents">${links(current)}</div><p class="tn-small">${esc(current.approval)}${current.confirmation?' · '+esc(current.confirmation):''}${current.submitted_at?' · Submitted '+esc(new Date(current.submitted_at*1000).toLocaleString()):''}${current.acknowledged_at?' · Acknowledged '+esc(new Date(current.acknowledged_at*1000).toLocaleString()):''}</p>`}
      <footer>Compliance Express · www.compliance-express.com · info@compliance-express.com</footer>`;
    dialog.querySelector('#tnClose').onclick=()=>{if(!working)dialog.close();};
    dialog.querySelector('#tnCreateDraft')?.addEventListener('click',()=>operate('create',{ein:context.result.ein,name:context.result.organization_name,scenario:dialog.querySelector('#tnDemoScenario').value}));
    dialog.querySelector('#tnPriorFiling')?.addEventListener('change',function(){const b=dialog.querySelector('#tnSubmitDemo');if(b)b.disabled=this.value!=='no'||!current.eligibility.eligible||unknownSend;});
    dialog.querySelector('#tnSaveDraft')?.addEventListener('click',()=>operate('save',values()));
    dialog.querySelector('#tnSubmitDemo')?.addEventListener('click',()=>operate('submit',{...values(),test_response:dialog.querySelector('#tnTestResponse').value}));
    dialog.querySelector('#tnCheckReceipt')?.addEventListener('click',()=>operate('receipt',{}));
    dialog.querySelector('form')?.addEventListener('submit',e=>e.preventDefault());
  }
  function values(){return {fields:Object.fromEntries(new FormData(dialog.querySelector('form'))),prior_filing:dialog.querySelector('#tnPriorFiling').value,reviewed:dialog.querySelector('#tnReviewed').checked,authorized:dialog.querySelector('#tnAuthorized').checked};}
  async function operate(action,extra) {
    if(working)return;working=true;dialog.querySelectorAll('button').forEach(b=>b.disabled=true);
    try {
      const r=await request({action,...(current?{id:current.id}:{}),...extra});current=r;unknownSend=false;draw();void hydrate('status',true);
    } catch(e) {
      if(current&&extra.fields){current.fields={...current.fields,...extra.fields};current.prior_filing=extra.prior_filing;current.reviewed=extra.reviewed;current.authorized=extra.authorized;}
      if(action==='submit'&&(!e.message||e.name==='AbortError'||e.message.includes('fetch')||e.message.includes('temporarily unavailable')))unknownSend=true;
      if(current)draw(e.message);else{dialog.querySelector('#tnDemoError').textContent=e.message;dialog.querySelectorAll('button').forEach(b=>b.disabled=false);}
    } finally{working=false;}
  }
  window.CCTennesseeExtensions={render};
})();
