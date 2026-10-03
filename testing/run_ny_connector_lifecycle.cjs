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
  const tabs=new Map(initial.tabs||[[1,{id:1,windowId:10,url:'https://staging.compliance-express.com/'}],[2,{id:2,windowId:99,url:'https://charities-search.ag.ny.gov/RegistrySearch'}]]);
  let next=Math.max(100,...[...tabs.keys()].map(n=>n+1)), deferred=null, now=initial.now??10000;
  const chrome={storage:{local:area('local'),session:area('session')},runtime:{id:'fixture-extension',getManifest:()=>JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8')),onMessage:event(),onConnect:event()},tabs:{
    onRemoved:event(),create:async options=>{if(deferred)await deferred;const tab={id:next++,...options};tabs.set(tab.id,tab);created.push(tab.id);return tab;},
    get:async id=>{if(!tabs.has(id))throw Error('Tab absent');return tabs.get(id);},
    update:async(id,options)=>Object.assign(tabs.get(id),options),
    remove:async id=>{tabs.delete(id);removed.push(id);chrome.tabs.onRemoved.emit(id);},
    sendMessage:async(tab,message)=>{if(message.action==='ready')return {ready:true,url:tabs.get(tab).url};if(message.action==='back-to-results'){tabs.get(tab).url='https://charities-search.ag.ny.gov/RegistrySearch';return {ok:true};}if(message.action==='open-detail'){tabs.get(tab).url='https://charities-search.ag.ny.gov/RegistrySearch/'+message.query.orgID;return {ok:true};}queries.push({tab,...message});return {ok:true,evidence:{query:message.query,rows:[]}};}
  }};
  class Clock extends Date { static now(){return now;} }
  const recovery={clearForTab:async(tabId,owned,close)=>{repairs.push({tabId,owned});await close();}};
  const context=vm.createContext({URL,Date:Clock,chrome,CCNYRecovery:recovery,importScripts:()=>{},setTimeout:(fn,ms)=>{const t={fn,ms,due:now+ms,cleared:false};timers.push(t);return t;},clearTimeout:t=>{if(t)t.cleared=true;}});
  for(const file of ['protocol.js','registry-worker.js','worker.js']) {
    const sourceRoot=['registry-worker.js','worker.js'].includes(file)&&process.env.CC_TEST_TRIAL_DIR?process.env.CC_TEST_TRIAL_DIR:root;
    let source=fs.readFileSync(path.join(sourceRoot,file),'utf8');
    if(file==='protocol.js' && initial.trialOrigin) source=source.replace('const TRIAL_ORIGIN = "";',`const TRIAL_ORIGIN = ${JSON.stringify(initial.trialOrigin)};`);
    if(file==='protocol.js' && initial.trialOrigin && initial.trialOnly) source=source.replace('function registryAllowed(state, origin) {','function registryAllowed(state, origin) { if (origin !== TRIAL_ORIGIN || state === "NY") return false;');
    vm.runInContext(source,context);
  }
  function connect(n=1,sender={id:chrome.runtime.id,frameId:0,url:tabs.get(1).url,tab:{id:1}},refresh=false,resume=false) {
    const port={name:(resume?'cc-ny-resume-v1:':refresh?'cc-ny-refresh-v1:':'cc-ny-lookup-v1:')+id(n),sender,onMessage:event(),onDisconnect:event(),messages:[],disconnected:false,
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

for(const succeeds of [true,false])test(`trial NY open-page recovery preserves user state and retries only once: ${succeeds}`,async()=>{
 const trialOrigin='https://fixture-final-four.onrender.com';
 const h=harness({trialOrigin,tabs:[[1,{id:1,windowId:10,url:trialOrigin}],[2,{id:2,windowId:99,url:'https://charities-search.ag.ny.gov/RegistrySearch/16-40-81'}]]});
 h.recovery.clearForTab=async()=>{throw Error('NY_CONNECTOR_RECOVERY_PAGE_OPEN');};
 let calls=0;const attempts=[];
 h.chrome.tabs.sendMessage=async(tab,m)=>{
  if(m.action==='ready')return {ready:true,url:h.tabs.get(tab).url};
  calls++;attempts.push({tab,retryUsed:m.verificationRetryUsed});
  return calls===2&&succeeds?{ok:true,evidence:{query:m.query,rows:[]}}:
    {ok:false,reason:'NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED',verificationRetryUsed:true};
 };
 const p=h.connect();const result=await h.query(p,11);
 assert.equal(result.ok,succeeds);if(!succeeds)assert.equal(result.reason,'NY_CONNECTOR_RECOVERY_PAGE_OPEN');
 assert.equal(calls,2);assert.deepEqual(h.created,[100,101]);
 assert.deepEqual(attempts,[{tab:100,retryUsed:false},{tab:101,retryUsed:true}]);
 assert.equal(h.tabs.get(2).url,'https://charities-search.ag.ny.gov/RegistrySearch/16-40-81');
 assert.ok(h.removed.every(n=>n>=100));assert.deepEqual(h.data.local.ccnyRepair,{});
 assert.equal(h.data.session.ccnyRuntime.queue[0]?.activeExpiresAt ?? 310000,310000);
 if(succeeds)assert.equal(h.data.session.ccnyRuntime.queue[0].nyFreshPageRecoveryOnly,true);
});

test('mature NY and explicit refresh retain the open-page cleanup guard',async()=>{
 for(const trialOrigin of [null,'https://fixture-final-four.onrender.com']){
  const h=harness({trialOrigin});
  h.recovery.clearForTab=async()=>{throw Error('NY_CONNECTOR_RECOVERY_PAGE_OPEN');};
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true,url:h.tabs.get(tab).url}:
    {ok:false,reason:'NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED'};
  const p=h.connect(1,undefined,!!trialOrigin);let result;
  if(trialOrigin){p.onMessage.emit({action:'refresh',id:id(11)});await tick();result=p.messages.find(m=>m.id===id(11)&&!m.progress);}
  else result=await h.query(p,11);
  assert.equal(result.reason,'NY_CONNECTOR_RECOVERY_PAGE_OPEN');assert.deepEqual(h.created,[100]);
  assert.ok(h.tabs.has(2));assert.deepEqual(h.data.local.ccnyRepair,{});
 }
});

test('trial NY cancellation during cleanup cannot open another retry tab',async()=>{
 const h=harness({trialOrigin:'https://fixture-final-four.onrender.com'});let release;
 h.recovery.clearForTab=async()=>{await new Promise(resolve=>{release=resolve;});throw Error('NY_CONNECTOR_RECOVERY_PAGE_OPEN');};
 h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true,url:h.tabs.get(tab).url}:
   {ok:false,reason:'NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED'};
 const p=h.connect();await h.query(p,11);p.onMessage.emit({action:'finish',id:id(12)});await tick();release();await tick();
 assert.deepEqual(h.created,[100]);assert.deepEqual(h.removed,[100]);assert.ok(h.tabs.has(2));
 assert.equal(p.messages.some(m=>m.id===id(11)&&m.ok),false);
});
test('readiness advertises the installed manifest version',async()=>{
  const h=harness();let response;
  h.chrome.runtime.onMessage.emit({action:'ping',id:id(99)}, {id:h.chrome.runtime.id,frameId:0,url:'https://staging.compliance-express.com/',tab:{id:1}}, value=>{response=value;});
  await tick();assert.equal(response.ok,true);assert.equal(response.version,h.chrome.runtime.getManifest().version);
});

test('NV unanswered content message cannot outlive the original job deadline',async()=>{
 const h=harness();h.tabs.set(3,{id:3,url:'https://orion.nv.gov/portal/public/'});
 let release;h.chrome.tabs.sendMessage=()=>new Promise(resolve=>{release=resolve;});
 const job={tab:3,registryState:'NV',activeExpiresAt:310000,closed:false};
 const promise=h.context.registryMessage(job,{action:'registry-nv',budgetMs:110000});
 const rejected=assert.rejects(promise,/NV_COMMAND_TIMEOUT/);await tick();
 await h.advance(300000);await rejected;
 assert.equal(job.activeExpiresAt,310000);
 release({ok:true});await tick();
});

test('NV completed content response clears its worker deadline',async()=>{
 const h=harness();h.tabs.set(3,{id:3,url:'https://orion.nv.gov/portal/public/'});
 const result=await h.context.registryMessage({tab:3,registryState:'NV',activeExpiresAt:310000,closed:false},{action:'registry-nv',budgetMs:45000});
 assert.equal(result.ok,true);assert.ok(h.timers.filter(t=>t.ms===300000).every(t=>t.cleared));
});

async function nvVisibilityFixture({wrongWindow=false,unowned=false}={}) {
 const origin='https://fixture-final-four.onrender.com',h=harness({trialOrigin:origin});await tick();
 h.tabs.get(1).url=origin+'/';h.tabs.get(1).active=true;
 h.tabs.set(3,{id:3,windowId:wrongWindow?99:10,active:false,url:'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=fixture'});
 if(!unowned)vm.runInContext('owned.add(3)',h.context);
 h.chrome.tabs.query=async options=>[...h.tabs.values()].filter(t=>t.windowId===options.windowId&&t.active===options.active);
 const changes=[];
 h.chrome.tabs.update=async(id,options)=>{
  changes.push(id);if(options.active)for(const t of h.tabs.values())if(t.windowId===h.tabs.get(id).windowId)t.active=false;
  return Object.assign(h.tabs.get(id),options);
 };
 const job={tab:3,sender:{url:origin,tab:{id:1}},registryState:'NV',activeExpiresAt:70000,closed:false};
 return {h,job,changes};
}

test('NV pending detail recovers visibility without resubmission or changing its deadline',async()=>{
 const {h,job,changes}=await nvVisibilityFixture();let release,calls=0;
 h.chrome.tabs.sendMessage=async(id,m)=>{calls++;assert.equal(m.query.identifier,'NV20121738342');return new Promise(r=>{release=r;});};
 const pending=h.context.registryMessage(job,{action:'registry-nv',query:{state:'NV',operation:'detail',identifier:'NV20121738342'},budgetMs:45000});
 await tick();await h.advance(2999);assert.deepEqual(changes,[]);
 await h.advance(1);assert.deepEqual(changes,[3]);assert.equal(h.tabs.get(3).active,true);
 release({ok:true,evidence:{complete:true,identifier:'NV20121738342'}});
 assert.equal((await pending).ok,true);assert.deepEqual(changes,[3]);assert.equal(calls,1);
 await h.context.registryRestoreNevadaVisibility(job);assert.deepEqual(changes,[3,1]);
 assert.equal(job.activeExpiresAt,70000);assert.ok(h.timers.filter(t=>t.ms===60000).every(t=>t.cleared));
});

test('NV fast responses do not activate any tab',async()=>{
 const {h,job,changes}=await nvVisibilityFixture();h.chrome.tabs.sendMessage=async()=>({ok:true});
 assert.equal((await h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000})).ok,true);
 await h.advance(4000);assert.deepEqual(changes,[]);
});

test('NV stalled initial form recovers visibility despite fast readiness replies',async()=>{
 const {h,job,changes}=await nvVisibilityFixture();const calls=[];
 h.tabs.get(3).url=vm.runInContext("registryStart('NV')",h.context);
 h.chrome.tabs.sendMessage=async(id,m)=>{
  calls.push(m.action);return {ready:h.tabs.get(id).active,documentId:'same-public-document',url:h.tabs.get(id).url};
 };
 const ready=h.context.registryReady(job);await tick();await h.advance(3000);await h.advance(200);
 assert.equal((await ready).documentId,'same-public-document');
 assert.deepEqual(changes,[3]);assert.ok(calls.every(x=>x==='registry-ready'));
 assert.equal(job.activeExpiresAt,70000);
 await h.context.registryRestoreNevadaVisibility(job);assert.deepEqual(changes,[3,1]);
});

test('NV form readiness cannot override a user switch or take unowned or moved tabs',async()=>{
 for(const reason of ['unowned','wrongWindow','userSwitch']){
  const {h,job,changes}=await nvVisibilityFixture({unowned:reason==='unowned',wrongWindow:reason==='wrongWindow'});
  h.tabs.get(3).url=vm.runInContext("registryStart('NV')",h.context);
  let complete=false;
  h.chrome.tabs.sendMessage=async id=>({ready:complete,documentId:'same',url:h.tabs.get(id).url});
  const ready=h.context.registryReady(job);await tick();
  if(reason==='userSwitch'){h.tabs.get(1).active=false;h.tabs.set(4,{id:4,windowId:10,active:true,url:'https://example.com/'});}
  await h.advance(3000);assert.deepEqual(changes,[]);complete=true;await h.advance(200);await ready;
 }
});

test('NV continuation retains one visibility lease and finish restores then closes only its owned tab',async()=>{
 const {h,job,changes}=await nvVisibilityFixture();let release,calls=0;
 h.chrome.tabs.sendMessage=()=>{calls++;return calls===1?new Promise(r=>{release=r;}):Promise.resolve({ok:true});};
 const first=h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000});await tick();await h.advance(3000);
 release({ok:true});await first;
 assert.equal((await h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000})).ok,true);
 await h.advance(3000);assert.deepEqual(changes,[3]);assert.equal(calls,2);
 await h.context.close(job);assert.deepEqual(changes,[3,1]);assert.deepEqual(h.removed,[3]);
 assert.equal(h.tabs.get(1).active,true);assert.ok(h.tabs.has(2));
});

test('NV a user switch after one recovery is respected through later continuation commands',async()=>{
 const {h,job,changes}=await nvVisibilityFixture();let release;
 h.chrome.tabs.sendMessage=()=>new Promise(r=>{release=r;});
 const first=h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000});await tick();await h.advance(3000);
 release({ok:true});await first;h.tabs.get(3).active=false;
 h.tabs.set(4,{id:4,windowId:10,active:true,url:'https://example.com/'});
 const second=h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000});await tick();await h.advance(3000);
 release({ok:true});await second;await h.context.close(job);
 assert.deepEqual(changes,[3]);assert.equal(h.tabs.get(4).active,true);
});

test('NV visibility recovery preserves user switches before and after activation',async()=>{
 for(const before of [true,false]) {
  const {h,job,changes}=await nvVisibilityFixture();let release;
  h.chrome.tabs.sendMessage=()=>new Promise(r=>{release=r;});
  const pending=h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000});await tick();
  if(!before)await h.advance(3000);
  for(const tab of h.tabs.values())if(tab.windowId===10)tab.active=false;
  h.tabs.set(4,{id:4,windowId:10,active:true,url:'https://example.com/'});
  if(before)await h.advance(3000);
  release({ok:true});await pending;await h.context.registryRestoreNevadaVisibility(job);
  assert.deepEqual(changes,before?[]:[3]);assert.equal(h.tabs.get(4).active,true);
 }
});

test('NV visibility recovery cannot take unowned or moved tabs or navigate outside its source',async()=>{
 for(const reason of ['unowned','wrongWindow','sourceChanged','sourceLeft','closed']) {
  const {h,job,changes}=await nvVisibilityFixture({unowned:reason==='unowned',wrongWindow:reason==='wrongWindow'});let release;
  h.chrome.tabs.sendMessage=()=>new Promise(r=>{release=r;});
  const pending=h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000});await tick();
  if(reason==='sourceChanged')h.tabs.get(3).url='https://example.com/';
  if(reason==='sourceLeft')h.tabs.get(1).url='https://example.com/';
  if(reason==='closed')job.closed=true;
  await h.advance(3000);release({ok:false});await pending;assert.deepEqual(changes,[],reason);
 }
});

test('NV unresolved visible command still stops at its original deadline and restores its caller',async()=>{
 const {h,job,changes}=await nvVisibilityFixture();let release;
 h.chrome.tabs.sendMessage=()=>new Promise(r=>{release=r;});
 const pending=assert.rejects(h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000}),/NV_COMMAND_TIMEOUT/);
 await tick();await h.advance(60000);await pending;
 assert.deepEqual(changes,[3,1]);assert.equal(job.activeExpiresAt,70000);release({ok:true});await tick();
});

test('NV page timeout reply can trigger return recovery without a competing transport timer',async()=>{
 const h=harness();h.tabs.set(3,{id:3,url:'https://orion.nv.gov/portal/public/'});
 let release;h.chrome.tabs.sendMessage=()=>new Promise(resolve=>{release=resolve;});
 const promise=h.context.registryMessage({tab:3,registryState:'NV',activeExpiresAt:310000,closed:false},
   {action:'registry-nv-return',budgetMs:10000});await tick();
 await h.advance(10100);
 release({ok:false,reason:'NY_CONNECTOR_REGISTRY_NV_RETURN_READY_TIMEOUT'});
 assert.equal((await promise).reason,'NY_CONNECTOR_REGISTRY_NV_RETURN_READY_TIMEOUT');
 assert.ok(h.timers.filter(t=>t.ms===300000).every(t=>t.cleared));
});

test('NV fresh navigation waits for the search route before reload and ignores ready old detail',async()=>{
 const trialOrigin='https://fixture-final-four.onrender.com',h=harness({trialOrigin});
 const start=vm.runInContext("registryStart('NV')",h.context);
 const reservation='https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=NameReservationDetails&id=fixture';
 h.tabs.set(3,{id:3,windowId:10,url:reservation});let generation=1,reloads=0;
 h.chrome.tabs.update=async(id,options)=>{
  h.context.setTimeout(()=>Object.assign(h.tabs.get(id),options),400);
  return h.tabs.get(id);
 };
 h.chrome.tabs.reload=async(id)=>{assert.equal(h.tabs.get(id).url,start);generation++;reloads++;};
 h.chrome.tabs.sendMessage=async(id)=>({ready:true,documentId:String(generation),url:h.tabs.get(id).url});
 const job={tab:3,registryState:'NV',activeExpiresAt:310000,closed:false,nvReservationDetail:true};
 const pending=h.context.registryNavigate(job,start,45000,true);await tick();
 assert.equal(reloads,0);await h.advance(600);
 assert.equal((await pending).url,start);assert.equal(reloads,1);assert.equal(job.activeExpiresAt,310000);
});

test('NV wrong-route readiness cannot consume more than the original navigation allowance',async()=>{
 const h=harness({trialOrigin:'https://fixture-final-four.onrender.com'});
 const start=vm.runInContext("registryStart('NV')",h.context);
 h.tabs.set(3,{id:3,url:'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=NameReservationDetails&id=fixture'});
 let reloads=0;h.chrome.tabs.update=async(id)=>h.tabs.get(id);h.chrome.tabs.reload=async()=>{reloads++;};
 h.chrome.tabs.sendMessage=async(id)=>({ready:true,documentId:'old',url:h.tabs.get(id).url});
 const job={tab:3,registryState:'NV',activeExpiresAt:310000,closed:false,nvReservationDetail:true};
 const pending=assert.rejects(h.context.registryNavigate(job,start,45000,true));await tick();await h.advance(45000);
 await pending;assert.equal(reloads,0);assert.equal(job.activeExpiresAt,310000);
});

test('NV fresh return reloads the committed public route even when its old form never becomes ready',async()=>{
 const h=harness({trialOrigin:'https://fixture-final-four.onrender.com'});
 const start=vm.runInContext("registryStart('NV')",h.context);
 h.tabs.set(3,{id:3,url:'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=NameReservationDetails&id=fixture'});
 let generation=1,reloads=0;
 h.chrome.tabs.update=async(id,options)=>{
  h.context.setTimeout(()=>Object.assign(h.tabs.get(id),options),400);return h.tabs.get(id);
 };
 h.chrome.tabs.reload=async(id)=>{assert.equal(h.tabs.get(id).url,start);generation++;reloads++;};
 h.chrome.tabs.sendMessage=async(id)=>({ready:generation>1,documentId:String(generation),url:h.tabs.get(id).url});
 const job={tab:3,registryState:'NV',activeExpiresAt:310000,closed:false,nvReservationDetail:true};
 const pending=h.context.registryNavigate(job,start,45000,true);await tick();
 assert.equal(reloads,0);await h.advance(600);
 assert.equal(reloads,1,'The planned refresh must not depend on the stale form becoming usable');
 assert.equal((await pending).ready,true);assert.equal(job.activeExpiresAt,310000);
});

for(const failed of ['form','document'])test(`NV fresh return still requires a new ready document after reload: ${failed}`,async()=>{
 const h=harness({trialOrigin:'https://fixture-final-four.onrender.com'});
 const start=vm.runInContext("registryStart('NV')",h.context);
 h.tabs.set(3,{id:3,url:'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=NameReservationDetails&id=fixture'});
 let generation=1,reloads=0;
 h.chrome.tabs.reload=async()=>{reloads++;if(failed!=='document')generation++;};
 h.chrome.tabs.sendMessage=async(id)=>({ready:failed!=='form',documentId:String(generation),url:h.tabs.get(id).url});
 const job={tab:3,registryState:'NV',activeExpiresAt:310000,closed:false,nvReservationDetail:true};
 const pending=assert.rejects(h.context.registryNavigate(job,start,45000,true),/TAB_READY_TIMEOUT/);
 await tick();await h.advance(45000);await pending;
 assert.equal(reloads,1);assert.equal(job.activeExpiresAt,310000);assert.equal(h.queries.length,0);
});

test('NV navigation-only readiness cannot weaken another state or a results-document wait',async()=>{
 const h=harness({trialOrigin:'https://fixture-final-four.onrender.com'});
 for(const [state,oldDocument,path] of [['TN',null,'/portal/registered-charities-search'],['NC',null,'/online_services/search/by_title/search_charities'],['NV','old','/portal/public/'],['NV',null,'/other']]){
  const job={tab:3,registryState:state,activeExpiresAt:310000,closed:false};
  await assert.rejects(h.context.registryReady(job,oldDocument,path,45000,null,true),/INVALID_SEQUENCE/);
 }
 assert.equal(h.queries.length,0);
});

for(const next of ['search','detail','changed-detail'])test(`NV reservation return uses public form and preserves identity: ${next}`,async()=>{
 const trialOrigin='https://fixture-final-four.onrender.com',h=harness({trialOrigin});
 const start=vm.runInContext("registryStart('NV')",h.context),reservation='https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=NameReservationDetails&id=fixture';
 h.tabs.set(1,{id:1,windowId:10,url:trialOrigin});h.tabs.set(3,{id:3,windowId:10,url:reservation});
 let generation=1,reloads=0;const actions=[];
 const prior={query:{state:'NV',operation:'search',name:'Example'},evidence:{query:{state:'NV',operation:'search',name:'Example'},complete:true,total:1,rows:[{identifier:'NV12345',name:'Example'}]}};
 h.chrome.tabs.reload=async()=>{generation++;reloads++;};
 h.chrome.tabs.sendMessage=async(tab,m)=>{
  actions.push(m);
  if(m.action==='registry-ready')return {ready:true,documentId:String(generation),url:h.tabs.get(tab).url};
  if(m.action==='registry-nv-return')throw Error('Reservation Back would leave public search');
  if(m.query.operation==='search')return {ok:true,evidence:{...prior.evidence,query:m.query,
    rows:next==='changed-detail'?[{identifier:'NV12345',name:'Other Organization'}]:prior.evidence.rows}};
  return {ok:true,evidence:{query:m.query,complete:true,fields:{'NV Business ID':'NV12345'}}};
 };
 const job={tab:3,registryState:'NV',activeExpiresAt:310000,closed:false,finalFourSearchComplete:true,
   nvReservationDetail:true,nvLastSearch:prior,sender:{url:trialOrigin,tab:{id:1}}};
 const query=next==='search'?{state:'NV',operation:'search',name:'Next Alias'}:{state:'NV',operation:'detail',identifier:'NV12345'};
 const promise=h.context.performRegistryQuery(job,query);
 if(next==='changed-detail')await assert.rejects(promise,/NV_RESTORED_RESULTS_CHANGED/);
 else assert.equal((await promise).ok,true);
 assert.equal(reloads,1);assert.equal(h.tabs.get(3).url,start);assert.equal(job.activeExpiresAt,310000);
 const searches=actions.filter(m=>m.query?.operation==='search');assert.equal(searches.length,1);
 assert.equal(searches[0].query.name,next==='search'?'Next Alias':'Example');
 if(next==='changed-detail')assert.equal(actions.some(m=>m.query?.operation==='detail'),false);
});

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
  const h=harness();for(const changes of [{url:'https://example.com/'},{url:'https://www.compliance-express.com.evil.example/'},{id:'another-extension'},{frameId:1}]){
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
    await tick();if(close==='disconnect')await h.advance(90000);
    assert.deepEqual(h.removed,[100]);assert.ok(h.tabs.has(2));assert.equal(p.disconnected,true);
  }
});
test('closing origin during tab creation cannot leak its newly created tab',async()=>{
  const h=harness();let release;h.deferCreate(new Promise(resolve=>{release=resolve;}));const p=h.connect();p.onMessage.emit({action:'search',id:id(11),query:ein});
  await tick();h.chrome.tabs.onRemoved.emit(1);release();await tick();assert.deepEqual(h.removed,[100]);assert.deepEqual(h.queries,[]);
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
  const q=h.connect(2);await tick();h.timers.filter(t=>t.ms===1200000).at(-1).fn();await tick();
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

for(const recovered of [true,false])test(`trial NY reset cooldown still permits one normal fresh lookup: ${recovered}`,async()=>{
 const trialOrigin='https://fixture-final-four.onrender.com';
 const saved={phase:'failed',attemptedAt:5000,nextAllowedAt:999999,reason:'NY_CONNECTOR_RECOVERY_REJECTED'};
 const h=harness({trialOrigin,local:{ccnyRepair:saved},tabs:[[1,{id:1,windowId:10,url:trialOrigin}]]});
 let attempts=0;
 h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true,url:h.tabs.get(tab).url}:
  (attempts++,recovered?{ok:true,evidence:{query:m.query,rows:[]}}:
   {ok:false,reason:'NY_CONNECTOR_SEARCH_VERIFICATION_REJECTED',verificationRetryUsed:true});
 const p=h.connect();const result=await h.query(p,11);
 assert.equal(result?.ok,recovered);assert.equal(attempts,1);assert.deepEqual(h.created,[100]);
 assert.equal(h.repairs.length,0);assert.equal(h.data.local.ccnyRepair.nextAllowedAt,999999);
 if(!recovered)assert.equal(result.reason,'NY_CONNECTOR_RECOVERY_REJECTED');
 if(recovered)assert.equal(h.data.session.ccnyRuntime.queue[0].activeExpiresAt,310000);
 else {assert.equal(h.data.session.ccnyRuntime.queue.length,0);assert.deepEqual(h.removed,[100]);}
 assert.ok(h.timers.some(t=>t.due===310000));
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
  await h.query(p,11);h.chrome.tabs.onRemoved.emit(1);release();await tick();
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


test('verified detail navigation closes only owned detail tabs and releases queue',async()=>{
  const h=harness(),p=h.connect();await h.query(p,901);
  assert.equal((await h.query(p,902,{orgID:'10-20-30'})).ok,true);
  h.tabs.get(100).url='https://charities-search.ag.ny.gov/RegistrySearch/10-20-30';
  assert.equal((await h.query(p,903,{orgID:'11-22-33'})).ok,true);
  p.onMessage.emit({action:'finish',id:id(904)});await tick();
  assert.deepEqual(h.removed,[100]);assert(h.tabs.has(2));
  const next=h.connect(2);await h.advance(3000);assert.equal((await h.query(next,905)).ok,true);
});

module.exports={harness,tick,id};

for(const scenario of ['success','rejected-again','verify-fails','late','mature'])test(`NY detail authorization recovery remains bounded: ${scenario}`,async()=>{
 const trialOrigin=scenario==='mature'?null:'https://fixture-final-four.onrender.com';
 const h=harness({trialOrigin});if(trialOrigin)h.tabs.get(1).url=trialOrigin;
 let searches=0,verifications=0,backs=0,opens=0;const deadlines=[];
 h.chrome.tabs.sendMessage=async(tab,m)=>{
  if(m.action==='ready')return {ready:true,url:h.tabs.get(tab).url,documentId:String(opens)+String(backs)};
  if(m.action==='back-to-results'){assert.equal(m.trialNavigation,trialOrigin?true:undefined);backs++;h.tabs.get(tab).url='https://charities-search.ag.ny.gov/RegistrySearch';return {ok:true};}
  if(m.action==='open-detail'){assert.equal(m.trialNavigation,trialOrigin?true:undefined);opens++;h.tabs.get(tab).url='https://charities-search.ag.ny.gov/RegistrySearch/'+m.query.orgID;return {ok:true};}
  if(m.action==='verify'){verifications++;assert.equal(m.verificationRetryUsed,true);return scenario==='verify-fails'?{ok:false,reason:'NY_CONNECTOR_VERIFICATION_REJECTED'}:{ok:true,evidence:{verified:true}};}
  searches++;deadlines.push(h.data.session.ccnyRuntime.queue[0].activeExpiresAt);
  return searches===2&&scenario==='success'?{ok:true,evidence:{query:m.query}}:{ok:false,reason:'NY_CONNECTOR_DETAIL_UNAUTHORIZED'};
 };
 const p=h.connect();await tick();if(scenario==='late')await h.advance(286000);
 let result=await h.query(p,11,{orgID:'12-34-56'});await tick();
 result=p.messages.find(m=>m.id===id(11)&&!m.progress);
 assert.equal(result?.ok,scenario==='success');
 assert.equal(verifications,['mature','late'].includes(scenario)?0:1);
 assert.equal(searches,scenario==='success'||scenario==='rejected-again'?2:1);
 assert.equal(h.repairs.length,0);assert.ok(h.tabs.has(2));
 if(scenario==='verify-fails')assert.equal(result.reason,'NY_CONNECTOR_VERIFICATION_REJECTED');
 else if(scenario!=='success')assert.equal(result.reason,'NY_CONNECTOR_DETAIL_UNAUTHORIZED');
 assert.ok(deadlines.length);assert.ok(deadlines.every(value=>value===310000));
});
