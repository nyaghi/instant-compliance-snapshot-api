/* Public-registry transport in the existing connector; no independent runtime. */
const registryOrigin = state => ({IL:"https://charitable.illinoisattorneygeneral.gov",GA:"https://verify.sos.ga.gov",AL:"https://ago.igovsolution.net",NC:"https://www.sosnc.gov",NV:"https://orion.nv.gov",TN:"https://tncab.tnsos.gov"})[state];
const registryStart = state => registryOrigin(state) + ({IL:"/search",GA:"/verification/Search.aspx?facility=Y",AL:"/online/Lookups/Business.aspx",NC:"/online_services/search/by_title/search_charities",NV:"/portal/public/#/public/nvsos/en/CaseXscreen?screen=external-GenericFilingsSearch&tabRoute=business",TN:"/portal/registered-charities-search"})[state];
async function registryMessage(job, message) {
  if (job.closed || Date.now() >= job.activeExpiresAt) throw new Error("NY_CONNECTOR_TIMEOUT");
  const tab = await chrome.tabs.get(job.tab);
  if (new URL(tab.url).origin !== registryOrigin(job.registryState)) throw new Error("NY_CONNECTOR_INCOMPLETE");
  return chrome.tabs.sendMessage(job.tab, message, {frameId:0});
}
async function registryReady(job, oldDocument = null, path = null, budgetMs = 45000, ncSubmittedQuery = null) {
  const started = Date.now();
  const deadline = Math.min(Date.now()+Math.max(1,Math.min(45000,budgetMs)), job.activeExpiresAt);
  let verificationPending=false, visibilityAttempted=false, previousVisible=null, submissionRetried=false;
  try { while (!job.closed && Date.now()<deadline) {
    try {
      const value=await registryMessage(job,{action:"registry-ready"});
      verificationPending=job.registryState==='NC'&&value?.verification_pending===true;
      if (value?.ready && value.documentId !== oldDocument && (!path || new URL(value.url).pathname===path)) return value;
      // An acknowledged NC Search can leave the same ordinary, enabled form
      // without navigating. Retry once only after observing that exact form;
      // disabled Processing and verification pages are never resubmitted.
      // The original deadline and expected results document stay unchanged.
      if (ncSubmittedQuery && job.registryState==='NC' && !submissionRetried && !verificationPending
          && Date.now()-started>=3000 && Date.now()<deadline && value?.ready && value.documentId===oldDocument
          && new URL(value.url).pathname==='/online_services/search/by_title/search_charities') {
        submissionRetried=true;
        const retried=await registryMessage(job,{action:'registry-nc-retry',query:ncSubmittedQuery});
        diagnostic('nc-submit-recovery',job,retried?.phase==='submitted'?'same-query resubmitted':'form changed; no resubmission');
      }
    } catch {
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
    await nap(200);
  }
  throw new Error(verificationPending ? "NY_CONNECTOR_NC_VERIFICATION_PENDING" : "NY_CONNECTOR_TAB_READY_TIMEOUT");
  } finally {
    if (previousVisible) try {
      const tab=await chrome.tabs.get(job.tab), prior=await chrome.tabs.get(previousVisible.id);
      if (owned.has(job.tab) && tab.active && tab.windowId===previousVisible.windowId && prior.windowId===tab.windowId
          && new URL(tab.url).origin===registryOrigin('NC') && (!path || new URL(tab.url).pathname===path))
        await chrome.tabs.update(prior.id,{active:true});
    } catch { /* Preserve user navigation or closure during verification. */ }
  }
}
async function registryNorthCarolinaVisibility(job) {
  // Same-document visibility recovery, as used for Illinois. The state's own
  // scripts may finish a passive verification; no checkbox, challenge, token,
  // cookie, reload, additional request, or budget extension is performed here.
  if (job.registryState!=='NC' || job.closed || !owned.has(job.tab)) return null;
  try {
    const tab=await chrome.tabs.get(job.tab), source=await chrome.tabs.get(job.sender.tab.id);
    if (tab.active || tab.windowId!==source.windowId || new URL(tab.url).origin!==registryOrigin('NC')
        || !new URL(tab.url).pathname.startsWith('/online_services/search/')) return null;
    const prior=(await chrome.tabs.query({active:true,windowId:tab.windowId}))[0];
    if (!prior || prior.id===tab.id || job.closed || !owned.has(job.tab)) return null;
    diagnostic('nc-verification',job,'same-document visibility recovery');
    await chrome.tabs.update(tab.id,{active:true});
    return {id:prior.id,windowId:prior.windowId};
  } catch { return null; }
}
async function registryNavigate(job, url, budgetMs = 45000) {
  if (new URL(url).origin !== registryOrigin(job.registryState)) throw new Error("NY_CONNECTOR_INCOMPLETE");
  let previous;
  if (job.tab !== null) {
    try { previous=(await registryMessage(job,{action:"registry-ready"})).documentId; } catch {}
    // Updating a tab to its current URL may leave the same document in place.
    // Explicitly reload so the next search starts with a fresh public form.
    const current = await chrome.tabs.get(job.tab);
    if (current.url === url) await chrome.tabs.reload(job.tab);
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
    job.creating=chrome.tabs.create({windowId:origin.windowId,url,active:false});
    const tab=await job.creating; job.creating=null; job.tab=tab.id; owned.add(tab.id); await saveRuntime();
  }
  return registryReady(job,previous,new URL(url).pathname,budgetMs);
}
async function registryIllinoisVerification(job, collect) {
  // Preserve the verification document. Reloading here resets Illinois's
  // normal challenge instead of recovering it. Only activate our owned tab;
  // the state's own code must enable Search before collection can proceed.
  if (job.closed || !owned.has(job.tab) || job.activeExpiresAt-Date.now() <= 45000)
    return {ok:false,reason:"NY_CONNECTOR_IL_VERIFICATION_PENDING"};
  const tab = await chrome.tabs.get(job.tab);
  const origin = await chrome.tabs.get(job.sender.tab.id);
  if (tab.url !== registryStart("IL") || tab.windowId !== origin.windowId)
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
  if (query.state === "AL") {
    if (job.tab === null && trialAlIdle) {
      const saved=trialAlIdle; trialAlIdle=null;
      try {
        const tab=await chrome.tabs.get(saved.id), source=await chrome.tabs.get(job.sender.tab.id);
        if (owned.has(saved.id) && tab.url===registryStart('AL') && tab.windowId===source.windowId && saved.expiresAt>Date.now()) job.tab=saved.id;
        else await removeOwned(saved.id);
      } catch { await removeOwned(saved.id); }
      await saveRuntime();
    }
    if (job.tab===null) await registryNavigate(job,registryStart('AL'));
    else await registryReady(job,null,'/online/Lookups/Business.aspx');
    // Reuse only the connector-owned verified page. Each command must observe
    // a fresh result; no verification code or previous result is shared.
    return registryMessage(job,{action:'registry-al',query,budgetMs:Math.max(1,Math.min(45000,job.activeExpiresAt-Date.now()))});
  }
  if (query.state === "NC") return registryNorthCarolinaQuery(job,query);
  if (["NV", "TN"].includes(query.state)) {
    if (query.operation === "search") {
      if (query.state==='NV' && job.tab!==null && !job.finalFourReusableForm) {
        const returned=await registryMessage(job,{action:'registry-nv-return',budgetMs:Math.max(1,Math.min(45000,job.activeExpiresAt-Date.now()))});
        if (!returned?.ok) throw new Error(returned?.reason||'NY_CONNECTOR_INCOMPLETE');
        await registryReady(job,null,new URL(registryStart('NV')).pathname);
      } else if (job.tab === null || !job.finalFourReusableForm) await registryNavigate(job,registryStart(query.state));
      else await registryReady(job,null,new URL(registryStart(query.state)).pathname);
    } else if (job.tab === null || !job.finalFourSearchComplete) {
      throw new Error("NY_CONNECTOR_INVALID_SEQUENCE");
    }
    job.finalFourReusableForm = false;
    const response = await registryMessage(job,{action:`registry-${query.state.toLowerCase()}`,query,budgetMs:Math.max(1,Math.min(45000,job.activeExpiresAt-Date.now()))});
    if (query.operation === "search") job.finalFourSearchComplete = response?.ok === true;
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
    let result = await collect(12000);
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
    await registryNavigate(job,registryOrigin("GA")+"/verification/Details.aspx?result="+current.detail_key);
    return registryMessage(job,{action:"registry-ga-detail",query});
  }
  return registryGaSearch(job,query);
}
async function registryNorthCarolinaQuery(job,query) {
  if(query.operation==='search') {
    const prior=await registryNavigate(job,registryStart('NC'));
    const submitted=await registryMessage(job,{action:'registry-nc-form',query});
    if(!submitted?.ok||submitted.phase!=='submitted')throw new Error('NY_CONNECTOR_INCOMPLETE');
    await registryReady(job,prior.documentId,'/online_services/search/Charities_Results',45000,query);
    const result=await registryMessage(job,{action:'registry-nc-rows',query,budgetMs:Math.max(1,Math.min(45000,job.activeExpiresAt-Date.now()))});
    if(result?.ok && result.evidence?.complete===true) {
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
  let document=await registryNavigate(job,registryStart("GA"));
  let form=await registryMessage(job,{action:"registry-ga-form",query});
  if (form.phase === "profession") {
    document=await registryReady(job,document.documentId,"/verification/Search.aspx");
    form=await registryMessage(job,{action:"registry-ga-form",query});
  }
  if (!form.ok || form.phase!=="submitted") throw new Error("NY_CONNECTOR_INCOMPLETE");
  document=await registryReady(job,document.documentId,"/verification/SearchResults.aspx");
  const rows=[];
  for(let page=1;page<=10;page++) {
    const result=await registryMessage(job,{action:"registry-ga-rows"});
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
    if(!next.ok) throw new Error("NY_CONNECTOR_INCOMPLETE");
    document=await registryReady(job,document.documentId,"/verification/SearchResults.aspx");
  }
  throw new Error("NY_CONNECTOR_INCOMPLETE");
}
