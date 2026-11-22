const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/worker.js'),'utf8');
const body = source.slice(source.indexOf('let pendingAdmissionBatch'), source.indexOf('function newJob'));
function harness() {
  const writes = [];
  const job = {workflowObservation:{}};
  const state = {queue:[], diagnostics:[], ownedTabs:[]};
  const context = {
    state, P:{TRIAL_ORIGIN:true}, Date, Promise, structuredClone, keepAlive(){}, allJobs:()=>[job],
    keepAliveTimer:null, runtimeState:()=>({...state,queue:[...state.queue]}),
    trialAlIdle:null, trialTnIdle:null, trialNyIdle:null, saving:Promise.resolve(),
    runtimeCheckpointSequence:0,runtimeCheckpointPending:0,armRuntimeLatencyProbe:()=>()=>{},
    chrome:{storage:{session:{set:({ccnyRuntime})=>new Promise((resolve,reject)=>{
      writes.push({value:ccnyRuntime,resolve,reject});
    })}}}
  };
  vm.runInNewContext(body,context);
  return {state,writes,job,save:context.saveRuntime};
}
const tick = () => new Promise(resolve=>setImmediate(resolve));
test('nine admission promises wait for durable recovery of all nine jobs',async()=>{
  const h=harness(),pending=[];
  for(let n=0;n<9;n++){
    h.state.queue.push({id:n,active:false,meta:{n}});
    pending.push(h.save(true));
  }
  let released=0;
  pending.forEach(p=>p.then(()=>released++));
  await tick();
  assert.equal(h.writes.length,1);
  assert.deepEqual(h.writes[0].value.queue,h.state.queue);
  assert.equal(released,0);
  h.writes[0].resolve(); await Promise.all(pending);
  assert.equal(released,9);
});
test('updates, removals and intervening save preserve ordering and immutable recovery snapshots',async()=>{
  const h=harness();
  h.state.queue.push({id:1,active:false});const p1=h.save(true);
  h.state.queue[0].active=true;h.state.queue.push({id:2});const p2=h.save(true);
  h.state.queue.shift();const p3=h.save();
  h.state.queue.push({id:3});const p4=h.save(true);
  for(let i=0;i<4;i++){await tick();assert.equal(h.writes.length,i+1);h.writes[i].resolve();}
  await Promise.all([p1,p2,p3,p4]);
  assert.deepEqual(h.writes.map(w=>w.value.queue.map(j=>j.id)),[[1],[1,2],[2],[2,3]]);
  assert.equal(h.writes[0].value.queue[0].active,false);
  assert.equal(h.writes[1].value.queue[0].active,true);
});
test('duplicate success waits for its predecessor, failure permits real retry, worker restart writes again',async()=>{
  const h=harness();const a=h.save();const b=h.save();
  let returned=false;b.then(()=>returned=true);
  await tick();assert.equal(returned,false);h.writes[0].resolve();await Promise.all([a,b]);
  assert.equal(h.writes.length,1);
  h.state.ownedTabs.push(12);const bad=h.save();const rejection=assert.rejects(bad,/simulated/);
  await tick();h.writes[1].reject(Error('simulated'));await rejection;
  const retry=h.save();await tick();assert.equal(h.writes.length,3);h.writes[2].resolve();await retry;
  h.state.ownedTabs.pop();const restored=h.save();await tick();assert.equal(h.writes.length,4);
  h.writes[3].resolve();await restored;
  const fresh=harness();const started=fresh.save();await tick();assert.equal(fresh.writes.length,1);
  fresh.writes[0].resolve();await started;
});
test('failed grouped admission rejects every caller, then latest image can be saved',async()=>{
  const h=harness();h.state.queue.push({id:1});const a=h.save(true);
  h.state.queue.push({id:2});const b=h.save(true);
  const rejected=Promise.all([assert.rejects(a,/quota/),assert.rejects(b,/quota/)]);
  await tick();h.writes[0].reject(Error('quota'));await rejected;
  const recovery=h.save();await tick();assert.equal(h.writes[1].value.queue.length,2);
  h.writes[1].resolve();await recovery;
});
