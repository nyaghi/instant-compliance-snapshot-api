/* Execution transport only; all identity and status decisions stay in the master. */
(() => {
  'use strict';
  if (location.origin !== 'https://staging.compliance-express.com') return;
  async function run(options) {
    const {apiBase, name, ein, states, aliases=[], mode='standard', credentials,
      signal, onResult=()=>{}, externalLookup} = options;
    const results=new Map(), external=states.filter(s=>s==='IL'||s==='GA');
    let token=null, externalDone=false, released=false;
    const requestId=crypto.randomUUID();
    const missing=state=>({state,ein,organization_name:name,status:'Unable to Confirm',success:false,
      comments:'The state check did not provide a complete response. Registration status remains unconfirmed.'});
    const record=result=>{
      if(signal?.aborted || !states.includes(result.state) || results.has(result.state)) return;
      results.set(result.state,result);onResult(result);
    };
    async function call(action,extra={},detached=false) {
      const timeout=AbortSignal.timeout(detached?10000:25000);
      const response=await fetch(apiBase+'/api/workflow',{method:'POST',
        headers:{'Content-Type':'application/json'},signal:!detached&&signal?AbortSignal.any([signal,timeout]):timeout,
        body:JSON.stringify({...credentials,action,token,...extra})});
      if(!response.ok) throw new Error('State-check progress is temporarily unavailable ('+response.status+').');
      return response.json();
    }
    const cancel=()=>{if(token) void call('cancel',{},true).catch(()=>{});};
    signal?.throwIfAborted();signal?.addEventListener('abort',cancel,{once:true});
    const connector=Promise.all(external.map(async state=>{
      try{record(await externalLookup(state));}catch{if(!signal?.aborted)record(missing(state));}
    })).then(()=>{externalDone=true;});
    try {
      if(states.length>external.length) {
        const payload={organization_name:name,ein,alternate_names:aliases,states,mode,consent:true,request_id:requestId};
        let accepted;
        try{accepted=await call('start',payload);}catch(error){
          signal?.throwIfAborted();accepted=await call('start',payload); // same idempotency key
        }
        token=accepted.token;
        if(signal?.aborted){cancel();signal.throwIfAborted();}
        let failures=0;
        const deadline=performance.now()+900000;
        while(performance.now()<deadline) {
          signal?.throwIfAborted();
          if(externalDone&&!released&&external.length){
            try{await call('release-external');released=true;}catch{signal?.throwIfAborted();}
          }
          let progress;
          try{progress=await call('poll');failures=0;}catch(error){
            signal?.throwIfAborted();if(++failures>=5)throw error;
          }
          if(progress){
            for(const result of progress.results)record(result);
            if(progress.finished!==null)break;
          }
          await new Promise(resolve=>setTimeout(resolve,500));
        }
      }
      await connector;
      for(const state of states)if(!results.has(state))record(missing(state));
      return states.map(state=>results.get(state));
    } catch(error) {
      cancel();
      if(signal?.aborted)throw error;
      await connector;
      for(const state of states)if(!results.has(state))record(missing(state));
      return states.map(state=>results.get(state));
    } finally {signal?.removeEventListener('abort',cancel);}
  }
  window.CCOptimized=Object.freeze({run,version:'2026.09.28.5-staging'});
})();
