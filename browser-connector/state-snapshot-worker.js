/* Capture only an admitted connector-owned public source tab. Tennessee may use its native desktop-responsive viewport. Nevada scrolls
   only the bound original source panel; both restore their original state.
   No navigation, focus, verification, DOM/CSS rewriting or other-window capture. */
async function captureStateSnapshot(job, query, commandId) {
  const started=Date.now(), tabId=job.tab, generation=job.generation;
  const alive=()=>P.TRIAL_ORIGIN && isActive(job) && !job.closed && owned.has(tabId)
    && job.tab===tabId && job.generation===generation && job.pending===commandId
    && job.command?.id===commandId && P.sameQuery(job.command.query,query)
    && Date.now()<job.activeExpiresAt;
  const observed={phase:'entry',captures:job.snapshotCaptures||0};
  const trace=()=>{if(job.registryState==='NV'&&typeof diagnostic==='function')diagnostic('source-snapshot-phase',job,JSON.stringify({operation:query.operation||'search',...observed}));};
  if(!alive() || job.snapshotViewportBusy || !chrome.debugger || (job.snapshotCaptures||0)>=4
      || job.activeExpiresAt-Date.now()<4000){observed.phase='entry-rejected';trace();return null;}
  const state=job.registryState;
  const allowed=state==='NY' ? P.NY : registryOrigin(state);
  let attached=false, cancelled=false, timeoutId,restoreModal=false,desktopViewport=false;
  const operation=async()=>{
    try {
      observed.phase='tab';const tab=await chrome.tabs.get(tabId);
      if(!alive() || new URL(tab.url).origin!==allowed)return null;
      observed.phase='metadata';let meta=await chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0});
      if(!alive() || meta?.url!==tab.url || typeof meta.public_text!=='string'
          || !meta.public_text.trim() || meta.public_text.length>20000
          || /verify you are human|user validation required|just a moment|access denied/i.test(meta.public_text))return null;
      if(state==='NV'){observed.detail=meta?.source_detail===true;observed.fields_visible=meta?.source_fields_visible===true;observed.visible=meta?.source_visible===true;}
      observed.phase='identity';if(['TN','NV'].includes(state)&&query.operation==='detail'&&meta.source_detail!==true)return null;
      observed.phase='attach';await chrome.debugger.attach({tabId},'1.3');attached=true;
      if(cancelled || !alive())return null;
      observed.phase='layout';let layout=await chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics');
      if(state==='NV'){observed.width=layout.cssLayoutViewport?.clientWidth||0;observed.height=layout.cssLayoutViewport?.clientHeight||0;}
      if(state==='TN'&&query.operation==='detail'&&layout.cssLayoutViewport?.clientWidth<800) {
        // The state's Kendo FinancialPeriod column has media:min-width 800px.
        // Ask Chrome to render that original desktop layout, not invented CSS.
        job.snapshotViewportBusy=true;desktopViewport=true;
        observed.phase='viewport';await chrome.debugger.sendCommand({tabId},'Emulation.setDeviceMetricsOverride',
          {width:1024,height:900,deviceScaleFactor:0,mobile:false});
        if(cancelled||!alive())return null;
        observed.phase='settled-metadata';meta=await chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query,settle:true},{frameId:0});
        layout=await chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics');
        if(cancelled||!alive()||meta?.url!==tab.url||typeof meta.public_text!=='string'
          ||!meta.public_text.trim()||meta.public_text.length>20000
          ||/verify you are human|user validation required|just a moment|access denied/i.test(meta.public_text))return null;
        if(meta.source_detail!==true)return null;
      }
      const size=layout.cssContentSize;
      if(state==='NV'){observed.content_width=size?.width||0;observed.content_height=size?.height||0;}
      if(cancelled || !alive() || !size || size.width<=0 || size.height<=0
          || size.width*size.height>20000000)return null;
      const tnModal=state==='TN'&&query.operation==='detail'&&Array.isArray(meta.capture_views)
        &&meta.capture_views.length>=2&&meta.capture_views.length<=3&&meta.capture_views[0]==='top'
        &&new Set(meta.capture_views).size===meta.capture_views.length
        &&meta.capture_views.every(view=>['top','expiration','financial'].includes(view));
      const nvModal=state==='NV'&&query.operation==='detail'&&Array.isArray(meta.capture_views)
        &&meta.capture_views.length>=1&&meta.capture_views.length<=3
        &&meta.capture_views.every((view,index)=>view==='nv-'+index);
      if(state==='NV'&&query.operation==='detail'&&!nvModal)return null;
      const modal=tnModal||nvModal;
      const viewport=layout.cssLayoutViewport;
      if(modal&&(!viewport||viewport.clientWidth<=0||viewport.clientHeight<=0
        ||viewport.clientWidth*viewport.clientHeight>20000000))return null;
      const images=[];
      for(const view of modal?meta.capture_views:[null]) {
        if(cancelled||!alive())return null;
        if(view) {
          restoreModal=true;
          const changed=await chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view},{frameId:0});
          if(changed?.ok!==true||cancelled||!alive())return null;
        }
        observed.phase='capture';const image=await chrome.debugger.sendCommand({tabId},'Page.captureScreenshot',
          {format:'jpeg',quality:75,captureBeyondViewport:!modal,fromSurface:true,
            clip:modal?{x:viewport.pageX||0,y:viewport.pageY||0,width:viewport.clientWidth,height:viewport.clientHeight,scale:1}:
              {x:0,y:0,width:size.width,height:size.height,scale:1}});
        if(typeof image?.data!=='string'||image.data.length>4000000||!/^[A-Za-z0-9+/]+={0,2}$/.test(image.data))return null;
        if(!images.includes(image.data))images.push(image.data);
        if(modal&&images.reduce((total,item)=>total+item.length,0)>3000000)return null;
      }
      if(modal&&images.length!==meta.capture_views.length)return null;
      observed.phase='postvalidation';const after=await chrome.tabs.get(tabId);
      const afterMeta=await chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0});
      if(cancelled || !alive() || after.url!==tab.url || !images.length
          || afterMeta?.url!==meta.url || afterMeta?.public_text!==meta.public_text
          || (state==='TN'&&query.operation==='detail'&&afterMeta.source_detail!==true)
          || (state==='NV'&&query.operation==='detail'&&afterMeta.source_detail!==true)
          )return null;
      observed.phase='image-validated';
      return {query:JSON.parse(JSON.stringify(query)),source_url:tab.url,public_text:meta.public_text,
        image:images[0],...(images.length>1?{images}:{}),captured_at:Date.now()/1000,capture_ms:Date.now()-started};
    } catch {observed.phase+='-error';return null;}
    finally {
      if(restoreModal&&alive())try{await chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view:'restore'},{frameId:0});}catch{}
      if(desktopViewport&&attached)try{await chrome.debugger.sendCommand({tabId},'Emulation.clearDeviceMetricsOverride');}catch{}
      if(attached)try{await chrome.debugger.detach({tabId});}catch{}
      if(desktopViewport)delete job.snapshotViewportBusy;
    }
  };
  // Evidence capture may consume at most 1.5s of the original budget. A late
  // callback discards its image and detaches its own tab; it never publishes it.
  const timed=new Promise(resolve=>{timeoutId=setTimeout(()=>{
    cancelled=true;observed.phase+='-timeout';
    // Detach the original owned target on timeout so Chrome also drops its
    // session viewport override. Late callbacks cannot publish a source image.
    if(state==='NV'&&restoreModal&&attached)
      chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view:'restore'},{frameId:0}).catch(()=>{});
    if((desktopViewport||state==='NV')&&attached)chrome.debugger.detach({tabId}).catch(()=>{});
    resolve(null);
  },1500);});
  let captured=null;
  try{captured=await Promise.race([operation(),timed]);if(captured){job.snapshotCaptures=(job.snapshotCaptures||0)+1;observed.phase='published';}return captured;}
  finally{
    clearTimeout(timeoutId);trace();
    if(typeof diagnostic==='function')diagnostic('source-snapshot',job,JSON.stringify({
      operation:query.operation||'search',capture_ms:Math.max(0,Date.now()-started),
      saved:!!captured,pages:captured?(captured.images?.length||1):0}));
  }
}
