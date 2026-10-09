import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const script=fs.readFileSync(process.env.CC_CONNECTOR_WORKER
  || new URL('../browser-connector/registry-worker.js',import.meta.url),'utf8');
const origin='https://charityclarity-final-four-29-2.onrender.com/';
const registry='https://charities.sos.ms.gov/online/portal/ch/page/charities-search/Portal.aspx';
const query={state:'MS',operation:'search',name:'Independent fixture charity'};
const incomplete=()=>({ok:false,reason:'NY_CONNECTOR_INCOMPLETE',
  ms_diagnostic:{source_error:'REGISTRY_RESPONSE_INCOMPLETE'}});
const complete=total=>({ok:true,evidence:{query,complete:true,rows:[],total}});

async function scenario(responses,{reuse=false}={}) {
  const calls=[];
  const context=vm.createContext({URL,Date,setTimeout,clearTimeout,
    P:{TRIAL_ORIGIN:new URL(origin).origin,validQuery:()=>true,registryAllowed:()=>true},
    chrome:{tabs:{get:async()=>({url:registry})}},
    diagnostic:(type,job,detail)=>calls.push({type,detail})});
  vm.runInContext(script,context);
  context.registryNavigate=async (job,url,budgetMs)=>{calls.push({type:'navigate',budgetMs});job.tab=41;return {documentId:'new'};};
  context.registryReady=async()=>{calls.push({type:'ready'});return {documentId:'same'};};
  context.registryMessage=async(job,message)=>{
    calls.push({type:'message',name:message.query.name,reuse:message.requireFreshGrid===true});
    return responses.shift();
  };
  const job={registryState:'MS',tab:reuse?41:null,msReusableForm:reuse,
    sender:{url:origin},activeExpiresAt:Date.now()+120000};
  const result=await vm.runInContext('performRegistryQuery(job,query)',
    Object.assign(context,{job,query}));
  return {calls,job,result};
}

const recovered=await scenario([incomplete(),complete(0)]);
assert.equal(recovered.result.ok,true);
assert.equal(recovered.result.evidence.total,0);
assert.equal(recovered.calls.filter(c=>c.type==='navigate').length,2);
assert.deepEqual(recovered.calls.filter(c=>c.type==='message').map(c=>c.name),
  [query.name,query.name]);
assert.equal(recovered.job.msReusableForm,true);
assert.equal(recovered.calls.filter(c=>c.type==='navigate')[1].budgetMs,10000);
assert.ok(recovered.job.msDeadlineAt<=recovered.job.activeExpiresAt);
assert.ok(recovered.job.msDeadlineAt>Date.now());

const firstPass=await scenario([complete(1)]);
assert.equal(firstPass.result.ok,true);
assert.equal(firstPass.calls.filter(c=>c.type==='navigate').length,1);

const stillIncomplete=await scenario([incomplete(),incomplete()]);
assert.equal(stillIncomplete.result.ok,false);
assert.equal(stillIncomplete.calls.filter(c=>c.type==='navigate').length,2);
assert.equal(stillIncomplete.job.msReusableForm,false);

const reused=await scenario([incomplete(),complete(1)],{reuse:true});
assert.equal(reused.result.ok,true);
assert.equal(reused.calls.filter(c=>c.type==='ready').length,1);
assert.equal(reused.calls.filter(c=>c.type==='navigate').length,1);
assert.equal(reused.calls.filter(c=>c.type==='navigate')[0].budgetMs,10000);

// A prior signed query that consumed the state's allowance must not start
// another generated-name search or turn incomplete evidence into a negative.
{
  const calls=[];
  const context=vm.createContext({URL,Date,setTimeout,clearTimeout,
    P:{TRIAL_ORIGIN:new URL(origin).origin,validQuery:()=>true,registryAllowed:()=>true},
    chrome:{tabs:{get:async()=>({url:registry})}},
    diagnostic:()=>{}});
  vm.runInContext(script,context);
  context.registryReady=async()=>{calls.push('ready');return {documentId:'same'};};
  context.registryMessage=async()=>{calls.push('search');return complete(0);};
  const job={registryState:'MS',tab:41,msReusableForm:true,sender:{url:origin},
    activeExpiresAt:Date.now()+120000,msDeadlineAt:Date.now()-1};
  await assert.rejects(vm.runInContext('performRegistryQuery(job,query)',
    Object.assign(context,{job,query})),/NY_CONNECTOR_TIMEOUT/);
  assert.deepEqual(calls,[]);
}

for(const [reuse,expectedMs] of [[false,12000],[true,8000]]) {
  let timerMs;
  const context=vm.createContext({URL,Date,
    setTimeout:(fn,ms)=>{timerMs=ms;queueMicrotask(fn);return 1;},clearTimeout:()=>{},
    P:{TRIAL_ORIGIN:new URL(origin).origin},
    chrome:{tabs:{get:async()=>({url:registry}),sendMessage:async()=>new Promise(()=>{})}},
    diagnostic:()=>{}});
  vm.runInContext(script,context);
  context.registryOrigin=()=>new URL(registry).origin;
  const job={registryState:'MS',tab:41,closed:false,activeExpiresAt:Date.now()+120000};
  const result=await vm.runInContext('registryMessage(job,message)',
    Object.assign(context,{job,message:{action:'registry-ms',query,
      requireFreshGrid:reuse,budgetMs:30000}}));
  assert.equal(timerMs,expectedMs);
  assert.equal(result.ok,false);
  assert.equal(result.ms_diagnostic.source_error,'REGISTRY_GRID_WATCHDOG');
  assert.equal(result.ms_diagnostic.reused_form,reuse);
}

// Reload readiness must inherit the ten-second recovery allowance. The old
// path passed a fresh 30-second allowance and repeatedly took ~48 seconds.
{
  let readinessMs, reloads=0;
  const context=vm.createContext({URL,Date,setTimeout,clearTimeout,
    P:{TRIAL_ORIGIN:new URL(origin).origin},
    chrome:{tabs:{get:async()=>({url:registry}),reload:async()=>{reloads++;}}},
    diagnostic:()=>{}});
  vm.runInContext(script,context);
  context.registryMessage=async()=>({documentId:'old'});
  context.registryReady=async(job,previous,path,budgetMs)=>{
    readinessMs=budgetMs;return {documentId:'new'};};
  const job={registryState:'MS',tab:41,closed:false,activeExpiresAt:Date.now()+120000};
  await vm.runInContext('registryNavigate(job,registry,10000)',
    Object.assign(context,{job,registry}));
  assert.equal(reloads,1);
  assert.ok(readinessMs>0&&readinessMs<=10000);
}

console.log('Mississippi initial/reused grid recovery: positive, no-record, and incomplete controls passed.');
