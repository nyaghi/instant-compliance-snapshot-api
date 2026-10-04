const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const source = fs.readFileSync(process.env.CC_TEST_CONNECTOR_SOURCE || path.join(__dirname,'../web-staging/ny-connector.js'),'utf8');
const capabilities = ['lookup-tab-v1','verification-retry-v1','search-verification-retry-v1','search-schema-errors-v1','nullable-ein-v1','queue-v1','connection-recovery-v1','recovery-causes-v1','cleanup-ack-v1','timeout-recovery-v1','resume-v1','verified-detail-v1','detail-navigation-v1','il-ga-public-dom-v1','il-ga-complete-search-v2','il-session-reuse-v1','il-large-pages-v1','ga-exempt-record-v1','ga-legacy-rows-v1'];

async function exercise({state='GA',commands=42,elapsedPerCommand=100,stopStatus='Delinquent',missedPings=0,incompatible=false,oldIllinois=false,nyFailureCause=null,abortCheckpoint=false}={}) {
  const controller=new AbortController();
  const actions=[],stages=[];let advance=0,clock=0,listener,pings=0;
  const window={addEventListener:(kind,fn)=>{if(kind==='message')listener=fn;},postMessage(message){
    actions.push(message.action);
    if(message.action==='ping' && ++pings<=missedPings)return;
    if(message.action==='search')queueMicrotask(()=>listener({source:window,origin:'https://staging.compliance-express.com',data:{...message,direction:'response',progress:true,ny_diagnostics:[{stage:'verify',event:'click',elapsed_ms:1,visibility:'hidden',token:'MUST-NOT-EXPORT'}]}}));
    queueMicrotask(()=>listener({source:window,origin:'https://staging.compliance-express.com',data:{
      ...message,direction:'response',ok:true,version:oldIllinois?'0.5.8':'0.5.9',capabilities:incompatible?[]:[...capabilities,'final-four-public-v1',...(oldIllinois?[]:['il-dom-events-v1'])],evidence:{complete:true,rows:[]},page_visibility:'hidden',ny_failure_cause:nyFailureCause,ny_reset_cooldown:true,ny_diagnostics:[{stage:'verify',event:'response',elapsed_ms:15,http_status:401,verified:false,payload_type:'object',visibility:'hidden',error_codes:['timeout-or-duplicate','MUST-NOT-EXPORT'],token:'MUST-NOT-EXPORT'}],diagnostics:[{phase:'results',event:'incomplete',elapsed_ms:35000,visibility:'hidden',private_field:'MUST-NOT-EXPORT'}]
    }}));
  }};
  const context=vm.createContext({window,location:{origin:'https://staging.compliance-express.com'},
    document:{querySelector:()=>null,getElementById:()=>null},crypto:webcrypto,setTimeout:(f,ms)=>setTimeout(f,ms===5000?1:ms),clearTimeout,AbortSignal,
    Date:{now:()=>clock},fetch:async(_url,options)=>{
      const request=JSON.parse(options.body);actions.push('api:'+request.action);
      let payload;
      if(request.action==='cancel')payload={};
      else if(request.action==='fail')payload={phase:'complete',result:{state,status:'Unable to Confirm',reason:request.reason}};
      else {
        if(request.action==='advance'){advance++;clock+=elapsedPerCommand;}
        payload=advance>=commands?{phase:'complete',result:{state,status:stopStatus}}:
          {phase:'search',check_token:'test-only-token',query_id:'query-'+advance,query:{state,orgName:'Variant '+advance,name:'Public name',operation:'search',private_field:'MUST-NOT-EXPORT'}};
      }
      return {ok:true,json:async()=>payload};
    }});
  vm.runInContext(source,context);
  let result,error;
  try {result=await window.CCNYConnector.lookup({state,organization_name:'Example Foundation',ein:'12-3456789',email:'test@example.invalid',admin_passcode:'test-only',device_id:'test-only',signal:controller.signal,onProgress:(_message,stage)=>{if(stage)stages.push(stage);if(abortCheckpoint&&stage?.stage==='browser stage')controller.abort();}});}
  catch(e){error=e;}
  return {result,error,advance,actions,stages};
}

test('trial stage diagnostics preserve results and export public fields only',{skip:!process.env.CC_TEST_CONNECTOR_SOURCE},async()=>{
  const run=await exercise({state:'NV',commands:2});assert.ifError(run.error);
  assert.equal(run.result.status,'Delinquent');assert.equal(run.advance,2);
  assert.equal(run.stages.filter(s=>s.stage==='browser query started').length,2);
  assert.equal(run.stages.filter(s=>s.stage==='browser query returned').length,2);
  assert.equal(run.stages.filter(s=>s.stage==='master response'&&s.action==='advance').length,2);
  const exported=JSON.stringify(run.stages);
  for(const secret of ['MUST-NOT-EXPORT','test-only','test@example.invalid','check_token','private_field'])assert.ok(!exported.includes(secret),secret);
  for(const state of ['NY','IL','GA']){
    const mature=await exercise({state,commands:1});assert.ifError(mature.error);
    assert.equal(mature.result.status,'Delinquent');assert.equal(mature.advance,1);
    assert.equal(mature.stages.filter(s=>s.stage==='browser query returned').length,1);
    assert.equal(mature.stages.find(s=>s.stage==='browser query returned').page_visibility,'hidden');
    if(state==='IL')assert.deepEqual(JSON.parse(JSON.stringify(mature.stages.find(s=>s.stage==='browser query returned').il_dom)),[{phase:'results',event:'incomplete',elapsed_ms:35000,visibility:'hidden'}]);
    const publicStages=JSON.stringify(mature.stages);
    for(const secret of ['MUST-NOT-EXPORT','test-only','test@example.invalid','check_token','private_field'])assert.ok(!publicStages.includes(secret),state+': '+secret);
    assert.equal(mature.stages.find(s=>s.stage==='browser query started').query.orgName,'Variant 0');
  }
});

test('trial NY failure diagnostics allow only the two source rejection codes',{skip:!process.env.CC_TEST_CONNECTOR_SOURCE},async()=>{
 for(const cause of ['NY_CONNECTOR_VERIFICATION_REJECTED','NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED','private verification material']) {
  const r=await exercise({state:'NY',commands:1,nyFailureCause:cause});assert.ifError(r.error);
  const returned=r.stages.find(s=>s.stage==='browser query returned');
  if(cause.startsWith('NY_CONNECTOR_')){
   assert.equal(returned.ny_diagnostics[0].http_status,401);assert.ok(!JSON.stringify(returned).includes('MUST-NOT-EXPORT'));assert.equal(returned.ny_failure_cause,cause);assert.equal(returned.ny_reset_cooldown,true);
  } else {
   assert.equal(returned.ny_failure_cause,undefined);assert.ok(!JSON.stringify(r.stages).includes(cause));
  }
  assert.equal(r.advance,1);assert.equal(r.result.status,'Delinquent');
 }
});
test('GA full reviewed-name search completes beyond both former command caps',async()=>{
  const run=await exercise();assert.ifError(run.error);assert.equal(run.advance,42);assert.equal(run.result.status,'Delinquent');assert.ok(run.actions.includes('finish'));
});
test('IL long completed negative also follows the master continuation',async()=>{
  const run=await exercise({state:'IL',commands:61,stopStatus:'Not Registered / Non-Compliant'});assert.ifError(run.error);assert.equal(run.advance,61);assert.equal(run.result.status,'Not Registered / Non-Compliant');
});
test('master inconclusive completion is retained without a generic frontend exception',async()=>{
  const run=await exercise({commands:38,stopStatus:'Unable to Confirm'});assert.ifError(run.error);assert.equal(run.result.status,'Unable to Confirm');
});
test('a nonterminating IL/GA continuation fails conservatively at five minutes',async()=>{
  const run=await exercise({commands:1000,elapsedPerCommand:10000});assert.ifError(run.error);assert.equal(run.advance,30);assert.equal(run.result.status,'Unable to Confirm');assert.equal(run.result.reason,'NY_CONNECTOR_TIMEOUT');assert.ok(run.actions.includes('finish'));
});
test('New York retains its existing ten-command ceiling',async()=>{
  const run=await exercise({state:'NY',commands:20});assert.equal(run.advance,10);assert.match(run.error.message,/complete result/);assert.ok(run.actions.includes('finish'));
});
test('one missed readiness response recovers before a single lookup starts',async()=>{
  const run=await exercise({commands:1,missedPings:1});assert.ifError(run.error);
  assert.equal(run.result.status,'Delinquent');assert.equal(run.actions.filter(a=>a==='ping').length,2);
  assert.equal(run.actions.filter(a=>a==='acquire').length,1);assert.equal(run.actions.filter(a=>a==='api:start').length,1);
  assert.equal(run.actions.filter(a=>a==='search').length,1);
});
test('absent connector remains inconclusive after exactly two readiness attempts',async()=>{
  const run=await exercise({commands:1,missedPings:2});assert.ifError(run.error);
  assert.equal(run.result.status,'Unable to Confirm');assert.equal(run.result.reason,'NY_CONNECTOR_UNAVAILABLE');
  assert.equal(run.actions.filter(a=>a==='ping').length,2);assert.ok(!run.actions.includes('search'));assert.ok(!run.actions.includes('acquire'));
});
test('incompatible connector is not retried or treated as ready',async()=>{
  const run=await exercise({commands:1,incompatible:true});assert.ifError(run.error);
  assert.equal(run.result.reason,'NY_CONNECTOR_UPDATE_REQUIRED');assert.equal(run.actions.filter(a=>a==='ping').length,1);assert.ok(!run.actions.includes('search'));
});

test('Illinois requires the event-readiness fix while old NY and GA remain usable',async()=>{
  const il=await exercise({state:'IL',oldIllinois:true,commands:1});assert.ifError(il.error);
  assert.equal(il.result.reason,'NY_CONNECTOR_UPDATE_REQUIRED');assert.ok(!il.actions.includes('search'));
  for(const state of ['NY','GA'])assert.equal((await exercise({state,oldIllinois:true,commands:1})).result.status,'Delinquent');
});

async function recoveryExercise({persistent=false,finishFails=false,finishInterrupted=false,persistentInterruption=false,acquireFails=false,abortRecovery=false,overBudget=false,repeatDirective=false}={}) {
  const state=process.env.CC_TEST_RECOVERY_STATE || 'IL';
  const failureReason=state==='NC'?'NY_CONNECTOR_TAB_READY_TIMEOUT':'NY_CONNECTOR_IL_VERIFICATION_PENDING';
  const actions=[],searches=[],controller=new AbortController();let listener,clock=0,failures=0,admissions=0,finishes=0;
  const query=state==='NC'?{state,operation:'search',name:'Example Foundation'}:{state,ein:'123456789'};
  const window={addEventListener:(type,fn)=>listener=fn,postMessage(m){
    actions.push({action:m.action,id:m.lookup_id,query:m.query});
    let r={ok:true};
    if(m.action==='ping')r={ok:true,version:'0.5.10',capabilities:[...capabilities,'il-dom-events-v1','final-four-public-v1']};
    if(m.action==='acquire' && ++admissions===2){
      if(abortRecovery){controller.abort(new Error('Canceled by test'));return;}
      if(acquireFails)r={ok:false,reason:'NY_CONNECTOR_QUEUE_TIMEOUT'};
      if(overBudget)clock=300001;
    }
    if(m.action==='finish' && finishFails)r={ok:false,reason:'NY_CONNECTOR_TIMEOUT'};
    if(m.action==='finish' && (++finishes===1 && finishInterrupted || persistentInterruption))r={ok:false,reason:'NY_CONNECTOR_INTERRUPTED'};
    if(m.action==='search'){
      searches.push(m);clock+=60000;
      r=searches.length===1||persistent||repeatDirective?{ok:false,reason:failureReason}:{ok:true,evidence:{query,complete:true,total:0,rows:[]}};
    }
    queueMicrotask(()=>listener({source:window,origin:'https://staging.compliance-express.com',data:{...m,...r,direction:'response'}}));
  }};
  const context=vm.createContext({window,location:{origin:'https://staging.compliance-express.com'},
    document:{querySelector:()=>null,getElementById:()=>null},crypto:webcrypto,setTimeout,clearTimeout,AbortSignal,
    Date:{now:()=>clock},fetch:async(url,options)=>{
      const p=JSON.parse(options.body);actions.push({action:'api:'+p.action,payload:p});let response;
      if(p.action==='start')response={phase:'search',check_token:'initial',query_id:'original-query',query};
      else if(p.action==='cancel')response={};
      else if(p.action==='advance')response={phase:'complete',result:{state,status:'Not Registered / Non-Compliant'}};
      else if(p.action==='fail' && p.reason===failureReason && (++failures===1||repeatDirective))
        response={phase:'search',check_token:'continued',query_id:'retry-query',query,recovery:{action:'fresh_browser',attempt:1}};
      else response={phase:'complete',result:{state,status:'Unable to Confirm',reason:p.reason}};
      return {ok:true,json:async()=>response};
    }});
  vm.runInContext(source,context);let result,error;
  try{result=await window.CCNYConnector.lookup({state,organization_name:'Example',ein:'123456789',signal:controller.signal});}catch(e){error=e;}
  return {actions,searches,result,error};
}

test('master fresh-page recovery changes only the transport and retries the exact pending query',async()=>{
  const r=await recoveryExercise();assert.ifError(r.error);assert.equal(r.result.status,'Not Registered / Non-Compliant');
  assert.equal(r.searches.length,2);assert.notEqual(r.searches[0].lookup_id,r.searches[1].lookup_id);
  assert.deepEqual(r.searches[0].query,r.searches[1].query);
  assert.equal(r.actions.filter(a=>a.action==='api:start').length,1);
  assert.equal(r.actions.filter(a=>a.action==='api:advance').length,1);
  assert.equal(r.actions.find(a=>a.action==='api:fail').payload.query_id,'original-query');
  assert.equal(r.actions.find(a=>a.action==='api:advance').payload.query_id,'retry-query');
  assert.equal(r.actions.filter(a=>a.action==='finish').length,2);
});

test('a repeated verification failure remains inconclusive after one recovery',async()=>{
  const r=await recoveryExercise({persistent:true});assert.ifError(r.error);
  assert.equal(r.result.status,'Unable to Confirm');assert.equal(r.searches.length,2);
  assert.equal(r.actions.filter(a=>a.action==='api:advance').length,0);
});

test('cleanup and re-admission failures cannot submit another search',async()=>{
  for(const option of ['finishFails','acquireFails','overBudget']){
    const r=await recoveryExercise({[option]:true});assert.ifError(r.error);
    assert.equal(r.result.status,'Unable to Confirm');assert.equal(r.searches.length,1);
  }
});

test('canceling during recovery cleans up without another search',async()=>{
  const r=await recoveryExercise({abortRecovery:true});assert.match(r.error.message,/Canceled by test/);
  assert.equal(r.searches.length,1);assert.equal(r.actions.at(-1).action,'api:cancel');
  assert.equal(r.actions.filter(a=>a.action==='finish').length,2);
});

test('a repeated master recovery directive is rejected instead of looping',async()=>{
  const r=await recoveryExercise({repeatDirective:true});assert.ifError(r.error);
  assert.equal(r.result.reason,'NY_CONNECTOR_INCOMPLETE');assert.equal(r.searches.length,2);
});

test('failed-job disconnect racing finish is acknowledged before recovery acquires',async()=>{
  const r=await recoveryExercise({finishInterrupted:true});assert.ifError(r.error);
  assert.equal(r.result.status,'Not Registered / Non-Compliant');assert.equal(r.searches.length,2);
  const beforeAcquire=r.actions.slice(0,r.actions.findLastIndex(a=>a.action==='acquire'));
  const cleanup=beforeAcquire.filter(a=>a.action==='finish');assert.equal(cleanup.length,2);
  assert.equal(cleanup[0].id,cleanup[1].id);assert.equal(cleanup[0].id,r.searches[0].lookup_id);
});

test('persistent cleanup interruption cannot acquire a fresh job or loop',async()=>{
  const r=await recoveryExercise({persistentInterruption:true});assert.ifError(r.error);
  assert.equal(r.result.status,'Unable to Confirm');assert.equal(r.result.reason,'NY_CONNECTOR_INTERRUPTED');
  assert.equal(r.searches.length,1);assert.equal(r.actions.filter(a=>a.action==='acquire').length,1);
  assert.equal(r.actions.filter(a=>a.action==='finish').length,3); // two bounded attempts and final cleanup
});

test('trial frontend saves checkpoint before completed response',{skip:!process.env.CC_TEST_CONNECTOR_SOURCE},async()=>{
 const r=await exercise({state:'NY',commands:1});
 const before=r.stages.findIndex(s=>s.stage==='browser stage');
 const after=r.stages.findIndex(s=>s.stage==='browser query returned');
 assert.ok(before>=0&&before<after);assert.equal(r.advance,1);
 assert.ok(!JSON.stringify(r.stages).includes('MUST-NOT-EXPORT'));
});

test('trial NY checkpoint survives cancellation without accepting a late result',{skip:!process.env.CC_TEST_CONNECTOR_SOURCE},async()=>{
 const r=await exercise({state:'NY',commands:1,abortCheckpoint:true});
 assert.ok(r.error);assert.equal(r.result,undefined);assert.equal(r.advance,0);
 assert.ok(r.stages.some(s=>s.stage==='browser stage'));assert.ok(r.actions.includes('finish'));
});
