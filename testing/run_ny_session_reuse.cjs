const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {harness,tick}=require('./run_ny_connector_lifecycle.cjs');
const TRIAL='https://fixture-final-four.onrender.com';
const id=n=>String(n).padStart(20,'0');
async function setup(){
 const h=harness({trialOrigin:TRIAL,tabs:[[1,{id:1,windowId:10,url:TRIAL}],[2,{id:2,windowId:99,url:'https://charities-search.ag.ny.gov/RegistrySearch'}]]});
 await tick();return h;
}

for(const cause of ['NY_CONNECTOR_VERIFICATION_REJECTED','NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED'])test('trial NY retains source rejection when reset is cooling down: '+cause,async()=>{
 const h=await setup();
 await h.context.saveRepair({phase:'verified',nextAllowedAt:900000});
 const original=h.chrome.tabs.sendMessage;
 h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='search'?{ok:false,reason:cause,verificationRetryUsed:true}:original(tab,m);
 const p=h.connect(),r=await h.query(p,11);
 assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_RECOVERY_REJECTED');
 assert.equal(r.ny_failure_cause,cause);assert.equal(r.ny_reset_cooldown,true);
 assert.equal(h.repairs.length,0);assert.equal(h.created.length,1);
});
test('trial NY consecutive organizations reuse only the owned successful page and search afresh',async()=>{
 const h=await setup(),p=h.connect();assert.equal((await h.query(p,11,{ein:'123456789'})).ok,true);
 p.onMessage.emit({action:'finish',id:id(12)});await tick();assert.ok(h.tabs.has(100));
 await h.advance(3000);const q=h.connect(2);assert.equal((await h.query(q,21,{ein:'987654321'})).ok,true);
 assert.deepEqual(h.created,[100]);assert.deepEqual(h.queries.map(x=>x.query),[{ein:'123456789'},{ein:'987654321'}]);
 assert.ok(h.tabs.has(2));
});
test('trial NY returns from detail with browser Back before sending another search command',async()=>{
 const h=await setup(),p=h.connect();await h.query(p,11);
 h.tabs.get(100).url='https://charities-search.ag.ny.gov/RegistrySearch/12-34-56';
 const original=h.chrome.tabs.sendMessage;let backs=0;
 h.chrome.tabs.sendMessage=async(tab,m)=>{if(m.action==='back-to-results')backs++;if(m.action==='search')assert.equal(h.tabs.get(tab).url,'https://charities-search.ag.ny.gov/RegistrySearch');return original(tab,m);};
 const r=await h.query(p,12,{orgName:'Another name'});assert.equal(r.ok,true);assert.equal(backs,1);
});
test('NY idle page expires and is not kept alive indefinitely by reuse',async()=>{
 const h=await setup(),p=h.connect();await h.query(p,11);p.onMessage.emit({action:'finish',id:id(12)});await tick();
 const expiry=h.data.session.ccnyRuntime.trialNyIdle?.expiresAt;assert.ok(expiry);
 await h.advance(3000);const q=h.connect(2);await h.query(q,21);q.onMessage.emit({action:'finish',id:id(22)});await tick();
 assert.equal(h.data.session.ccnyRuntime.trialNyIdle.expiresAt,expiry);await h.advance(300000);
 assert.ok(!h.tabs.has(100));assert.ok(h.tabs.has(2));
});
for(const reason of ['NY_CONNECTOR_TIMEOUT','NY_CONNECTOR_INTERRUPTED','NY_CONNECTOR_RECOVERY_REJECTED'])test('NY unsuccessful cleanup never reuses its page: '+reason,async()=>{
 const h=await setup(),p=h.connect();await h.query(p,11);const job=vm.runInContext('allJobs()[0]',h.context);
 await h.context.close(job,reason);assert.deepEqual(h.removed,[100]);assert.equal(h.data.session.ccnyRuntime.trialNyIdle,undefined);
});
test('NY owned idle page survives worker restart, but not a moved source origin',async()=>{
 const h=await setup(),p=h.connect();await h.query(p,11);p.onMessage.emit({action:'finish',id:id(12)});await tick();
 const session=JSON.parse(JSON.stringify(h.data.session));assert.ok(session.ccnyRuntime.trialNyIdle);
 const restored=harness({trialOrigin:TRIAL,session,tabs:[...h.tabs.entries()]});await tick();assert.ok(restored.tabs.has(100));
 const moved=harness({trialOrigin:TRIAL,session,tabs:[...h.tabs.entries()].map(([i,t])=>[i,i===1?{...t,url:'https://example.com'}:t])});await tick();assert.ok(!moved.tabs.has(100));assert.ok(moved.tabs.has(2));
});
test('closing the source removes its idle NY collector, without touching other NY pages',async()=>{
 const h=await setup(),p=h.connect();await h.query(p,11);p.onMessage.emit({action:'finish',id:id(12)});await tick();
 h.chrome.tabs.onRemoved.emit(1);await tick();assert.ok(!h.tabs.has(100));assert.ok(h.tabs.has(2));
 assert.equal(h.data.session.ccnyRuntime.trialNyIdle,undefined);
});

async function fieldTransitionFixture(){
 const h=await setup();let fields=[],document=1,reloads=0;
 const original=h.chrome.tabs.sendMessage;
 h.chrome.tabs.reload=async()=>{reloads++;document++;fields=[];};
 h.chrome.tabs.sendMessage=async(tab,m)=>{
  if(m.action==='ready')return {ready:true,url:h.tabs.get(tab).url,documentId:String(document),formFields:[...fields]};
  if(m.action==='search'&&!m.query.orgID){
   const key=Object.keys(m.query)[0];
   // Live NY returned HTTP400 after editing EIN to empty and switching to
   // name. A fresh name-only form and same-field name edits both succeeded.
   if(fields.some(old=>old!==key))return {ok:false,reason:'NY_CONNECTOR_SEARCH_HTTP_ERROR'};
   fields=[key];
  }
  return original(tab,m);
 };
 return {h,reloads:()=>reloads,fields:()=>fields};
}
test('NY EIN-to-name uses a new normal document, while same-field queries reuse verification',async()=>{
 const {h,reloads}=await fieldTransitionFixture(),p=h.connect();
 assert.equal((await h.query(p,11,{ein:'271635830'})).ok,true);
 const deadline=h.data.session.ccnyRuntime.queue[0].activeExpiresAt;
 assert.equal((await h.query(p,12,{orgName:'Achieving the Dream, Inc.'})).ok,true);
 assert.equal(reloads(),1);
 assert.equal((await h.query(p,13,{orgName:'Achieving The Dream Inc'})).ok,true);
 assert.equal(reloads(),1,'same-field alias must not repeat verification');
 assert.equal(h.data.session.ccnyRuntime.queue[0].activeExpiresAt,deadline);
 assert.deepEqual(h.created,[100]);assert.deepEqual(h.repairs,[]);
});
test('NY cross-organization reuse checks the actual restored form filters',async()=>{
 const {h,reloads}=await fieldTransitionFixture(),p=h.connect();
 await h.query(p,11,{orgName:'Previous Charity'});p.onMessage.emit({action:'finish',id:id(12)});await tick();
 await h.advance(3000);const q=h.connect(2);
 assert.equal((await h.query(q,21,{ein:'271635830'})).ok,true);assert.equal(reloads(),1);
 assert.deepEqual(h.created,[100]);assert.ok(h.tabs.has(2));
});

test('NY form transition stops if the job expires during readiness inspection',async()=>{
 const {h,reloads}=await fieldTransitionFixture(),p=h.connect();
 await h.query(p,11,{ein:'271635830'});
 const original=h.chrome.tabs.sendMessage,job=vm.runInContext('allJobs()[0]',h.context);
 h.chrome.tabs.sendMessage=async(tab,m)=>{
  const result=await original(tab,m);
  if(m.action==='ready')job.activeExpiresAt=0;
  return result;
 };
 const result=await h.query(p,12,{orgName:'Achieving the Dream, Inc.'});
 assert.equal(result.ok,false);assert.equal(result.reason,'NY_CONNECTOR_INTERRUPTED');
 assert.equal(reloads(),0);assert.equal(h.queries.length,1);
});
