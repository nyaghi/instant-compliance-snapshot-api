const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const sandbox=vm.createContext({URL,require:n=>n==='node:test'?{test:()=>{}}:require(n),__dirname,setImmediate});
vm.runInContext(fs.readFileSync(path.join(__dirname,'run_ny_connector_lifecycle.cjs'),'utf8'),sandbox);
const harness=initial=>{sandbox.input=initial||{};return vm.runInContext('harness(input)',sandbox);};
const tick=()=>new Promise(r=>setImmediate(r));const id=n=>String(n).padStart(20,'0');
const snapshot=h=>({session:JSON.parse(JSON.stringify(h.data.session)),local:JSON.parse(JSON.stringify(h.data.local)),tabs:JSON.parse(JSON.stringify([...h.tabs]))});

test('transient port loss reconnects same job and replays completed response without another search',async()=>{
 const h=harness(),p=h.connect();const first=await h.query(p,11);p.disconnect();await tick();
 const resumed=h.connect(1,undefined,false,true);await tick();const replay=await h.query(resumed,11);
 assert.deepEqual(replay,first);assert.equal(h.queries.length,1);assert.equal(h.removed.length,0);
 assert.ok(resumed.messages.some(m=>m.action==='resumed'));
});
test('reconnect of an in-flight query joins its result instead of starting another query',async()=>{
 const h=harness(),p=h.connect();let release;
 h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:await new Promise(r=>release=()=>r({ok:true,evidence:{query:m.query,rows:[]}}));
 await h.query(p,11);p.disconnect();await tick();const resumed=h.connect(1,undefined,false,true);await tick();
 await h.query(resumed,11);release();await tick();assert.ok(resumed.messages.some(m=>m.id===id(11)&&m.ok));
 assert.equal(h.created.length,1);
});
test('worker restart restores FIFO and original active/queued deadlines',async()=>{
 const h=harness(),first=h.connect(1);await h.query(first,11);h.connect(2);h.connect(3);await tick();
 const saved=snapshot(h),expiry=saved.session.ccnyRuntime.queue.map(j=>[j.id,j.expiresAt,j.activeExpiresAt]);
 const r=harness({...saved,now:20000});const last=r.connect(3,undefined,false,true);await tick();
 assert.ok(last.messages.some(m=>m.action==='resumed'));
 assert.deepEqual(JSON.parse(JSON.stringify(r.data.session.ccnyRuntime.queue.map(j=>[j.id,j.expiresAt,j.activeExpiresAt]))),expiry);
 const p=r.connect(1,undefined,false,true);await tick();assert.equal((await r.query(p,11)).ok,true);assert.equal(r.queries.length,0);
 const second=r.connect(2,undefined,false,true);await tick();second.onMessage.emit({action:'acquire',id:id(21)});
 p.onMessage.emit({action:'finish',id:id(12)});await tick();await r.advance(3000);
 assert.ok(second.messages.some(m=>m.id===id(21)&&m.ok));assert.ok(!last.messages.some(m=>m.ok));
});
test('other tabs cannot take over a stored job even with its ID',async()=>{
 const h=harness(),p=h.connect();await h.query(p,11);const before=h.queries.length;
 const bad=h.connect(1,{id:h.chrome.runtime.id,frameId:0,url:'https://staging.compliance-express.com/',tab:{id:2}},false,true);await tick();
 assert.equal(bad.messages.at(-1).reason,'NY_CONNECTOR_INTERRUPTED');assert.equal(h.queries.length,before);assert.equal(p.disconnected,false);
});
test('unknown resumed ID cannot silently create a fresh job or reset a deadline',async()=>{
 const h=harness(),p=h.connect(99,undefined,false,true);await tick();assert.equal(p.messages.at(-1).reason,'NY_CONNECTOR_INTERRUPTED');assert.equal(h.created.length,0);
});
test('replayed command ID cannot change EIN',async()=>{
 const h=harness(),p=h.connect();await h.query(p,11,{ein:'123456789'});p.messages.length=0;assert.equal((await h.query(p,11,{ein:'987654321'})).reason,'NY_CONNECTOR_INVALID_SEQUENCE');assert.equal(h.queries.length,1);
});
test('restored retry and verification budgets are not reset',async()=>{
 const h=harness(),p=h.connect();await h.query(p,11);vm.runInContext('active.rateRetries=2;active.timeoutRetries=1;active.verificationRetryUsed=true;',h.context);await vm.runInContext('saveRuntime()',h.context);
 const r=harness(snapshot(h));r.connect(1,undefined,false,true);await tick();
 const saved=r.data.session.ccnyRuntime.queue[0];assert.equal(saved.rateRetries,2);assert.equal(saved.timeoutRetries,1);assert.equal(saved.verificationRetryUsed,true);
});
test('active expiry still terminates a recovered connection at the original deadline',async()=>{
 const h=harness(),p=h.connect();await h.query(p,11);const r=harness({...snapshot(h),now:309000});const resumed=r.connect(1,undefined,false,true);await tick();await r.advance(1000);
 assert.ok(resumed.messages.some(m=>m.reason==='NY_CONNECTOR_TIMEOUT'));assert.equal(r.created.length,0);
});
test('worker owns keepalive only while bounded work exists',async()=>{
 const h=harness();await tick();assert.ok(!h.timers.some(t=>t.ms===20000&&!t.cleared));const p=h.connect();await h.query(p,11);
 assert.ok(h.timers.some(t=>t.ms===20000&&!t.cleared));p.onMessage.emit({action:'finish',id:id(12)});await tick();assert.ok(!h.timers.some(t=>t.ms===20000&&!t.cleared));
});
test('restart preserves the remaining rate-limit pause before retrying',async()=>{
 const h=harness(),p=h.connect();h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:false,reason:'NY_CONNECTOR_RATE_LIMITED'};
 await h.query(p,11);const r=harness({...snapshot(h),now:12000});const resumed=r.connect(1,undefined,false,true);await tick();await r.query(resumed,11);
 assert.equal(r.queries.length,0);await r.advance(2999);assert.equal(r.queries.length,0);await r.advance(1);
 assert.equal(r.queries.length,1);assert.equal(r.queries[0].attempt,'0:1');
});
test('a different document in the same tab cannot resume the saved search',async()=>{
 const h=harness(),sender={id:h.chrome.runtime.id,frameId:0,url:'https://staging.compliance-express.com/',tab:{id:1},documentId:'original-document'};
 const p=h.connect(1,sender);await h.query(p,11);const r=harness(snapshot(h));const changed=r.connect(1,{...sender,documentId:'new-document'},false,true);await tick();
 assert.equal(changed.messages.at(-1).reason,'NY_CONNECTOR_INTERRUPTED');assert.equal(r.queries.length,0);
});
