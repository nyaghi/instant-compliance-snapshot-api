const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const {harness,tick}=require('./run_ny_connector_lifecycle.cjs');
const ORIGIN='https://fixture-final-four.onrender.com';
async function setup(state='NC') {
 const h=harness({trialOrigin:ORIGIN,tabs:[[1,{id:1,windowId:10,url:ORIGIN+'/',active:true}]]});await tick();
 const url=vm.runInContext(`registryStart('${state}')`,h.context);
 h.tabs.set(3,{id:3,windowId:20,url,active:true});vm.runInContext('owned.add(3)',h.context);
 const changes=[],bounds={left:10,top:20,width:1400,height:1000,state:'normal'};
 h.chrome.tabs.query=async q=>[...h.tabs.values()].filter(t=>t.windowId===q.windowId&&(q.active===undefined||t.active===q.active));
 h.chrome.windows.get=async id=>({id,...bounds});
 h.chrome.windows.getLastFocused=async()=>({id:10,focused:true});
 h.chrome.windows.update=async(id,options)=>{changes.push({id,...options});return {id,...bounds,...options};};
 return {h,changes,job:{registryState:state,tab:3,sender:{tab:{id:1}},activeExpiresAt:70000,closed:false},bounds};
}
test('small source window uses its actual display rectangle for all five isolated collectors',async()=>{
 const {h,job,bounds}=await setup();Object.assign(bounds,{width:560,height:400});
 h.chrome.tabs.sendMessage=async(id,m)=>{assert.equal(id,1);assert.equal(m.action,'trial-collector-display');return {left:-1920,top:0,width:1920,height:1040};};
 const positions=[];
 for(const state of ['NV','NY','IL','NC','TN']){
  const p=await h.context.registryTrialWindowOptions({...job,registryState:state},h.tabs.get(1));
  assert.equal(p.focused,true);assert.ok(p.left>=-1920&&p.left+p.width<=0);positions.push(p);
 }
 for(let i=0;i<positions.length;i++)for(let j=i+1;j<positions.length;j++){
  const a=positions[i],b=positions[j];assert.ok(a.left+a.width<=b.left||b.left+b.width<=a.left||a.top+a.height<=b.top||b.top+b.height<=a.top);
 }
 assert.equal(bounds.width,560);assert.equal(job.activeExpiresAt,70000);assert.equal(h.created.length,0);
});
test('invalid work area and minimized source never cause unbounded placement',async()=>{
 for(const display of [{left:0,top:0,width:900,height:600},{left:0,top:0,width:Infinity,height:900},{left:999999,top:0,width:1920,height:1040},{}]){
  const {h,job,bounds}=await setup();Object.assign(bounds,{width:560,height:400});h.chrome.tabs.sendMessage=async()=>display;
  assert.equal((await h.context.registryTrialWindowOptions(job,h.tabs.get(1))).focused,false);
 }
 const {h,job,bounds}=await setup();bounds.state='minimized';h.chrome.tabs.sendMessage=async()=>assert.fail('minimized source must not request layout');
 assert.equal((await h.context.registryTrialWindowOptions(job,h.tabs.get(1))).focused,false);
});
test('NC verification exposes its owned separate window without another search or a longer deadline',async()=>{
 const {h,job,changes}=await setup();
 await h.context.registryNorthCarolinaVisibility(job);
 assert.equal(changes.length,1);assert.equal(changes[0].id,20);assert.equal(changes[0].focused,true);
 assert.equal(h.created.length,0);assert.equal(h.queries.length,0);assert.equal(job.activeExpiresAt,70000);assert.equal(h.tabs.get(1).active,true);
});
test('NC recovery refuses user changes, shared windows, navigation, cancellation and expiry',async()=>{
 for(const condition of ['unowned','shared','unrelated-focus','focus-changed','source-moved','navigated','closed','expired']){
  const {h,job,changes}=await setup();
  if(condition==='unowned')vm.runInContext('owned.delete(3)',h.context);
  if(condition==='shared')h.tabs.set(4,{id:4,windowId:20,url:'https://example.org',active:false});
  if(condition==='unrelated-focus'){h.tabs.set(4,{id:4,windowId:30,url:'https://example.org',active:true});h.chrome.windows.getLastFocused=async()=>({id:30,focused:true});}
  if(condition==='focus-changed'){let calls=0;h.chrome.windows.getLastFocused=async()=>({id:++calls===1?10:30,focused:true});}
  if(condition==='source-moved')h.chrome.windows.get=async()=>{h.tabs.get(1).windowId=99;return {left:0,top:0,width:1400,height:1000};};
  if(condition==='navigated')h.tabs.get(3).url='https://example.org/';
  if(condition==='closed')job.closed=true;
  if(condition==='expired')job.activeExpiresAt=0;
  await h.context.registryNorthCarolinaVisibility(job);assert.equal(changes.length,0,condition);
 }
});
test('NV readiness reassesses unavailable ownership once after collector setup completes',async()=>{
 const {h,job,changes}=await setup('NV');
 h.tabs.set(4,{id:4,windowId:30,url:'https://charitable.illinoisattorneygeneral.gov/search',active:true});
 h.chrome.windows.getLastFocused=async()=>({id:30,focused:true});
 h.chrome.tabs.sendMessage=async()=>({ready:changes.length>0,page_visibility:changes.length?'visible':'hidden',documentId:'nv-form',url:h.tabs.get(3).url});
 const pending=h.context.registryReady(job,null,null,6000);await tick();
 await h.advance(2000);vm.runInContext('owned.add(4)',h.context);await h.advance(1400);
 assert.equal(changes.length,1);const result=await pending;assert.equal(result.ready,true);assert.equal(job.activeExpiresAt,70000);
});
test('NV small-source recovery preserves an already coordinated display footprint',async()=>{
 const {h,job,changes,bounds}=await setup('NV');Object.assign(bounds,{width:560,height:400});
 h.chrome.tabs.sendMessage=async(id,m)=>m.action==='trial-collector-display'?{left:0,top:0,width:1920,height:1040}:{page_visibility:'hidden'};
 const placement=await h.context.registryTrialWindowOptions(job,h.tabs.get(1));
 h.chrome.windows.get=async id=>id===10?{id,...bounds}:{id,...placement};
 const snapshot=await h.context.registryNevadaVisibleSnapshot(job);assert.ok(snapshot.coordinatedPlacement);
 await h.context.registryNevadaMakeVisible(job,snapshot);
 assert.equal(changes.length,1);assert.equal(changes[0].width,placement.width);assert.equal(changes[0].height,placement.height);
});
test('display bridge answers only the same extension background in its isolated origin',()=>{
 const listeners=[],screen={availLeft:0,availTop:0,availWidth:1920,availHeight:1040},window={screen,addEventListener:()=>{}};window.top=window;
 const context={CCNYProtocol:{TRIAL_ORIGIN:ORIGIN,allowedOrigin:()=>true},location:{origin:ORIGIN},window,chrome:{runtime:{id:'fixture',onMessage:{addListener:f=>listeners.push(f)}}}};
 const root=process.env.CC_TEST_TRIAL_DIR||path.join(__dirname,'../browser-connector');
 vm.runInNewContext(fs.readFileSync(path.join(root,'staging-bridge.js'),'utf8'),context);
 assert.equal(listeners.length,1);const replies=[];
 for(const sender of [{id:'other'},{id:'fixture',tab:{id:3}}])listeners[0]({action:'trial-collector-display'},sender,x=>replies.push(x));
 assert.equal(replies.length,0);listeners[0]({action:'trial-collector-display'},{id:'fixture'},x=>replies.push(x));
 assert.equal(replies.length,1);assert.deepEqual(JSON.parse(JSON.stringify(replies[0])),{left:0,top:0,width:1920,height:1040});
});

test('NV exposes only its isolated collector when Chrome is inactive on a stale unrelated tab',async()=>{
 const {h,job,changes}=await setup('NV');
 h.tabs.set(4,{id:4,windowId:30,url:'https://example.org/user-page',active:true});
 let focus={id:30,focused:false};h.chrome.windows.getLastFocused=async()=>focus;
 const snapshot=await h.context.registryNevadaVisibleSnapshot(job);
 assert.equal(snapshot.inactiveBrowser,true);assert.ok(snapshot.coordinatedPlacement);
 await h.context.registryNevadaMakeVisible(job,snapshot);
 assert.equal(changes.length,1);assert.equal(changes[0].id,20);
 assert.equal(job.nvInactiveBrowserActivationUsed,true);
 assert.equal(job.nvVisibilityOutcome,'activated_from_inactive_browser');
 assert.equal(job.activeExpiresAt,70000);assert.equal(h.queries.length,0);
 focus={id:20,focused:true};await h.context.registryRestoreNevadaVisibility(job);
 assert.equal(changes.length,1,'Unrelated prior window must never be restored or changed');
 focus={id:30,focused:false};job.nvVisibilityAttempted=false;
 assert.equal(await h.context.registryNevadaVisibleSnapshot(job),null,'One inactive-browser activation per job');
});

test('NV inactive-browser recovery cancels for an active user page or a context change',async()=>{
 for(const condition of ['already-focused','focus-changed','tab-changed','shared','expired','closed']){
  const {h,job,changes}=await setup('NV');
  h.tabs.set(4,{id:4,windowId:30,url:'https://example.org/user-page',active:true});
  let focus={id:30,focused:condition==='already-focused'};
  h.chrome.windows.getLastFocused=async()=>focus;
  const snapshot=await h.context.registryNevadaVisibleSnapshot(job);
  if(condition==='already-focused'){assert.equal(snapshot,null);continue;}
  assert.ok(snapshot);
  if(condition==='focus-changed')focus={id:30,focused:true};
  if(condition==='tab-changed')h.tabs.get(4).url='https://example.org/changed';
  if(condition==='shared')h.tabs.set(5,{id:5,windowId:20,url:'https://example.org/shared',active:false});
  if(condition==='expired')job.activeExpiresAt=0;
  if(condition==='closed')job.closed=true;
  await h.context.registryNevadaMakeVisible(job,snapshot);
  assert.equal(changes.length,0,condition);
 }
});
