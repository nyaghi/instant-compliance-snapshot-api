/* Usage display only. Never awaited by discovery, registry checks or results. */
(() => {
  'use strict';
  let shown=-1, pending=null;
  function display(count) {
    if(!Number.isSafeInteger(count)||count<0||count<shown)return;
    const root=document.getElementById('checksCompleted');if(!root)return;
    const digits=root.querySelector('.check-digits'),label=root.querySelector('.check-count-label');
    const before=shown<0?'':String(shown),after=String(count);
    digits.replaceChildren(...[...after].map((digit,index)=>{
      const tile=document.createElement('span');tile.className='check-digit';tile.textContent=digit;
      if(before&&before.padStart(after.length,'0')[index]!==digit)tile.classList.add('check-flip');
      return tile;
    }));
    digits.setAttribute('aria-label',count.toLocaleString()+' organization checks completed');
    label.textContent='Organization checks completed';root.hidden=false;shown=count;
  }
  async function send(options,extra) {
    try {
      const response=await fetch(options.apiBase+'/api/checks-completed',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...options.credentials,...extra}),signal:AbortSignal.timeout(5000)});
      if(!response.ok)return false;
      display((await response.json()).count);return true;
    } catch {return false;}
  }
  function load(options){return send(options,{action:'read'});}
  function completed(options) {
    const request={action:'complete',check_id:options.id,states:options.states,ein:options.ein,run_completed:true};
    // One bounded acknowledgement retry uses the same ID. No durable secrets,
    // no perpetual polling and no synthetic count if persistence is unavailable.
    pending=send(options,request).then(ok=>ok||send(options,request));
  }
  window.CCCompletedChecks=Object.freeze({load,completed});
})();
