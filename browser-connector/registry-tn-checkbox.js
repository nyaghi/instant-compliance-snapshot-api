/* A single ordinary visible checkbox action; no challenge/token APIs. */
(() => {
  'use strict';
  const origin='https://challenges.cloudflare.com',tn='https://tncab.tnsos.gov';
  if(window===window.top || location.origin!==origin
      || !location.pathname.startsWith('/cdn-cgi/challenge-platform/'))return;
  const ancestors=Array.from(location.ancestorOrigins||[]);
  if(!ancestors.length || ancestors.at(-1)!==tn || ancestors.some(x=>![origin,tn].includes(x)))return;
  const id=crypto.randomUUID(),deadline=Date.now()+45000;
  let stopped=false,pending=false,timer;
  const visible=el=>{
    if(!el?.isConnected || document.visibilityState!=='visible')return false;
    const rect=el.getBoundingClientRect(),style=getComputedStyle(el);
    return rect.width>0 && rect.height>0 && rect.bottom>0 && rect.right>0
      && rect.top<innerHeight && rect.left<innerWidth && style.visibility!=='hidden'
      && style.display!=='none' && style.pointerEvents!=='none';
  };
  const candidate=()=>{
    const boxes=[...document.querySelectorAll('input[type="checkbox"], [role="checkbox"]')];
    const choices=boxes.map(box=>({box,target:box.closest('label')||box}))
      .filter(({box,target})=>!box.disabled && box.getAttribute('aria-disabled')!=='true'
        && !box.checked && box.getAttribute('aria-checked')!=='true' && visible(target));
    return choices.length===1?choices[0]:null;
  };
  const stop=()=>{stopped=true;clearTimeout(timer);observer.disconnect();};
  const inspect=async()=>{
    if(stopped || pending)return;
    if(Date.now()>=deadline){stop();return;}
    const choice=candidate();
    if(choice){
      pending=true;
      try{
        const result=await chrome.runtime.sendMessage({action:'tn-checkbox-permission',id});
        if(result?.allowed===true){
          const current=candidate();let phase='changed-before-click';
          if(Date.now()<deadline && current?.box===choice.box && current.target===choice.target){
            try{choice.target.click();phase='clicked';}catch{phase='click-unavailable';}
          }
          stop();
          await chrome.runtime.sendMessage({action:'tn-checkbox-outcome',id,phase});
          return;
        }
      }catch{}
      finally{pending=false;}
    }
    if(!stopped){clearTimeout(timer);timer=setTimeout(inspect,500);}
  };
  const observer=new MutationObserver(inspect);
  observer.observe(document.documentElement,{childList:true,subtree:true,attributes:true,
    attributeFilter:['style','class','disabled','aria-disabled','aria-checked']});
  inspect();
})();
