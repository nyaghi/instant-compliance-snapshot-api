/* Existing staging origin only; never pass app credentials to the extension. */
(() => {
  'use strict';
  const origin='https://charityclarity-final-four-29-2.onrender.com';
  if(location.origin!==origin||window!==window.top)return;
  const pending=new Set();
  window.addEventListener('message',event=>{
    const m=event.data;
    if(event.source!==window||event.origin!==origin||m?.channel!=='cc-owned-source-evidence-v1'
      ||!['request','cancel'].includes(m.direction)||typeof m.id!=='string'||!/^[a-f0-9-]{36}$/.test(m.id))return;
    if(m.direction==='cancel'){
      if(pending.delete(m.id))chrome.runtime.sendMessage({action:'cc-owned-source-cancel',id:m.id}).catch(()=>{});
      return;
    }
    if(pending.has(m.id))return;
    pending.add(m.id);
    chrome.runtime.sendMessage({action:'cc-owned-source-evidence',id:m.id,request:m.request})
      .then(result=>pending.has(m.id)&&window.postMessage({channel:m.channel,direction:'response',id:m.id,result},origin))
      .catch(()=>pending.has(m.id)&&window.postMessage({channel:m.channel,direction:'response',id:m.id,result:{ok:false,reason:'connector_unavailable'}},origin)).finally(()=>pending.delete(m.id));
  });
})();
