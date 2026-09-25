/* IL/GA transport module of the existing connector; no independent runtime. */
const registryOrigin = state => state === "IL" ? "https://charitable.illinoisattorneygeneral.gov" : "https://verify.sos.ga.gov";
const registryStart = state => registryOrigin(state) + (state === "IL" ? "/search" : "/verification/Search.aspx?facility=Y");
async function registryMessage(job, message) {
  if (job.closed || Date.now() >= job.activeExpiresAt) throw new Error("NY_CONNECTOR_TIMEOUT");
  const tab = await chrome.tabs.get(job.tab);
  if (new URL(tab.url).origin !== registryOrigin(job.registryState)) throw new Error("NY_CONNECTOR_INCOMPLETE");
  return chrome.tabs.sendMessage(job.tab, message, {frameId:0});
}
async function registryReady(job, oldDocument = null, path = null) {
  const deadline = Math.min(Date.now()+45000, job.activeExpiresAt);
  while (!job.closed && Date.now()<deadline) {
    try {
      const value=await registryMessage(job,{action:"registry-ready"});
      if (value?.ready && value.documentId !== oldDocument && (!path || new URL(value.url).pathname===path)) return value;
    } catch { /* Navigation or the normal public verification page is loading. */ }
    await nap(200);
  }
  throw new Error("NY_CONNECTOR_TAB_READY_TIMEOUT");
}
async function registryNavigate(job, url) {
  if (new URL(url).origin !== registryOrigin(job.registryState)) throw new Error("NY_CONNECTOR_INCOMPLETE");
  let previous;
  if (job.tab !== null) {
    try { previous=(await registryMessage(job,{action:"registry-ready"})).documentId; } catch {}
    // Updating a tab to its current URL may leave the same document in place.
    // Explicitly reload so the next search starts with a fresh public form.
    const current = await chrome.tabs.get(job.tab);
    if (current.url === url) await chrome.tabs.reload(job.tab);
    else await chrome.tabs.update(job.tab,{url});
  } else {
    const origin=await chrome.tabs.get(job.sender.tab.id);
    job.creating=chrome.tabs.create({windowId:origin.windowId,url,active:false});
    const tab=await job.creating; job.creating=null; job.tab=tab.id; owned.add(tab.id); await saveRuntime();
  }
  return registryReady(job,previous,new URL(url).pathname);
}
async function performRegistryQuery(job, query) {
  if (!P.validQuery(query) || query.state !== job.registryState || new URL(job.sender.url).origin !== P.STAGING) throw new Error("NY_CONNECTOR_INVALID_SEQUENCE");
  if (query.state === "IL") {
    await registryNavigate(job, registryStart("IL"));
    return registryMessage(job,{action:"registry-il",query});
  }
  if (query.identifier) {
    await registryNavigate(job,registryOrigin("GA")+"/verification/Details.aspx?result="+query.detail_key);
    return registryMessage(job,{action:"registry-ga-detail",query});
  }
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
    rows.push(...result.rows);
    if(rows.length>100) throw new Error("NY_CONNECTOR_INCOMPLETE");
    if(!result.next) return {ok:true,evidence:{query,complete:true,total:rows.length,rows}};
    const next=await registryMessage(job,{action:"registry-ga-next",page:page+1});
    if(!next.ok) throw new Error("NY_CONNECTOR_INCOMPLETE");
    document=await registryReady(job,document.documentId,"/verification/SearchResults.aspx");
  }
  throw new Error("NY_CONNECTOR_INCOMPLETE");
}
