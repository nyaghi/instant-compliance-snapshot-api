const {test}=require('node:test');
const assert=require('node:assert/strict');
const {harness,tick,id}=require('./run_ny_connector_lifecycle.cjs');
function event(){const list=[];return {addListener:f=>list.push(f),emit:(...a)=>list.forEach(f=>f(...a))};}
function connect(h,state,n=1,origin='https://staging.compliance-express.com/') {
  const p={name:`cc-${state.toLowerCase()}-lookup-v1:`+id(n),sender:{id:h.chrome.runtime.id,frameId:0,url:origin,tab:{id:1}},onMessage:event(),onDisconnect:event(),messages:[],disconnected:false,
    postMessage:m=>p.messages.push(JSON.parse(JSON.stringify(m))),disconnect:()=>{p.disconnected=true;p.onDisconnect.emit();}};
  h.chrome.runtime.onConnect.emit(p);return p;
}
function registryFixture(h) {
  let serial=0;const docs=new Map();
  const create=h.chrome.tabs.create,update=h.chrome.tabs.update;
  h.chrome.tabs.create=async options=>{const t=await create(options);docs.set(t.id,++serial);return t;};
  h.chrome.tabs.update=async (id,options)=>{docs.set(id,++serial);return update(id,options);};
  h.chrome.tabs.reload=async id=>{docs.set(id,++serial);};
  h.chrome.tabs.sendMessage=async(tab,m)=>{
    const t=h.tabs.get(tab);
    if(m.action==='registry-ready')return {ready:true,url:t.url,documentId:String(docs.get(tab))};
    if(m.action==='registry-il')return {ok:true,evidence:{query:m.query,complete:true,total:0,rows:[]}};
    if(m.action==='registry-ga-form'){t.url='https://verify.sos.ga.gov/verification/SearchResults.aspx';docs.set(tab,++serial);return {ok:true,phase:'submitted'};}
    if(m.action==='registry-ga-rows')return {ok:true,rows:[],page:1,next:false};
    throw Error('Unexpected action: '+m.action);
  };
}
test('IL exact EIN query returns complete evidence through the existing queue',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'IL');
  const result=await h.query(p,20,{state:'IL',ein:'363673599'});
  assert.equal(result.ok,true);assert.equal(result.evidence.complete,true);
  assert.match(h.tabs.get(h.created[0]).url,/illinoisattorneygeneral/);
  p.onMessage.emit({action:'finish',id:id(21)});await tick();assert.deepEqual(h.removed,h.created);assert.ok(h.tabs.has(2));
});
test('Illinois follow-up explicitly reloads the same URL before reading a new document',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'IL');
  assert.equal((await h.query(p,20,{state:'IL',ein:'363673599'})).ok,true);
  let reloaded=0;const reload=h.chrome.tabs.reload;
  h.chrome.tabs.reload=async id=>{reloaded++;return reload(id);};
  assert.equal((await h.query(p,21,{state:'IL',identifier:'01015532'})).ok,true);
  assert.equal(reloaded,1);assert.equal(h.created.length,1);
});
test('Georgia normal form navigation produces a completed empty result',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'GA');
  const result=await h.query(p,20,{state:'GA',orgName:'Nonexistent Control'});
  assert.equal(result.ok,true);assert.equal(result.evidence.total,0);
});
test('a state-specific port rejects evidence requested for a different state',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'IL');
  const result=await h.query(p,20,{state:'GA',orgName:'Control'});
  assert.equal(result.ok,false);assert.equal(h.created.length,0);
});
test('new states are staging-only and cannot be opened from production',async()=>{
  const h=harness();registryFixture(h);
  for(const state of ['IL','GA'])assert.equal(connect(h,state,1,'https://www.compliance-express.com/').disconnected,true);
  assert.equal(h.created.length,0);
});
test('New York verification recovery does not block Illinois',async()=>{
  const h=harness({local:{ccnyRepair:{phase:'failed',nextAllowedAt:500000,reason:'NY_CONNECTOR_RECOVERY_REJECTED'}}});registryFixture(h);
  const p=connect(h,'IL');assert.equal((await h.query(p,20,{state:'IL',ein:'363673599'})).ok,true);
  assert.equal(h.repairs.length,0);
});
test('new states use the same FIFO queue and separate owned tabs',async()=>{
  const h=harness();registryFixture(h);const il=connect(h,'IL');
  assert.equal((await h.query(il,20,{state:'IL',ein:'363673599'})).ok,true);
  const ga=connect(h,'GA',2);ga.onMessage.emit({action:'acquire',id:id(21)});await tick();assert.equal(ga.messages.at(-1).position,1);
  il.onMessage.emit({action:'finish',id:id(22)});await tick();await h.advance(3000);
  assert.equal((await h.query(ga,23,{state:'GA',orgName:'Control'})).ok,true);
  assert.equal(h.created.length,2);assert.notEqual(h.created[0],h.created[1]);
});
