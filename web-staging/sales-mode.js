/* Staging presentation mode. All registry interpretation stays in the master API. */
(() => {
  'use strict';
  if (location.origin !== 'https://staging.compliance-express.com') return;
  const VERSION = '2026.09.24-sales.1';
  const RUN_LIMIT_MS = 60000;
  const STATE_CONCURRENCY = 15;
  const STATES = Object.freeze(["AK", "AR", "CA", "CO", "CT", "DC", "FL", "HI", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MS", "ND", "NH", "NJ", "NM", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "VA", "WA", "WI", "WV", "IL", "GA"]);
  const NAMES = {"IL":"Illinois", "GA":"Georgia", "AK": "Alaska", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DC": "District of Columbia", "RI": "Rhode Island", "FL": "Florida", "HI": "Hawaii", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "MA": "Massachusetts", "MD": "Maryland", "ME": "Maine", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "ND": "North Dakota", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "SC": "South Carolina", "VA": "Virginia", "WA": "Washington", "WI": "Wisconsin", "WV": "West Virginia"};
  // Display grouping only: never infer a registry outcome from a failed request.
  function displayStatus(result) {
    if (result.state === 'IL' && result.status === 'Not Registered / Non-Compliant' && result.success !== false) return result.status;
    if (result.success === false) return 'Unable to Confirm';
    const key = String(result.status || '').toLowerCase().replace(/[^a-z]/g, '');
    const groups = {current:'Current',upcomingfiling:'Current',delinquent:'Delinquent',failedtorenew:'Delinquent',notregistered:'Not Found',closedwithdrawncanceled:'Inactive',closedwithdrawncancelled:'Inactive',inactive:'Inactive',exempt:'Exempt',pending:'Pending',pendinginprocess:'Pending',revokedsuspended:'Inactive',revoked:'Inactive',suspended:'Inactive'};
    return groups[key] || 'Unable to Confirm';
  }
  const main = document.querySelector('#appShell main');
  const standard = [...main.children];
  const style = document.createElement('style');
  style.textContent = `
    .cc-sales-bolt{display:inline-block;vertical-align:-3px;margin-left:4px}.cc-modebar button[aria-pressed=true]{box-shadow:0 0 0 3px #0b2a5b20}.cc-sales-states{margin-top:22px;border-top:1px solid #e2e8f0;padding-top:16px}.cc-sales-states legend{font-weight:700}.cc-sales-state-actions{display:flex;align-items:center;gap:12px;margin:10px 0}.cc-sales-state-actions button{padding:6px 14px;font-size:13px}.cc-sales-state-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px 12px}.cc-sales-state-grid label{display:flex;align-items:center;gap:8px;margin:0;font-weight:400}.cc-sales-state-grid input{accent-color:#C62828}.cc-sales[hidden]{display:none!important}.cc-modebar{max-width:1180px;margin:0 auto;padding:18px 24px;display:flex;gap:10px;border-bottom:1px solid #e2e8f0}
    .cc-modebar button,.cc-sales button{border-radius:24px;padding:10px 22px;font-weight:700;cursor:pointer;border:1px solid #cbd5e1;background:#fff;color:#0B2A5B}
    .cc-modebar .cc-red,.cc-sales .cc-red{background:#C62828;color:white;border-color:#C62828}.cc-modebar button:disabled,.cc-sales button:disabled{opacity:.55;cursor:wait}
    .cc-modebar button:focus-visible,.cc-sales input:focus-visible{outline:3px solid #93c5fd;outline-offset:3px}
    .cc-sales{max-width:1040px;margin:0 auto;padding:32px 24px 48px;color:#0B2A5B}.cc-sales-logo{width:260px;max-width:80%;height:auto;margin-bottom:22px}
    .cc-sales h1{font-size:32px;line-height:1.2;font-weight:750;margin-bottom:8px}.cc-sales-sub{color:#64748b;margin-bottom:24px}
    .cc-sales-card{background:white;border:1px solid #e2e8f0;border-radius:18px;padding:24px;box-shadow:0 8px 26px #0b2a5b08}
    .cc-sales-fields{display:grid;grid-template-columns:2fr 1fr auto;gap:16px;align-items:end}.cc-sales label{display:block;font-size:13px;font-weight:650;margin-bottom:6px}
    .cc-sales input[type=text]{width:100%;border:1px solid #cbd5e1;border-radius:9px;padding:11px;font-size:16px;color:#0B2A5B}.cc-sales-consent{display:flex!important;gap:8px;align-items:center;margin-top:16px;font-weight:400!important;color:#475569}
    .cc-sales-statusbar{display:flex;justify-content:space-between;gap:12px;align-items:center;margin:24px 0 12px}.cc-sales-statusbar strong{font-size:20px}.cc-sales table{width:100%;border-collapse:collapse;font-size:15px}.cc-sales th{text-align:left;color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:.06em;padding:10px 14px;background:#f8fafc}.cc-sales td{padding:11px 14px;border-top:1px solid #f1f5f9}.cc-sales td:last-child{width:48%}
    .cc-sales-pill{display:inline-block;border-radius:20px;padding:4px 13px;font-size:13px;font-weight:700;background:#f1f5f9;color:#475569}.cc-sales-pill[data-status=Current]{background:#dcfce7;color:#166534}.cc-sales-pill[data-status=Delinquent]{background:#fee2e2;color:#991b1b}.cc-sales-pill[data-status=Exempt]{background:#e0f2fe;color:#075985}.cc-sales-pill[data-status=Pending]{background:#fef3c7;color:#92400e}
    .cc-sales-pill[data-status="Not Registered / Non-Compliant"]{background:linear-gradient(90deg,#f1f5f9 0%,#f1f5f9 50%,#fee2e2 50%,#fee2e2 100%);color:#0f172a}
    .cc-sales-error{color:#991b1b;margin-top:12px}.cc-sales-version{font-size:11px;color:#94a3b8;margin-top:20px}.cc-sales-progress{height:4px;background:#f1f5f9;border-radius:4px;overflow:hidden;margin-bottom:12px}.cc-sales-progress span{display:block;height:100%;background:#C62828;transition:width .15s}
    @media(max-width:650px){.cc-sales-fields{grid-template-columns:1fr}.cc-sales h1{font-size:27px}.cc-sales-card{padding:16px}.cc-sales{padding:24px 16px}.cc-sales-statusbar{align-items:flex-start;flex-direction:column}}
  `;
  document.head.append(style);
  const bar = document.createElement('div');bar.className='cc-modebar';
  bar.innerHTML='<button id="ccStandardMode" type="button" aria-pressed="true">Standard</button><button id="ccSalesMode" type="button" class="cc-red" aria-pressed="false">Sales <svg class="cc-sales-bolt" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="#FFD54F" d="M13 2 4 14h7l-1 8 10-13h-7l2-7z"/></svg></button>';
  const panel = document.createElement('section');panel.className='cc-sales';panel.hidden=true;panel.id='ccSalesPanel';
  panel.innerHTML=`<img class="cc-sales-logo" src="/sales-charityclarity.png" alt="CharityClarity"><h1>CharityClarity for Sales</h1><p class="cc-sales-sub">Choose any or all 34 states. Results appear as they finish. Checks stop after one minute; unfinished states show Unable to Confirm.</p>
    <p class="cc-sales-sub" id="ccSalesDisclaimer">Quick scan: alternate-name discovery is not performed. Registrations under other names may be missed. “Not Found” does not establish that an organization is unregistered. Run a full assessment to confirm.</p><div class="cc-sales-card"><form id="ccSalesForm"><div class="cc-sales-fields"><div><label for="ccSalesName">Organization name</label><input id="ccSalesName" type="text" required maxlength="240" autocomplete="organization"></div><div><label for="ccSalesEin">EIN</label><input id="ccSalesEin" type="text" required inputmode="numeric" placeholder="XX-XXXXXXX" pattern="[0-9]{2}-?[0-9]{7}" maxlength="10"></div><button type="submit" id="ccSalesRun" class="cc-red">Run Sales Check</button></div>
    <fieldset class="cc-sales-states" id="ccSalesStates"><legend>States to check</legend><div class="cc-sales-state-actions"><button id="ccSalesSelectAll" type="button">Select all 34</button><button id="ccSalesClear" type="button">Clear</button><span id="ccSalesSelectedCount" aria-live="polite">0 selected</span></div><div class="cc-sales-state-grid">${STATES.map(state=>`<label><input type="checkbox" name="salesStates" value="${state}">${NAMES[state]}</label>`).join('')}</div></fieldset>
    <label class="cc-sales-consent"><input type="checkbox" id="ccSalesConsent" required> I understand this is an informational compliance snapshot.</label><p id="ccSalesError" class="cc-sales-error" role="alert"></p></form>
    <div id="ccSalesResults" hidden><div class="cc-sales-statusbar"><strong id="ccSalesOrganization"></strong><span id="ccSalesProgress" role="status" aria-live="polite"></span></div><div class="cc-sales-progress"><span id="ccSalesProgressFill"></span></div><table aria-label="Sales compliance snapshot"><thead><tr><th scope="col">State</th><th scope="col">Status</th></tr></thead><tbody id="ccSalesRows"></tbody></table></div></div><p class="cc-sales-version">Staging · Sales Mode ${VERSION}</p>`;
  main.prepend(bar,panel);
  const $ = id => document.getElementById(id);
  let busy=false, active=false, runId=0;
  const stateInputs = [...panel.querySelectorAll('input[name="salesStates"]')];
  const updateSelected = () => {$('ccSalesSelectedCount').textContent=stateInputs.filter(el=>el.checked).length+' selected';};
  stateInputs.forEach(el=>el.addEventListener('change',updateSelected));
  $('ccSalesSelectAll').onclick=()=>{if(!busy){stateInputs.forEach(el=>el.checked=true);updateSelected();}};
  $('ccSalesClear').onclick=()=>{if(!busy){stateInputs.forEach(el=>el.checked=false);updateSelected();}};
  function setMode(sales) {
    if(busy || (!$('progressBox').classList.contains('hidden') && $('submitButton').disabled)) return;
    active=sales;panel.hidden=!sales;standard.forEach(el=>el.hidden=sales);
    $('ccSalesMode').setAttribute('aria-pressed',String(sales));$('ccStandardMode').setAttribute('aria-pressed',String(!sales));
    if(sales){$('ccSalesName').value ||= $('organizationName').value;$('ccSalesEin').value ||= $('ein').value;$('ccSalesName').focus();}
  }
  $('ccSalesMode').onclick=()=>setMode(true);$('ccStandardMode').onclick=()=>setMode(false);
  const seconds = ms => (ms/1000).toFixed(1)+'s';
  $('ccSalesForm').addEventListener('submit',async event=>{
    event.preventDefault();if(busy || !active) return;
    const org=$('ccSalesName').value.trim(),ein=$('ccSalesEin').value.replace(/\D/g,'');
    $('ccSalesError').textContent='';
    if(!org || ein.length!==9 || !$('ccSalesConsent').checked) return;
    const selectedStates=stateInputs.filter(el=>el.checked).map(el=>el.value);
    if(!selectedStates.length){$('ccSalesError').textContent='Select at least one state.';return;}
    if(!internalUnlocked || !isComplianceExpressEmail($('email').value) || !$('adminPasscode').value.trim()) {$('ccSalesError').textContent='Unlock staging to run a sales check.';return;}
    busy=true;const id=++runId,start=performance.now(),deadline=start+RUN_LIMIT_MS;let completed=0,closed=false,cutoff=false;const results=[],settled=new Set(),controller=new AbortController();
    for(const el of [$('ccSalesRun'),$('ccSalesMode'),$('ccStandardMode'),$('ccSalesName'),$('ccSalesEin'),$('ccSalesConsent'),$('ccSalesStates')]) el.disabled=true;
    $('ccSalesOrganization').textContent=org;$('ccSalesResults').hidden=false;$('ccSalesRows').replaceChildren();
    const cells=new Map();
    for(const state of selectedStates){const row=document.createElement('tr');const label=document.createElement('td');row.dataset.state=state;label.textContent=NAMES[state];const value=document.createElement('td');value.textContent='Checking…';row.append(label,value);$('ccSalesRows').append(row);cells.set(state,value);}
    const progress=()=>{$('ccSalesProgress').textContent=`${completed} of ${selectedStates.length} · ${seconds(performance.now()-start)}`;$('ccSalesProgressFill').style.width=(completed/selectedStates.length*100)+'%';};
    const record=(state,result)=>{
      if(settled.has(state)) return;
      settled.add(state);
      const status=displayStatus(result),pill=document.createElement('span');pill.className='cc-sales-pill';pill.dataset.status=status;pill.textContent=status;pill.title=String(result.comments||'');cells.get(state).replaceChildren(pill);
      if(result.status_reason==='SALES_TIME_LIMIT') { const note=document.createElement('small');note.textContent='One-minute limit reached. Run Standard for a full check.';note.style.display='block';cells.get(state).append(note); }
      cells.get(state).parentElement.dataset.elapsedSeconds=((performance.now()-start)/1000).toFixed(3);
      completed++;results.push({state,status,result,elapsed_seconds:(performance.now()-start)/1000});progress();
    };
    let releaseDeadline;
    const expired=new Promise(resolve=>{releaseDeadline=resolve;});
    const expire=()=>{
      if(closed) return;
      closed=true;cutoff=true;controller.abort();
      for(const state of selectedStates) if(!settled.has(state)) record(state,{state,ein,organization_name:org,status:'Unable to Confirm',success:false,status_reason:'SALES_TIME_LIMIT',comments:`${NAMES[state]} did not finish within the one-minute Sales check limit. Registration status remains unconfirmed. Run Standard mode for a full check.`});
      releaseDeadline();
    };
    progress();const timer=setInterval(()=>{if(performance.now()>=deadline)expire();else progress();},100);
    const deadlineTimer=setTimeout(expire,Math.max(0,deadline-performance.now()));
    try {
      const queue=[...selectedStates.filter(s=>s==='NY'),...selectedStates.filter(s=>s!=='NY')];let cursor=0,inFlight=0,peak=0;
      async function worker(){while(!closed && cursor<queue.length){if(performance.now()>=deadline){expire();return;}const state=queue[cursor++];inFlight++;peak=Math.max(peak,inFlight);
        let result;
        try{result=await requestSingleState(API_BASE,ein,$('email').value.trim(),state,org,false,[],{signal:controller.signal});}
        catch{result={state,status:'Unable to Confirm',success:false,comments:`${NAMES[state]} did not return a complete response. Registration status remains unconfirmed.`};}
        inFlight--;
        if(closed)return;
        if(performance.now()>=deadline){expire();return;}
        record(state,result);
      }}
      await Promise.race([Promise.all(Array.from({length:Math.min(STATE_CONCURRENCY,queue.length)},worker)),expired]);
      panel.dataset.peakConcurrency=String(peak);
    } finally {
      closed=true;clearTimeout(deadlineTimer);clearInterval(timer);busy=false;progress();
      for(const el of [$('ccSalesRun'),$('ccSalesMode'),$('ccStandardMode'),$('ccSalesName'),$('ccSalesEin'),$('ccSalesConsent'),$('ccSalesStates')]) el.disabled=false;
      window.dispatchEvent(new CustomEvent('cc-sales-complete',{detail:{run_id:id,organization:org,ein,seconds:(performance.now()-start)/1000,results,version:VERSION,time_limit_reached:cutoff}}));
    }
  });
  window.CCSales=Object.freeze({version:VERSION,states:STATES,displayStatus});
})();
