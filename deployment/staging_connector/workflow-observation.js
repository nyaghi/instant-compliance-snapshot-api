/* Passive observation of the owned workflow. No Chrome calls or new timers. */
const wfWorkerTag = 'workflow-observation-1-' + Math.random().toString(36).slice(2);
function wfEvent(job, stage, outcome, fields={}) {
  try {
    if(!P.TRIAL_ORIGIN || !job)return null;
    const trace=job.workflowObservation ||= {schema:1,worker_tag:wfWorkerTag,lookup_id:job.lookupId,
      state:job.registryState,started_epoch_seconds:Date.now()/1000,sequence:0,events:[],failures:[],
      pending:{},dropped_events:0,dropped_failures:0,coverage_complete:false};
    const peers=typeof allJobs==='function'?allJobs().filter(j=>j&&!j.closed).map(j=>({
      lookup_id:j.lookupId,state:j.registryState,tab_id:j.tab,generation:j.generation,
      pending_command_id:j.pending,active:j.activeExpiresAt!==null})):[];
    const event={seq:++trace.sequence,at_seconds:Date.now()/1000-trace.started_epoch_seconds,
      stage,outcome,command_id:job.pending||null,tab_id:job.tab,generation:job.generation,
      remaining_seconds:Number.isFinite(job.activeExpiresAt)?(job.activeExpiresAt-Date.now())/1000:null,
      same_tab_peers:peers.filter(p=>p.lookup_id!==job.lookupId&&p.tab_id!=null&&p.tab_id===job.tab),
      active_peer_count:peers.filter(p=>p.active).length,...fields};
    if(trace.events.length<800)trace.events.push(event);else trace.dropped_events++;
    const tail=trace.terminal_events ||= [];tail.push(event);if(tail.length>120)tail.shift();
    if(outcome==='exception'||event.same_tab_peers.length) {
      if(trace.failures.length>=100){trace.failures.shift();trace.dropped_failures++;}
      trace.failures.push(event);
    }
    return event.seq;
  } catch {return null;}
}
function wfStart(job,stage) {
  const seq=wfEvent(job,stage,'started');
  if(seq!=null)job.workflowObservation.pending[seq]={seq,stage,command_id:job.pending,tab_id:job.tab};
  return {seq,stage,started:Date.now()};
}
function wfEnd(job,span,outcome='returned',error=null) {
  try {
    wfEvent(job,span.stage,outcome,{span_id:span.seq,duration_seconds:(Date.now()-span.started)/1000,
      error_type:error?(error.name||'Error'):null});
    if(span.seq!=null)delete job.workflowObservation.pending[span.seq];
  } catch {}
}
function wfAwait(job,stage,operation) {
  if(!P.TRIAL_ORIGIN)return operation();
  const span=wfStart(job,stage);
  try {return Promise.resolve(operation()).then(value=>{
    if(value&&typeof value==='object'&&value.wf_content) {
      const content=value.wf_content,trace=job.workflowObservation;
      if(trace){trace.content ||= [];if(trace.content.length<100)trace.content.push({worker_span:span.seq,...content});else trace.dropped_content=(trace.dropped_content||0)+1;}
      const {wf_content,...original}=value;value=original;
    }
    wfEnd(job,span);return value;},error=>{
    wfEnd(job,span,'exception',error);throw error;
  });} catch(error){wfEnd(job,span,'exception',error);throw error;}
}
function wfReturn(job,stage,value) {
  wfEvent(job,stage,'branch_return',{return_kind:value===null?'null':typeof value});return value;
}
function wfExport(job) {
  const trace=job?.workflowObservation;
  return trace?{...trace,events:[...trace.events],terminal_events:[...(trace.terminal_events||[])],capture_terminal:{...(trace.capture_terminal||{})},failures:[...trace.failures],pending:{...trace.pending}}:null;
}

// Keep the last bounded capture facts separately from the human-readable trace.
// No page bodies, URLs, query names, pixels, requests or timers are retained here.
function wfCaptureFact(job, detail) {
  try {
    if(!P.TRIAL_ORIGIN || !job || typeof detail!=='string' || detail.length>20000)return;
    const value=JSON.parse(detail);
    if(!value || typeof value!=='object' || Array.isArray(value))return;
    const operation=['search','detail'].includes(value.operation)?value.operation:'other';
    const fact={operation};
    for(const key of ['phase','waiting','reserve_trigger','metadata_mode'])
      if(typeof value[key]==='string' && /^[a-zA-Z0-9_. -]{1,100}$/.test(value[key]))fact[key]=value[key];
    for(const key of ['budget_ms','prior_capture_ms','wait_started_ms','captures','required_pages','width','height','paint_wait_ms'])
      if(Number.isFinite(value[key]) && value[key]>=0 && value[key]<=2000000)fact[key]=value[key];
    for(const key of ['completion_reserve','detail','fields_visible','visible','loader_clear','alive','url_same','document_same','body_same','binding_present','binding_same'])
      if(typeof value[key]==='boolean')fact[key]=value[key];
    fact.steps=Array.isArray(value.steps)?value.steps.slice(-6).filter(x=>x && typeof x.api==='string' && /^[a-zA-Z0-9_. -]{1,100}$/.test(x.api) && Number.isFinite(x.ms) && x.ms>=0 && x.ms<=2000000).map(x=>({api:x.api,ms:x.ms})):[];
    const seq=wfEvent(job,'capture.terminal','observed',{capture_phase:fact.phase||'unknown'});
    if(seq==null)return;
    fact.seq=seq;fact.tab_id=job.tab;fact.generation=job.generation;
    fact.command_id=job.pending||null;
    fact.remaining_seconds=Number.isFinite(job.activeExpiresAt)?(job.activeExpiresAt-Date.now())/1000:null;
    (job.workflowObservation.capture_terminal ||= {})[operation]=fact;
  } catch { /* Diagnostic failure must not change capture behavior. */ }
}
