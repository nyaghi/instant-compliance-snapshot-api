/* Capture only an admitted connector-owned public source tab. Tennessee may use its native desktop-responsive viewport. Nevada scrolls

   only the bound original source panel; both restore their original state.

   No navigation, focus, verification, DOM/CSS rewriting or other-window capture. */

async function captureStateSnapshot(job, query, commandId, prepared = null) {

  const started=Date.now(), tabId=job.tab, generation=job.generation;

  const alive=()=>P.TRIAL_ORIGIN && isActive(job) && !job.closed && owned.has(tabId)

    && job.tab===tabId && job.generation===generation && job.pending===commandId

    && job.command?.id===commandId && P.sameQuery(job.command.query,query)

    && Date.now()<job.activeExpiresAt;

  const observed={phase:'entry',captures:job.snapshotCaptures||0};

  const trace=()=>{
    if(job.registryState==='NV'&&typeof diagnostic==='function')diagnostic('source-snapshot-phase',job,JSON.stringify({operation:query.operation||(['GA','IL'].includes(job.registryState)&&Object.hasOwn(query,'identifier')?'detail':'search'),...observed}));
    if(['NC','GA','IL','AL','TN','NM','MS'].includes(job.registryState)&&typeof diagnostic==='function')try {
      diagnostic('source-snapshot-phase',job,JSON.stringify({operation:query.operation||(['GA','IL'].includes(job.registryState)&&Object.hasOwn(query,'identifier')?'detail':'search'),...observed}));
    } catch { /* Observation cannot invalidate an original screenshot. */ }
  };

  // Reserve the last existing image slot for a selected Georgia detail.
  if(job.registryState==='GA'&&!Object.hasOwn(query,'identifier')&&(job.snapshotCaptures||0)>=3){observed.phase='detail-slot-reserved';trace();return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:29:143:return",(null));}
  const ilDetail=job.registryState==='IL'&&Object.hasOwn(query,'identifier');
  if(job.registryState==='IL'&&!ilDetail&&(job.snapshotCaptures||0)>=3){observed.phase='detail-slot-reserved';trace();return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:31:118:return",(null));}
  if(!alive() || job.snapshotCleanupBusy || job.snapshotViewportBusy || job.ilTnSnapshotCleanupBusy || (job.registryState==='AL'&&job.alSnapshotCaptureBusy) || !chrome.debugger || (job.snapshotCaptures||0)>=(((job.registryState==='GA'&&Object.hasOwn(query,'identifier'))||(['NC','TN'].includes(job.registryState)&&query.operation==='detail'))?24:4)

      || job.activeExpiresAt-Date.now()<4000){observed.phase='entry-rejected';trace();return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:34:86:return",(null));}

  const state=job.registryState;
  if(state==='AL')job.alSnapshotCaptureBusy=true;

  // One bounded allowance covers selected setup, pixels and fresh validation.
  // Earlier optional search captures cannot spend it. Repeated required
  // captures share it; the original state expiry always wins.
  const completionState=['AL','IL','NM','MS','NV'].includes(state);
  const completionRequired=completionState&&(state==='AL'
    ?prepared?.kind==='al-completed-record'&&prepared.command_id===commandId&&P.sameQuery(prepared.query,query)
    :state==='IL'?ilDetail:query.operation==='detail');
  const legacySpendKey=state.toLowerCase()+'SnapshotSpentMs';
  if(completionState&&!job.requiredCaptureSpentByState) {
    // Conservatively retain any old-version spending when resuming a job.
    const old=job[legacySpendKey];
    job.requiredCaptureSpentByState={[state]:old===undefined?0:Number.isFinite(old)&&old>=0?old:20000};
  }
  const completionSpent=completionState?job.requiredCaptureSpentByState[state]??0:0;
  if(completionRequired&&(!Number.isFinite(completionSpent)||completionSpent<0||completionSpent>=19500)) {
    if(state==='AL')delete job.alSnapshotCaptureBusy;
    observed.phase='required-capture-budget-exhausted';trace();return null;
  }
  let captureBudgetMs=state==='NV'&&query.operation==='detail'?2500:1500;
  const workerSettledDetail=(state==='IL'&&ilDetail)||(state==='TN'&&query.operation==='detail');
  if(workerSettledDetail) {
    const spentKey=state==='IL'?'ilSnapshotSpentMs':'tnSnapshotSpentMs';
    const spent=completionRequired?completionSpent:Number.isFinite(job[spentKey])?Math.max(0,job[spentKey]):0;
    captureBudgetMs=Math.min(state==='TN'?16000:20000,Math.max(0,(state==='TN'?18000:20000)-spent),job.activeExpiresAt-started-500);
    if(captureBudgetMs<500){observed.phase='detail-budget-exhausted';trace();return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:45:77:return",(null));}
    observed.prior_capture_ms=spent;
    job.ilTnSnapshotCleanupBusy=true;
  }
  if(state==='NM'&&query.operation==='detail') {
    const spent=completionSpent;
    captureBudgetMs=Math.min(20000,Math.max(0,20000-spent),job.activeExpiresAt-started-1000);
    if(captureBudgetMs<500){observed.phase='detail-budget-exhausted';trace();return null;}
    observed.prior_capture_ms=spent;
  }
  if(state==='AL') {
    // Only a bound positive record gets the measured slow-capture reserve.
    // Negative/search captures keep their prior caps; state expiry is unchanged.
    const record=['al-completed-record','al-final-empty'].includes(prepared?.kind)&&prepared.command_id===commandId&&P.sameQuery(prepared.query,query);
    const positiveRecord=record&&prepared.kind==='al-completed-record';
    const spent=completionRequired?completionSpent:Number.isFinite(job.alSnapshotSpentMs)?Math.max(0,job.alSnapshotSpentMs):0;
    const remaining=Math.max(0,(positiveRecord?20000:6000)-spent);
    if(remaining<1000){delete job.alSnapshotCaptureBusy;observed.phase='capture-budget-exhausted';trace();return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:55:106:return",(null));}
    captureBudgetMs=Math.min(record?remaining:1500,remaining,job.activeExpiresAt-started-1000);
    observed.prior_capture_ms=spent;
  }
  if(state==='NC') {
    // Detail metadata took 6.3s in the retained full-state trace. Bound that
    // original-image work to 10s / 12s aggregate, without changing state expiry.
    // Search images keep their prior limits and one-second completion reserve.
    const selected=query.operation==='detail';
    const spent=Number.isFinite(job.ncSnapshotSpentMs)?Math.max(0,job.ncSnapshotSpentMs):0;
    const remaining=Math.max(0,(selected?12000:6000)-spent);
    if(remaining<1000){observed.phase='capture-budget-exhausted';trace();return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:66:73:return",(null));}
    captureBudgetMs=Math.min(selected?10000:3000,remaining,job.activeExpiresAt-started-1000);
    observed.prior_capture_ms=spent;
  }


  const gaRequiredDetail=state==='GA'&&Object.hasOwn(query,'identifier');
  const gaDetailKey=gaRequiredDetail?JSON.stringify([query.identifier,query.record_name||'']):null;
  if(gaRequiredDetail) {
    // Each distinct signed candidate needs its own original detail. Repeated
    // attempts for that same credential share one allowance; earlier candidates
    // cannot consume it. The existing job expiry still bounds the entire search.
    if(!job.gaDetailSnapshotSpentByRecord)job.gaDetailSnapshotSpentByRecord=Object.create(null);
    const prior=job.gaDetailSnapshotSpentByRecord[gaDetailKey];
    const spent=Number.isFinite(prior)?Math.max(0,prior):0;
    const remaining=Math.max(0,10000-spent);
    if(remaining<1000){observed.phase='detail-capture-budget-exhausted';trace();return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:76:80:return",(null));}
    captureBudgetMs=Math.min(remaining,job.activeExpiresAt-started-1000);
    observed.prior_capture_ms=spent;
  }
  if(state==='NY') {
    // Selected-detail setup exceeded the four-second readiness admission point.
    // Bound its capture work to ten seconds/twelve aggregate; preserve search caps.
    // Searches retain their original limit; the state deadline is unchanged.
    const spent=Number.isFinite(job.nySnapshotSpentMs)?Math.max(0,job.nySnapshotSpentMs):0;
    const selected=Object.hasOwn(query,'orgID');
    const remaining=Math.max(0,(selected?12000:6000)-spent);
    captureBudgetMs=Math.min(selected?10000:1500,remaining,job.activeExpiresAt-started-1000);
    if(captureBudgetMs<500){observed.phase='capture-budget-exhausted';trace();return null;}
    observed.prior_capture_ms=spent;
  }
  if(state==='MS') {
    // The retained full-state trace spent 2.6s reading the tab and 3.9s
    // awaiting metadata. Use the shared selected completion allowance, bounded by
    // the original state expiry; searches retain their six-second aggregate.
    const spent=completionRequired?completionSpent:Number.isFinite(job.msSnapshotSpentMs)?Math.max(0,job.msSnapshotSpentMs):0;
    const remaining=Math.max(0,(query.operation==='detail'?20000:6000)-spent);
    // Readiness and post-image validation share this same absolute end.
    captureBudgetMs=Math.min(query.operation==='detail'?Math.max(0,20000-spent):1500,remaining,job.activeExpiresAt-started-1000);
    if(captureBudgetMs<500){observed.phase='capture-budget-exhausted';trace();return null;}
    observed.prior_capture_ms=spent;
  }
  if(['NV','NC','GA','IL','AL','TN','NM','MS'].includes(state)){observed.budget_ms=captureBudgetMs;observed.steps=[];}

  function sampled(label,operation) {

    if(state==='NC'||state==='GA'||state==='IL'||state==='AL'||state==='TN'||state==='NM'||state==='MS') {
      const begin=Date.now();observed.waiting=label;observed.wait_started_ms=begin-started;
      const finished=()=>{
        if(observed.steps.length<20)observed.steps.push({api:label,ms:Math.max(0,Date.now()-begin)});
        if(observed.waiting===label)delete observed.waiting;
      };
      // Issue the same API immediately; observation adds no timer or request.
      try {return wfReturn(job,"state-snapshot-worker.js:sampled:91:11:return",(Promise.resolve(operation()).finally(finished)));}
      catch(error){finished();throw error;}
    }
    if(state!=='NV')return wfReturn(job,"state-snapshot-worker.js:sampled:94:20:return",(operation()));

    const begin=Date.now();observed.waiting=label;observed.wait_started_ms=begin-started;

    return wfReturn(job,"state-snapshot-worker.js:sampled:98:4:return",(Promise.resolve().then(operation).finally(()=>{

      if(observed.steps.length<20)observed.steps.push({api:label,ms:Math.max(0,Date.now()-begin)});

      if(observed.waiting===label)delete observed.waiting;

    })));

  }



  const allowed=state==='NY' ? P.NY : registryOrigin(state);

  let attached=false, cancelled=false, timeoutId,expireCapture,restoreModal=false,desktopViewport=false,ilPaintActive=false,msOriginalScroll=null,timeoutDetach=null;
  let validatedResult=null, publishRestored;
  const restoredImage=new Promise(resolve=>{publishRestored=resolve;});

  const ncSelectedDetail=state==='NC'&&query.operation==='detail';
  if(ncSelectedDetail)job.ilTnSnapshotCleanupBusy=true;
  const operation=async()=>{
    let settleCleanup;
    const cleanupCompletion=new Promise(resolve=>{settleCleanup=resolve;});
    job.snapshotCleanupCompletion=cleanupCompletion;

    try {

      job.snapshotCleanupBusy=true;

      observed.phase='tab';const tab=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:120:37:await",()=>(sampled('tab',()=>chrome.tabs.get(tabId))));

      if(!alive() || new URL(tab.url).origin!==allowed)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:122:55:return",(null));

      const validBinding=m=>typeof m?.source_binding==='string'&&m.source_binding.length>0&&m.source_binding.length<=20000

        &&typeof m.document_id==='string'&&m.document_id.length>0&&m.document_id.length<=100;

      const preparedAge=prepared?Date.now()-prepared.observed_at:NaN;

      const usePrepared=state==='NV'&&query.operation==='detail'&&prepared?.command_id===commandId

        &&P.sameQuery(prepared.query,query)&&Number.isFinite(preparedAge)&&preparedAge>=0&&preparedAge<=(validBinding(prepared.metadata)?45000:1000)

        &&typeof prepared.document_id==='string'&&prepared.document_id.length>0&&prepared.document_id.length<=100

        &&prepared.metadata?.document_id===prepared.document_id&&prepared.metadata?.url===tab.url

        &&prepared.metadata?.source_detail===true&&typeof prepared.metadata.public_text==='string';

      if(state==='NV'){

        observed.metadata_mode=usePrepared?'completed-detail-reply':'fresh-message';

        if(typeof diagnostic==='function')diagnostic('source-snapshot-phase',job,JSON.stringify({operation:query.operation,phase:'metadata-admission',prepared_present:!!prepared,age_ms:Number.isFinite(preparedAge)?preparedAge:null,use_prepared:usePrepared,record_binding:validBinding(prepared?.metadata)}));

      }

      observed.phase='metadata';let meta=usePrepared?prepared.metadata

        :await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:150:9:await",()=>(sampled('metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}))));

      if(!alive() || meta?.url!==tab.url || typeof meta.public_text!=='string'

          || !meta.public_text.trim() || meta.public_text.length>20000

          || /verify you are human|user validation required|just a moment|access denied/i.test(meta.public_text))return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:156:113:return",(null));

      if(state==='NV'){
        observed.detail=meta?.source_detail===true;observed.fields_visible=meta?.source_fields_visible===true;observed.visible=meta?.source_visible===true;
        if(query.operation==='detail')observed.loader_clear=meta.source_loading_visible===false;
        const waited=prepared?.paint_readiness?.wait_ms;
        if(Number.isFinite(waited)&&waited>=0&&waited<=45000)observed.paint_wait_ms=waited;
      }

      const boundNvDetail=state==='NV'&&query.operation==='detail'&&validBinding(meta);

      observed.phase='identity';if((ilDetail||['TN','NV'].includes(state)&&query.operation==='detail')&&meta.source_detail!==true)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:167:130:return",(null));

      // A selected record can render its identity before its date labels.
      // Wait only within this same capture allowance, never photograph a shell.
      while(workerSettledDetail&&meta.source_summary_ready===false&&!cancelled&&alive()
          &&Date.now()<started+captureBudgetMs-500) {
        await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:173:8:await",()=>(new Promise(resolve=>setTimeout(resolve,40))));
        meta=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:174:13:await",()=>(sampled('summary-readiness',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}))));
        if(meta?.url!==tab.url||meta.source_detail!==true)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:175:58:return",(null));
      }
      if(workerSettledDetail&&meta.source_summary_ready===false)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:177:64:return",(null));

      if(state==='NV'&&query.operation==='search'&&meta.source_search_empty!==true)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:179:83:return",(null));
      if(state==='NV'&&query.operation==='detail'&&meta.source_loading_visible!==false)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:180:87:return",(null));

      // Three original source views are three screenshot operations. Give only

      // a validated NV detail plan its per-page allowance; keep one-page and

      // other-state behavior, the original state expiry and a cleanup reserve.

      if(state==='NV'&&query.operation==='detail'&&!cancelled

          &&Array.isArray(meta.capture_views)&&meta.capture_views.length>=2&&meta.capture_views.length<=8

          &&meta.capture_views.every((view,index)=>view==='nv-'+index)) {

        const planned=Math.min(4500,Math.max(2500,1500*meta.capture_views.length),job.activeExpiresAt-started-500);

        if(planned>captureBudgetMs) {

          captureBudgetMs=planned;observed.budget_ms=planned;observed.required_pages=meta.capture_views.length;

          clearTimeout(timeoutId);timeoutId=setTimeout(expireCapture,Math.max(1,started+planned-Date.now()));

        }

      }

      // The pre-resize view count is not a readiness budget: the same record
      // can become one page after its original layout settles. Give a bound
      // detail the shared completion allowance, preserving the state deadline.
      if(boundNvDetail&&!cancelled) {
        const remaining=Math.min(20000-completionSpent,job.activeExpiresAt-started-500);
        if(remaining>captureBudgetMs) {
          captureBudgetMs=remaining;observed.budget_ms=remaining;
          clearTimeout(timeoutId);timeoutId=setTimeout(expireCapture,Math.max(1,started+remaining-Date.now()));
        }
      }

      // Selected summaries get a bounded readiness/capture window, not a
      // mandatory delay. The worker exits as soon as actual fields are stable.
      // Do not start a new debugger session after this NC capture expired.
      if(state==='NC'&&(cancelled||!alive()))return null;
      observed.phase='attach';await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:208:30:await",()=>(sampled('attach',()=>chrome.debugger.attach({tabId},'1.3'))));attached=true;

      if(cancelled || !alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:210:31:return",(null));

      // The selected Illinois record is already identity-bound above. Let its
      // original opening animation paint while our owned source is backgrounded.
      // No user-window activation, DOM/CSS rewriting, or verification interaction.
      if(ilDetail&&meta.source_detail===true&&alive()) {
        ilPaintActive=true;
        observed.phase='IL-detail-paint';
        await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:218:8:await",()=>(sampled('IL-detail-paint',()=>chrome.debugger.sendCommand({tabId},'Emulation.setFocusEmulationEnabled',{enabled:true}))));
        if(cancelled||!alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:219:31:return",(null));
      }

      observed.phase='layout';let layout=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:222:41:await",()=>(sampled('layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'))));

      if(state==='NV'){observed.width=layout.cssLayoutViewport?.clientWidth||0;observed.height=layout.cssLayoutViewport?.clientHeight||0;}

      if(boundNvDetail&&(layout.cssLayoutViewport?.clientWidth<1024||layout.cssLayoutViewport?.clientHeight<1000)) {
        // Render the state's own desktop layout in this owned capture target.
        // Preserve its content, selected-record binding, and existing time budget.
        const priorBinding=meta.source_binding,priorDocument=meta.document_id;
        job.snapshotViewportBusy=true;desktopViewport=true;
        observed.phase='NV-desktop-viewport';
        await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:232:8:await",()=>(sampled('NV-desktop-viewport',()=>chrome.debugger.sendCommand({tabId},'Emulation.setDeviceMetricsOverride',
          {width:Math.max(1024,layout.cssLayoutViewport.clientWidth),height:Math.max(1000,layout.cssLayoutViewport.clientHeight),deviceScaleFactor:0,mobile:false}))));
        if(cancelled||!alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:234:31:return",(null));
        meta=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:235:13:await",()=>(sampled('NV-desktop-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}))));
        layout=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:236:15:await",()=>(sampled('NV-desktop-layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'))));
        if(cancelled||!alive()||meta?.url!==tab.url||meta.document_id!==priorDocument
          ||meta.source_binding!==priorBinding||meta.source_detail!==true||meta.source_loading_visible!==false)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:238:111:return",(null));
      }

      if(boundNvDetail) {
        // ORION animates its original layout after the existing viewport step.
        // Do not freeze a multi-view plan while that layout is still changing.
        // Keep the same identity, document, source pixels, allowance and deadline.
        const binding=meta.source_binding,documentId=meta.document_id;
        let previous=null,stable=0;
        observed.phase='NV-selected-detail-ready';
        while(!cancelled&&alive()&&Date.now()<started+captureBudgetMs-500) {
          const shape=Array.isArray(meta.source_view_shape)?JSON.stringify(meta.source_view_shape):null;
          stable=shape&&shape===previous?stable+1:0;previous=shape;
          if(stable>=2)break;
          await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:252:10:await",()=>(new Promise(resolve=>setTimeout(resolve,40))));
          meta=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:253:15:await",()=>(sampled('NV-detail-ready',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}))));
          if(meta?.url!==tab.url||meta.document_id!==documentId||meta.source_binding!==binding
            ||meta.source_detail!==true||meta.source_loading_visible!==false)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:255:77:return",(null));
        }
        if(stable<2||cancelled||!alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:257:41:return",(null));
        layout=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:258:15:await",()=>(sampled('NV-ready-layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'))));
      }

      if(((state==='TN'&&query.operation==='detail')||ilDetail)&&layout.cssLayoutViewport?.clientWidth<800) {

        // TN's financial column and IL's long selected record need the native desktop layout.

        // Ask Chrome to render that original desktop layout, not invented CSS.

        job.snapshotViewportBusy=true;desktopViewport=true;

        observed.phase='viewport';await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:269:34:await",()=>(chrome.debugger.sendCommand({tabId},'Emulation.setDeviceMetricsOverride',

          {width:1024,height:900,deviceScaleFactor:0,mobile:false})));

        if(cancelled||!alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:273:31:return",(null));

        observed.phase='settled-metadata';
        // This worker timer avoids hidden-page timer throttling. The three
        // subsequent original-view observations still prove stable paint.
        if(workerSettledDetail)await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:278:31:await",()=>(new Promise(resolve=>setTimeout(resolve,40))));
        meta=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:279:13:await",()=>(sampled('settled-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query,settle:!workerSettledDetail},{frameId:0}))));

        layout=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:281:15:await",()=>(chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics')));

        if(cancelled||!alive()||meta?.url!==tab.url||typeof meta.public_text!=='string'

          ||!meta.public_text.trim()||meta.public_text.length>20000

          ||/verify you are human|user validation required|just a moment|access denied/i.test(meta.public_text))return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:287:112:return",(null));

        if(meta.source_detail!==true)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:289:37:return",(null));

      }

      if(state==='AL'&&query.operation==='search'&&meta.source_grid_clipped===true) {
        const width=meta.source_grid_viewport_width,originalText=meta.public_text;
        if(!Number.isSafeInteger(width)||width<1024||width>1600)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:295:64:return",(null));
        job.snapshotViewportBusy=true;desktopViewport=true;
        observed.phase='viewport';await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:297:34:await",()=>(sampled('AL-grid-viewport',()=>chrome.debugger.sendCommand({tabId},'Emulation.setDeviceMetricsOverride',
          {width,height:900,deviceScaleFactor:0,mobile:false}))));
        if(cancelled||!alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:299:31:return",(null));
        observed.phase='settled-metadata';meta=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:300:47:await",()=>(sampled('AL-grid-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}))));
        layout=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:301:15:await",()=>(sampled('AL-grid-layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'))));
        try {observed.al_grid_check={url_same:meta?.url===tab.url,clipped:meta?.source_grid_clipped??null,
          text_same:meta?.public_text===originalText,text_length:typeof meta?.public_text==='string'?meta.public_text.length:null,
          viewport_width:meta?.source_viewport_width??null,requested_width:width,
          layout:layout?.cssLayoutViewport?[layout.cssLayoutViewport.pageX,layout.cssLayoutViewport.pageY,layout.cssLayoutViewport.clientWidth,layout.cssLayoutViewport.clientHeight]:null};}catch{}
        if(cancelled||!alive()||meta?.url!==tab.url||meta.source_grid_clipped!==false
          ||typeof meta.public_text!=='string'||meta.public_text!==originalText||!meta.public_text.trim()||meta.public_text.length>20000
          ||/verification failed|invalid verification|user validation required|access denied/i.test(meta.public_text))return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:304:118:return",(null));
      }

      // Short GA/NM/AL collector windows can repeat their first painted strip when
      // Chrome captures beyond the viewport. Fit the unchanged original page
      // inside one viewport, then capture that viewport once. No stitching.
      const nyRequiredDetail=state==='NY'&&Object.hasOwn(query,'orgID');
      if(nyRequiredDetail&&(!/^[0-9]{2}-[0-9]{2}-[0-9]{2}$/.test(query.orgID)
          ||meta.url!==P.NY+'/RegistrySearch/'+query.orgID
          ||!meta.public_text.includes(query.orgID)||typeof meta.document_id!=='string'))return null;
      // NC's short owned profile window produced repeated upper strips in
      // one native beyond-viewport image. Fit the same complete profile once.
      if(ncSelectedDetail&&(meta.url!==query.url||meta.source_detail!==true||!validBinding(meta)))return null;
      const ncBinding=ncSelectedDetail?meta.source_binding:null;
      const ncDocument=ncSelectedDetail?meta.document_id:null;
      const nmRequiredDetail=state==='NM'&&query.operation==='detail';
      const msRequiredDetail=state==='MS'&&query.operation==='detail';
      if(msRequiredDetail&&typeof diagnostic==='function')try {
        const c=layout?.cssContentSize,v=layout?.cssLayoutViewport;
        diagnostic('ms-capture-admission',job,JSON.stringify({
          detail_ready:meta.source_ms_detail_ready===true,summary_visible:meta.source_ms_summary_visible===true,
          content:c?[c.width,c.height]:null,viewport:v?[v.pageX,v.pageY,v.clientWidth,v.clientHeight]:null,
          text_length:meta.public_text.length,identifier:String(query.identifier||'').slice(0,40)
        }));
      } catch { /* Passive diagnostics must not change capture behavior. */ }
      if(msRequiredDetail&&meta.source_ms_detail_ready!==true)return null;
      if(msRequiredDetail&&(layout.cssLayoutViewport?.pageX||layout.cssLayoutViewport?.pageY)) {
        const prior=layout.cssLayoutViewport,originalText=meta.public_text;
        if(!Number.isFinite(prior.pageX)||!Number.isFinite(prior.pageY)||!alive()||cancelled)return null;
        msOriginalScroll=[prior.pageX,prior.pageY];observed.phase='MS-original-page-top';
        await sampled('MS-original-page-top',()=>chrome.debugger.sendCommand({tabId},'Runtime.evaluate',
          {expression:"window.scrollTo({left:0,top:0,behavior:'instant'})",returnByValue:true}));
        if(cancelled||!alive())return null;
        let fresh=await sampled('MS-top-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}));
        layout=await sampled('MS-top-layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'));
        try {observed.ms_top_check={url_same:fresh?.url===tab.url,text_same:fresh?.public_text===originalText,
          detail_ready:fresh?.source_ms_detail_ready===true,summary_visible:fresh?.source_ms_summary_visible===true,
          before_length:originalText.length,after_length:typeof fresh?.public_text==='string'?fresh.public_text.length:null,
          layout:layout?.cssLayoutViewport?[layout.cssLayoutViewport.pageX,layout.cssLayoutViewport.pageY,layout.cssLayoutViewport.clientWidth,layout.cssLayoutViewport.clientHeight]:null};}catch{}
        if(cancelled||!alive()||fresh?.url!==tab.url||fresh.public_text!==originalText||fresh.source_ms_detail_ready!==true)return null;
        meta=fresh;
        while((layout.cssLayoutViewport?.pageX||layout.cssLayoutViewport?.pageY)
            &&!cancelled&&alive()&&Date.now()<started+captureBudgetMs-500) {
          await new Promise(resolve=>setTimeout(resolve,40));
          await sampled('MS-settle-page-top',()=>chrome.debugger.sendCommand({tabId},'Runtime.evaluate',
            {expression:"window.scrollTo({left:0,top:0,behavior:'instant'})",returnByValue:true}));
          fresh=await sampled('MS-settle-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}));
          layout=await sampled('MS-settle-layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'));
          if(cancelled||!alive()||fresh?.url!==tab.url||fresh.public_text!==originalText
              ||fresh.source_ms_detail_ready!==true)return null;
          meta=fresh;
        }
      }

      // A wide, long NM record may exceed the existing image-area guard.
      // Reflow that same original document once at a bounded desktop width.
      // Retain all text, identity, fit, area, deadline and restoration guards.
      if(nmRequiredDetail) {
        const c=layout.cssContentSize,v=layout.cssLayoutViewport,w=meta.source_viewport_width;
        if(!c||!v||v.pageX||v.pageY||!Number.isInteger(w)||w<v.clientWidth||w>2400)return null;
        if(!Number.isInteger(meta.source_record_bottom)||meta.source_record_bottom<200)return null;
        const planWidth=Math.ceil(Math.max(c.width,1000,w)),planHeight=meta.source_record_bottom;
        try {observed.nm_area_check={width:planWidth,height:planHeight,pixels:planWidth*planHeight};}catch{}
        const boundedWidth=(planWidth*planHeight>20000000&&planWidth>1280&&planHeight<=16000)
            ||(planHeight>16000&&planWidth<1280&&planWidth*planHeight<=20000000);
        if(boundedWidth||planWidth!==w) {
          const originalText=meta.public_text,originalDocument=meta.document_id;
          if(!Number.isFinite(c.width)||!Number.isFinite(c.height)||c.width<=0||c.height<=0||!alive()||cancelled)return null;
          desktopViewport=true;job.snapshotViewportBusy=true;observed.phase='NM-bounded-width';
          await sampled('NM-bounded-width',()=>chrome.debugger.sendCommand({tabId},'Emulation.setDeviceMetricsOverride',
            {width:boundedWidth?1280:planWidth,height:900,deviceScaleFactor:0,mobile:false}));
          if(cancelled||!alive())return null;
          const fresh=await sampled('NM-width-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}));
          layout=await sampled('NM-width-layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'));
          if(cancelled||!alive()||fresh?.url!==tab.url||fresh.public_text!==originalText
              ||fresh.document_id!==originalDocument||!Number.isInteger(fresh.source_record_bottom)||fresh.source_record_bottom<200)return null;
          meta=fresh;
        }
      }

      // One bounded desktop reflow for an observed inner horizontal scroller.
      // No source search, content rewrite, new window or allowance extension.
      if(nyRequiredDetail&&meta.source_horizontal_clipped===true&&meta.source_viewport_width<1280) {
        const originalText=meta.public_text,originalDocument=meta.document_id,originalLayoutText=meta.source_layout_text;
        if(typeof originalLayoutText!=='string'||!originalLayoutText.trim()||originalLayoutText.length>20000)return null;
        desktopViewport=true;job.snapshotViewportBusy=true;
        await sampled('NY-horizontal-width',()=>chrome.debugger.sendCommand({tabId},'Emulation.setDeviceMetricsOverride',
          {width:1280,height:900,deviceScaleFactor:0,mobile:false}));
        if(cancelled||!alive())return null;
        const fresh=await sampled('NY-width-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}));
        layout=await sampled('NY-width-layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'));
        // Passive bounded diagnostics for the existing width-transition guard.
        try {
          const before=String(originalLayoutText||''),after=String(fresh?.source_layout_text||'');
          let difference=0;while(difference<Math.min(before.length,after.length)&&before[difference]===after[difference])difference++;
          wfEvent(job,'snapshot.NY.width_binding','observed',{
            cancelled,owner_alive:alive(),same_url:fresh?.url===tab.url,
            same_document:fresh?.document_id===originalDocument,
            same_layout_text:fresh?.source_layout_text===originalLayoutText,
            horizontal_clipped:fresh?.source_horizontal_clipped??null,
            before_width:meta.source_viewport_width,after_width:fresh?.source_viewport_width??null,
            before_length:before.length,after_length:after.length,first_difference:difference,
            before_excerpt:before.slice(Math.max(0,difference-40),difference+160),
            after_excerpt:after.slice(Math.max(0,difference-40),difference+160)
          });
        } catch { /* Diagnostics cannot affect capture decisions. */ }
        if(cancelled||!alive()||fresh?.url!==tab.url||fresh.source_layout_text!==originalLayoutText
            ||fresh.document_id!==originalDocument||fresh.source_horizontal_clipped!==false)return null;
        meta=fresh;
      }

      const alRequiredGrid=state==='AL'&&query.operation==='search'&&meta.source_grid_clipped===false
        &&prepared?.kind==='al-completed-record'&&prepared.command_id===commandId&&P.sameQuery(prepared.query,query);
      let gaFullViewport=false;
      if(gaRequiredDetail||nmRequiredDetail||alRequiredGrid||msRequiredDetail||nyRequiredDetail||ncSelectedDetail) {
        const originalText=meta.public_text,content=layout.cssContentSize,view=layout.cssLayoutViewport;
        // Use the existing complete NY schema binding across responsive cards
        // and tables. Raw source text must still settle before the screenshot.
        const nyLayoutText=nyRequiredDetail&&typeof meta.source_layout_text==='string'
          &&meta.source_layout_text.trim()&&meta.source_layout_text.length<=20000?meta.source_layout_text:null;
        let nyFitObservations=0;
        if(!content||!view||view.pageX||view.pageY)return null;
        // Preserve the full source viewport width, including its scrollbar gutter.
        // Layout clientWidth excludes that gutter; reusing it shrinks the page.
        if((nmRequiredDetail||alRequiredGrid||nyRequiredDetail||ncSelectedDetail)&&(!Number.isInteger(meta.source_viewport_width)||meta.source_viewport_width<view.clientWidth||meta.source_viewport_width>2400))return null;
        const width=(nyRequiredDetail||ncSelectedDetail)?meta.source_viewport_width:Math.ceil(Math.max(content.width,nmRequiredDetail?1000:0,(nmRequiredDetail||alRequiredGrid||nyRequiredDetail)?meta.source_viewport_width:view.clientWidth)),height=nmRequiredDetail?meta.source_record_bottom:Math.ceil(Math.max(content.height+32,view.clientHeight));
        if(width<320||width>2400||height<200||height>(nmRequiredDetail?16000:nyRequiredDetail?20000000/width:3000)||width*height>20000000)return null;
        desktopViewport=true;job.snapshotViewportBusy=true;
        observed.phase=state+'-full-viewport';
        await sampled(state+'-full-viewport',()=>chrome.debugger.sendCommand({tabId},'Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:0,mobile:false}));
        // A bound MS detail can spend the existing completion reserve on its
        // first post-resize layout read. Stable text/geometry is still required
        // below before any image is admitted; no new viewport or query is added.
        if(msRequiredDetail&&!cancelled&&alive()
            &&Date.now()<started+captureBudgetMs&&started+captureBudgetMs-Date.now()<4000) {
          const extended=Math.min(16000-(observed.prior_capture_ms||0),job.activeExpiresAt-started-1000);
          if(extended>captureBudgetMs) {
            captureBudgetMs=extended;observed.budget_ms=extended;
            observed.completion_reserve=true;observed.reserve_trigger='first-layout-read';
            clearTimeout(timeoutId);timeoutId=setTimeout(expireCapture,Math.max(1,started+extended-Date.now()));
          }
        }
        let previous='',stable=0;
        while(!cancelled&&alive()&&Date.now()<started+captureBudgetMs-500) {
          const fresh=await sampled(state+'-full-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}));
          layout=await sampled(state+'-full-layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'));
          const c=layout.cssContentSize,v=layout.cssLayoutViewport;
          if(ncSelectedDetail&&(fresh?.source_detail!==true||fresh.source_binding!==ncBinding||fresh.document_id!==ncDocument))return null;
          const textSame=fresh?.public_text===originalText||(nyRequiredDetail&&nyLayoutText!==null
            &&typeof fresh?.public_text==='string'&&fresh.public_text.trim()&&fresh.public_text.length<=20000
            &&!/verify you are human|user validation required|just a moment|access denied/i.test(fresh.public_text)
            &&fresh.source_layout_text===nyLayoutText);
          if(ncSelectedDetail&&nyFitObservations++<3)try {
            wfEvent(job,'snapshot.NC.full_viewport_binding','observed',{
              same_url:fresh?.url===query.url,same_document:fresh?.document_id===ncDocument,
              same_profile:fresh?.source_binding===ncBinding,raw_text_same:fresh?.public_text===originalText,
              viewport:v?[v.clientWidth,v.clientHeight]:null,content:c?[c.width,c.height]:null,
              remaining_ms:Math.max(0,started+captureBudgetMs-Date.now())});
          } catch { /* Passive bounded geometry facts cannot alter capture. */ }
          if(nyRequiredDetail&&nyFitObservations++<3)try {
            wfEvent(job,'snapshot.NY.full_viewport_binding','observed',{
              same_url:fresh?.url===tab.url,same_document:fresh?.document_id===meta.document_id,
              raw_text_same:fresh?.public_text===originalText,
              same_source_fields:nyLayoutText!==null&&fresh?.source_layout_text===nyLayoutText,
              text_bound:!!textSame,viewport_origin:v?[v.pageX,v.pageY]:null,
              viewport:v?[v.clientWidth,v.clientHeight]:null,content:c?[c.width,c.height]:null,
              remaining_ms:Math.max(0,started+captureBudgetMs-Date.now())
            });
          } catch { /* Passive diagnostics cannot alter capture decisions. */ }
          if(fresh?.url!==tab.url||!textSame||(nyRequiredDetail&&fresh.document_id!==meta.document_id)||!c||!v||v.pageX||v.pageY)return null;
          const shape=JSON.stringify([c.width,c.height,v.clientWidth,v.clientHeight]);
          stable=(nyRequiredDetail?fresh.source_page_fits===true:c.width<=v.clientWidth&&(nmRequiredDetail?fresh.source_page_fits===true&&fresh.source_record_bottom===height:c.height<=v.clientHeight))&&shape===previous?stable+1:0;previous=shape;
          if(msRequiredDetail&&stable>=1&&!cancelled&&alive()
              &&Date.now()<started+captureBudgetMs&&started+captureBudgetMs-Date.now()<4000) {
            const extended=Math.min(16000-(observed.prior_capture_ms||0),job.activeExpiresAt-started-1000);
            if(extended>captureBudgetMs) {
              captureBudgetMs=extended;observed.budget_ms=extended;
              observed.completion_reserve=true;
              clearTimeout(timeoutId);timeoutId=setTimeout(expireCapture,Math.max(1,started+extended-Date.now()));
            }
          }
          if(stable>=2){meta=fresh;gaFullViewport=true;break;}
          await new Promise(resolve=>setTimeout(resolve,40));
        }
        if(!gaFullViewport||cancelled||!alive())return null;
      }

      const size=layout.cssContentSize;

      if(state==='NV'){observed.content_width=size?.width||0;observed.content_height=size?.height||0;}

      if(cancelled || !alive() || !size || size.width<=0 || size.height<=0

          || (nmRequiredDetail?layout.cssLayoutViewport.clientWidth*layout.cssLayoutViewport.clientHeight:size.width*size.height)>20000000)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:313:45:return",(null));

      const tnModal=state==='TN'&&query.operation==='detail'&&Array.isArray(meta.capture_views)

        &&meta.capture_views.length>=1&&meta.capture_views.length<=3&&meta.capture_views[0]==='top'

        &&new Set(meta.capture_views).size===meta.capture_views.length

        &&meta.capture_views.every(view=>['top','expiration','financial'].includes(view));

      const nvModal=state==='NV'&&(query.operation==='detail'||meta.source_search_empty===true)&&Array.isArray(meta.capture_views)

        &&meta.capture_views.length>=1&&meta.capture_views.length<=(query.operation==='detail'?8:3)

        &&meta.capture_views.every((view,index)=>view==='nv-'+index);

      if(state==='NV'&&!nvModal)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:329:32:return",(null));

      const ilModal=ilDetail&&Array.isArray(meta.capture_views)&&meta.capture_views.length>=1&&meta.capture_views.length<=3
        &&meta.capture_views[0]==='top'&&new Set(meta.capture_views).size===meta.capture_views.length
        &&meta.capture_views.every(view=>['top','expiration','financial'].includes(view));
      if(ilDetail&&!ilModal)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:334:28:return",(null));
      if(state==='TN'&&query.operation==='detail'&&!tnModal)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:335:60:return",(null));
      const modal=tnModal||nvModal||ilModal;

      const viewport=layout.cssLayoutViewport;

      if(modal&&(!viewport||viewport.clientWidth<=0||viewport.clientHeight<=0

        ||viewport.clientWidth*viewport.clientHeight>20000000))return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:342:63:return",(null));

      const images=[];
      let completedViews=0;

      const captureViews=modal?[...meta.capture_views]:[null];
      for(const view of captureViews) {

        if(cancelled||!alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:349:31:return",(null));

        if(view) {

          restoreModal=true;

          let changed;
          if(workerSettledDetail||boundNvDetail) {
            let previous=null,stable=0;
            // Preserve the half-second completion reserve inside the existing state expiry.
            const end=started+captureBudgetMs-500;
            let step='prepare';
            while(!cancelled&&alive()&&Date.now()<end) {
              changed=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:362:22:await",()=>(sampled('view:'+view,()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view,worker_step:step,...(boundNvDetail?{source_binding:meta.source_binding}:{})},{frameId:0}))));
              step='observe';
              if(state==='TN'&&(observed.view_observations||0)<4){observed.view_observations=(observed.view_observations||0)+1;try{diagnostic('source-snapshot-view',job,JSON.stringify({view,ready:changed?.view_ready===true,stable,probe:changed?.il_view_probe||null}));}catch{}}
              if(changed?.ok!==true||changed.view_protocol!=='worker-settle-1')return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:365:79:return",(null));
              const proof=JSON.stringify([changed.view_shape,changed.view_text]);
              stable=changed.view_ready===true&&proof===previous?stable+1:0;previous=proof;
              if(stable>=2)break;
              await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:369:14:await",()=>(new Promise(resolve=>setTimeout(resolve,40))));
            }
            if(ilDetail&&typeof diagnostic==='function')try {diagnostic('il-view-ready',job,JSON.stringify({view,stable,cancelled,alive:alive(),probe:changed?.il_view_probe||null}));} catch { /* Passive observation cannot discard evidence. */ }
            if(ilDetail) {
              const required=changed?.summary_views;
              if(!Array.isArray(required)||!['["top"]','["top","expiration"]'].includes(JSON.stringify(required)))return null;
              // The source can reflow after initial metadata. Capture every
              // currently required summary view within the unchanged budget.
              for(const requiredView of required)if(!captureViews.includes(requiredView))captureViews.push(requiredView);
            }
            observed.view_stable=stable;
            if(stable<2||cancelled||!alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:373:45:return",(null));
          } else {changed=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:374:26:await",()=>(sampled('view:'+view,()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view,...(boundNvDetail?{source_binding:meta.source_binding}:{})},{frameId:0}))));}

          if(state==='IL'&&changed?.il_view_observation) {
            const v=changed.il_view_observation;
            observed.il_view={view:String(v.view||'').slice(0,12),reason:String(v.reason||'').slice(0,40),
              samples:Number.isSafeInteger(v.samples)?Math.min(100,Math.max(0,v.samples)):null,
              stable:Number.isSafeInteger(v.stable)?Math.min(100,Math.max(0,v.stable)):null,
              opaque:typeof v.opaque==='boolean'?v.opaque:null,
              shape_changes:Number.isSafeInteger(v.shape_changes)?Math.min(100,Math.max(0,v.shape_changes)):null};
          }
          if(changed?.ok!==true||cancelled||!alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:384:53:return",(null));

        }

        if(ilPaintActive&&attached){await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:388:36:await",()=>(sampled('IL-paint-restored',()=>chrome.debugger.sendCommand({tabId},'Emulation.setFocusEmulationEnabled',{enabled:false}))));ilPaintActive=false;if(cancelled||!alive())return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:388:208:return",(null));}
        observed.phase='capture';const image=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:389:45:await",()=>(sampled('capture:'+images.length,()=>chrome.debugger.sendCommand({tabId},'Page.captureScreenshot',

          {format:'jpeg',quality:75,captureBeyondViewport:!modal&&!gaFullViewport,fromSurface:true,

            clip:(modal||(nmRequiredDetail||nyRequiredDetail||ncSelectedDetail)&&gaFullViewport)?{x:viewport.pageX||0,y:viewport.pageY||0,width:viewport.clientWidth,height:viewport.clientHeight,scale:1}:

              {x:0,y:0,width:size.width,height:size.height,scale:1}}))));

        if(state==='NM')wfEvent(job,'NM image validation','started',{image_characters:typeof image?.data==='string'?image.data.length:null});
        if(typeof image?.data!=='string'||image.data.length>4000000||!/^[A-Za-z0-9+/]+={0,2}$/.test(image.data))return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:397:112:return",(null));

        // A completed NM image still needs fresh identity/geometry validation.
        // Use only the unspent existing aggregate allowance for that final step;
        // do not admit late images or bypass any post-capture checks.
        if(nmRequiredDetail&&!cancelled&&alive()&&Date.now()<started+captureBudgetMs
            &&started+captureBudgetMs-Date.now()<3000) {
          const extended=Math.min(12000-(observed.prior_capture_ms||0),job.activeExpiresAt-started-1000);
          if(extended>captureBudgetMs) {
            captureBudgetMs=extended;observed.budget_ms=extended;
            observed.completion_reserve=true;observed.reserve_trigger='completed-image-postvalidation';
            clearTimeout(timeoutId);timeoutId=setTimeout(expireCapture,Math.max(1,started+extended-Date.now()));
          }
        }

        if(!images.includes(image.data))images.push(image.data);
        completedViews++;
        if(state==='NM')wfEvent(job,'NM image validation','returned');

        if(modal&&images.reduce((total,item)=>total+item.length,0)>3000000)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:402:75:return",(null));

      }

      // Illinois view targets can clamp to the same original scroll position.
      // Require every validated capture to complete; keep identical pixels once.
      if(modal&&(ilModal?completedViews:images.length)!==captureViews.length)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:408:83:return",(null));

      observed.phase='postvalidation';const after=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:410:50:await",()=>(sampled('post-tab',()=>chrome.tabs.get(tabId))));

      let afterMeta;

      if(state==='NV'&&query.operation==='detail'&&restoreModal) {

        // Reuse the existing bound restoration response for fresh validation.

        const restored=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:418:23:await",()=>(sampled('restore',()=>chrome.tabs.sendMessage(tabId,

          {action:'registry-snapshot-view',query,command_id:commandId,view:'restore',returnMetadata:true},{frameId:0}))));

        if(restored?.ok!==true)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:422:31:return",(null));

        restoreModal=false;afterMeta=restored.snapshot_metadata;

      }

      // Older admitted content scripts can still supply the original metadata

      // message. Missing fresh metadata never authorizes publication.

      if(!afterMeta)afterMeta=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:432:30:await",()=>(sampled('post-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}))));

      if(ncSelectedDetail&&(afterMeta?.source_detail!==true||afterMeta.source_binding!==ncBinding
          ||afterMeta.document_id!==ncDocument||afterMeta.source_page_fits!==true))return null;
      if(nyRequiredDetail&&afterMeta?.document_id!==meta.document_id)return null;
      if(ilDetail&&(!Array.isArray(afterMeta?.capture_views)||afterMeta.capture_views.some(view=>!captureViews.includes(view))))return null;
      if((nmRequiredDetail||nyRequiredDetail)&&gaFullViewport&&afterMeta?.source_page_fits!==true)return null;
      if(nmRequiredDetail&&afterMeta?.source_record_bottom!==meta.source_record_bottom)return null;
      if(msRequiredDetail&&(afterMeta?.source_ms_detail_ready!==true||afterMeta?.source_ms_summary_visible!==true))return null;
      if(state==='NV'&&typeof diagnostic==='function')diagnostic('source-snapshot-phase',job,JSON.stringify({operation:query.operation,phase:'postvalidation-check',alive:alive(),url_same:after.url===tab.url,document_same:afterMeta?.document_id===meta.document_id,body_same:afterMeta?.public_text===meta.public_text,binding_present:boundNvDetail,binding_same:afterMeta?.source_binding===meta.source_binding}));

      let ilHeadingLabelsOnly=false;
      if(ilDetail&&Array.isArray(meta.source_heading_texts)&&Array.isArray(afterMeta?.source_heading_texts)
        &&meta.source_heading_texts.length===afterMeta.source_heading_texts.length) {
        let additions=0;
        const sameHeadings=meta.source_heading_texts.every((value,index)=>{
          const next=afterMeta.source_heading_texts[index];
          if(value===next)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:442:26:return",(true));
          if(value===''&&next==='Empty heading'){additions++;return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:443:61:return",(true));}
          return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:444:10:return",(false));
        });
        // Three source-empty h4 slots gain only accessibility placeholder text.
        // Preserve all original record text, heading positions, image pixels and
        // existing name/credential/URL/generation/visibility/deadline checks.
        const lines=String(afterMeta?.public_text||'').split('\n');
        ilHeadingLabelsOnly=sameHeadings&&additions===3&&lines[0]!=='Empty heading'
          &&lines.filter(line=>line==='Empty heading').length===3
          &&lines.filter(line=>line!=='Empty heading').join('\n')===meta.public_text;
      }

      if(ilDetail&&typeof diagnostic==='function') {
        const beforeLines=String(meta.public_text||'').split(/\n/),afterLines=String(afterMeta?.public_text||'').split(/\n/);
        diagnostic('source-snapshot-phase',job,JSON.stringify({operation:'detail',phase:'il-postvalidation-check',alive:alive(),cancelled,
          tab_same:after.url===tab.url,url_same:afterMeta?.url===meta.url,body_same:afterMeta?.public_text===meta.public_text,
          detail:afterMeta?.source_detail===true,images:images.length,heading_labels_only:ilHeadingLabelsOnly,heading_changes:Array.isArray(meta.source_heading_texts)&&Array.isArray(afterMeta?.source_heading_texts)?meta.source_heading_texts.flatMap((v,i)=>v===afterMeta.source_heading_texts[i]?[]:[{index:i,before:v.slice(0,40),after:String(afterMeta.source_heading_texts[i]||'').slice(0,40)}]).slice(0,5):[],
          removed:beforeLines.filter(x=>!afterLines.includes(x)).join(' | ').slice(0,120),
          added:afterLines.filter(x=>!beforeLines.includes(x)).join(' | ').slice(0,120)}));
      }

      // Passive TN-only final-check facts. Keep each record below the existing
      // diagnostic cap; never change the capture decision or public source.
      if(state==='TN'&&query.operation==='detail'&&typeof diagnostic==='function')try {
        const beforeText=String(meta.public_text||''),afterText=String(afterMeta?.public_text||'');
        diagnostic('source-snapshot-phase',job,JSON.stringify({operation:'detail',phase:'tn-final-check',
          alive:alive(),cancelled,tab_same:after.url===tab.url,url_same:afterMeta?.url===meta.url,
          body_same:afterText===beforeText,detail:afterMeta?.source_detail===true,
          images:images.length,completed_views:completedViews,views:meta.capture_views,
          after_views:afterMeta?.capture_views,before_length:beforeText.length,after_length:afterText.length}));
        if(beforeText!==afterText) {
          let index=0;while(index<Math.min(beforeText.length,afterText.length)&&beforeText[index]===afterText[index])index++;
          diagnostic('source-snapshot-phase',job,JSON.stringify({operation:'detail',phase:'tn-text-difference',index,
            before:beforeText.slice(Math.max(0,index-50),index+130),after:afterText.slice(Math.max(0,index-50),index+130)}));
        }
      } catch { /* Observation failure cannot discard or authorize evidence. */ }

      // The IR source trace changed only the responsive Financials columns.
      // The requested evidence is the original identity/status/date summary.
      // Keep its complete text, including address/purpose and financial count,
      // byte-for-byte stable; never let a changed required field pass here.
      let tnSummaryOnly=false;
      if(state==='TN'&&query.operation==='detail'&&meta.source_summary_ready===true
        &&afterMeta?.source_summary_ready===true&&afterMeta.source_detail===true
        &&JSON.stringify(meta.capture_views)===JSON.stringify(afterMeta.capture_views)
        &&Array.isArray(meta.capture_views)&&meta.capture_views.length>0
        &&meta.capture_views.every(view=>['top','expiration'].includes(view))) {
        const summary=text=>{
          if(typeof text!=='string'||/verify you are human|user validation required|just a moment|access denied/i.test(text))return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:491:125:return",(null));
          const marks=[...text.matchAll(/\nFinancials \(\d+\)\n/g)];
          if(marks.length!==1||marks[0].index<1)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:493:48:return",(null));
          return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:494:10:return",(text.slice(0,marks[0].index+marks[0][0].length)));
        };
        const beforeSummary=summary(meta.public_text),afterSummary=summary(afterMeta.public_text);
        tnSummaryOnly=beforeSummary!==null&&beforeSummary===afterSummary;
      }

      if(state==='AL'&&desktopViewport&&afterMeta?.source_grid_clipped!==false)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:500:79:return",(null));
      if(usePrepared&&afterMeta?.document_id!==prepared.document_id)return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:501:68:return",(null));

      if(boundNvDetail&&(!validBinding(afterMeta)||typeof afterMeta.public_text!=='string'||!afterMeta.public_text.trim()||afterMeta.public_text.length>20000||afterMeta.document_id!==meta.document_id||afterMeta.source_binding!==meta.source_binding

        ||/verify you are human|user validation required|just a moment|access denied/i.test(afterMeta.public_text||'')))return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:505:120:return",(null));

      if(cancelled || !alive() || after.url!==tab.url || !images.length

          || afterMeta?.url!==meta.url || (!boundNvDetail&&!ilHeadingLabelsOnly&&!tnSummaryOnly&&afterMeta?.public_text!==meta.public_text)

          || ((ilDetail||state==='TN'&&query.operation==='detail')&&afterMeta.source_detail!==true)

          || (state==='NV'&&query.operation==='detail'&&(afterMeta.source_detail!==true||afterMeta.source_loading_visible!==false))

          || (state==='NV'&&query.operation==='search'&&afterMeta.source_search_empty!==true)

          )return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:517:11:return",(null));

      observed.phase='image-validated';

      // Keep the original command for all ownership/freshness checks above.
      // AL's one-time verification answer is transport-only: its completed
      // evidence and signed pending query intentionally contain public fields.
      const sourceQuery=state==='AL'?{state:'AL',operation:'search',name:query.name}:query;
      return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:525:6:return",(validatedResult={query:JSON.parse(JSON.stringify(sourceQuery)),source_url:tab.url,public_text:meta.public_text,

        image:images[0],...(images.length>1?{images}:{}),captured_at:Date.now()/1000,capture_ms:Date.now()-started}));

    } catch {observed.phase+='-error';return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:529:38:return",(null));}

    finally {

      if(restoreModal&&alive())try{await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:533:35:await",()=>(sampled('restore',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view:'restore'},{frameId:0}))));}catch{}

      if(desktopViewport&&attached)try{await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:535:39:await",()=>(chrome.debugger.sendCommand({tabId},'Emulation.clearDeviceMetricsOverride')));}catch{}
      if(msOriginalScroll&&attached&&alive())try {
        await sampled('MS-restore-scroll',()=>chrome.debugger.sendCommand({tabId},'Runtime.evaluate',
          {expression:`window.scrollTo({left:${msOriginalScroll[0]},top:${msOriginalScroll[1]},behavior:'instant'})`,returnByValue:true}));
      } catch { /* Owned target may have closed during cleanup. */ }
      if(ilPaintActive&&attached)try{await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:536:37:await",()=>(chrome.debugger.sendCommand({tabId},'Emulation.setFocusEmulationEnabled',{enabled:false})));}catch{}

      // A fully validated image is complete once its original view is restored.
      // Keep the capture lease until detach settles so a following capture
      // cannot attach while this old cleanup is still pending.
      if(workerSettledDetail&&desktopViewport)delete job.snapshotViewportBusy;
      if(workerSettledDetail&&validatedResult&&!cancelled&&alive()&&Date.now()-started<captureBudgetMs) {
        observed.phase='restored-image-validated';publishRestored(validatedResult);
      }
      if(attached)try{await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:545:22:await",()=>(sampled('detach',()=>chrome.debugger.detach({tabId}))));}catch{}
      // A timeout may have started a second detach. Its acknowledgement also
      // belongs to this capture and must settle before admitting another command.
      if(timeoutDetach)await timeoutDetach;
      if(workerSettledDetail||ncSelectedDetail)delete job.ilTnSnapshotCleanupBusy;

      if(desktopViewport)delete job.snapshotViewportBusy;
      if(state==='AL')delete job.alSnapshotCaptureBusy;
      delete job.snapshotCleanupBusy;
      if(job.snapshotCleanupCompletion===cleanupCompletion)delete job.snapshotCleanupCompletion;
      settleCleanup();

    }

  };

  // A bound NV detail may use up to10s, bounded by the

  // original state expiry; late images remain unpublished. Other captures1.5s.

  const timed=new Promise(resolve=>{expireCapture=()=>{



    // All admitted images have already passed fresh identity, record, viewport,
    // command and deadline binding before entering finally. Slow cleanup must
    // not erase completed evidence. The original capture lease stays busy until
    // restoration and detach actually settle.
    // Keep all cleanup ownership locks until the original cleanup settles.
    const completedImage=validatedResult&&alive()
      &&validatedResult.capture_ms<captureBudgetMs ? validatedResult : null;
    cancelled=true;observed.phase+=completedImage?'-cleanup-timeout-image-retained':'-timeout';

    // Detach the original owned target on timeout so Chrome also drops its

    // session viewport override. Late callbacks cannot publish a source image.

    if(state==='NV'&&restoreModal&&attached)

      chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view:'restore'},{frameId:0}).catch(()=>{});

    // AL's next query must not inherit an attachment left by a timed-out
    // screenshot. Clear this invocation's ownership before detaching, so its
    // late finally cannot detach a later capture. The busy flag remains until
    // the old Chrome operation has actually settled.
    if(state==='AL'&&attached){attached=false;timeoutDetach=chrome.debugger.detach({tabId}).catch(()=>{});}
    else if((desktopViewport||ilDetail||state==='NV')&&attached)timeoutDetach=chrome.debugger.detach({tabId}).catch(()=>{});

    resolve(completedImage);

  };timeoutId=setTimeout(expireCapture,captureBudgetMs);});

  let captured=null;

  try{captured=await wfAwait(job,"state-snapshot-worker.js:captureStateSnapshot:586:15:await",()=>(Promise.race([operation(),timed,...(workerSettledDetail?[restoredImage]:[])])));if(captured&&workerSettledDetail&&!alive())captured=null;if(captured){job.snapshotCaptures=(job.snapshotCaptures||0)+1;observed.phase='published';}return wfReturn(job,"state-snapshot-worker.js:captureStateSnapshot:586:246:return",(captured));}

  finally{

    if(completionRequired)job.requiredCaptureSpentByState[state]=completionSpent+Math.max(0,Date.now()-started);
    if(state==='NY')job.nySnapshotSpentMs=(Number.isFinite(job.nySnapshotSpentMs)?Math.max(0,job.nySnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    if(state==='MS')job.msSnapshotSpentMs=(Number.isFinite(job.msSnapshotSpentMs)?Math.max(0,job.msSnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    if(state==='NM')job.nmSnapshotSpentMs=(Number.isFinite(job.nmSnapshotSpentMs)?Math.max(0,job.nmSnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    if(state==='IL')job.ilSnapshotSpentMs=(Number.isFinite(job.ilSnapshotSpentMs)?Math.max(0,job.ilSnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    if(state==='TN')job.tnSnapshotSpentMs=(Number.isFinite(job.tnSnapshotSpentMs)?Math.max(0,job.tnSnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    if(gaRequiredDetail)job.gaDetailSnapshotSpentMs=(Number.isFinite(job.gaDetailSnapshotSpentMs)?Math.max(0,job.gaDetailSnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    if(gaRequiredDetail)job.gaDetailSnapshotSpentByRecord[gaDetailKey]=(job.gaDetailSnapshotSpentByRecord[gaDetailKey]||0)+Math.max(0,Date.now()-started);
    if(state==='AL')job.alSnapshotSpentMs=(Number.isFinite(job.alSnapshotSpentMs)?Math.max(0,job.alSnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    if(state==='NC')job.ncSnapshotSpentMs=(Number.isFinite(job.ncSnapshotSpentMs)?Math.max(0,job.ncSnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    clearTimeout(timeoutId);trace();

    if(typeof diagnostic==='function')diagnostic('source-snapshot',job,JSON.stringify({

      operation:query.operation||(['GA','IL'].includes(job.registryState)&&Object.hasOwn(query,'identifier')?'detail':'search'),capture_ms:Math.max(0,Date.now()-started),

      saved:!!captured,pages:captured?(captured.images?.length||1):0}));

  }

}
