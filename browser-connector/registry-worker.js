/* Public-registry transport in the existing connector; no independent runtime. */
const registryOrigin = state => ({IL:"https://charitable.illinoisattorneygeneral.gov",GA:"https://verify.sos.ga.gov",AL:"https://ago.igovsolution.net",NC:"https://www.sosnc.gov",NV:"https://orion.nv.gov",TN:"https://tncab.tnsos.gov",NM:"https://secure.nmdoj.gov",MS:"https://charities.sos.ms.gov"})[state];
const registryStart = state => registryOrigin(state) + ({IL:"/search",GA:"/verification/Search.aspx?facility=Y",AL:"/online/Lookups/Business.aspx",NC:"/online_services/search/by_title/search_charities",NV:"/portal/public/#/public/nvsos/en/CaseXscreen?screen=external-GenericFilingsSearch&tabRoute=business",TN:"/portal/registered-charities-search",NM:"/CharitySearch/",MS:"/online/portal/ch/page/charities-search/Portal.aspx"})[state];
function registryTrialLayout(origin) {
  const source=new URL(origin.url);
  if(!P.TRIAL_ORIGIN || source.origin!==P.TRIAL_ORIGIN
      || !['/','/connector/final-four-validation.html'].includes(source.pathname))return '';
  if(source.pathname==='/connector/final-four-validation.html') {
    const requested=source.searchParams.get('collector_layout');
    if(requested==='visible')return 'visible'; // Preserve the four-state comparison.
    if(requested && requested!=='coordinated')return '';
  }
  return 'coordinated';
}
async function registryTrialWindowOptions(job, origin) {
  const options={type:'normal',focused:false};
  // Active tabs can still be hidden when their windows cover one another.
  // Keep owned trial collectors disjoint; never move the user's source window.
  const layout=registryTrialLayout(origin);
  if(!layout)return options;
  const slot=(layout==='visible'?['NV','NY','IL','NC']:['NV','NY','IL','NC','TN']).indexOf(job.registryState);
  if(slot<0)return options;
  let bounds;
  try { bounds=await chrome.windows.get(origin.windowId); }
  catch(error) { if(layout==='visible')throw error;return options; }
  // Existing full-size layouts stay unchanged. The ordinary trial may be
  // launched from a small or minimized window; use its actual display work area
  // rather than silently creating overlapping, unfocused collectors.
  const usable=b=>['left','top','width','height'].every(k=>Number.isFinite(b?.[k]))
    && b.width>=1080 && b.height>=700 && b.width<=16384 && b.height<=16384;
  if(layout==='coordinated' && (bounds?.state==='minimized' || !usable(bounds))) {
    let timer;
    try {
      const display=await Promise.race([
        chrome.tabs.sendMessage(origin.id,{action:'trial-collector-display'},{frameId:0}),
        new Promise(resolve=>{timer=setTimeout(()=>resolve(null),Math.max(1,Math.min(250,job.activeExpiresAt-Date.now())));})
      ]);
      if(usable(display) && Math.abs(display.left)<=65536 && Math.abs(display.top)<=65536)
        bounds={...display,state:'normal'};
    } catch {} finally {clearTimeout(timer);}
  }
  if(!['left','top','width','height'].every(k=>Number.isFinite(bounds?.[k]))
      || bounds.width<1080 || bounds.height<700 || bounds.state==='minimized') {
    if(layout!=='visible')return options;
    throw new Error('NY_CONNECTOR_VISIBLE_LAYOUT_UNAVAILABLE');
  }
  if(job.closed || Date.now()>=job.activeExpiresAt)throw new Error('NY_CONNECTOR_INTERRUPTED');
  const current=await chrome.tabs.get(origin.id);
  if(current.windowId!==origin.windowId || current.url!==origin.url)
    throw new Error('NY_CONNECTOR_VISIBLE_LAYOUT_UNAVAILABLE');
  const columns=layout==='visible'?2:3;
  const width=Math.floor((bounds.width-8*(columns+1))/columns),height=Math.floor((bounds.height-24)/2);
  return {...options,focused:true,state:'normal',width,height,
    left:bounds.left+8+(slot%columns)*(width+8),top:bounds.top+8+Math.floor(slot/columns)*(height+8)};
}
async function registryCreateOwnedTab(job,url,origin) {
  let tab;
  if(P.TRIAL_ORIGIN && job.registryState==='NV' && job.nvSourceInitiallyMinimized===undefined) {
    try {job.nvSourceInitiallyMinimized=(await chrome.windows.get(origin.windowId)).state==='minimized';}
    catch {job.nvSourceInitiallyMinimized=false;}
  }
  // Tennessee also needs its own visible document for Kendo modal transitions.
  // The mature connector and unrelated trial states retain their existing path.
  if(P.TRIAL_ORIGIN && (['NV','NY','IL','NC'].includes(job.registryState)
      || job.registryState==='TN'&&registryTrialLayout(origin)==='coordinated') && new URL(origin.url).origin===P.TRIAL_ORIGIN){
    const window=await chrome.windows.create({url,...await registryTrialWindowOptions(job,origin)});
    tab=window?.tabs?.[0];
    if(!Number.isInteger(tab?.id))throw new Error('NY_CONNECTOR_INCOMPLETE');
  } else tab=await chrome.tabs.create({windowId:origin.windowId,url,active:false});
  job.tab=tab.id;owned.add(tab.id);await saveRuntime();
}
async function registryTennesseeOwnedWindow(tab,source) {
  if(!owned.has(tab.id) || tab.url!==registryStart('TN'))return false;
  if(tab.windowId===source.windowId)return true; // Existing same-window sessions.
  const siblings=await chrome.tabs.query({windowId:tab.windowId});
  return siblings.length===1 && siblings[0].id===tab.id && tab.active;
}
async function registryExposeReusedNyTab(job, origin) {
  // The layout creates windows in front, but a retained NY or TN page
  // can be covered when the validation page is brought forward for another
  // run. Expose only its isolated window; preserve the document and session.
  if(!P.TRIAL_ORIGIN || !['NY','TN'].includes(job.registryState) || job.closed
      || Date.now()>=job.activeExpiresAt || !owned.has(job.tab))return false;
  try {
    const layout=registryTrialLayout(origin);
    if(!layout)return false;
    const tab=await chrome.tabs.get(job.tab),source=await chrome.tabs.get(origin.id);
    if(!(job.registryState==='NY'?nyRegistryPage(tab.url):tab.url===registryStart('TN')) || !tab.active || tab.windowId===source.windowId
        || source.windowId!==origin.windowId || source.url!==origin.url)return false;
    const siblings=await chrome.tabs.query({windowId:tab.windowId});
    if(siblings.length!==1 || siblings[0].id!==tab.id || !siblings[0].active
        || siblings[0].url!==tab.url || job.closed || Date.now()>=job.activeExpiresAt
        || job.tab!==tab.id || !owned.has(tab.id))return false;
    const placement=layout==='coordinated'?await registryTrialWindowOptions(job,origin):{focused:true};
    if(!placement.focused)return false;
    const {type,...update}=placement;
    const latest=await chrome.tabs.get(tab.id);
    if(job.closed || Date.now()>=job.activeExpiresAt || !owned.has(tab.id)
        || latest.windowId!==tab.windowId || latest.url!==tab.url || !latest.active)return false;
    await chrome.windows.update(tab.windowId,update);
    diagnostic(job.registryState.toLowerCase()+'-reuse-visible',job,'same owned window and verified document');
    return true;
  } catch { return false; } // No extra request or recovery when focus is unavailable.
}
async function registryNevadaVisibleSnapshot(job) {
  if (!P.TRIAL_ORIGIN || job.registryState!=='NV' || job.nvVisibilityAttempted || !owned.has(job.tab)) return null;
  try {
    const tab=await chrome.tabs.get(job.tab), source=await chrome.tabs.get(job.sender.tab.id);
    let coordinatedPlacement=null;
    if(tab.active && tab.windowId!==source.windowId && registryTrialLayout(source)==='coordinated') {
      const planned=await registryTrialWindowOptions(job,source),actual=await chrome.windows.get(tab.windowId);
      // Chrome may clamp a small collector to its minimum window size. The
      // planned footprint is still valid for our isolated window; exact old
      // coordinates must not disable bounded visibility recovery.
      if(planned.focused){const {type,...placement}=planned;coordinatedPlacement=placement;}
      if(planned.focused && ['left','top','width','height'].every(k=>actual[k]===planned[k])) {
        // Matching coordinates do not prove that another application/window
        // has not covered this document. Confirm visibility in the page.
        let state,timer;
        try {state=await Promise.race([
          chrome.tabs.sendMessage(tab.id,{action:'registry-ready'},{frameId:0}),
          new Promise(resolve=>{timer=setTimeout(()=>resolve(null),Math.max(1,Math.min(250,job.activeExpiresAt-Date.now())));})
        ]);} catch {} finally {clearTimeout(timer);}
        if(state?.page_visibility==='visible') {job.nvVisibilityOutcome='coordinated_window';return null;}
        const {type,...placement}=planned;coordinatedPlacement=placement;
      }
    }
    if (!tab.active && tab.windowId===source.windowId && new URL(source.url).origin===P.TRIAL_ORIGIN)
      return (await chrome.tabs.query({active:true,windowId:tab.windowId}))[0]||null;
    if (tab.active && tab.windowId!==source.windowId && new URL(source.url).origin===P.TRIAL_ORIGIN) {
      const focus=await chrome.windows.getLastFocused();
      const prior=(await chrome.tabs.query({active:true,windowId:focus.id}))[0];
      if(focus.focused && focus.id===tab.windowId){job.nvVisibilityOutcome='already_foreground';return null;}
      // getLastFocused can describe a stale, unrelated tab while Chrome is
      // not foreground at all. An explicit trial may expose its own isolated
      // collector once in that case, without touching/restoring that old tab.
      const initialMinimized=job.nvSourceInitiallyMinimized===true
        && (await chrome.windows.get(source.windowId)).state==='minimized';
      const inactiveBrowser=(focus.focused===false||initialMinimized) && prior?.active===true
        && !job.nvInactiveBrowserActivationUsed;
      if(!registryNevadaOwnedForeground(prior,source) && !inactiveBrowser){
        job.nvVisibilityOutcome='user_window_or_tab';
        registryNevadaDiagnostic(job,'visibility-snapshot-refused',{
          prior_present:!!prior,prior_active:prior?.active===true,prior_owned:!!prior&&owned.has(prior.id),
          prior_is_source:prior?.id===source.id,browser_focused:focus.focused===true,
          coordinated_placement:!!coordinatedPlacement,inactive_activation_used:!!job.nvInactiveBrowserActivationUsed});
        return null;
      }
      // Starting an explicit trial already creates focused collector windows.
      // Give this owned stalled window the same single bounded activation even
      // when the initiating application (e.g. Codex) remains foreground. Keep
      // the captured focus state so a subsequent browser/user switch cancels it.
      job.nvVisibilityOutcome=focus.focused?'eligible_separate_window':'eligible_owned_browser_activation';
      return {mode:'window',id:prior.id,windowId:prior.windowId,url:prior.url,
        nvWindowId:tab.windowId,sourceWindowId:source.windowId,sourceUrl:source.url,
        browserFocused:focus.focused===true,coordinatedPlacement,
        sourceWasMinimized:initialMinimized,
        inactiveBrowser:inactiveBrowser&&!registryNevadaOwnedForeground(prior,source)};
    }
  } catch {job.nvVisibilityOutcome='snapshot_unavailable';}
  return null;
}
function registryNevadaOwnedForeground(tab,source) {
  if(!tab?.active)return false;
  if(tab.id===source.id)return tab.windowId===source.windowId&&tab.url===source.url;
  if(!owned.has(tab.id))return false;
  try {return nyRegistryPage(tab.url)||['IL','GA','AL','NC','NV','TN','NM','MS'].some(s=>new URL(tab.url).origin===registryOrigin(s));}
  catch {return false;}
}
function registryNevadaDiagnostic(job, phase, detail={}) {
  if(!P.TRIAL_ORIGIN || job.registryState!=='NV' || job.closed || !job.pending
      || !owned.has(job.tab) || (job.nvDiagnosticCount||0)>=96)return;
  job.nvDiagnosticCount=(job.nvDiagnosticCount||0)+1;
  post(job,{id:job.pending,progress:true,nv_diagnostic:{phase,...detail}});
}
async function registryNevadaExposeWindow(job,previous) {
  const tab=await chrome.tabs.get(job.tab),source=await chrome.tabs.get(job.sender.tab.id);
  const siblings=await chrome.tabs.query({windowId:tab.windowId});
  const bounds=await chrome.windows.get(source.windowId),nv=await chrome.windows.get(tab.windowId);
  // Read foreground last: geometry reads may yield while the user switches.
  const focus=await chrome.windows.getLastFocused();
  const prior=(await chrome.tabs.query({active:true,windowId:previous.windowId}))[0];
  if((focus.focused===true)!==(previous.browserFocused!==false) || focus.id!==previous.windowId){job.nvVisibilityOutcome='foreground_changed';registryNevadaDiagnostic(job,'foreground-changed',{browser_focused:focus.focused===true});return null;}
  // TN can legitimately activate its owned collector in the source window.
  // Treat that as coordination, not as a user selecting an unrelated page.
  // Record the actual owned foreground so completion restores that collector.
  const ownedTransition=prior?.id!==previous.id && registryNevadaOwnedForeground(prior,source)
    && owned.has(prior.id);
  const minimizedSourceAllowed=job.nvSourceInitiallyMinimized===true
    && previous.sourceWasMinimized===true && bounds.state==='minimized';
  const inactiveBrowser=previous.inactiveBrowser===true && (focus.focused===false||minimizedSourceAllowed)
    && !job.nvInactiveBrowserActivationUsed
    && prior?.active===true && prior.id===previous.id && prior.url===previous.url;
  if(!tab.active || tab.windowId!==previous.nvWindowId || tab.windowId===source.windowId
      || source.windowId!==previous.sourceWindowId || source.url!==previous.sourceUrl
      || new URL(source.url).origin!==P.TRIAL_ORIGIN || new URL(tab.url).origin!==registryOrigin('NV')
      || !new URL(tab.url).pathname.startsWith('/portal/public/') || siblings.length!==1 || siblings[0].id!==tab.id
      || (!ownedTransition && (prior?.id!==previous.id || prior.url!==previous.url))
      || (!registryNevadaOwnedForeground(prior,source) && !inactiveBrowser) || nv.state==='minimized'
      || bounds.state==='minimized' && !minimizedSourceAllowed
      || !['left','top','width','height'].every(k=>Number.isFinite(bounds[k]))
      || !inactiveBrowser && !minimizedSourceAllowed && !previous.coordinatedPlacement && (bounds.width<1000 || bounds.height<700)
      || job.closed || Date.now()>=job.activeExpiresAt || job.tab!==tab.id || !owned.has(tab.id)){
    job.nvVisibilityOutcome='ownership_or_geometry_changed';
    registryNevadaDiagnostic(job,'visibility-refused',{
      inactive_tab:!tab.active, nv_window_changed:tab.windowId!==previous.nvWindowId,
      shared_window:tab.windowId===source.windowId,
      source_window_changed:source.windowId!==previous.sourceWindowId,
      source_url_changed:source.url!==previous.sourceUrl,
      source_origin_changed:new URL(source.url).origin!==P.TRIAL_ORIGIN,
      nv_origin_changed:new URL(tab.url).origin!==registryOrigin('NV'),
      nv_path_changed:!new URL(tab.url).pathname.startsWith('/portal/public/'),
      siblings_changed:siblings.length!==1 || siblings[0].id!==tab.id,
      prior_changed:!ownedTransition && (prior?.id!==previous.id || prior.url!==previous.url),
      foreground_not_owned:!registryNevadaOwnedForeground(prior,source),
      nv_minimized:nv.state==='minimized',source_minimized:bounds.state==='minimized',
      invalid_bounds:!['left','top','width','height'].every(k=>Number.isFinite(bounds[k])),
      source_width_small:bounds.width<1000,source_height_small:bounds.height<700,
      source_width:bounds.width,source_height:bounds.height,
      expired:Date.now()>=job.activeExpiresAt,closed:job.closed,
      tab_changed:job.tab!==tab.id,not_owned:!owned.has(tab.id)});
    return null;
  }
  // Unlike the four-window experiment, move only our stalled NV window.
  // A smaller foreground window leaves other full-size collectors exposed;
  // never reload/resubmit the in-flight command or extend its deadline.
  const width=Math.min(960,Math.floor(bounds.width*.7)),height=Math.min(700,Math.floor(bounds.height*.7));
  const restore={...previous,id:prior.id,url:prior.url};
  job.nvVisibilityAttempted=true;job.nvPreviousVisible=restore;
  if(inactiveBrowser)job.nvInactiveBrowserActivationUsed=true;
  // An already tiled collector must keep its footprint, not expand over peers.
  // Missing layout information must not block exposure of an already owned
  // isolated collector. Focus in place: no guessed geometry or other windows.
  const placement=previous.coordinatedPlacement || (minimizedSourceAllowed||inactiveBrowser?{focused:true}:{focused:true,state:'normal',width,height,
    left:bounds.left+bounds.width-width-8,top:bounds.top+bounds.height-height-8});
  await chrome.windows.update(tab.windowId,placement);
  diagnostic('nv-visibility',job,'owned separate window; same document and deadline');
  job.nvVisibilityOutcome=inactiveBrowser?'activated_from_inactive_browser':ownedTransition?'activated_after_owned_transition':'activated_separate_window';
  registryNevadaDiagnostic(job,'visibility-activated',{inactive_browser:focus.focused===false,
    kept_existing_bounds:!previous.coordinatedPlacement&&(minimizedSourceAllowed||inactiveBrowser),
    coordinated_placement:!!previous.coordinatedPlacement,
    source_remains_minimized:minimizedSourceAllowed});
  await saveRuntime();return restore;
}
async function registryNevadaMakeVisible(job, initialVisible) {
  if (!P.TRIAL_ORIGIN || job.registryState!=='NV' || !initialVisible || job.closed || job.nvVisibilityAttempted
      || Date.now()>=job.activeExpiresAt || !owned.has(job.tab)) return null;
  try {
    if(initialVisible.mode==='window')return await registryNevadaExposeWindow(job,initialVisible);
    const tab=await chrome.tabs.get(job.tab), source=await chrome.tabs.get(job.sender.tab.id);
    const active=(await chrome.tabs.query({active:true,windowId:tab.windowId}))[0];
    if (tab.active || tab.windowId!==initialVisible.windowId || tab.windowId!==source.windowId
        || active?.id!==initialVisible.id || new URL(source.url).origin!==P.TRIAL_ORIGIN
        || new URL(tab.url).origin!==registryOrigin('NV')
        || !new URL(tab.url).pathname.startsWith('/portal/public/')) return null;
    const previous={id:initialVisible.id,windowId:initialVisible.windowId};
    job.nvVisibilityAttempted=true;job.nvPreviousVisible=previous;
    diagnostic('nv-visibility',job,'same-document visibility recovery');
    await chrome.tabs.update(tab.id,{active:true});await saveRuntime();
    return previous;
  } catch {job.nvVisibilityOutcome='activation_unavailable';return null;}
}
async function registryMessage(job, message) {
  if (job.closed || Date.now() >= job.activeExpiresAt) throw new Error("NY_CONNECTOR_TIMEOUT");
  // Search and detail are separate hydration steps. Another owned collector
  // may cover NV between them; allow one fresh guarded visibility check at
  // the first detail, never a repeated focus loop or a new request/deadline.
  if (P.TRIAL_ORIGIN && job.registryState==='NV' && message.action==='registry-nv'
      && message.query?.operation==='detail' && !job.nvDetailVisibilityChecked) {
    job.nvDetailVisibilityChecked=true;
    if(job.nvVisibilityAttempted && owned.has(job.tab)) {
      try {
        const tab=await chrome.tabs.get(job.tab);
        if(new URL(tab.url).origin===registryOrigin('NV')) {
          const state=await chrome.tabs.sendMessage(job.tab,{action:'registry-ready'},{frameId:0});
          if(state?.page_visibility==='hidden')job.nvVisibilityAttempted=false;
        }
      } catch { /* Observation failure must not prevent the original detail. */ }
    }
    await saveRuntime();
  }
  const send=async()=>{
    const tab = await chrome.tabs.get(job.tab);
    if (new URL(tab.url).origin !== registryOrigin(job.registryState)) throw new Error("NY_CONNECTOR_INCOMPLETE");
    return chrome.tabs.sendMessage(job.tab, {...message,...(P.TRIAL_ORIGIN && job.registryState==='NV' && message.action==='registry-nv'?{diagnosticId:job.pending,skipHistory:message.query?.operation==='detail'}:{})}, {frameId:0});
  };
  if(P.TRIAL_ORIGIN && job.registryState==='MS' && message.action==='registry-ms'
      && message.query?.operation==='search' && Number.isFinite(message.budgetMs)) {
    // A Kendo grid is evidence only after this signed search produces a new
    // completed response. Under load both a fresh form and a reused form can
    // leave the grid unchanged, while hidden-tab timers delay the page error.
    // Bound that wait and use the same-query fresh-form recovery below.
    const waitMs=Math.max(1,Math.min(message.requireFreshGrid?8000:12000,
      message.budgetMs,job.activeExpiresAt-Date.now(),
      (job.msDeadlineAt ?? job.activeExpiresAt)-Date.now()));
    let timer;
    try {
      return await Promise.race([send(),new Promise(resolve=>{
        timer=setTimeout(()=>{
          diagnostic('ms-grid-watchdog',job,`reuse=${message.requireFreshGrid===true} wait_ms=${waitMs}`);
          resolve({ok:false,reason:'NY_CONNECTOR_INCOMPLETE',
            ms_diagnostic:{source_error:'REGISTRY_GRID_WATCHDOG',
              reused_form:message.requireFreshGrid===true,wait_ms:waitMs}});
        },waitMs);
      })]);
    } finally {clearTimeout(timer);}
  }
  if (job.registryState!=='NV' || !Number.isFinite(message.budgetMs)) return send();
  // Keep the overall job deadline as the transport bound. A second timer at
  // exactly the page's allowance races its normal timeout reply and prevents
  // the existing bounded fresh-form recovery from running. Page observers
  // retain their own allowances; a hung message cannot outlive this job.
  let timer, visibilityTimer, visibilityPending=null, previousVisible=null;
  let settled=false;
  // ORION's detail hydration can stall in a background tab. Keep the same
  // in-flight command and document; expose only our owned trial tab once.
  // Capture the active tab first so a later user switch is never overridden.
  const initialVisible=await registryNevadaVisibleSnapshot(job);
  visibilityTimer=setTimeout(()=>{
    visibilityPending=(async()=>{
      if (settled || job.closed || Date.now()>=job.activeExpiresAt || !owned.has(job.tab)) return;
      // A concurrent owned collector can finish opening after the initial
      // snapshot. Reassess a missing snapshot once; never override a changed
      // foreground captured in a previously eligible snapshot.
      previousVisible=await registryNevadaMakeVisible(job,initialVisible || await registryNevadaVisibleSnapshot(job));
    })();
  },Math.min(3000,Math.max(1,job.activeExpiresAt-Date.now())));
  try {
    return await Promise.race([send(),new Promise((_,reject)=>{
      timer=setTimeout(()=>reject(new Error('NY_CONNECTOR_REGISTRY_NV_COMMAND_TIMEOUT')),
        Math.max(1,job.activeExpiresAt-Date.now()));
    })]);
  } finally {
    settled=true;clearTimeout(timer);clearTimeout(visibilityTimer);
    if (visibilityPending) await visibilityPending;
    // Keep hydration visible through this state's continuation. Restoring
    // after every command reintroduced hidden-page stalls and paid the same
    // recovery delay repeatedly. Completion/cancellation restores the caller;
    // a user switch is never reversed or followed by another activation.
    if (job.closed || Date.now()>=job.activeExpiresAt) await registryRestoreNevadaVisibility(job);
  }
}
async function registryRestoreNevadaVisibility(job) {
  const previous=job.nvPreviousVisible;job.nvPreviousVisible=null;
  if (!P.TRIAL_ORIGIN || job.registryState!=='NV' || !previous || !owned.has(job.tab)) return;
  if(previous.inactiveBrowser||previous.sourceWasMinimized)return; // Never restore unrelated or minimized source windows.
  try {
    const tab=await chrome.tabs.get(job.tab),prior=await chrome.tabs.get(previous.id);
    const source=await chrome.tabs.get(job.sender.tab.id);
    if(previous.mode==='window'){
      const focus=await chrome.windows.getLastFocused();
      const siblings=await chrome.tabs.query({windowId:tab.windowId});
      if(focus.focused && focus.id===previous.nvWindowId && tab.active && tab.windowId===previous.nvWindowId
          && siblings.length===1 && siblings[0].id===tab.id && prior.windowId===previous.windowId
          && prior.url===previous.url && source.windowId===previous.sourceWindowId && source.url===previous.sourceUrl
          && new URL(source.url).origin===P.TRIAL_ORIGIN && new URL(tab.url).origin===registryOrigin('NV')
          && new URL(tab.url).pathname.startsWith('/portal/public/') && registryNevadaOwnedForeground(prior,source))
        await chrome.windows.update(previous.windowId,{focused:true});
      return;
    }
    if (tab.active && tab.windowId===previous.windowId && prior.windowId===tab.windowId
        && source.windowId===tab.windowId && new URL(source.url).origin===P.TRIAL_ORIGIN
        && new URL(tab.url).origin===registryOrigin('NV') && new URL(tab.url).pathname.startsWith('/portal/public/'))
      await chrome.tabs.update(prior.id,{active:true});
  } catch { /* Preserve a user switch, moved tab, or closure. */ }
}
async function registryReady(job, oldDocument = null, path = null, budgetMs = 45000, ncSubmittedQuery = null, nvRouteOnly = false) {
  if (nvRouteOnly && (job.registryState!=='NV' || oldDocument!==null
      || path!==new URL(registryStart('NV')).pathname)) throw new Error('NY_CONNECTOR_INVALID_SEQUENCE');
  const started = Date.now();
  const deadline = Math.min(Date.now()+Math.max(1,Math.min(45000,budgetMs)), job.activeExpiresAt);
  let verificationPending=false, visibilityAttempted=false, previousVisible=null, submissionRetried=false, resubmissionAcknowledged=false;
  let nvInitialVisible=await registryNevadaVisibleSnapshot(job), nvVisibilityRechecked=false, ncVisibilityRechecked=false;
  try { while (!job.closed && Date.now()<deadline) {
    try {
      if(P.TRIAL_ORIGIN && job.registryState==='NM') {
        const tab=await chrome.tabs.get(job.tab),url=new URL(tab.url);
        // NM redirects failures to a lowercase route outside its normal
        // content-script match. The exact public error route is authoritative
        // even when there is no content-script receiver on that document.
        if(url.origin===registryOrigin('NM') && /^\/charitysearch\/GenericError\.htm$/i.test(url.pathname))
          throw new Error('NY_CONNECTOR_REGISTRY_NM_SOURCE_ERROR');
      }
      const value=await registryMessage(job,{action:"registry-ready",...(ncSubmittedQuery ? {query:ncSubmittedQuery} : {})});
      if(P.TRIAL_ORIGIN && job.registryState==='NC' && !ncSubmittedQuery) {
        const observed={phase:'readiness',ready:value?.ready===true,
          visible:value?.page_visibility==='visible',verification_pending:value?.verification_pending===true,
          separate_window_activated:job.ncWindowVisibilityAttempted===true};
        const signature=JSON.stringify(observed);
        if(signature!==job.ncSubmissionSignature) {
          job.ncSubmissionSignature=signature;job.ncSubmissionObservations ||= [];
          const entry={seconds:(Date.now()-started)/1000,...observed};
          if(job.ncSubmissionObservations.length<8)job.ncSubmissionObservations.push(entry);else job.ncSubmissionObservations[7]=entry;
        }
      }
      if(P.TRIAL_ORIGIN && job.registryState==='NC' && ncSubmittedQuery && value?.nc_readiness) {
        const observed=value.nc_readiness,signature=JSON.stringify(observed);
        if(signature!==job.ncSubmissionSignature){
          job.ncSubmissionSignature=signature;job.ncSubmissionObservations ||= [];
          const entry={seconds:(Date.now()-started)/1000,...observed};
          if(job.ncSubmissionObservations.length<8)job.ncSubmissionObservations.push(entry);
          else job.ncSubmissionObservations[7]=entry;
        }
        // A rejected request is not an idle form awaiting a second click.
        if (Array.isArray(observed.requests) && observed.requests.some(request =>
            request?.search_route===true && request.status===429))
          throw new Error('NY_CONNECTOR_NC_RATE_LIMITED');
      }
      if(job.registryState==='NM' && value?.source_failure==='REGISTRY_NM_SOURCE_ERROR')
        throw new Error('NY_CONNECTOR_REGISTRY_NM_SOURCE_ERROR');
      if(job.registryState==='NV'&&value?.nv_readiness)job.nvReadiness={...value.nv_readiness,page_visibility:value.page_visibility||'unknown'};
      // Fast readiness polls never leave registryMessage's visibility timer
      // pending long enough to fire. Recover a stalled initial form using the
      // same owned-tab lease as detail commands, without a request or reload.
      if(job.registryState==='NV'&&!value?.ready&&Date.now()-started>=3000) {
        if(!nvInitialVisible && !nvVisibilityRechecked) {
          nvVisibilityRechecked=true;nvInitialVisible=await registryNevadaVisibleSnapshot(job);
        }
        await registryNevadaMakeVisible(job,nvInitialVisible);
      }
      verificationPending=['NC','TN'].includes(job.registryState)&&value?.verification_pending===true;
      if(job.registryState==='TN'&&!value?.ready&&!visibilityAttempted&&Date.now()-started>=3000) {
        visibilityAttempted=true;previousVisible=await registryNorthCarolinaVisibility(job);
      }
        const observedRoute=nvRouteOnly&&typeof value?.documentId==='string'&&value.documentId.length>0;
        if ((value?.ready || observedRoute) && value.documentId !== oldDocument && (!path || new URL(value.url).pathname===path)
            && (job.registryState!=='NV' || new URL(value.url).hash===new URL(registryStart('NV')).hash)) return value;
      // An acknowledged NC Search can leave the same ordinary, enabled form
      // without navigating. Retry once only after observing that exact form;
      // disabled Processing and verification pages are never resubmitted.
      // The original deadline and expected results document stay unchanged.
      if (ncSubmittedQuery && job.registryState==='NC' && !submissionRetried && !verificationPending
          && Date.now()-started>=3000 && Date.now()<deadline && value?.ready && value.documentId===oldDocument
          && new URL(value.url).pathname==='/online_services/search/by_title/search_charities') {
        submissionRetried=true;
        // A background form can acknowledge Search without its public async
        // action navigating. Reuse the existing owned-tab visibility recovery
        // before the single exact-query retry. No new query or time allowance.
        if (P.TRIAL_ORIGIN && !visibilityAttempted) {
          visibilityAttempted=true;
          previousVisible=await registryNorthCarolinaVisibility(job);
        }
        const retried=await registryMessage(job,{action:'registry-nc-retry',query:ncSubmittedQuery});
        resubmissionAcknowledged=retried?.ok===true&&retried.phase==='submitted';
        diagnostic('nc-submit-recovery',job,retried?.phase==='submitted'?'same-query resubmitted':'form changed; no resubmission');
      }
      // Only a proven identical idle form can fail early. A disabled Processing
      // action, verification, changed query or document retains normal waits.
      // The master may recover once in a fresh page within the original expiry.
      if (P.TRIAL_ORIGIN && job.registryState==='NC' && ncSubmittedQuery && resubmissionAcknowledged
          && !verificationPending && Date.now()-started>=8000 && value?.ready && value.nc_search_idle===true
          && value.documentId===oldDocument && new URL(value.url).pathname==='/online_services/search/by_title/search_charities')
        throw new Error('NY_CONNECTOR_NC_SEARCH_NOT_STARTED');
    } catch(error) {
      if(['NY_CONNECTOR_REGISTRY_NM_SOURCE_ERROR','NY_CONNECTOR_NC_SEARCH_NOT_STARTED','NY_CONNECTOR_NC_RATE_LIMITED'].includes(error?.message))throw error;
      // The public challenge can precede content-script readiness. Its visible
      // tab title is sufficient to describe a pending verification, not a result.
      if (job.registryState==='NC') try {
        const tab=await chrome.tabs.get(job.tab);
        verificationPending= new URL(tab.url).origin===registryOrigin('NC') && /^Just a moment/i.test(tab.title||'');
      } catch {}
    }
    if (verificationPending && !visibilityAttempted && Date.now()<deadline) {
      visibilityAttempted=true;
      previousVisible=await registryNorthCarolinaVisibility(job);
    }
    if(P.TRIAL_ORIGIN && job.registryState==='NC' && verificationPending
        && !job.ncWindowVisibilityAttempted && !ncVisibilityRechecked && Date.now()-started>=3000 && Date.now()<deadline) {
      ncVisibilityRechecked=true;await registryNorthCarolinaVisibility(job);
    }
    await nap(200);
  }
  throw new Error(verificationPending ? `NY_CONNECTOR_${job.registryState}_VERIFICATION_PENDING` : "NY_CONNECTOR_TAB_READY_TIMEOUT");
  } finally {
    if (previousVisible) try {
      const tab=await chrome.tabs.get(job.tab), prior=await chrome.tabs.get(previousVisible.id);
      if (owned.has(job.tab) && tab.active && tab.windowId===previousVisible.windowId && prior.windowId===tab.windowId
          && new URL(tab.url).origin===registryOrigin(job.registryState) && (!path || new URL(tab.url).pathname===path))
        await chrome.tabs.update(prior.id,{active:true});
    } catch { /* Preserve user navigation or closure during verification. */ }
  }
}
async function registryNorthCarolinaVisibility(job) {
  // Same-document visibility recovery, as used for Illinois. The state's own
  // scripts may finish a passive verification; no checkbox, challenge, token,
  // cookie, reload, additional request, or budget extension is performed here.
  if (!['NC','TN'].includes(job.registryState) || job.closed || !owned.has(job.tab)) return null;
  try {
    const tab=await chrome.tabs.get(job.tab), source=await chrome.tabs.get(job.sender.tab.id);
    if(P.TRIAL_ORIGIN && job.registryState==='NC' && !job.ncWindowVisibilityAttempted && tab.active && tab.windowId!==source.windowId
        && new URL(source.url).origin===P.TRIAL_ORIGIN && new URL(tab.url).origin===registryOrigin('NC')
        && new URL(tab.url).pathname.startsWith('/online_services/search/') && Date.now()<job.activeExpiresAt) {
      const focus=await chrome.windows.getLastFocused();
      const prior=(await chrome.tabs.query({active:true,windowId:focus.id}))[0];
      if(focus.focused && focus.id===tab.windowId || !registryNevadaOwnedForeground(prior,source))return null;
      const siblings=await chrome.tabs.query({windowId:tab.windowId});
      if(siblings.length!==1 || siblings[0].id!==tab.id)return null;
      const placement=await registryTrialWindowOptions(job,source);
      if(!placement.focused)return null;
      const latest=await chrome.tabs.get(tab.id),currentSource=await chrome.tabs.get(source.id);
      const latestFocus=await chrome.windows.getLastFocused();
      const active=(await chrome.tabs.query({active:true,windowId:focus.id}))[0];
      if(latest.windowId!==tab.windowId || latest.url!==tab.url || !latest.active
          || currentSource.windowId!==source.windowId || currentSource.url!==source.url
          || latestFocus.id!==focus.id || latestFocus.focused!==focus.focused
          || active?.id!==prior.id || active.url!==prior.url
          || !owned.has(tab.id) || job.closed || Date.now()>=job.activeExpiresAt)return null;
      const {type,...update}=placement;
      await chrome.windows.update(tab.windowId,update);
      job.ncWindowVisibilityAttempted=true;
      diagnostic('nc-verification',job,'owned separate window; same document and deadline');
      // Closing the collector releases this window. Do not activate a prior
      // tab inside another collector while its own command is still running.
      return null;
    }
    if (tab.active || tab.windowId!==source.windowId || new URL(tab.url).origin!==registryOrigin(job.registryState)
        || (job.registryState==='NC' ? !new URL(tab.url).pathname.startsWith('/online_services/search/') : tab.url!==registryStart('TN'))) return null;
    const prior=(await chrome.tabs.query({active:true,windowId:tab.windowId}))[0];
    if (!prior || prior.id===tab.id || job.closed || !owned.has(job.tab)) return null;
    diagnostic('nc-verification',job,'same-document visibility recovery');
    await chrome.tabs.update(tab.id,{active:true});
    return {id:prior.id,windowId:prior.windowId};
  } catch { return null; }
}
async function registryNavigate(job, url, budgetMs = 45000, freshNvRecovery = false) {
  if (new URL(url).origin !== registryOrigin(job.registryState)) throw new Error("NY_CONNECTOR_INCOMPLETE");
  if (freshNvRecovery && (job.registryState!=='NV' || url!==registryStart('NV')
      || !(job.nvReturnRecoveryUsed || job.nvReservationDetail || job.nvModeRecoveryUsed))) throw new Error('NY_CONNECTOR_INVALID_SEQUENCE');
    const navigationStarted=Date.now();
    const deadline=Math.min(job.activeExpiresAt,Date.now()+Math.max(1,Math.min(45000,budgetMs)));
    let previous;
  if (job.tab !== null) {
    try { previous=(await registryMessage(job,{action:"registry-ready"})).documentId; } catch {}
    // Updating a tab to its current URL may leave the same document in place.
    // Explicitly reload so the next search starts with a fresh public form.
    const current = await chrome.tabs.get(job.tab);
    if (freshNvRecovery) {
        if(current.url!==url) {
          await chrome.tabs.update(job.tab,{url});
          // A tabs.update acknowledgement is not navigation completion. Wait
          // for the public route before reloading, or Chrome can reload the
          // old reservation document. The old form need not become usable:
          // recovering that form is why this refresh is required. Only after
          // reload must the fresh document and complete form be ready. Both
          // waits share the original allowance.
          const target=await registryReady(job,null,new URL(url).pathname,deadline-Date.now(),null,true);
          previous=target.documentId;
          diagnostic('nv-navigation',job,'public route reached; refreshing form');
        }
      await chrome.tabs.reload(job.tab);
    } else if (current.url === url) await chrome.tabs.reload(job.tab);
    else {
      const before=new URL(current.url),after=new URL(url);
      await chrome.tabs.update(job.tab,{url});
      // ORION changes the hash to return from a detail to search. Chrome keeps
      // the same document/content script, so waiting for a new document ID can
      // never succeed. The NV ready check still requires the rendered Business
      // search form; nvSearch separately binds filters and a fresh loading cycle.
      if(job.registryState==='NV'&&before.origin===after.origin&&before.pathname===after.pathname
          &&before.search===after.search&&before.hash!==after.hash)previous=null;
    }
  } else {
    const origin=await chrome.tabs.get(job.sender.tab.id);
    job.creating=(async()=>{
      // A different state's verification can hide NV after its one visibility
      // recovery. An active tab in a separate, unfocused normal window removes
      // that competition without serializing states or extending their budgets.
      // Existing owned-tab cleanup closes this window's only tab on completion.
      // Record ownership before creation settles so cancellation can clean up
      // a window that Chrome creates after the caller has already stopped.
      await registryCreateOwnedTab(job,url,origin);
    })();
    await job.creating;job.creating=null;
    if(P.TRIAL_ORIGIN && job.registryState==='MS')
      diagnostic('ms-tab-created',job,`ms=${Date.now()-navigationStarted}`);
  }
    const ready=await registryReady(job,previous,new URL(url).pathname,
      freshNvRecovery || job.registryState==='MS' ? Math.max(1,deadline-Date.now()) : budgetMs);
    if(P.TRIAL_ORIGIN && job.registryState==='MS')
      diagnostic('ms-page-ready',job,`ms=${Date.now()-navigationStarted} tab=${job.tab}`);
    return ready;
}
async function registryIllinoisVerification(job, collect) {
  // Preserve the verification document. Reloading here resets Illinois's
  // normal challenge instead of recovering it. Only activate our owned tab;
  // the state's own code must enable Search before collection can proceed.
  if (job.closed || !owned.has(job.tab) || job.activeExpiresAt-Date.now() <= 45000)
    return {ok:false,reason:"NY_CONNECTOR_IL_VERIFICATION_PENDING"};
  const tab = await chrome.tabs.get(job.tab);
  const origin = await chrome.tabs.get(job.sender.tab.id);
  const activeTrialCollector=P.TRIAL_ORIGIN && new URL(origin.url).origin===P.TRIAL_ORIGIN && tab.active;
  if (tab.url !== registryStart("IL") || (tab.windowId !== origin.windowId && !activeTrialCollector))
    throw new Error("NY_CONNECTOR_INCOMPLETE");
  const previous = (await chrome.tabs.query({active:true,windowId:tab.windowId}))[0];
  diagnostic("il-verification",job,"same-document visibility recovery");
  try {
    if (job.closed || !owned.has(tab.id)) throw new Error("NY_CONNECTOR_INTERRUPTED");
    if (!tab.active) await chrome.tabs.update(tab.id,{active:true});
    return await collect(45000);
  } finally {
    // Do not override a user who switched elsewhere while the check ran.
    try {
      const current = await chrome.tabs.get(tab.id);
      const prior = previous && await chrome.tabs.get(previous.id);
      if (current.active && current.url === registryStart("IL") && prior && prior.id !== tab.id && prior.windowId === current.windowId)
        await chrome.tabs.update(prior.id,{active:true});
    } catch { /* A user may close or move either tab during collection. */ }
  }
}
async function performRegistryQuery(job, query) {
  if (!P.validQuery(query) || query.state !== job.registryState || !P.registryAllowed(query.state,new URL(job.sender.url).origin)) throw new Error("NY_CONNECTOR_INVALID_SEQUENCE");
  if(query.state==='MS') {
    // The public MS page can take nearly a minute to reload after a stalled
    // Kendo query. Bound the complete state sequence, not each generated name
    // separately; unfinished searches remain inconclusive.
    job.msDeadlineAt ??= Math.min(job.activeExpiresAt,Date.now()+60000);
    const remaining=()=>Math.min(job.activeExpiresAt,job.msDeadlineAt)-Date.now();
    const allowance=max=>{if(remaining()<=0)throw new Error('NY_CONNECTOR_TIMEOUT');
      return Math.max(1,Math.min(max,remaining()));};
    if(query.operation==='search') {
      // Reuse a completed search form within this owned trial job. The page
      // handler must see a new Kendo render after submission; its old grid is
      // never evidence for the next signed query. Detail opens a modal and
      // resets this allowance, so the next search uses a fresh public form.
      const current=job.tab===null?null:await chrome.tabs.get(job.tab);
      const reuse=!!P.TRIAL_ORIGIN && job.msReusableForm===true && current?.url===registryStart('MS');
      const navigationStarted=Date.now();
      diagnostic('ms-navigation-start',job,reuse?'reuse ready form':'open fresh form');
      if(reuse) await registryReady(job,null,new URL(registryStart('MS')).pathname,allowance(30000));
      else await registryNavigate(job,registryStart('MS'),allowance(30000));
      diagnostic('ms-navigation-done',job,`reuse=${reuse} ms=${Date.now()-navigationStarted}`);
      job.msReusableForm=false;
      const started=Date.now();
      let result=await registryMessage(job,{action:'registry-ms',query,requireFreshGrid:reuse,
        budgetMs:allowance(30000)});
      diagnostic('ms-command',job,`reuse=${reuse} ms=${Date.now()-started} ${result?.ok?'complete':result?.reason||'incomplete'}`);
      if(P.TRIAL_ORIGIN && result?.ms_diagnostic)
        diagnostic('ms-page',job,JSON.stringify(result.ms_diagnostic));
      if(!result?.ok && remaining()>20000 &&
          (reuse || ['REGISTRY_GRID_WATCHDOG','REGISTRY_RESPONSE_INCOMPLETE']
            .includes(result.ms_diagnostic?.source_error))) {
        diagnostic('ms-fresh-recovery',job,'repeating identical signed query on new public form');
        await registryNavigate(job,registryStart('MS'),allowance(10000));
        result=await registryMessage(job,{action:'registry-ms',query,
          budgetMs:allowance(10000)});
      }
      job.msReusableForm=result?.ok===true;
      return result;
    }
    if(job.tab===null)throw new Error('NY_CONNECTOR_INVALID_SEQUENCE');
    job.msReusableForm=false;
    return registryMessage(job,{action:'registry-ms',query,budgetMs:allowance(20000)});
  }
  if(query.state==='NM') {
    if(query.operation==='search') {
      // ASP.NET preserves the submitted filters when this URL is reloaded.
      // Reuse the ready owned search form for the next fallback. The Search
      // postback still must produce a new document and query-bound row count.
      const current=job.tab===null?null:await chrome.tabs.get(job.tab);
      if(current?.url===registryStart('NM'))
        await registryReady(job,null,'/CharitySearch/',Math.min(30000,job.activeExpiresAt-Date.now()));
      else await registryNavigate(job,registryStart('NM'),Math.min(30000,job.activeExpiresAt-Date.now()));
      for(let attempt=0;attempt<2;attempt++) {
        const submitted=await registryMessage(job,{action:'registry-nm-form',query});
        if(!submitted?.ok)throw new Error('NY_CONNECTOR_INCOMPLETE');
        await registryReady(job,submitted.documentId,'/CharitySearch/',Math.min(30000,job.activeExpiresAt-Date.now()));
        if(submitted.phase!=='page-size')return registryMessage(job,{action:'registry-nm-rows',query});
      }
      throw new Error('NY_CONNECTOR_INCOMPLETE');
    }
    const url=registryStart('NM')+'CharityDetail.aspx?FEIN='+query.identifier.slice(0,2)+'-'+query.identifier.slice(2);
    await registryNavigate(job,url,Math.min(30000,job.activeExpiresAt-Date.now()));
    return registryMessage(job,{action:'registry-nm-detail',query});
  }
  if (query.state === "AL") {
    if (job.tab === null && trialAlIdle) {
      const saved=trialAlIdle; trialAlIdle=null;
      try {
        const tab=await chrome.tabs.get(saved.id), source=await chrome.tabs.get(job.sender.tab.id);
        // An authorized trial page may run in another Chrome window. The
        // owned tab, source origin and expiry are the security boundaries;
        // moving the caller to a dedicated validation window must not discard
        // the already verified public session.
        if (owned.has(saved.id) && tab.url===registryStart('AL') && new URL(source.url).origin===P.TRIAL_ORIGIN && saved.expiresAt>Date.now()) job.tab=saved.id;
        else await removeOwned(saved.id);
      } catch { await removeOwned(saved.id); }
      await saveRuntime();
    }
    if (job.tab===null) await registryNavigate(job,registryStart('AL'));
    else await registryReady(job,null,'/online/Lookups/Business.aspx');
    // Reuse only the connector-owned verified page. Each command must observe
    // a fresh result; no verification code or previous result is shared.
    return registryMessage(job,{action:'registry-al',query,automaticVerification:!!P.TRIAL_ORIGIN,
      budgetMs:Math.max(1,Math.min(45000,job.activeExpiresAt-Date.now()))});
  }
  if (query.state === "NC") return registryNorthCarolinaQuery(job,query);
  if (["NV", "TN"].includes(query.state)) {
    if (P.TRIAL_ORIGIN && query.state==='TN' && query.operation==='search' && job.tab===null && trialTnIdle) {
      const saved=trialTnIdle;trialTnIdle=null;clearTimeout(trialTnIdleTimer);
      try {
        const tab=await chrome.tabs.get(saved.id),source=await chrome.tabs.get(job.sender.tab.id);
        if(owned.has(saved.id) && saved.expiresAt>Date.now() && tab.url===registryStart('TN')
            && tab.windowId===saved.windowId && source.windowId===(saved.sourceWindowId??saved.windowId)
            && new URL(source.url).origin===P.TRIAL_ORIGIN
            && await registryTennesseeOwnedWindow(tab,source)) {
          job.tab=saved.id;job.finalFourReusableForm=true;
          await registryExposeReusedNyTab(job,source);
          // Reuse page initialization only. tnSearch closes any old dialog,
          // clears observed rows and submits every new query afresh.
          diagnostic('tn-session-reuse',job,'initialized owned page; fresh query required');
        } else await removeOwned(saved.id);
      } catch {await removeOwned(saved.id);}
      await saveRuntime();
    }
    if (query.state==='NV' && job.nvReservationDetail) {
      // ORION reservation Back leads to ExistingBusinessFilings and sign-in,
      // not public search. Reopen the known public form, within this job's
      // deadline. A second detail must first re-observe the entire same result
      // set; it cannot reuse detached links or changed registration evidence.
      const prior=job.nvLastSearch;
      await registryNavigate(job,registryStart('NV'),Math.min(45000,job.activeExpiresAt-Date.now()),true);
      job.nvReservationDetail=false;job.finalFourReusableForm=true;
      if (query.operation==='detail') {
        if (!prior?.evidence?.complete) throw new Error('NY_CONNECTOR_INVALID_SEQUENCE');
        const restored=await registryMessage(job,{action:'registry-nv',query:prior.query,
          budgetMs:Math.max(1,Math.min(150000,job.activeExpiresAt-Date.now()))});
        if (!restored?.ok || restored.evidence?.complete!==true || !P.sameQuery(restored.evidence.query,prior.query)
            || restored.evidence.total!==prior.evidence.total
            || JSON.stringify(restored.evidence.rows)!==JSON.stringify(prior.evidence.rows))
          throw new Error('NY_CONNECTOR_REGISTRY_NV_RESTORED_RESULTS_CHANGED');
      }
    }
    if (query.operation === "search") {
      if (query.state==='NV' && job.tab!==null && !job.finalFourReusableForm) {
        if (P.TRIAL_ORIGIN && job.nvReturnRecoveryUsed) {
          // This organization's native return has already stalled. Open the
          // public form for each remaining signed search instead of spending
          // another return allowance or failing after reading its records.
          // No query is skipped, and the original active deadline still owns
          // every navigation and response.
          diagnostic('nv-return-known-stall',job,'fresh public form within original deadline');
          await registryNavigate(job,registryStart('NV'),Math.min(45000,job.activeExpiresAt-Date.now()),true);
        } else {
        // Form hydration shares the normal navigation allowance and the
        // original job deadline. A ten-second sub-budget rejected a still
        // loading public form despite remaining lookup time. Sales supplies
        // its own one-minute cancellation; this never extends that limit.
        const returned=await registryMessage(job,{action:'registry-nv-return',budgetMs:Math.max(1,Math.min(P.TRIAL_ORIGIN?8000:45000,job.activeExpiresAt-Date.now()))});
        if(returned?.nv_readiness)job.nvReadiness=returned.nv_readiness;
        if (!returned?.ok) {
          if (returned?.reason!=='NY_CONNECTOR_REGISTRY_NV_RETURN_READY_TIMEOUT' || job.nvReturnRecoveryUsed
              || job.activeExpiresAt-Date.now()<5000) throw new Error(returned?.reason||'NY_CONNECTOR_INCOMPLETE');
          job.nvReturnRecoveryUsed=true;
          diagnostic('nv-return-recovery',job,'fresh public form within original deadline');
          await registryNavigate(job,registryStart('NV'),Math.min(45000,job.activeExpiresAt-Date.now()),true);
        } else await registryReady(job,null,new URL(registryStart('NV')).pathname);
        }
      } else if (job.tab === null || !job.finalFourReusableForm) await registryNavigate(job,registryStart(query.state));
      else await registryReady(job,null,new URL(registryStart(query.state)).pathname);
    } else if (job.tab === null || !job.finalFourSearchComplete) {
      throw new Error("NY_CONNECTOR_INVALID_SEQUENCE");
    }
    job.finalFourReusableForm = false;
    // A short reviewed alias can legitimately return thousands of entities.
    // Give that complete paged search margin inside this job's existing
    // deadline; never borrow another state's time or reset Sales' one minute.
    const allowance=query.state==='NV'&&query.operation==='search'?150000:45000;
    let response = await registryMessage(job,{action:`registry-${query.state.toLowerCase()}`,query,budgetMs:Math.max(1,Math.min(allowance,job.activeExpiresAt-Date.now()))});
    if (P.TRIAL_ORIGIN && query.state==='NV' && query.operation==='search'
        && ['NY_CONNECTOR_REGISTRY_NV_MODE_NOT_SELECTED','NY_CONNECTOR_REGISTRY_NV_FORM_NOT_SETTLED'].includes(response?.reason)
        && !job.nvModeRecoveryUsed && job.activeExpiresAt-Date.now()>8000) {
      // An unsettled public dropdown or bound filter form is not a completed
      // search. Reopen only
      // our public form once, retry the identical signed query and retain the
      // original deadline. Never retry or invent detail/history evidence.
      job.nvModeRecoveryUsed=true;
      diagnostic('nv-mode-recovery',job,'fresh public form; same signed query');
      await registryNavigate(job,registryStart('NV'),Math.min(45000,job.activeExpiresAt-Date.now()),true);
      response=await registryMessage(job,{action:'registry-nv',query,
        budgetMs:Math.max(1,Math.min(allowance,job.activeExpiresAt-Date.now()))});
    }
    if (query.operation === "search") job.finalFourSearchComplete = response?.ok === true;
    if (query.state==='NV' && response?.ok===true) {
      if (query.operation==='search') job.nvLastSearch={query,evidence:response.evidence};
      job.nvReservationDetail=query.operation==='detail' && /^(?:NR|C)\d{8}-\d+$/.test(query.identifier);
    }
    // TN keeps its result grid behind the detail dialog. NV navigates to a
    // detail route, so its next name search uses the public Return To Search.
    job.finalFourReusableForm = response?.ok === true && (query.state === "TN" || query.operation === "search");
    return response;
  }
  if (query.state === "IL") {
    // Keep one ordinary search form through the same organization's fallbacks.
    // Reloading for every name repeatedly discards normal page readiness and
    // verification. The content handler clears all public filters each time.
    // A previously opened detail or failed command still requires a fresh form.
    if (job.tab === null || !job.ilReusableForm) await registryNavigate(job, registryStart("IL"));
    else await registryReady(job,null,"/search");
    job.ilReusableForm = false;
    const collect = async (formWaitMs = 45000) => {
      const started = Date.now();
      const result = await registryMessage(job,{action:"registry-il",query,formWaitMs});
      for (const entry of Array.isArray(result?.diagnostics) ? result.diagnostics.slice(0,32) : []) {
        if (!["form","results","page-size","detail"].includes(entry.phase) || !["observed","ready","incomplete"].includes(entry.event)
          || !Number.isFinite(entry.elapsed_ms) || entry.elapsed_ms < 0 || entry.elapsed_ms > 300000
          || !["visible","hidden","unknown"].includes(entry.visibility)) continue;
        diagnostic("il-dom",job,`${entry.phase}:${entry.event} ms=${entry.elapsed_ms} visibility=${entry.visibility}`);
      }
      diagnostic("il-command",job,`${query.identifier ? "detail" : query.ein ? "ein" : "name"} ms=${Date.now()-started} ${result?.ok ? "complete" : /^NY_CONNECTOR_[A-Z_]+$/.test(result?.reason) ? result.reason : "incomplete"}`);
      return result;
    };
    let result = await collect(0);
    if (result?.reason === "NY_CONNECTOR_IL_VERIFICATION_PENDING") {
      result = await registryIllinoisVerification(job, collect);
      job.ilReusableForm = result?.ok === true && !Object.hasOwn(query,"identifier");
      return result;
    }
    // One fresh-form retry for a search that never completed or an unopened
    // detail. Loaded records with absent dates are complete evidence.
    const retryable = ["NY_CONNECTOR_IL_FORM_READY_TIMEOUT", "NY_CONNECTOR_IL_FORM_DISABLED", "NY_CONNECTOR_IL_FORM_MISSING", "NY_CONNECTOR_IL_RESPONSE_TIMEOUT",
      "NY_CONNECTOR_IL_DETAIL_NOT_OPENED", "NY_CONNECTOR_IL_DETAIL_BLANK", "NY_CONNECTOR_IL_DETAIL_RESPONSE_TIMEOUT"];
    if (retryable.includes(result?.reason) && job.activeExpiresAt-Date.now()>50000) {
      diagnostic("il-public-retry",job,result.reason);
      await registryNavigate(job, registryStart("IL"));
      result = await collect();
      if (result?.reason === "NY_CONNECTOR_IL_VERIFICATION_PENDING")
        result = await registryIllinoisVerification(job, collect);
    }
    job.ilReusableForm = result?.ok === true && !Object.hasOwn(query,"identifier");
    return result;
  }
  if (Object.hasOwn(query,"identifier")) {
    // GA invalidates earlier-page detail links after another result page is
    // visited. Reopen the same public search and locate the requested license
    // before following its currently displayed link. The master still owns
    // selection and confirms the requested license in the returned body.
    const legacy = ["", "EXEMPT"].includes(query.identifier);
    const source=job.gaSearchByIdentifier?.[legacy ? query.detail_key : query.identifier];
    if(!source)throw new Error("NY_CONNECTOR_INCOMPLETE");
    const current=await registryGaSearch(job,source,query.identifier,legacy ? query : null);
    if(!current?.detail_key)throw new Error("NY_CONNECTOR_INCOMPLETE");
    const detailStarted=Date.now();
    if(P.TRIAL_ORIGIN)diagnostic('ga-detail-navigation-start',job,'open selected public detail');
    await registryNavigate(job,registryOrigin("GA")+"/verification/Details.aspx?result="+current.detail_key);
    if(P.TRIAL_ORIGIN)diagnostic('ga-detail-navigation-done',job,`ms=${Date.now()-detailStarted}`);
    const result=await registryMessage(job,{action:"registry-ga-detail",query});
    if(P.TRIAL_ORIGIN)diagnostic('ga-detail-command',job,`ms=${Date.now()-detailStarted} ${result?.ok?'complete':result?.reason||'incomplete'}`);
    return result;
  }
  return registryGaSearch(job,query);
}
async function registryNorthCarolinaQuery(job,query) {
  if(query.operation==='search') {
    job.ncSubmissionObservations=[];job.ncSubmissionSignature=null;
    const prior=await registryNavigate(job,registryStart('NC'));
    const submitted=await registryMessage(job,{action:'registry-nc-form',query});
    if(!submitted?.ok||submitted.phase!=='submitted')throw new Error('NY_CONNECTOR_INCOMPLETE');
    await registryReady(job,prior.documentId,'/online_services/search/Charities_Results',45000,query);
    const result=await registryMessage(job,{action:'registry-nc-rows',query,budgetMs:Math.max(1,Math.min(45000,job.activeExpiresAt-Date.now()))});
    if(result?.ok && result.evidence?.complete===true) {
      for(const entry of Array.isArray(result.diagnostics)?result.diagnostics.slice(0,1):[]) {
        if(entry?.phase==='pending-count' && [entry.displayed,entry.cards,entry.groups].every(n=>Number.isInteger(n)&&n>=0&&n<=100))
          diagnostic('nc-count',job,`Pending application cards retained: displayed=${entry.displayed}; cards=${entry.cards}; groups=${entry.groups}`);
      }
      job.ncProfiles ||= Object.create(null);
      for(const row of result.evidence.rows||[])job.ncProfiles[row.License]=row.profile_url;
    }
    return result;
  }
  if(job.ncProfiles?.[query.identifier]!==query.url)throw new Error('NY_CONNECTOR_INVALID_SEQUENCE');
  await registryNavigate(job,query.url);
  const profile=await registryMessage(job,{action:'registry-nc-profile',query});
  if(!profile?.ok)return profile;
  const expected=query.url.replace('/charities_profile/','/charities_filings/');
  if(profile.filings_url===expected) {
    profile.evidence.filings={url:expected,complete:false,rows:[]};
    if(job.activeExpiresAt-Date.now()>5000) {
      try {
        await registryNavigate(job,expected,Math.min(8000,job.activeExpiresAt-Date.now()-1000));
        const history=await registryMessage(job,{action:'registry-nc-filings',query});
        if(history?.ok)profile.evidence.filings=history.filings;
      } catch { /* Optional history cannot invalidate a complete profile. */ }
    }
  }
  return {ok:true,evidence:profile.evidence};
}
async function registryGaSearch(job, query, requestedIdentifier=null, selectedRecord=null) {
  let phaseStarted=Date.now(), totalStarted=phaseStarted;
  const phase=name=>{
    const elapsed=Date.now()-phaseStarted;phaseStarted=Date.now();
    if(P.TRIAL_ORIGIN)diagnostic('ga-phase',job,`${name} ms=${elapsed} total_ms=${phaseStarted-totalStarted}`);
  };
  if(P.TRIAL_ORIGIN)diagnostic('ga-search-start',job,requestedIdentifier===null?'name search':'record detail');
  let document=await registryNavigate(job,registryStart("GA"));
  phase('navigate');
  let form=await registryMessage(job,{action:"registry-ga-form",query});
  phase('form');
  if (form.phase === "profession") {
    document=await registryReady(job,document.documentId,"/verification/Search.aspx");
    phase('profession-ready');
    form=await registryMessage(job,{action:"registry-ga-form",query});
    phase('profession-form');
  }
  if (!form.ok || form.phase!=="submitted") throw new Error("NY_CONNECTOR_INCOMPLETE");
  document=await registryReady(job,document.documentId,"/verification/SearchResults.aspx");
  phase('results-ready');
  const rows=[];
  for(let page=1;page<=10;page++) {
    const result=await registryMessage(job,{action:"registry-ga-rows"});
    phase('rows');
    if(!result.ok || result.page!==page || !Array.isArray(result.rows)) throw new Error("NY_CONNECTOR_INCOMPLETE");
    if(requestedIdentifier !== null) {
      const found=result.rows.filter(row=>row.identifier===requestedIdentifier && (!selectedRecord
        || row.name===selectedRecord.record_name && row.location===selectedRecord.record_location));
      if(found.length>1)throw new Error("NY_CONNECTOR_INCOMPLETE");
      if(found.length===1)return found[0];
    } else {
      job.gaSearchByIdentifier ||= Object.create(null);
      for(const row of result.rows)job.gaSearchByIdentifier[["", "EXEMPT"].includes(row.identifier) ? row.detail_key : row.identifier]={...query};
    }
    rows.push(...result.rows);
    if(rows.length>100) throw new Error("NY_CONNECTOR_INCOMPLETE");
    if(!result.next) {
      if(requestedIdentifier !== null)throw new Error("NY_CONNECTOR_INCOMPLETE");
      return {ok:true,evidence:{query,complete:true,total:rows.length,rows}};
    }
    const next=await registryMessage(job,{action:"registry-ga-next",page:page+1});
    phase('next-page');
    if(!next.ok) throw new Error("NY_CONNECTOR_INCOMPLETE");
    document=await registryReady(job,document.documentId,"/verification/SearchResults.aspx");
    phase('page-ready');
  }
  throw new Error("NY_CONNECTOR_INCOMPLETE");
}
