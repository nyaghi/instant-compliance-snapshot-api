const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {harness,tick}=require('./run_ny_connector_lifecycle.cjs');

const ORIGIN='https://fixture-final-four.onrender.com';
const QUERY={state:'MS',operation:'search',name:'Example Foundation'};
function setup(){
  const h=harness({trialOrigin:ORIGIN,trialOnly:true});
  h.tabs.set(3,{id:3,windowId:20,url:vm.runInContext("registryStart('MS')",h.context)});
  vm.runInContext('owned.add(3)',h.context);
  const job={tab:3,sender:{url:ORIGIN+'/',tab:{id:1}},registryState:'MS',
    activeExpiresAt:310000,closed:false,msReusableForm:true};
  h.context.fixtureMsJob=job;
  vm.runInContext('activeLanes.set("MS",fixtureMsJob)',h.context);
  return {h,job};
}
test('completed reused Mississippi grid is returned without recovery',async()=>{
  const {h,job}=setup();let calls=0;
  h.chrome.tabs.sendMessage=async()=>{calls++;return {ok:true,evidence:{rows:[],total:0}};};
  const response=await h.context.registryMessage(job,{action:'registry-ms',query:QUERY,requireFreshGrid:true,budgetMs:30000});
  assert.equal(response.ok,true);assert.equal(calls,1);
  await h.advance(8000);
  assert.equal(vm.runInContext('diagnostics.filter(x=>x.type==="ms-grid-watchdog").length',h.context),0);
});
test('stalled reused grid is inconclusive at worker watchdog, without accepting old rows',async()=>{
  const {h,job}=setup();
  h.chrome.tabs.sendMessage=async()=>new Promise(()=>{});
  const pending=h.context.registryMessage(job,{action:'registry-ms',query:QUERY,requireFreshGrid:true,budgetMs:30000});
  await tick();await h.advance(7999);
  assert.equal(vm.runInContext('diagnostics.filter(x=>x.type==="ms-grid-watchdog").length',h.context),0);
  await h.advance(1);
  const response=await pending;
  assert.equal(response.ok,false);assert.equal(response.reason,'NY_CONNECTOR_INCOMPLETE');
  assert.equal(response.ms_diagnostic.source_error,'REGISTRY_GRID_WATCHDOG');
  assert.equal(response.evidence,undefined);
});
test('stalled reuse repeats the identical signed query on fresh form',async()=>{
  const {h,job}=setup();let sends=0,navigations=0;
  h.context.registryReady=async()=>({ready:true});
  h.context.registryNavigate=async()=>{navigations++;return {ready:true};};
  h.chrome.tabs.sendMessage=async(_tab,message)=>{
    if(message.action==='registry-ready')return {ready:true};
    sends++;
    if(sends===1)return new Promise(()=>{});
    assert.equal(message.query.name,QUERY.name);
    assert.equal(message.requireFreshGrid,undefined);
    return {ok:true,evidence:{rows:[],total:0}};
  };
  const pending=h.context.performRegistryQuery(job,QUERY);
  await tick();await h.advance(8000);
  const response=await pending;
  assert.equal(response.ok,true);assert.equal(navigations,1);assert.equal(sends,2);
  assert.equal(job.msReusableForm,true);
});
test('insufficient remaining time does not start a fresh recovery or report no record',async()=>{
  const {h,job}=setup();job.activeExpiresAt=30000;let sends=0;
  h.context.registryReady=async()=>({ready:true});
  h.context.registryNavigate=async()=>{throw Error('unexpected navigation');};
  h.chrome.tabs.sendMessage=async()=>{sends++;return new Promise(()=>{});};
  const pending=h.context.performRegistryQuery(job,QUERY);
  await tick();await h.advance(8000);
  const response=await pending;
  assert.equal(response.ok,false);assert.equal(sends,1);assert.equal(job.msReusableForm,false);
});
