/* Execution transport only; all identity and status decisions stay in the master. */
(() => {
  'use strict';
  if (location.origin !== 'https://staging.compliance-express.com') return;
  async function run(options) {
    const {apiBase, name, ein, states, aliases=[], mode='standard', credentials,
      signal, onResult=()=>{}, externalLookup} = options;
    const results=new Map(), external=states.filter(s=>s==='IL'||s==='GA');
    const evidenceTasks=[];
    const needsIdentity=mode==='sales'&&external.length>0&&aliases.length===0;
    let token=null, externalDone=false, released=false;
    const settledExternal=new Set();
    let progressiveRelease=false, releasedCount=0;
    const requestId=crypto.randomUUID();
    const missing=state=>({state,ein,organization_name:name,status:'Unable to Confirm',success:false,
      comments:'The state check did not provide a complete response. Registration status remains unconfirmed.'});
    const record=result=>{
      if(signal?.aborted || !states.includes(result.state) || results.has(result.state)) return;
      results.set(result.state,result);onResult(result);
      if(['WI','DC'].includes(result.state) && result.desktop_evidence_request && !result.evidence_url)
        evidenceTasks.push(captureOriginal(result));
    };
    async function call(action,extra={},detached=false) {
      const timeout=AbortSignal.timeout(detached?10000:25000);
      const response=await fetch(apiBase+'/api/workflow',{method:'POST',
        headers:{'Content-Type':'application/json'},signal:!detached&&signal?AbortSignal.any([signal,timeout]):timeout,
        body:JSON.stringify({...credentials,action,token,...extra})});
      if(!response.ok) {
        if(response.status===503) {
          const detail=await response.json().catch(()=>null);
          if(detail?.code==='PERFORMANCE_LAB_EXPIRED') {
            const error=new Error(detail.error);
            error.code=detail.code;
            throw error;
          }
        }
        throw new Error('State-check progress is temporarily unavailable ('+response.status+').');
      }
      return response.json();
    }
    async function captureOriginal(result) {
      const started=performance.now();
      let sourceObservation=null, evidencePhase='capture';
      try {
        if(signal?.aborted)return;
        const id=crypto.randomUUID(),channel='cc-owned-source-evidence-v1';
        const captured=await new Promise(resolve=>{
          let timer;
          const cleanup=()=>{clearTimeout(timer);window.removeEventListener('message',receive);signal?.removeEventListener('abort',abort);};
          const abort=()=>{cleanup();resolve({ok:false,reason:'cancelled'});};
          const receive=event=>{
            if(event.source!==window || event.origin!==location.origin || event.data?.channel!==channel || event.data.direction!=='response' || event.data.id!==id)return;
            cleanup();resolve(event.data.result||{ok:false});
          };
          window.addEventListener('message',receive);signal?.addEventListener('abort',abort,{once:true});
          timer=setTimeout(()=>{cleanup();resolve({ok:false,reason:'capture_timeout'});},result.state==='DC'?32000:22000);
          window.postMessage({channel,direction:'request',id,request:result.desktop_evidence_request},location.origin);
        });
        sourceObservation={phase:'capture',reason:typeof captured.reason==='string'
          && /^[a-zA-Z0-9_.:-]{1,100}$/.test(captured.reason)?captured.reason:'',timing:captured.timing||null};
        if(signal?.aborted || !captured.ok)return;
        evidencePhase='archive_request';
        const response=await fetch(apiBase+'/api/source-evidence',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+credentials.admin_passcode},
          signal:signal?AbortSignal.any([signal,AbortSignal.timeout(6000)]):AbortSignal.timeout(6000),
          body:JSON.stringify({...credentials,token,state:result.state,completion:captured})});
        evidencePhase='archive_decode';
        sourceObservation.http_status=response.status;
        const saved=await response.json();
        evidencePhase='archive_binding';
        if(response.ok && /^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(saved.evidence_url||'')){
          for(const key of ['evidence_url','evidence_capture','evidence_captured_at','evidence_metrics','desktop_evidence_timing','search_history_url','search_history_capture'])
            if(Object.hasOwn(saved,key))result[key]=saved[key];
        }
        sourceObservation.phase=result.evidence_url?'complete':'archive_rejected';
      } catch(error) {
        sourceObservation={...(sourceObservation||{}),phase:evidencePhase,
          error_type:['TimeoutError','AbortError','TypeError','SyntaxError'].includes(error?.name)?error.name:'Error'};
        /* Evidence failure never replaces the state status. */
      }
      finally {
        result.desktop_evidence_seconds=(performance.now()-started)/1000;
        if(Array.isArray(window.__CCLabStateTrace)){
          window.__CCLabStateTrace.push({at:Date.now(),state:result.state,stage:'desktop evidence completed',
            source_observation:sourceObservation,
            seconds:result.desktop_evidence_seconds,captured:!!result.evidence_url,timing:result.desktop_evidence_timing||null});
          if(window.__CCLabStateTrace.length>2000)window.__CCLabStateTrace.splice(0,window.__CCLabStateTrace.length-2000);
        }
      }
    }
    // A successful archive can outlive its browser acknowledgement. Read the
    // existing workflow once; never repeat a source search or screenshot here.
    async function reconcileSavedEvidence() {
      if (!token || signal?.aborted) return;
      const pending = [...results.values()].filter(r => ['WI','DC'].includes(r.state)
        && r.desktop_evidence_request && !r.evidence_url);
      if (!pending.length) return;
      try {
        const progress = await call('poll');
        for (const result of pending) {
          if (signal?.aborted || result.evidence_url) continue;
          const matches = (progress.results || []).filter(r => r.state === result.state);
          if (matches.length !== 1) continue;
          const saved = matches[0];
          const fields = ['state','ein','organization_name','status','success',
            'matched_registry_identifier','matched_registry_name','raw_status_text',
            'confirmation_required','execution_version'];
          if (!fields.every(k => saved[k] === result[k]) || saved.confirmation_required) continue;
          if (saved.evidence_capture !== 'captured' ||
              !/^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(saved.evidence_url || '') ||
              !Number.isFinite(saved.evidence_captured_at) ||
              !Number.isFinite(result.desktop_evidence_request.issued_at) ||
              saved.evidence_captured_at < result.desktop_evidence_request.issued_at - 1) continue;
          for (const key of ['evidence_url','evidence_capture','evidence_captured_at',
            'evidence_metrics','desktop_evidence_timing','search_history_url','search_history_capture'])
            if (Object.hasOwn(saved,key)) result[key] = saved[key];
          if (Array.isArray(window.__CCLabStateTrace)) {
            window.__CCLabStateTrace.push({at:Date.now(),state:result.state,
              stage:'saved evidence reconciled',captured:true});
            if (window.__CCLabStateTrace.length>2000) window.__CCLabStateTrace.splice(0,window.__CCLabStateTrace.length-2000);
          }
        }
      } catch { /* Preserve the original result when persistence is unavailable. */ }
    }
    const cancel=()=>{if(token) void call('cancel',{},true).catch(()=>{});};
    signal?.throwIfAborted();signal?.addEventListener('abort',cancel,{once:true});
    let connector=Promise.resolve(),connectorStarted=false;
    const startConnector=(names,confirmed=true)=>{
      if(connectorStarted||signal?.aborted)return;
      connectorStarted=true;
      connector=Promise.all(external.map(async state=>{
        try{
          let result=await externalLookup(state,names);
          if(!confirmed&&/^Not Registered/.test(result.status||''))result={...missing(state),
            status_reason:'SALES_IDENTITY_INCOMPLETE',
            comments:'The Sales name-evidence step was incomplete. A negative name-only search cannot confirm non-registration. Run Standard for a full check.'};
          record(result);
        }catch{if(!signal?.aborted)record(missing(state));}
        finally{settledExternal.add(state);}
      })).then(()=>{externalDone=true;});
    };
    if(!needsIdentity)startConnector(aliases);
    try {
      if(states.length>external.length||needsIdentity) {
        const payload={organization_name:name,ein,alternate_names:aliases,states,mode,consent:true,request_id:requestId};
        let accepted;
        try{accepted=await call('start',payload);}catch(error){
          if(error.code==='PERFORMANCE_LAB_EXPIRED')throw error;
          signal?.throwIfAborted();accepted=await call('start',payload); // same idempotency key
        }
        token=accepted.token;
        progressiveRelease=accepted.progressive_external_release===true;
        if(signal?.aborted){cancel();signal.throwIfAborted();}
        let failures=0;
        const deadline=performance.now()+900000;
        while(performance.now()<deadline) {
          signal?.throwIfAborted();
          if(!progressiveRelease&&externalDone&&!released&&external.length){
            try{await call('release-external');released=true;}catch{signal?.throwIfAborted();}
          }
          let progress;
          const settled_count=settledExternal.size;
          const update=progressiveRelease&&settled_count>releasedCount?{settled_count}:{};
          try{progress=await call('poll',update);releasedCount=settled_count;failures=0;}catch(error){
            signal?.throwIfAborted();if(++failures>=5)throw error;
          }
          if(progress){
            if(needsIdentity&&progress.connector_identity?.ready){
              const identity=progress.connector_identity;
              startConnector(identity.names,identity.confirmed===true);
            }
            for(const result of progress.results)record(result);
            if(progress.finished!==null)break;
          }
          await new Promise(resolve=>setTimeout(resolve,500));
        }
      }
      await connector;
      for(const state of states)if(!results.has(state))record(missing(state));
      await Promise.all(evidenceTasks);
      await reconcileSavedEvidence();
      return states.map(state=>results.get(state));
    } catch(error) {
      cancel();
      if(signal?.aborted)throw error;
      if(error.code==='PERFORMANCE_LAB_EXPIRED')throw error;
      await connector;
      for(const state of states)if(!results.has(state))record(missing(state));
      await Promise.all(evidenceTasks);
      await reconcileSavedEvidence();
      return states.map(state=>results.get(state));
    } finally {signal?.removeEventListener('abort',cancel);}
  }
  window.CCOptimized=Object.freeze({run,version:'2026.09.29.1-staging'});
})();
