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
  context.registryNavigate=async job=>{calls.push({type:'navigate'});job.tab=41;return {documentId:'new'};};
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

console.log('Mississippi initial/reused grid recovery: positive, no-record, and incomplete controls passed.');
