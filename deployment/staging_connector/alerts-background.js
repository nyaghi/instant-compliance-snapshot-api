(() => {
  if (!chrome.alarms) return;
  const URL = P.TRIAL_ORIGIN + '/alerts-runner.html';
  const ALARM = 'charityclarity-alerts';
  const PROFILE = 'ccAlertsProfile';
  const OWNED = 'ccAlertsRunnerTab';
  let opening = false;

  async function closeOwned(record) {
    if (!record) return;
    const tab = await chrome.tabs.get(record.id).catch(() => null);
    if (tab && [tab.url, tab.pendingUrl].includes(URL)) await chrome.tabs.remove(tab.id).catch(() => {});
    await chrome.storage.session.remove(OWNED);
  }

  async function openRunner() {
    if (opening) return;
    opening = true;
    try {
      const {[PROFILE]:profile} = await chrome.storage.local.get(PROFILE);
      if (!profile || allJobs().some(job => !job.closed)) return;
      const {[OWNED]:record} = await chrome.storage.session.get(OWNED);
      if (record && Date.now()-record.started<600000) {
        const tab=await chrome.tabs.get(record.id).catch(() => null);
        if (tab && [tab.url,tab.pendingUrl].includes(URL)) return;
      }
      await closeOwned(record);
      const tab=await chrome.tabs.create({url:URL,active:false});
      await chrome.storage.session.set({[OWNED]:{id:tab.id,started:Date.now()}});
    } finally {
      opening = false;
    }
  }

  async function ensureAlarm() {
    const {[PROFILE]:profile}=await chrome.storage.local.get(PROFILE);
    if (profile && !await chrome.alarms.get(ALARM))
      await chrome.alarms.create(ALARM,{delayInMinutes:0.5,periodInMinutes:5});
  }

  async function act(message,sender) {
    const path=new globalThis.URL(sender.url).pathname;
    if (path==='/alerts/' || path==='/alerts' || path==='/alerts.html') {
      if (message.action==='status') {
        const {[PROFILE]:profile}=await chrome.storage.local.get(PROFILE);
        return {ok:true,enabled:!!profile,quiet:true};
      }
      if (message.action==='enable' && /^[A-Za-z0-9_-]{43}$/.test(message.profile || '')) {
        await chrome.storage.local.set({[PROFILE]:message.profile});
        await ensureAlarm();
        // The first check is launched by the same alarm as future checks.
        return {ok:true,enabled:true};
      }
      if (message.action==='disable') {
        await chrome.storage.local.remove(PROFILE);
        await chrome.alarms.clear(ALARM);
        const {[OWNED]:record}=await chrome.storage.session.get(OWNED);
        await closeOwned(record);
        return {ok:true,enabled:false};
      }
    }
    if (path!=='/alerts-runner.html') return {ok:false};
    const {[OWNED]:record}=await chrome.storage.session.get(OWNED);
    if (record?.id!==sender.tab.id) return {ok:false};
    if (message.action==='config') {
      const {[PROFILE]:profile}=await chrome.storage.local.get(PROFILE);
      return {ok:!!profile,profile,quiet:true};
    }
    if (message.action==='done') {
      await closeOwned(record);
      return {ok:true};
    }
    return {ok:false};
  }

  chrome.runtime.onMessage.addListener((message,sender,respond) => {
    if (message?.type!=='cc-alerts-background' || !allowedSender(sender)) return false;
    act(message,sender).then(respond,()=>respond({ok:false}));
    return true;
  });
  chrome.alarms.onAlarm.addListener(alarm => {
    if (alarm.name===ALARM) void openRunner().catch(()=>{});
  });
  chrome.runtime.onStartup.addListener(()=>{void ensureAlarm().catch(()=>{});});
  chrome.runtime.onInstalled.addListener(()=>{void ensureAlarm().catch(()=>{});});
  void ensureAlarm().catch(()=>{});
})();
