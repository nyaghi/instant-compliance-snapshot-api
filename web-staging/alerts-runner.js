(async () => {
  const status=document.getElementById('runner-status');
  const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  async function post(action,data) {
    const response=await fetch('/api/alerts/runner/'+action,{method:'POST',
      headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',
      signal:AbortSignal.timeout(30000),body:JSON.stringify(data)});
    if(!response.ok)throw Error('Scheduled check unavailable.');
    return response.json();
  }
  try {
    let browser;
    for(let attempt=0;attempt<4;attempt++){
      browser=await window.CCAlertsBrowser('config');
      if(browser.ok)break;
      await pause(600);
    }
    if(!browser?.ok)return;
    const deadline=Date.now()+480000;
    while(Date.now()<deadline){
      const job=await post('claim',{profile:browser.profile});
      if(job.retry){await pause(6000);continue;}
      if(!job.lease)break;
      status.textContent='Checking '+job.name;
      try {
        const signal=AbortSignal.timeout(310000);
        await Promise.allSettled(job.states.map(state=>window.CCNYConnector.lookup({
          state,organization_name:job.name,ein:job.ein,alternate_names:job.aliases,
          alertLease:job.lease,signal
        })));
      } finally {
        await post('finish',{lease:job.lease});
      }
    }
    status.textContent='Scheduled checks finished.';
  } catch {
    status.textContent='Scheduled checks will retry when Chrome is available.';
  } finally {
    await window.CCAlertsBrowser('done');
  }
})();
