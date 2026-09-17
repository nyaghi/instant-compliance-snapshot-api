const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname,'..','browser-connector');
const event = () => { const listeners=[];return {addListener:f=>listeners.push(f),emit:(...args)=>listeners.forEach(f=>f(...args))}; };
const tick = () => new Promise(resolve=>setImmediate(resolve));
const id = n => String(n).padStart(20,'0');
const ein = {ein:'123456789'}, name = {orgName:'Example National Foundation'};
function harness(initial={}) {
  const timers=[],created=[],removed=[],queries=[],repairs=[];
  const data={local:initial.local||{},session:initial.session||{}};
  const area=name=>({get:async key=>({[key]:data[name][key]}),set:async value=>Object.assign(data[name],JSON.parse(JSON.stringify(value))),setAccessLevel:async()=>{}});
  const tabs=new Map([[1,{id:1,windowId:10,url:'https://staging.compliance-express.com/'}],[2,{id:2,windowId:99,url:'https://charities-search.ag.ny.gov/RegistrySearch'}]]);
  let next=100, deferred=null, now=10000;
  const chrome={storage:{local:area('local'),session:area('session')},runtime:{id:'fixture-extension',onMessage:event(),onConnect:event()},tabs:{
    onRemoved:event(),create:async options=>{if(deferred)await deferred;const tab={id:next++,...options};tabs.set(tab.id,tab);created.push(tab.id);return tab;},
    get:async id=>{if(!tabs.has(id))throw Error('Tab absent');return tabs.get(id);},
    update:async(id,options)=>Object.assign(tabs.get(id),options),
    remove:async id=>{tabs.delete(id);removed.push(id);chrome.tabs.onRemoved.emit(id);},
    sendMessage:async(tab,message)=>{if(message.action==='ready')return {ready:true};queries.push({tab,...message});return {ok:true,evidence:{query:message.query,rows:[]}};}
  }};
  class Clock extends Date { static now(){return now;} }
  const recovery={clearForTab:async(tabId,owned,close)=>{repairs.push({tabId,owned});await close();}};
  const context=vm.createContext({URL,Date:Clock,chrome,CCNYRecovery:recovery,importScripts:()=>{},setTimeout:(fn,ms)=>{const t={fn,ms,due:now+ms,cleared:false};timers.push(t);return t;},clearTimeout:t=>{if(t)t.cleared=true;}});
  for(const file of ['protocol.js','worker.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
  function connect(n=1,sender={id:chrome.runtime.id,frameId:0,url:tabs.get(1).url,tab:{id:1}},refresh=false) {
    const port={name:(refresh?'cc-ny-refresh-v1:':'cc-ny-lookup-v1:')+id(n),sender,onMessage:event(),onDisconnect:event(),messages:[],disconnected:false,
      postMessage:m=>port.messages.push(JSON.parse(JSON.stringify(m))),disconnect:()=>{if(!port.disconnected){port.disconnected=true;port.onDisconnect.emit();}}};
    chrome.runtime.onConnect.emit(port);return port;
  }
  const query=async(port,n,q=ein)=>{port.onMessage.emit({action:'search',id:id(n),query:q});await tick();return port.messages.find(m=>m.id===id(n)&&!m.progress);};
  async function advance(ms) {
    const end=now+ms;
    for (;;) {
      const t=timers.filter(t=>!t.cleared&&t.due<=end).sort((a,b)=>a.due-b.due)[0];
      if(!t)break;now=t.due;t.cleared=true;t.fn();await tick();
    }
    now=end;await tick();
  }
  return {chrome,tabs,timers,created,removed,queries,repairs,recovery,data,context,connect,query,advance,deferCreate:p=>{deferred=p;}};
}
test('one owned tab serves EIN and name; finish closes only that tab',async()=>{
  const h=harness(),p=h.connect();assert.equal((await h.query(p,11)).ok,true);assert.equal((await h.query(p,12,name)).ok,true);
  assert.equal(h.created.length,1);assert.deepEqual(h.queries.map(q=>q.tab),[100,100]);assert.deepEqual(h.queries.map(q=>q.query),[ein,name]);
  p.onMessage.emit({action:'finish',id:id(13)});await tick();assert.deepEqual(h.removed,[100]);assert.ok(h.tabs.has(2));assert.ok(p.messages.find(m=>m.id===id(13)&&m.ok));
  const next=h.connect(2);await h.advance(3000);await h.query(next,21);assert.deepEqual(h.created,[100,101]);
});
test('different originating lookups cannot share active tab or evidence',async()=>{
  const h=harness(),p=h.connect();await h.query(p,11);const other=h.connect(2);
  other.onMessage.emit({action:'acquire',id:id(20)});await tick();
  assert.equal(other.messages[0].position,1);assert.equal(other.disconnected,false);assert.equal(p.disconnected,false);assert.equal(h.created.length,1);
  assert.equal((await h.query(other,21,name)).reason,'NY_CONNECTOR_INVALID_SEQUENCE');
  assert.deepEqual(h.queries.map(q=>q.query),[ein]);
});
test('cross-origin, wrong-extension and subframe ports cannot start a lookup',async()=>{
  const h=harness();for(const changes of [{url:'https://compliance-express.com/'},{id:'another-extension'},{frameId:1}]){
    const p=h.connect(1,{id:h.chrome.runtime.id,frameId:0,url:'https://staging.compliance-express.com/',tab:{id:1},...changes});
    assert.equal(p.disconnected,true);await h.query(p,11);
  }assert.deepEqual(h.created,[]);
});
test('heartbeat never extends five-minute expiry and expiry is inconclusive',async()=>{
  const h=harness(),p=h.connect();await h.query(p,11);const expiry=h.timers.find(t=>t.ms===300000);
  for(let i=0;i<20;i++)p.onMessage.emit({action:'heartbeat'});
  assert.equal(h.timers.filter(t=>t.ms===300000).length,1);expiry.fn();await tick();
  assert.equal(p.messages.at(-1).reason,'NY_CONNECTOR_TIMEOUT');assert.deepEqual(h.removed,[100]);assert.equal(p.disconnected,true);
});
test('origin disconnect and user closing either involved tab clean up safely',async()=>{
  for(const close of ['disconnect','origin','registry']){
    const h=harness(),p=h.connect();await h.query(p,11);
    if(close==='disconnect')p.disconnect();else h.chrome.tabs.onRemoved.emit(close==='origin'?1:100);
    await tick();assert.deepEqual(h.removed,[100]);assert.ok(h.tabs.has(2));assert.equal(p.disconnected,true);
  }
});
test('closing origin during tab creation cannot leak its newly created tab',async()=>{
  const h=harness();let release;h.deferCreate(new Promise(resolve=>{release=resolve;}));const p=h.connect();p.onMessage.emit({action:'search',id:id(11),query:ein});
  await tick();p.disconnect();release();await tick();assert.deepEqual(h.removed,[100]);assert.deepEqual(h.queries,[]);
});
test('overlapping query cannot consume another query response',async()=>{
  const h=harness();let release;h.deferCreate(new Promise(resolve=>{release=resolve;}));const p=h.connect();p.onMessage.emit({action:'search',id:id(11),query:ein});
  const second=await h.query(p,12,name);assert.equal(second.reason,'NY_CONNECTOR_INVALID_SEQUENCE');release();await tick();assert.deepEqual(h.queries.map(q=>q.query),[ein]);
});
test('wrong query evidence and navigated registry tab fail closed',async()=>{
  for(const mode of ['wrong-query','navigated']){
    const h=harness(),p=h.connect();await h.query(p,11);
    if(mode==='navigated')h.tabs.get(100).url='https://example.com/';
    else h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:true,evidence:{query:ein,rows:[]}};
    assert.equal((await h.query(p,12,name)).reason,'NY_CONNECTOR_INCOMPLETE');assert.equal(p.disconnected,true);assert.deepEqual(h.removed,mode==='navigated'?[]:[100]);
  }
});

for (const count of [5,10,15]) test(count+' simultaneous sessions complete FIFO without sharing evidence',async()=>{
  const h=harness(),ports=Array.from({length:count},(_,i)=>h.connect(i+1));
  ports.forEach((p,i)=>p.onMessage.emit({action:'acquire',id:id(1000+i)}));
  await tick();
  for(let i=0;i<count;i++){
    assert.ok(ports[i].messages.some(m=>m.id===id(1000+i)&&m.ok));
    assert.ok(ports.slice(i+1).every(p=>!p.messages.some(m=>m.ok)));
    const query={ein:String(100000000+i)};
    const result=await h.query(ports[i],2000+i,query);
    assert.deepEqual(result.evidence.query,query);
    assert.equal(h.created.length,i+1);assert.equal(h.removed.length,i);
    ports[i].onMessage.emit({action:'finish',id:id(3000+i)});await tick();
    assert.equal(h.removed.length,i+1);
    await h.advance(3000);
  }
  assert.ok(ports.every(p=>p.disconnected));
  assert.ok(ports.every(p=>p.messages.every(m=>m.reason!=='NY_CONNECTOR_BUSY')));
});
test('queued cancellation advances position without touching active tab',async()=>{
  const h=harness(),p=h.connect(1);await h.query(p,11);
  const second=h.connect(2),third=h.connect(3);
  third.onMessage.emit({action:'acquire',id:id(31)});
  second.disconnect();await tick();assert.equal(third.messages.at(-1).position,1);
  assert.equal(h.removed.length,0);assert.equal(p.disconnected,false);
  p.onMessage.emit({action:'finish',id:id(12)});await tick();await h.advance(3000);
  assert.ok(third.messages.at(-1).ok);
});
test('queue expiry does not expire or extend the active lookup',async()=>{
  const h=harness(),p=h.connect(1);await h.query(p,11);
  const q=h.connect(2);h.timers.filter(t=>t.ms===1200000).at(-1).fn();await tick();
  assert.equal(q.messages.at(-1).reason,'NY_CONNECTOR_QUEUE_TIMEOUT');assert.equal(p.disconnected,false);
  assert.equal(h.timers.filter(t=>t.ms===300000).length,1);
});
test('rate limiting retries only twice with bounded pauses and same owned tab',async()=>{
  for (const recover of [true,false]) {
    const h=harness(),p=h.connect();let searches=0;
    h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:
      (++searches<=2||!recover?{ok:false,reason:'NY_CONNECTOR_RATE_LIMITED'}:{ok:true,evidence:{query:m.query,rows:[]}});
    await h.query(p,11);assert.equal(searches,1);
    await h.advance(5000);assert.equal(searches,2);
    await h.advance(15000);assert.equal(searches,3);
    const final=p.messages.find(m=>m.id===id(11)&&!m.progress);
    assert.equal(final.ok,recover);if(!recover)assert.equal(final.reason,'NY_CONNECTOR_RATE_LIMITED');
    assert.equal(h.created.length,1);
  }
});

test('Chrome without local storage access-level method still initializes',async()=>{
  const h=harness();delete h.chrome.storage.local.setAccessLevel;
  const p=h.connect();assert.equal((await h.query(p,11)).ok,true);
});

test('session persistence failure closes owned tab and releases queue capacity',async()=>{
  const h=harness(),p=h.connect();await h.query(p,11);
  h.chrome.storage.session.set=async()=>{throw Error('fixture storage failure');};
  p.onMessage.emit({action:'finish',id:id(12)});await tick();
  assert.equal(p.disconnected,true);assert.deepEqual(h.removed,[100]);
  h.chrome.storage.session.set=async value=>Object.assign(h.data.session,value);
  const next=h.connect(2);await h.advance(3000);assert.equal((await h.query(next,21)).ok,true);
});

test('registry tabs stay in the originating window even when another window is current',async()=>{
  const h=harness(),p=h.connect();await h.query(p,11);
  assert.equal(h.tabs.get(100).windowId,10);assert.equal(h.tabs.get(2).windowId,99);
  assert.equal(h.tabs.get(2).active,undefined);
});

test('queued origin moved to another window is resolved when its lookup starts',async()=>{
  const h=harness(),first=h.connect(1);await h.query(first,11);
  h.tabs.set(3,{id:3,windowId:20,url:'https://staging.compliance-express.com/'});
  const second=h.connect(2,{id:h.chrome.runtime.id,frameId:0,url:h.tabs.get(3).url,tab:{id:3}});
  h.tabs.get(3).windowId=30;
  first.onMessage.emit({action:'finish',id:id(12)});await tick();await h.advance(3000);
  assert.equal((await h.query(second,21)).ok,true);assert.equal(h.tabs.get(101).windowId,30);
});

test('missing origin cannot create a registry tab in another window',async()=>{
  const h=harness(),p=h.connect();h.tabs.delete(1);
  assert.equal((await h.query(p,11)).reason,'NY_CONNECTOR_INCOMPLETE');
  assert.deepEqual(h.created,[]);assert.equal(p.disconnected,true);assert.ok(h.tabs.has(2));
});

test('one 401 recovery replaces only the owned tab and retries the same query',async()=>{
  const h=harness(),p=h.connect();let attempts=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:
    (++attempts===1?{ok:false,reason:'NY_CONNECTOR_VERIFICATION_REJECTED'}:{ok:true,evidence:{query:m.query,rows:[]}});
  const result=await h.query(p,11);
  assert.equal(result.ok,true);assert.equal(attempts,2);assert.equal(h.repairs.length,1);
  assert.deepEqual(h.created,[100,101]);assert.deepEqual(h.removed,[100]);assert.ok(h.tabs.has(2));
  assert.equal(h.data.local.ccnyRepair.phase,'verified');
  assert.equal(h.tabs.get(101).active,false);
});

test('failed repair stops queued lookups without fifteen separate resets',async()=>{
  const h=harness(),ports=Array.from({length:15},(_,i)=>h.connect(i+1));let attempts=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:(attempts++,{ok:false,reason:'NY_CONNECTOR_VERIFICATION_REJECTED'});
  const result=await h.query(ports[0],11);await tick();await h.advance(3000);
  assert.equal(result.reason,'NY_CONNECTOR_RECOVERY_REJECTED');
  assert.equal(h.repairs.length,1);assert.equal(attempts,2);
  assert.ok(ports.every(p=>p.disconnected));assert.equal(h.data.local.ccnyRepair.phase,'failed');
  assert.ok(ports.slice(1).every(p=>p.messages.some(m=>m.reason==='NY_CONNECTOR_RECOVERY_REJECTED')));
});

test('recent successful repair does not grant a new reset for every organization',async()=>{
  const h=harness({local:{ccnyRepair:{phase:'verified',attemptedAt:5000,nextAllowedAt:999999,finishedAt:6000}}}),p=h.connect();
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:false,reason:'NY_CONNECTOR_VERIFICATION_REJECTED'};
  assert.equal((await h.query(p,11)).reason,'NY_CONNECTOR_RECOVERY_REJECTED');assert.equal(h.repairs.length,0);
  assert.equal(h.data.local.ccnyRepair.phase,'failed');
});

test('ordinary source network/schema failures never trigger cookie cleanup',async()=>{
  for(const reason of ['NY_CONNECTOR_SEARCH_NETWORK_ERROR','NY_CONNECTOR_SEARCH_ROWS_INVALID','NY_CONNECTOR_TIMEOUT']){
    const h=harness(),p=h.connect();h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:false,reason};
    assert.equal((await h.query(p,11)).reason,reason);assert.equal(h.repairs.length,0);
  }
});

test('user NY page blocker preserves the repair allowance for a later valid attempt',async()=>{
  const h=harness(),p=h.connect();h.recovery.clearForTab=async()=>{throw Error('NY_CONNECTOR_RECOVERY_PAGE_OPEN');};
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:false,reason:'NY_CONNECTOR_VERIFICATION_REJECTED'};
  assert.equal((await h.query(p,11)).reason,'NY_CONNECTOR_RECOVERY_PAGE_OPEN');
  assert.deepEqual(h.data.local.ccnyRepair,{});assert.ok(h.tabs.has(2));
});

test('cleanup failure and interrupted repair remain bounded after worker restart',async()=>{
  const h=harness(),p=h.connect();h.recovery.clearForTab=async()=>{throw Error('storage failed');};
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:false,reason:'NY_CONNECTOR_VERIFICATION_REJECTED'};
  await h.query(p,11);assert.equal(h.data.local.ccnyRepair.phase,'failed');
  const restarted=harness({local:JSON.parse(JSON.stringify(h.data.local))});const q=restarted.connect();await tick();
  assert.equal(q.disconnected,true);assert.equal(restarted.created.length,0);assert.equal(restarted.repairs.length,0);
  const interrupted=harness({local:{ccnyRepair:{phase:'repairing',attemptedAt:9000,nextAllowedAt:900000}}});const r=interrupted.connect();await tick();
  assert.equal(r.disconnected,true);assert.equal(interrupted.data.local.ccnyRepair.reason,'NY_CONNECTOR_INTERRUPTED');
});

test('manual refresh verifies normally and queued duplicate refreshes join it',async()=>{
  const h=harness(),a=h.connect(1,undefined,true),b=h.connect(2,undefined,true);let verifies=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:(verifies++,{ok:true,evidence:{verified:true}});
  await tick();a.onMessage.emit({action:'refresh',id:id(11)});await tick();
  assert.ok(a.messages.some(m=>m.id===id(11)&&m.verified));
  a.onMessage.emit({action:'finish',id:id(12)});await tick();await h.advance(3000);
  b.onMessage.emit({action:'refresh',id:id(21)});await tick();
  assert.ok(b.messages.some(m=>m.id===id(21)&&m.verified));assert.equal(h.repairs.length,1);assert.equal(verifies,1);
});

test('manual refresh cannot bypass the persisted recovery pause',async()=>{
  const h=harness({local:{ccnyRepair:{phase:'failed',nextAllowedAt:999999,reason:'NY_CONNECTOR_RECOVERY_REJECTED'}}});
  const p=h.connect(1,undefined,true);await tick();p.onMessage.emit({action:'refresh',id:id(11)});await tick();
  assert.equal(p.messages.find(m=>m.id===id(11)).reason,'NY_CONNECTOR_RECOVERY_COOLDOWN');assert.equal(h.repairs.length,0);
});

test('manual refresh preserves network, timeout and incomplete causes for the waiting queue',async()=>{
  for(const reason of ['NY_CONNECTOR_VERIFICATION_NETWORK_ERROR','NY_CONNECTOR_TIMEOUT','NY_CONNECTOR_VERIFICATION_REQUIRED','NY_CONNECTOR_RATE_LIMITED']){
    const h=harness(),p=h.connect(1,undefined,true),q=h.connect(2);
    let verifies=0;
    h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:(verifies++,{ok:false,reason});
    await tick();p.onMessage.emit({action:'refresh',id:id(11)});await tick();await h.advance(3000);
    assert.equal(p.messages.find(m=>m.id===id(11)&&!m.progress).reason,reason);
    assert.equal(h.data.local.ccnyRepair.reason,reason);
    assert.ok(q.messages.some(m=>m.reason===reason));
    assert.equal(h.repairs.length,1);assert.equal(verifies,1);
  }
});

test('manual refresh reports rejected only for an observed rejection',async()=>{
  for(const [reply,reason] of [
    [{ok:false,reason:'NY_CONNECTOR_VERIFICATION_REJECTED'},'NY_CONNECTOR_RECOVERY_REJECTED'],
    [{ok:true,evidence:{verified:false}},'NY_CONNECTOR_INCOMPLETE'],
    [{ok:false,reason:'untrusted arbitrary text'},'NY_CONNECTOR_INCOMPLETE']
  ]){
    const h=harness(),p=h.connect(1,undefined,true);
    h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:reply;
    await tick();p.onMessage.emit({action:'refresh',id:id(11)});await tick();
    assert.equal(p.messages.find(m=>m.id===id(11)&&!m.progress).reason,reason);
    assert.equal(h.data.local.ccnyRepair.reason,reason);
  }
});

test('schema failure after automatic repair retains its cause in later queue results',async()=>{
  const h=harness(),p=h.connect(),q=h.connect(2);let searches=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:false,reason:++searches===1?'NY_CONNECTOR_VERIFICATION_REJECTED':'NY_CONNECTOR_SEARCH_ROWS_INVALID'};
  assert.equal((await h.query(p,11)).reason,'NY_CONNECTOR_SEARCH_ROWS_INVALID');
  await h.advance(3000);
  assert.equal(h.data.local.ccnyRepair.reason,'NY_CONNECTOR_SEARCH_ROWS_INVALID');
  assert.ok(q.messages.some(m=>m.reason==='NY_CONNECTOR_SEARCH_ROWS_INVALID'));
  assert.equal(h.repairs.length,1);
});

test('closing an origin during cleanup never sends a late recovered result',async()=>{
  const h=harness(),p=h.connect();let release;
  h.recovery.clearForTab=async(tabId,ids,close)=>{await close();await new Promise(r=>{release=r;});};
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:false,reason:'NY_CONNECTOR_VERIFICATION_REJECTED'};
  await h.query(p,11);p.disconnect();release();await tick();
  assert.equal(p.messages.some(m=>m.id===id(11)&&m.ok),false);assert.deepEqual(h.created,[100]);
  assert.equal(h.data.local.ccnyRepair.phase,'failed');
});

test('stalled tab removal releases the slot within the cleanup bound',async()=>{
  const h=harness(),p=h.connect(),q=h.connect(2);await h.query(p,11);let release;
  const remove=h.chrome.tabs.remove;
  h.chrome.tabs.remove=async id=>{if(id===100)await new Promise(r=>release=r);return remove(id);};
  p.onMessage.emit({action:'finish',id:id(12)});await tick();
  await h.advance(10000);assert.ok(p.messages.some(m=>m.id===id(12)&&m.ok));
  await h.advance(3000);assert.equal((await h.query(q,21)).ok,true);
  release();await tick();assert.ok(h.tabs.has(101));
});
