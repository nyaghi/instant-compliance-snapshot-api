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
