/* Original Mississippi filing document, used only when the selected dialog could not be captured. */
const CCMsOriginalDocument=(()=>{
  const portal='https://charities.sos.ms.gov/online/portal/ch/page/charities-search/Portal.aspx';
  const prefix=portal.replace('Portal.aspx','~/ViewXSLTFileByName.aspx?providerName=CH_EntityBasedFilingDetails&FilingId=');
  function validUrl(url) {
    return typeof url==='string'&&url.startsWith(prefix)&&/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(url.slice(prefix.length));
  }
  // Runs on the state's own standalone filing. Never rewrites source markup.
  function measure() {
    if(document.readyState!=='complete'||document.querySelector('#modalwindow')||scrollX||scrollY)return null;
    const panels=document.querySelectorAll('#printDiv1');
    if(panels.length!==1)return null;
    const panel=panels[0],heading=panel.querySelector('font');
    const names=['Filing Number','Filing Status','Initial Date Filed','Expiration Date'];
    const pairs=new Map(),plain=el=>(el?.innerText||'').replace(/\s+/g,' ').trim();
    if(!plain(heading))return null;
    for(const row of panel.querySelectorAll('tr')) {
      const label=row.querySelector('td.infoText'),key=plain(label).replace(/:$/,'');
      if(!names.includes(key))continue;
      if(pairs.has(key)||row.cells.length<2)return null;
      pairs.set(key,[label,row.cells[1]]);
    }
    if(pairs.size!==4)return null;
    const elements=[heading,...names.flatMap(name=>pairs.get(name))],binding=JSON.stringify(elements.map(plain));
    let bottom=0,right=0;
    for(const el of elements) {
      const bounds=el.getBoundingClientRect();
      if(!el.getClientRects().length||bounds.top<0||bounds.left<0)return null;
      for(let node=el;node;node=node.parentElement) {
        const css=getComputedStyle(node);
        if(css.display==='none'||css.visibility!=='visible'||Number(css.opacity)<.999)return null;
      }
      bottom=Math.max(bottom,bounds.bottom);right=Math.max(right,bounds.right);
    }
    const width=Math.ceil(Math.max(innerWidth,right)),height=Math.ceil(bottom+12);
    if(width<200||height<80||width>3000||height>6000||width*height>8000000)return null;
    return {url:location.href,binding,width,height};
  }
  async function capture(job,query,id,original) {
    const start=Date.now(),spent=job.msSnapshotSpentMs;
    const end=Math.min(start+5500,start+20000-Math.max(spent,job.requiredCaptureSpentByState?.MS||0),job.activeExpiresAt-750);
    const active=()=>Date.now()<end&&P.TRIAL_ORIGIN&&isActive(job)&&!job.closed
      &&job.tab===original.tab&&owned.has(original.tab)&&job.generation===original.generation
      &&job.pending===id&&job.command?.id===id&&P.sameQuery(job.command.query,query);
    if(end-start<750||!active()||(job.snapshotCaptures||0)>=4)return null;
    let timer,finished=false,extra,attached=false,phase='selected filing',result=null;
    const live=()=>!finished&&active();
    const metadata=()=>chrome.tabs.sendMessage(original.tab,{action:'registry-snapshot-metadata',query},{frameId:0});
    const command=(method,params)=>chrome.debugger.sendCommand({tabId:extra},method,params);
    const read=async()=> (await command('Runtime.evaluate',{expression:'('+measure.toString()+')()',returnByValue:true})).result?.value;
    async function run() {
      const before=await metadata();
      // The registry's Details link appends an empty fragment to the search page.
      if(!live()||(before?.url!==portal&&before?.url!==portal+'#')||!before.source_ms_detail_ready||!validUrl(before.source_ms_document_url)
          ||!before.document_id||!before.source_ms_binding||!before.public_text)return null;
      phase='filing fields';
      const fields=JSON.parse(before.source_ms_binding);
      if(!Array.isArray(fields)||fields.length!==9||fields[2]!==query.identifier||!fields[0]||!fields[4])return null;
      phase='parent tab';
      const source=before.source_ms_document_url,parent=await chrome.tabs.get(original.tab);
      if(!live()||parent.url!==before.url)return null;
      phase='document navigation';
      const tab=await chrome.tabs.create({windowId:parent.windowId,url:source,active:false});
      extra=tab.id;owned.add(extra);
      if(!live()){await removeOwned(extra);return null;}
      await saveRuntime();
      while(live()) {
        const t=await chrome.tabs.get(extra);
        if(t.status==='complete'&&t.url===source)break;
        if(t.url&&t.url!==source&&t.url!=='about:blank')return null;
        await new Promise(resolve=>setTimeout(resolve,60));
      }
      if(!live())return null;
      await chrome.debugger.attach({tabId:extra},'1.3');attached=true;
      if(!live())return null;
      phase='document identity';
      const frame=await read();
      if(!live()||frame?.url!==source||frame.binding!==before.source_ms_binding)return null;
      phase='original pixels';
      const image=await command('Page.captureScreenshot',{format:'jpeg',quality:82,fromSurface:true,
        captureBeyondViewport:true,clip:{x:0,y:0,width:frame.width,height:frame.height,scale:1}});
      if(!live()||typeof image?.data!=='string'||image.data.length<100||image.data.length>4000000||!image.data.startsWith('/9j/'))return null;
      const after=await read(),current=await metadata();
      if(!live()||JSON.stringify(frame)!==JSON.stringify(after)||current?.url!==before.url
        ||current.document_id!==before.document_id||current.source_ms_binding!==frame.binding
        ||current.source_ms_document_url!==source||current.public_text!==before.public_text)return null;
      phase='verified';return {query:{...query},source_url:portal,public_text:before.public_text,
        image:image.data,captured_at:Date.now()/1000,capture_ms:Date.now()-start};
    }
    try {
      result=await Promise.race([run(),new Promise(resolve=>{timer=setTimeout(()=>resolve(null),end-Date.now());})]);
      if(result&&active())job.snapshotCaptures=(job.snapshotCaptures||0)+1;else result=null;
    } catch { result=null; }
    finally {
      finished=true;clearTimeout(timer);
      // Teardown never closes the original portal tab or a user-owned tab.
      if(attached&&Number.isInteger(extra))try{await chrome.debugger.detach({tabId:extra});}catch{}
      if(Number.isInteger(extra))try{await removeOwned(extra);}catch{}
      const duration=Date.now()-start;
      job.msSnapshotSpentMs+=duration;
      if(job.requiredCaptureSpentByState)job.requiredCaptureSpentByState.MS=(job.requiredCaptureSpentByState.MS||0)+duration;
      diagnostic('ms-original-document',job,JSON.stringify({phase,milliseconds:duration,verified:!!result}));
    }
    return result;
  }
  return {validUrl,measure,capture};
})();
