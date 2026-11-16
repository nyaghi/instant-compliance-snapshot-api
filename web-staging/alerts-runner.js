(async () => {
  const status=document.getElementById('runner-status');
  const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  let settled=true;
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
    if(!browser?.ok || browser.quiet !== true)return;
    const deadline=Date.now()+480000;
    while(Date.now()<deadline){
      // The alarm's idle check is not a lease for the entire roster. Recheck
      // between organizations so a requested Aurora run takes the next turn.
      const permission=await window.CCAlertsBrowser('config');
      if(!permission?.ok)break;
      const job=await post('claim',{profile:browser.profile});
      if(job.retry){await pause(6000);continue;}
      if(!job.lease)break;
      settled=false;
      status.textContent='Checking '+job.name;
      try {
        const checkDeadline = Math.min(deadline, Date.now() + 310000);
        const signal=AbortSignal.timeout(310000);
        await Promise.allSettled(job.states.map(async state => {
          const input = {
            state, organization_name:job.name, ein:job.ein, alternate_names:job.aliases,
            alertLease:job.lease, signal
          };
          const result = await window.CCNYConnector.lookup(input);
          const diagnostic = result?.lab_diagnostic;
          if (state === 'TN' && result?.success === false
              && ['NY_CONNECTOR_TN_VERIFICATION_PENDING', 'NY_CONNECTOR_TN_VERIFICATION_OR_FORM_PENDING'].includes(diagnostic?.code)
              && diagnostic.completed_count === 0 && diagnostic.pending_operation === 'search'
              && checkDeadline - Date.now() >= 60000 && !signal.aborted) {
            await pause(3000);
            if (!signal.aborted) await window.CCNYConnector.lookup(input);
          }
        }));
      } finally {
        let result=await post('finish',{lease:job.lease});
        while(result.pending && Date.now()<deadline) {
          await pause(1000);
          result=await post('finish',{lease:job.lease});
        }
        settled=!result.pending;
        if(!settled)throw Error('Scheduled check is still finishing.');
      }
    }
    status.textContent='Scheduled checks finished.';
  } catch {
    status.textContent='Scheduled checks will retry when Chrome is available.';
  } finally {
    // Keep the bounded owned-runner reservation if server completion could
    // not be confirmed. Never tell Aurora the browser is idle prematurely.
    if(settled)await window.CCAlertsBrowser('done');
  }
})();
