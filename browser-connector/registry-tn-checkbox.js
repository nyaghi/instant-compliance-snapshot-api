/* A single ordinary visible checkbox action; no challenge/token APIs. */
(() => {
  'use strict';
  const origin='https://challenges.cloudflare.com',tn='https://tncab.tnsos.gov';
  if(window===window.top || location.origin!==origin
      || !location.pathname.startsWith('/cdn-cgi/challenge-platform/'))return;
  const ancestors=Array.from(location.ancestorOrigins||[]);
  if(!ancestors.length || ancestors.at(-1)!==tn || ancestors.some(x=>![origin,tn].includes(x)))return;
  const id=crypto.randomUUID(),deadline=Date.now()+45000;
  let stopped=false,pending=false,timer,observations=0,lastObservation='';
  const visible=el=>{
    if(!el?.isConnected || document.visibilityState!=='visible')return false;
    const rect=el.getBoundingClientRect(),style=getComputedStyle(el);
    return rect.width>0 && rect.height>0 && rect.bottom>0 && rect.right>0
      && rect.top<innerHeight && rect.left<innerWidth && style.visibility!=='hidden'
      && style.display!=='none' && style.pointerEvents!=='none';
  };
  const checkboxScan=()=>{
    const selector='input[type="checkbox"], [role="checkbox"]';
    const boxes=[...document.querySelectorAll(selector)];
    const api=typeof chrome.dom?.openOrClosedShadowRoot==='function';
    if(!api)return {boxes,complete:true,meta:{}};
    const roots=[document],seen=new Set(roots);let nodes=0,shadowControls=0,complete=true;
    for(let i=0;i<roots.length;i++){
      const root=roots[i];
      if(i){
        const found=[...root.querySelectorAll(selector)];
        shadowControls+=found.length;boxes.push(...found);
      }
      if(boxes.length>500){complete=false;break;}
      for(const element of root.querySelectorAll('*')){
        if(++nodes>500){complete=false;break;}
        // Chrome's documented API accepts HTMLElement, not SVG elements.
        if(element.namespaceURI&&element.namespaceURI!=='http://www.w3.org/1999/xhtml')continue;
        let child;try{child=chrome.dom.openOrClosedShadowRoot(element);}catch{complete=false;break;}
        if(child&&!seen.has(child)){
          if(roots.length>=9){complete=false;break;}
          seen.add(child);roots.push(child);
        }
      }
      if(!complete)break;
    }
    return {boxes,complete,meta:{shadow_api:true,shadow_roots:roots.length-1,
      shadow_controls:Math.min(shadowControls,9),scan_complete:complete}};
  };
  const candidate=(scan=checkboxScan())=>{
    // An incomplete traversal cannot establish that only one control exists.
    if(!scan.complete)return null;
    const choices=scan.boxes.map(box=>({box,target:box.closest('label')||box}))
      .filter(({box,target})=>!box.disabled && box.getAttribute('aria-disabled')!=='true'
        && !box.checked && box.getAttribute('aria-checked')!=='true' && visible(target));
    return choices.length===1?choices[0]:null;
  };
  const observe=()=>{
    const timingAvailable=typeof performance!=='undefined'&&typeof performance.now==='function';
    const scanStarted=timingAvailable?performance.now():null;
    const boxes=[...document.querySelectorAll('input[type="checkbox"], [role="checkbox"]')],scan=checkboxScan();
    const detail={phase:'frame-observed',visible:document.visibilityState==='visible',
      controls:Math.min(boxes.length,9),actionable:candidate(scan)!==null,...scan.meta};
    const signature=JSON.stringify(detail);
    if(observations>=4 || signature===lastObservation)return;
    observations++;lastObservation=signature;
    // Timings are excluded from the signature so the existing observation cap
    // and emission frequency stay unchanged. No source content is recorded.
    if(timingAvailable){
      detail.scan_ms=Math.min(60000,Math.max(0,Math.round((performance.now()-scanStarted)*1000)/1000));
      detail.script_age_ms=Math.min(60000,Math.max(0,Date.now()-(deadline-45000)));
      const navigation=typeof performance.getEntriesByType==='function'
        ?performance.getEntriesByType('navigation')[0]:null;
      if(navigation){
        const bounded=x=>Number.isFinite(x)&&x>=0&&x<=600000;
        const nav={frame_nav_ms:performance.now(),frame_response_end_ms:navigation.responseEnd,
          frame_dom_interactive_ms:navigation.domInteractive,
          frame_dom_ready_ms:navigation.domContentLoadedEventEnd,
          frame_load_end_ms:navigation.loadEventEnd};
        if(Object.values(nav).every(bounded))Object.assign(detail,nav);
      }
    }
    // Counts, booleans and elapsed times only;never verification values/content.
    chrome.runtime.sendMessage({action:'tn-checkbox-observation',id,...detail}).catch(()=>{});
  };
  const stop=()=>{stopped=true;clearTimeout(timer);observer.disconnect();};
  const inspect=async()=>{
    if(stopped || pending)return;
    if(Date.now()>=deadline){stop();return;}
    observe();
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
