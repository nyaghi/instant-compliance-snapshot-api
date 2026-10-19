/* Capture only an admitted connector-owned public source tab. No navigation,
   focus, scroll, verification, arbitrary CDP commands or other-window capture. */
async function captureStateSnapshot(job, query, commandId) {
  const started=Date.now(), tabId=job.tab, generation=job.generation;
  const alive=()=>P.TRIAL_ORIGIN && isActive(job) && !job.closed && owned.has(tabId)
    && job.tab===tabId && job.generation===generation && job.pending===commandId
    && job.command?.id===commandId && P.sameQuery(job.command.query,query)
    && Date.now()<job.activeExpiresAt;
  if(!alive() || !chrome.debugger || (job.snapshotCaptures||0)>=4
      || job.activeExpiresAt-Date.now()<4000)return null;
  const state=job.registryState;
  const allowed=state==='NY' ? P.NY : registryOrigin(state);
  let attached=false, cancelled=false, timeoutId;
  const operation=async()=>{
    try {
      const tab=await chrome.tabs.get(tabId);
      if(!alive() || new URL(tab.url).origin!==allowed)return null;
      const meta=await chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata'},{frameId:0});
      if(!alive() || meta?.url!==tab.url || typeof meta.public_text!=='string'
          || !meta.public_text.trim() || meta.public_text.length>20000
          || /verify you are human|user validation required|just a moment|access denied/i.test(meta.public_text))return null;
      await chrome.debugger.attach({tabId},'1.3');attached=true;
      if(cancelled || !alive())return null;
      const layout=await chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics');
      const size=layout.cssContentSize;
      if(cancelled || !alive() || !size || size.width<=0 || size.height<=0
          || size.width*size.height>20000000)return null;
      const image=await chrome.debugger.sendCommand({tabId},'Page.captureScreenshot',
        {format:'jpeg',quality:75,captureBeyondViewport:true,fromSurface:true,
          clip:{x:0,y:0,width:size.width,height:size.height,scale:1}});
      const after=await chrome.tabs.get(tabId);
      const afterMeta=await chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata'},{frameId:0});
      if(cancelled || !alive() || after.url!==tab.url || typeof image?.data!=='string'
          || afterMeta?.url!==meta.url || afterMeta?.public_text!==meta.public_text
          || image.data.length>4000000 || !/^[A-Za-z0-9+/]+={0,2}$/.test(image.data))return null;
      job.snapshotCaptures=(job.snapshotCaptures||0)+1;
      return {query:JSON.parse(JSON.stringify(query)),source_url:tab.url,public_text:meta.public_text,
        image:image.data,captured_at:Date.now()/1000,capture_ms:Date.now()-started};
    } catch {return null;}
    finally {
      if(attached)try{await chrome.debugger.detach({tabId});}catch{}
    }
  };
  // Evidence capture may consume at most 1.5s of the original budget. A late
  // callback discards its image and detaches its own tab; it never publishes it.
  const timed=new Promise(resolve=>{timeoutId=setTimeout(()=>{cancelled=true;resolve(null);},1500);});
  try{return await Promise.race([operation(),timed]);}
  finally{clearTimeout(timeoutId);}
}
