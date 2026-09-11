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
function harness() {
  const timers=[],created=[],removed=[],queries=[];
  const tabs=new Map([[1,{id:1,url:'https://staging.compliance-express.com/'}],[2,{id:2,url:'https://charities-search.ag.ny.gov/RegistrySearch'}]]);
  let next=100, deferred=null;
  const chrome={runtime:{id:'fixture-extension',onMessage:event(),onConnect:event()},tabs:{
    onRemoved:event(),create:async options=>{if(deferred)await deferred;const tab={id:next++,...options};tabs.set(tab.id,tab);created.push(tab.id);return tab;},
    get:async id=>{if(!tabs.has(id))throw Error('Tab absent');return tabs.get(id);},
    update:async(id,options)=>Object.assign(tabs.get(id),options),
    remove:async id=>{tabs.delete(id);removed.push(id);chrome.tabs.onRemoved.emit(id);},
    sendMessage:async(tab,message)=>{if(message.action==='ready')return {ready:true};queries.push({tab,...message});return {ok:true,evidence:{query:message.query,rows:[]}};}
  }};
  const context=vm.createContext({URL,chrome,importScripts:()=>{},setTimeout:(fn,ms)=>{const t={fn,ms,cleared:false};timers.push(t);return t;},clearTimeout:t=>{if(t)t.cleared=true;}});
  for(const file of ['protocol.js','worker.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
  function connect(n=1,sender={id:chrome.runtime.id,frameId:0,url:tabs.get(1).url,tab:{id:1}}) {
    const port={name:'cc-ny-lookup-v1:'+id(n),sender,onMessage:event(),onDisconnect:event(),messages:[],disconnected:false,
      postMessage:m=>port.messages.push(JSON.parse(JSON.stringify(m))),disconnect:()=>{if(!port.disconnected){port.disconnected=true;port.onDisconnect.emit();}}};
    chrome.runtime.onConnect.emit(port);return port;
  }
  const query=async(port,n,q=ein)=>{port.onMessage.emit({action:'search',id:id(n),query:q});await tick();return port.messages.find(m=>m.id===id(n));};
  return {chrome,tabs,timers,created,removed,queries,connect,query,deferCreate:p=>{deferred=p;}};
}
test('one owned tab serves EIN and name; finish closes only that tab',async()=>{
  const h=harness(),p=h.connect();assert.equal((await h.query(p,11)).ok,true);assert.equal((await h.query(p,12,name)).ok,true);
  assert.equal(h.created.length,1);assert.deepEqual(h.queries.map(q=>q.tab),[100,100]);assert.deepEqual(h.queries.map(q=>q.query),[ein,name]);
  p.onMessage.emit({action:'finish',id:id(13)});await tick();assert.deepEqual(h.removed,[100]);assert.ok(h.tabs.has(2));assert.ok(p.messages.find(m=>m.id===id(13)&&m.ok));
  const next=h.connect(2);await h.query(next,21);assert.deepEqual(h.created,[100,101]);
});
test('different originating lookups cannot share active tab or evidence',async()=>{
  const h=harness(),p=h.connect();await h.query(p,11);const other=h.connect(2);
  assert.equal(other.messages[0].reason,'NY_CONNECTOR_BUSY');assert.equal(other.disconnected,true);assert.equal(p.disconnected,false);assert.equal(h.created.length,1);
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
  p.disconnect();release();await tick();assert.deepEqual(h.removed,[100]);assert.deepEqual(h.queries,[]);
});
test('overlapping query cannot consume another query response',async()=>{
  const h=harness();let release;h.deferCreate(new Promise(resolve=>{release=resolve;}));const p=h.connect();p.onMessage.emit({action:'search',id:id(11),query:ein});
  const second=await h.query(p,12,name);assert.equal(second.reason,'NY_CONNECTOR_BUSY');release();await tick();assert.deepEqual(h.queries.map(q=>q.query),[ein]);
});
test('wrong query evidence and navigated registry tab fail closed',async()=>{
  for(const mode of ['wrong-query','navigated']){
    const h=harness(),p=h.connect();await h.query(p,11);
    if(mode==='navigated')h.tabs.get(100).url='https://example.com/';
    else h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:true,evidence:{query:ein,rows:[]}};
    assert.equal((await h.query(p,12,name)).reason,'NY_CONNECTOR_INCOMPLETE');assert.equal(p.disconnected,true);assert.deepEqual(h.removed,[100]);
  }
});
