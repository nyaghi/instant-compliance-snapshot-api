const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const worker = fs.readFileSync(require('node:path').join(__dirname,'../deployment/staging_connector/registry-worker.js'),'utf8');
const start = 'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen';
const stalled = {document_loaded:true, search_route:true, loader_clear:false, inputs_present:false};
function trial({form=stalled, readyAt=Infinity, url=start, initial=true, state='NV', activeExpiresAt=90000, config=false, verification=false}={}) {
  let now=0;
  const context=vm.createContext({
    P:{TRIAL_ORIGIN:true}, Date:{now:()=>now}, URL, registryStart:()=>start, registryOrigin:()=>new URL(start).origin,
    registryNevadaVisibleSnapshot:()=>null, registryNevadaMakeVisible:()=>null,
    registryReadinessMessage:async()=>({url,documentId:'owned',ready:now>=readyAt,verification_pending:verification,
      nv_readiness:form,nv_startup_unreachable:config}),
    wfAwait:(_job,_label,fn)=>fn(), wfReturn:(_job,_label,value)=>value,
    nap:ms=>{now+=ms;}, registryNorthCarolinaVisibility:()=>null
  });
  vm.runInContext(worker.slice(worker.indexOf('async function registryReady('),worker.indexOf('async function registryNorthCarolinaVisibility(')),context);
  return {result:context.registryReady({registryState:state,activeExpiresAt},null,'/portal/public/',30000,null,false,initial),
    elapsed:()=>now};
}
test('Nevada initial registry spinner stops after 30 seconds',async()=>{
  const check=trial();
  await assert.rejects(check.result,{message:'NY_CONNECTOR_REGISTRY_NV_FORM_LOAD_TIMEOUT'});
  assert.equal(check.elapsed(),30000);
});
test('Nevada working slow form completes on the first attempt',async()=>{
  const check=trial({readyAt:21000});
  assert.equal((await check.result).ready,true);
  assert.equal(check.elapsed(),21000);
});
test('No outage label for off-route, missing telemetry, later navigation, or parent expiry',async()=>{
  for(const args of [{url:start+'/other'}, {form:null}, {initial:false}, {activeExpiresAt:12000}, {verification:true}]){
    await assert.rejects(trial(args).result,{message:'NY_CONNECTOR_TAB_READY_TIMEOUT'});
  }
});
test('Nevada still stops early on the existing confirmed configuration error',async()=>{
  const check=trial({config:true});
  await assert.rejects(check.result,{message:'NY_CONNECTOR_REGISTRY_NV_STARTUP_UNREACHABLE'});
  assert.equal(check.elapsed(),3000);
});
