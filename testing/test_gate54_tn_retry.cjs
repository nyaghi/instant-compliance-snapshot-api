const vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const input=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const pending={state:'TN',success:false,status:'Unable to Confirm',lab_diagnostic:{code:'NY_CONNECTOR_TN_VERIFICATION_PENDING',completed_count:0,pending_operation:'search'}};
async function run(source,org,{elapsed=50000,recovery=63000,quiet=true,mode='standard',first=pending,fail=false,stop=false,states=['TN'],secondState='TN'}={}){
  const window={},calls=[],published=[],timeouts=[];let now=0;
  const controller=new AbortController();
  const check=()=>{for(const x of timeouts)if(!x.controller.signal.aborted&&now>=x.deadline)x.controller.abort(new DOMException('Deadline','TimeoutError'));};
  const signals={timeout(ms){const controller=new AbortController();timeouts.push({deadline:now+ms,controller,ms});return controller.signal;},any(signals){return AbortSignal.any(signals);}};
  const location={origin:'https://fixture-final-four.onrender.com',pathname:'/',search:quiet?'?collector_layout=duo':'?aurora_connector_test=popup'};
  vm.runInNewContext(source,{window,location,URLSearchParams,crypto,AbortSignal:signals,performance:{now:()=>now},
    setTimeout:(fn,ms)=>setImmediate(()=>{now+=ms;check();fn();}),clearTimeout:clearImmediate,fetch:()=>{throw Error('Unexpected server workflow');}});
  const result=await window.CCOptimized.run({apiBase:location.origin,name:org.name,ein:org.ein,states,mode,aliases:['Reviewed name'],credentials:{},signal:controller.signal,onResult:r=>published.push(r),
    externalLookup:async(state,names,signal)=>{
      calls.push({state,names});
      if(state!=='TN')return {state,success:true,status:'Current'};
      if(calls.filter(x=>x.state==='TN').length===1){now+=elapsed;check();return first;}
      now+=recovery;check();if(stop)controller.abort();
      if(fail)throw Error('source unavailable');
      return {state:secondState,success:true,status:'Not Registered',source_url:'https://tncab.tnsos.gov/portal/public-search'};
    }});
  return {result,published,calls,now,timeouts:timeouts.map(x=>({ms:x.ms,deadline:x.deadline}))};
}
(async()=>{
 const rows=[];
 for(const [i,org] of input.cases.entries()){
   const elapsed=48000+i%7*1000,remaining=120000-elapsed-3000;
   const recovery=remaining-1000;
   const before=await run(input.previous,org,{elapsed,recovery});
   const after=await run(input.current,org,{elapsed,recovery});
   assert.equal(before.published[0].success,false);
   assert.equal(after.published[0].success,true);
   assert.equal(after.result[0].status,'Not Registered');
   assert.equal(after.calls.length,2);assert.deepEqual(after.calls[0].names,after.calls[1].names);
   assert.equal(after.timeouts[0].deadline,120000);
   const late=await run(input.current,org,{elapsed,recovery:remaining+1});
   assert.equal(late.result[0].success,false);
   const healthy={state:'TN',success:true,status:org.recorded_TN_status};
   for(const opts of [{first:healthy},{quiet:false},{mode:'sales'},
       {first:{...pending,lab_diagnostic:{...pending.lab_diagnostic,completed_count:1}}},
       {first:{...pending,lab_diagnostic:{...pending.lab_diagnostic,pending_operation:'detail'}}},
       {first:{...pending,lab_diagnostic:{...pending.lab_diagnostic,code:'OTHER_FAILURE'}}},
       {elapsed:78000},{states:['GA']},{fail:true},{recovery:1000},{secondState:'GA'}]){
     const a=await run(input.previous,org,opts),b=await run(input.current,org,opts);
     assert.equal(JSON.stringify(a.published),JSON.stringify(b.published),JSON.stringify(opts));
     assert.equal(JSON.stringify(a.calls),JSON.stringify(b.calls));
   }
   const stopped=await run(input.current,org,{stop:true,recovery:1000});
   assert.equal(stopped.published.length,0);
   rows.push({name:org.name,ein:org.ein,deadline_ms:120000,in_time_recovery_preserved:true,late_recovery_rejected:true,unchanged_paths_paired:11,user_stop_preserved:true});
 }
 console.log(JSON.stringify({passed:true,recorded_organizations:rows.length,scope:'Recorded organization inputs; synthetic clock and connector results, not live state searches.',cases:rows}));
})().catch(e=>{console.error(e);process.exitCode=1;});
