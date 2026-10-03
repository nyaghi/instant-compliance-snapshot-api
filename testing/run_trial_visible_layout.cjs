const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {harness,tick}=require('./run_ny_connector_lifecycle.cjs');
const ORIGIN='https://fixture-final-four.onrender.com';
const URL=ORIGIN+'/connector/final-four-validation.html?collector_layout=visible';
async function setup(url=URL,bounds={left:20,top:30,width:1400,height:1000,state:'normal'}){
 const h=harness({trialOrigin:ORIGIN,tabs:[[1,{id:1,windowId:10,url,active:true}]]});await tick();
 const created=[];
 h.chrome.windows.get=async id=>{assert.equal(id,10);return bounds;};
 h.chrome.windows.create=async options=>{
  created.push(options);const tab=await h.chrome.tabs.create({id:100+created.length,windowId:20+created.length,active:true,url:options.url});
  return {tabs:[tab]};
 };
 return {h,created,job:state=>({tab:null,registryState:state,sender:{tab:{id:1}},activeExpiresAt:70000,closed:false})};
}
test('visible validation creates four disjoint collector windows inside the source bounds',async()=>{
 const {h,created,job}=await setup();
 for(const state of ['NV','NY','IL','NC']){
  const j=job(state);await h.context.registryCreateOwnedTab(j,'https://example.invalid/'+state,h.tabs.get(1));
  assert.equal(j.activeExpiresAt,70000);
 }
 assert.equal(created.length,4);
 for(const r of created){
  assert.equal(r.focused,true);assert.equal(r.state,'normal');
  assert.ok(r.left>=20&&r.top>=30&&r.left+r.width<=1420&&r.top+r.height<=1030);
 }
 for(let i=0;i<4;i++)for(let j=i+1;j<4;j++){
  const a=created[i],b=created[j];
  assert.ok(a.left+a.width<=b.left||b.left+b.width<=a.left||a.top+a.height<=b.top||b.top+b.height<=a.top,'collector content cannot cover another collector');
 }
 assert.equal(h.tabs.get(1).url,URL);assert.equal(h.tabs.get(1).windowId,10);
});
test('ordinary app, normal validation, and nontrial paths never enable visible layout',async()=>{
 for(const url of [ORIGIN+'/',ORIGIN+'/?collector_layout=visible',ORIGIN+'/connector/final-four-validation.html',ORIGIN+'/connector/final-four-validation.html?collector_layout=other','https://staging.compliance-express.com/connector/final-four-validation.html?collector_layout=visible']){
  const {h,job}=await setup(url);h.chrome.windows.get=async()=>{throw Error('must not inspect window');};
  const options=await h.context.registryTrialWindowOptions(job('NV'),h.tabs.get(1));
  assert.equal(options.focused,false);assert.equal(options.width,undefined);
 }
});
test('visible layout preserves other state placement and never moves existing windows',async()=>{
 const {h,job}=await setup();h.chrome.windows.get=async()=>{throw Error('must not inspect window');};
 for(const state of ['AL','TN','GA','NM']){
  const options=await h.context.registryTrialWindowOptions(job(state),h.tabs.get(1));
  assert.equal(options.focused,false);assert.equal(options.left,undefined);
 }
});
test('visible comparison refuses unusable geometry rather than silently overlapping windows',async()=>{
 for(const bounds of [{left:0,top:0,width:900,height:900},{left:0,top:0,width:1400,height:600},{left:0,top:0,width:1400,height:900,state:'minimized'},{}]){
  const {h,job}=await setup(URL,bounds);
  await assert.rejects(h.context.registryTrialWindowOptions(job('NV'),h.tabs.get(1)),/VISIBLE_LAYOUT_UNAVAILABLE/);
 }
});
test('visible comparison respects source navigation and cancellation during geometry read',async()=>{
 for(const change of ['closed','moved','navigated']){
  const {h,job}=await setup(),j=job('NV'),source={...h.tabs.get(1)};
  h.chrome.windows.get=async()=>{
   if(change==='closed')j.closed=true;
   if(change==='moved')h.tabs.get(1).windowId=99;
   if(change==='navigated')h.tabs.get(1).url='https://example.invalid/';
   return {left:0,top:0,width:1400,height:900,state:'normal'};
  };
  await assert.rejects(h.context.registryTrialWindowOptions(j,source),/INTERRUPTED|VISIBLE_LAYOUT_UNAVAILABLE/);
  assert.equal(h.created.length,0);
 }
});

test('visible NY reuse exposes its existing owned window without refreshing verification',async()=>{
 const {h}=await setup();const changes=[];
 h.chrome.windows.update=async(id,options)=>{changes.push({id,...options});};
 h.chrome.tabs.query=async({windowId})=>[...h.tabs.values()].filter(t=>t.windowId===windowId);
 const p=h.connect();assert.equal((await h.query(p,11)).ok,true);
 p.onMessage.emit({action:'finish',id:String(12).padStart(20,'0')});await tick();
 const saved=h.data.session.ccnyRuntime.trialNyIdle,tab=h.tabs.get(saved.id);
 await h.advance(3000);
 const q=h.connect(2);assert.equal((await h.query(q,21,{ein:'987654321'})).ok,true);
 assert.deepEqual(changes,[{id:tab.windowId,focused:true}]);
 assert.equal(h.created.length,1);assert.equal(h.repairs.length,0);
 assert.equal(h.queries.length,2);assert.equal(vm.runInContext('allJobs()[0].nySessionExpiresAt',h.context),saved.expiresAt);
});

test('NY visibility reuse never takes user windows, other pages, or canceled work',async()=>{
 for(const change of ['ordinary','inactive','shared','same-window','navigated','closed','expired','source-moved']){
  const {h,job}=await setup(change==='ordinary'?ORIGIN+'/':URL),j=job('NY');
  h.tabs.set(99,{id:99,windowId:20,url:'https://charities-search.ag.ny.gov/RegistrySearch',active:true});
  vm.runInContext('owned.add(99)',h.context);j.tab=99;
  h.chrome.tabs.query=async({windowId})=>[...h.tabs.values()].filter(t=>t.windowId===windowId);
  const source={...h.tabs.get(1)},tab=h.tabs.get(99);
  if(change==='inactive')tab.active=false;
  if(change==='shared')h.tabs.set(98,{id:98,windowId:20,url:'https://example.com',active:false});
  if(change==='same-window')tab.windowId=10;
  if(change==='navigated')tab.url='https://example.com';
  if(change==='closed')j.closed=true;
  if(change==='expired')j.activeExpiresAt=0;
  if(change==='source-moved')h.tabs.get(1).windowId=42;
  h.chrome.windows.update=async()=>assert.fail('must not focus');
  await h.context.registryExposeReusedNyTab(j,source);
 }
});
