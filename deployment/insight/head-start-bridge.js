/* Assessment transport only. Registry searches and interpretation stay in Aurora. */
(() => {
  'use strict';
  const key = 'cc.headstart.assessment.v1';
  const fields = () => ({name:document.getElementById('organizationName'),ein:document.getElementById('ein')});
  const normalizeEin = value => String(value || '').replace(/\D/g,'');
  const normalizeName = value => String(value || '').trim().replace(/\s+/g,' ').toLowerCase();
  const insightButtonMarkup = '<span class="cc-journey-lead">Continue to</span><span class="cc-journey-mark cc-journey-mark--insight"><img src="/head-start/charityclarity-wordmark.png" alt=""><span class="cc-journey-script" aria-hidden="true">Insight</span></span>';
  function brandInsightButton(button) {
    if(!button || button.dataset.ccInsightBrand)return;
    button.dataset.ccInsightBrand='true';
    button.classList.add('cc-journey-cta');
    button.setAttribute('aria-label','Continue to CharityClarity Insight');
    button.innerHTML=insightButtonMarkup;
  }
  let assessment = null, applied = false;
  const card = document.createElement('section');
  card.hidden = true;
  card.style.cssText = 'border:1px solid #dbe3ed;border-left:3px solid #C62828;background:#f3f6fa;padding:18px 20px;margin-bottom:20px;border-radius:8px;color:#0B2A5B';
  const title = document.createElement('strong'); title.textContent = 'Head Start connected';
  const description = document.createElement('p'); description.style.cssText = 'font-size:14px;margin:6px 0 0';
  const message = document.createElement('p'); message.setAttribute('role','status'); message.style.cssText = 'font-size:13px;margin:6px 0 0';
  card.append(title,description,message);
  document.getElementById('snapshotForm').before(card);

  function validate(value) {
    if(!value || value.schema_version !== 'cc.head-start/1' || !value.organization_name || !/^\d{9}$/.test(normalizeEin(value.ein)) ||
       !Array.isArray(value.requirements) || value.requirements.length !== 51 || new Set(value.requirements.map(r=>r.code)).size !== 51 ||
       value.profile?.taxStatus !== 'recognized501c3' || JSON.stringify(value).length > 524288) throw Error('The Head Start assessment is incomplete. Return to Head Start and continue again.');
    return value;
  }
  function compatible(rows) {
    if(!assessment)return true;
    const f=fields();
    return normalizeEin(f.ein.value)===normalizeEin(assessment.ein) && normalizeName(f.name.value)===normalizeName(assessment.organization_name) &&
      (!rows || rows.every(r=>normalizeEin(r.ein)===normalizeEin(assessment.ein) && normalizeName(r.organization_name)===normalizeName(assessment.organization_name)));
  }
  function refresh() {
    if(!assessment)return;
    card.hidden=false;
    description.textContent=`${assessment.organization_name} · EIN ${normalizeEin(assessment.ein).replace(/^(\d{2})(\d{7})$/,'$1-$2')} · Requirements assessed ${new Date(assessment.assessed_at).toLocaleDateString()}`;
    const button=document.getElementById('generateReportButton');
    brandInsightButton(button);
    if(button && document.getElementById('resultRows')?.children.length)button.classList.remove('hidden');
    if(!compatible())message.textContent='The organization differs from Head Start. Return to the assessed organization or create a new assessment before combining the results.';
  }
  function applyStates() {
    if(!assessment || applied || !window.CCHeadStartConfig?.().unlocked)return;
    const p=assessment.profile;
    const suggestions=new Set([p.base,...(p.target||[]),...(p.donorStates||[]),...(p.operations||[]),p.incorporation,...(p.bankStates||[])].filter(Boolean));
    const boxes=[...document.querySelectorAll('input[name="states"],input[name="salesStates"]')];
    boxes.forEach(box=>{box.checked=suggestions.has(box.value);});
    const available=new Set(boxes.map(box=>box.value));
    const missing=[...suggestions].filter(s=>!available.has(s));
    const selected=new Set(boxes.filter(b=>b.checked).map(b=>b.value)).size;
    const salesCount=document.getElementById('ccSalesSelectedCount');if(salesCount)salesCount.textContent=`${selected} selected`;
    message.textContent=`${selected} reported-activity states selected. You can change the selection.${missing.length?` ${missing.length} additional activity states are outside Aurora's available checks and will remain not checked in Insight.`:''}`;
    applied=true;
  }
  function accept(value) {
    assessment=validate(value);applied=false;
    const f=fields();f.name.value=assessment.organization_name;f.ein.value=normalizeEin(assessment.ein).replace(/^(\d{2})(\d{7})$/,'$1-$2');
    f.name.dispatchEvent(new Event('input',{bubbles:true}));f.ein.dispatchEvent(new Event('input',{bubbles:true}));
    try{sessionStorage.setItem(key,JSON.stringify(assessment));}catch{/* The current browser copy remains available. */}
    message.textContent='Sign in to use the suggested states. Your Head Start findings will be included in Insight.';
    refresh();applyStates();
  }
  async function save() {
    if(!assessment)return;
    if(!compatible())throw Error('Head Start and Aurora must use the same organization and EIN.');
    const config=window.CCHeadStartConfig();
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),8000);
    try{
      const response=await fetch(`${config.apiBase}/api/head-start`,{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+config.passcode},signal:controller.signal,body:JSON.stringify({action:'save',head_start:assessment,email:config.email,admin_passcode:config.passcode})});
      if(!response.ok){const body=await response.json().catch(()=>({}));throw Error(body.error||'The Head Start assessment could not be saved. Your browser copy is retained.');}
    }finally{clearTimeout(timeout);}
  }
  window.CCHeadStart=Object.freeze({refresh,applyStates,save,hasAssessment:()=>!!assessment,forResults(rows){
    if(!assessment)return undefined;
    if(!compatible(rows))throw Error('These results and the Head Start assessment describe different organizations. Run Aurora for the assessed organization before generating Insight.');
    return structuredClone(assessment);
  }});
  for(const field of Object.values(fields()))field.addEventListener('input',refresh);
  window.addEventListener('cc-sales-complete',event=>{
    if(!assessment || !Array.isArray(event.detail?.results))return;
    // Consume settled raw results only, after Sales has ended; add no searches or time.
    window.CCHeadStartConfig().renderResults(event.detail.results);
    const panel=document.getElementById('ccSalesResults');if(!panel)return;
    let button=document.getElementById('ccSalesInsight');
    if(!button){
      button=document.createElement('button');button.id='ccSalesInsight';button.type='button';brandInsightButton(button);
      const feedback=document.createElement('p');feedback.id='ccSalesInsightMessage';feedback.setAttribute('role','status');
      button.addEventListener('click',async()=>{
        button.disabled=true;feedback.textContent='Preparing your Insight report…';
        try{await window.CCHeadStartConfig().generateReport();feedback.textContent=document.getElementById('reportMessage')?.textContent||'Your results are retained. Return to these results to prepare Insight.';}
        finally{button.disabled=false;}
      });
      panel.append(button,feedback);
    }
  });
  const fragment=new URLSearchParams(location.hash.slice(1));
  const sender=fragment.get('hs_sender'),nonce=fragment.get('hs_nonce');
  const allowed=new Set([location.origin,'http://127.0.0.1:8000','http://localhost:8000','https://charityclarity-head-start-test.nyaghi17.chatgpt.site']);
  if(sender && nonce && /^[a-f0-9-]{36}$/.test(nonce) && allowed.has(sender) && window.opener){
    let attempts=0,timer;
    const listener=event=>{
      if(event.source!==window.opener || event.origin!==sender || event.data?.type!=='cc.headstart.assessment' || event.data?.nonce!==nonce)return;
      try{accept(event.data.assessment);clearInterval(timer);window.removeEventListener('message',listener);history.replaceState(null,'',location.pathname+location.search);window.opener.postMessage({type:'cc.headstart.accepted',nonce},sender);}
      catch(error){card.hidden=false;message.textContent=error.message;}
    };
    window.addEventListener('message',listener);
    const ready=()=>{if(++attempts>120){clearInterval(timer);return;}window.opener.postMessage({type:'cc.headstart.ready',nonce},sender);};
    timer=setInterval(ready,250);ready();
  }else{
    try{const saved=sessionStorage.getItem(key);if(saved)accept(JSON.parse(saved));}catch{/* An invalid old browser copy is not attached. */}
  }
})();
