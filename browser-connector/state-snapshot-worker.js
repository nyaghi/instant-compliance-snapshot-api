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
    if(['NC','GA','IL','AL'].includes(job.registryState)&&typeof diagnostic==='function')try {
      diagnostic('source-snapshot-phase',job,JSON.stringify({operation:query.operation||(['GA','IL'].includes(job.registryState)&&Object.hasOwn(query,'identifier')?'detail':'search'),...observed}));
    } catch { /* Observation cannot invalidate an original screenshot. */ }
  };

  const ilDetail=job.registryState==='IL'&&Object.hasOwn(query,'identifier');
  if(job.registryState==='IL'&&!ilDetail&&(job.snapshotCaptures||0)>=3){observed.phase='detail-slot-reserved';trace();return null;}
  if(!alive() || job.snapshotViewportBusy || (job.registryState==='AL'&&job.alSnapshotCaptureBusy) || !chrome.debugger || (job.snapshotCaptures||0)>=4

      || job.activeExpiresAt-Date.now()<4000){observed.phase='entry-rejected';trace();return null;}

  const state=job.registryState;
  if(state==='AL')job.alSnapshotCaptureBusy=true;

  let captureBudgetMs=state==='NV'&&query.operation==='detail'?2500:1500;
  if(state==='NC') {
    // Chrome attach can start late in a full-state run. Use at most3s for one
    // original image, at most6s of active optional capture time per NC job,
    // and preserve the existing state expiry plus a1s completion reserve.
    const spent=Number.isFinite(job.ncSnapshotSpentMs)?Math.max(0,job.ncSnapshotSpentMs):0;
    const remaining=Math.max(0,6000-spent);
    if(remaining<1000){observed.phase='capture-budget-exhausted';trace();return null;}
    captureBudgetMs=Math.min(3000,remaining,job.activeExpiresAt-started-1000);
    observed.prior_capture_ms=spent;
  }


  const gaRequiredDetail=state==='GA'&&Object.hasOwn(query,'identifier');
  if(gaRequiredDetail) {
    const spent=Number.isFinite(job.gaDetailSnapshotSpentMs)?Math.max(0,job.gaDetailSnapshotSpentMs):0;
    const remaining=Math.max(0,6000-spent);
    if(remaining<1000){observed.phase='detail-capture-budget-exhausted';trace();return null;}
    captureBudgetMs=Math.min(3000,remaining,job.activeExpiresAt-started-1000);
    observed.prior_capture_ms=spent;
  }
  if(['NV','NC','GA','IL','AL'].includes(state)){observed.budget_ms=captureBudgetMs;observed.steps=[];}

  function sampled(label,operation) {

    if(state==='NC'||state==='GA'||state==='IL'||state==='AL') {
      const begin=Date.now();observed.waiting=label;observed.wait_started_ms=begin-started;
      const finished=()=>{
        if(observed.steps.length<20)observed.steps.push({api:label,ms:Math.max(0,Date.now()-begin)});
        if(observed.waiting===label)delete observed.waiting;
      };
      // Issue the same API immediately; observation adds no timer or request.
      try {return Promise.resolve(operation()).finally(finished);}
      catch(error){finished();throw error;}
    }
    if(state!=='NV')return operation();

    const begin=Date.now();observed.waiting=label;observed.wait_started_ms=begin-started;

    return Promise.resolve().then(operation).finally(()=>{

      if(observed.steps.length<20)observed.steps.push({api:label,ms:Math.max(0,Date.now()-begin)});

      if(observed.waiting===label)delete observed.waiting;

    });

  }



  const allowed=state==='NY' ? P.NY : registryOrigin(state);

  let attached=false, cancelled=false, timeoutId,expireCapture,restoreModal=false,desktopViewport=false;

  const operation=async()=>{

    try {

      observed.phase='tab';const tab=await sampled('tab',()=>chrome.tabs.get(tabId));

      if(!alive() || new URL(tab.url).origin!==allowed)return null;

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

        :await sampled('metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}));

      if(!alive() || meta?.url!==tab.url || typeof meta.public_text!=='string'

          || !meta.public_text.trim() || meta.public_text.length>20000

          || /verify you are human|user validation required|just a moment|access denied/i.test(meta.public_text))return null;

      if(state==='NV'){
        observed.detail=meta?.source_detail===true;observed.fields_visible=meta?.source_fields_visible===true;observed.visible=meta?.source_visible===true;
        if(query.operation==='detail')observed.loader_clear=meta.source_loading_visible===false;
        const waited=prepared?.paint_readiness?.wait_ms;
        if(Number.isFinite(waited)&&waited>=0&&waited<=45000)observed.paint_wait_ms=waited;
      }

      const boundNvDetail=state==='NV'&&query.operation==='detail'&&validBinding(meta);

      observed.phase='identity';if((ilDetail||['TN','NV'].includes(state)&&query.operation==='detail')&&meta.source_detail!==true)return null;

      if(state==='NV'&&query.operation==='search'&&meta.source_search_empty!==true)return null;
      if(state==='NV'&&query.operation==='detail'&&meta.source_loading_visible!==false)return null;

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

      observed.phase='attach';await sampled('attach',()=>chrome.debugger.attach({tabId},'1.3'));attached=true;

      if(cancelled || !alive())return null;

      observed.phase='layout';let layout=await sampled('layout',()=>chrome.debugger.sendCommand({tabId},'Page.getLayoutMetrics'));

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

      const nvModal=state==='NV'&&(query.operation==='detail'||meta.source_search_empty===true)&&Array.isArray(meta.capture_views)

        &&meta.capture_views.length>=1&&meta.capture_views.length<=(query.operation==='detail'?8:3)

        &&meta.capture_views.every((view,index)=>view==='nv-'+index);

      if(state==='NV'&&!nvModal)return null;

      const ilModal=ilDetail&&Array.isArray(meta.capture_views)&&meta.capture_views.length>=1&&meta.capture_views.length<=3
        &&meta.capture_views[0]==='top'&&new Set(meta.capture_views).size===meta.capture_views.length
        &&meta.capture_views.every(view=>['top','expiration','financial'].includes(view));
      if(ilDetail&&!ilModal)return null;
      const modal=tnModal||nvModal||ilModal;

      const viewport=layout.cssLayoutViewport;

      if(modal&&(!viewport||viewport.clientWidth<=0||viewport.clientHeight<=0

        ||viewport.clientWidth*viewport.clientHeight>20000000))return null;

      const images=[];

      for(const view of modal?meta.capture_views:[null]) {

        if(cancelled||!alive())return null;

        if(view) {

          restoreModal=true;

          const changed=await sampled('view:'+view,()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view,...(boundNvDetail?{source_binding:meta.source_binding}:{})},{frameId:0}));

          if(changed?.ok!==true||cancelled||!alive())return null;

        }

        observed.phase='capture';const image=await sampled('capture:'+images.length,()=>chrome.debugger.sendCommand({tabId},'Page.captureScreenshot',

          {format:'jpeg',quality:75,captureBeyondViewport:!modal,fromSurface:true,

            clip:modal?{x:viewport.pageX||0,y:viewport.pageY||0,width:viewport.clientWidth,height:viewport.clientHeight,scale:1}:

              {x:0,y:0,width:size.width,height:size.height,scale:1}}));

        if(typeof image?.data!=='string'||image.data.length>4000000||!/^[A-Za-z0-9+/]+={0,2}$/.test(image.data))return null;

        if(!images.includes(image.data))images.push(image.data);

        if(modal&&images.reduce((total,item)=>total+item.length,0)>3000000)return null;

      }

      if(modal&&images.length!==meta.capture_views.length)return null;

      observed.phase='postvalidation';const after=await sampled('post-tab',()=>chrome.tabs.get(tabId));

      let afterMeta;

      if(state==='NV'&&query.operation==='detail'&&restoreModal) {

        // Reuse the existing bound restoration response for fresh validation.

        const restored=await sampled('restore',()=>chrome.tabs.sendMessage(tabId,

          {action:'registry-snapshot-view',query,command_id:commandId,view:'restore',returnMetadata:true},{frameId:0}));

        if(restored?.ok!==true)return null;

        restoreModal=false;afterMeta=restored.snapshot_metadata;

      }

      // Older admitted content scripts can still supply the original metadata

      // message. Missing fresh metadata never authorizes publication.

      if(!afterMeta)afterMeta=await sampled('post-metadata',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-metadata',query},{frameId:0}));

      if(state==='NV'&&typeof diagnostic==='function')diagnostic('source-snapshot-phase',job,JSON.stringify({operation:query.operation,phase:'postvalidation-check',alive:alive(),url_same:after.url===tab.url,document_same:afterMeta?.document_id===meta.document_id,body_same:afterMeta?.public_text===meta.public_text,binding_present:boundNvDetail,binding_same:afterMeta?.source_binding===meta.source_binding}));

      if(usePrepared&&afterMeta?.document_id!==prepared.document_id)return null;

      if(boundNvDetail&&(!validBinding(afterMeta)||typeof afterMeta.public_text!=='string'||!afterMeta.public_text.trim()||afterMeta.public_text.length>20000||afterMeta.document_id!==meta.document_id||afterMeta.source_binding!==meta.source_binding

        ||/verify you are human|user validation required|just a moment|access denied/i.test(afterMeta.public_text||'')))return null;

      if(cancelled || !alive() || after.url!==tab.url || !images.length

          || afterMeta?.url!==meta.url || (!boundNvDetail&&afterMeta?.public_text!==meta.public_text)

          || ((ilDetail||state==='TN'&&query.operation==='detail')&&afterMeta.source_detail!==true)

          || (state==='NV'&&query.operation==='detail'&&(afterMeta.source_detail!==true||afterMeta.source_loading_visible!==false))

          || (state==='NV'&&query.operation==='search'&&afterMeta.source_search_empty!==true)

          )return null;

      observed.phase='image-validated';

      // Keep the original command for all ownership/freshness checks above.
      // AL's one-time verification answer is transport-only: its completed
      // evidence and signed pending query intentionally contain public fields.
      const sourceQuery=state==='AL'?{state:'AL',operation:'search',name:query.name}:query;
      return {query:JSON.parse(JSON.stringify(sourceQuery)),source_url:tab.url,public_text:meta.public_text,

        image:images[0],...(images.length>1?{images}:{}),captured_at:Date.now()/1000,capture_ms:Date.now()-started};

    } catch {observed.phase+='-error';return null;}

    finally {

      if(restoreModal&&alive())try{await sampled('restore',()=>chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view:'restore'},{frameId:0}));}catch{}

      if(desktopViewport&&attached)try{await chrome.debugger.sendCommand({tabId},'Emulation.clearDeviceMetricsOverride');}catch{}

      if(attached)try{await sampled('detach',()=>chrome.debugger.detach({tabId}));}catch{}

      if(desktopViewport)delete job.snapshotViewportBusy;
      if(state==='AL')delete job.alSnapshotCaptureBusy;

    }

  };

  // A validated NV detail plan may use1.5s/page (max4.5s), bounded by the

  // original state expiry; late images remain unpublished. Other captures1.5s.

  const timed=new Promise(resolve=>{expireCapture=()=>{



    cancelled=true;observed.phase+='-timeout';

    // Detach the original owned target on timeout so Chrome also drops its

    // session viewport override. Late callbacks cannot publish a source image.

    if(state==='NV'&&restoreModal&&attached)

      chrome.tabs.sendMessage(tabId,{action:'registry-snapshot-view',query,command_id:commandId,view:'restore'},{frameId:0}).catch(()=>{});

    // AL's next query must not inherit an attachment left by a timed-out
    // screenshot. Clear this invocation's ownership before detaching, so its
    // late finally cannot detach a later capture. The busy flag remains until
    // the old Chrome operation has actually settled.
    if(state==='AL'&&attached){attached=false;chrome.debugger.detach({tabId}).catch(()=>{});}
    else if((desktopViewport||state==='NV')&&attached)chrome.debugger.detach({tabId}).catch(()=>{});

    resolve(null);

  };timeoutId=setTimeout(expireCapture,captureBudgetMs);});

  let captured=null;

  try{captured=await Promise.race([operation(),timed]);if(captured){job.snapshotCaptures=(job.snapshotCaptures||0)+1;observed.phase='published';}return captured;}

  finally{

    if(gaRequiredDetail)job.gaDetailSnapshotSpentMs=(Number.isFinite(job.gaDetailSnapshotSpentMs)?Math.max(0,job.gaDetailSnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    if(state==='NC')job.ncSnapshotSpentMs=(Number.isFinite(job.ncSnapshotSpentMs)?Math.max(0,job.ncSnapshotSpentMs):0)+Math.max(0,Date.now()-started);
    clearTimeout(timeoutId);trace();

    if(typeof diagnostic==='function')diagnostic('source-snapshot',job,JSON.stringify({

      operation:query.operation||(['GA','IL'].includes(job.registryState)&&Object.hasOwn(query,'identifier')?'detail':'search'),capture_ms:Math.max(0,Date.now()-started),

      saved:!!captured,pages:captured?(captured.images?.length||1):0}));

  }

}
