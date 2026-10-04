const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {harness,tick}=require('./run_ny_connector_lifecycle.cjs');
const ORIGIN='https://fixture-final-four.onrender.com';
async function setup(){
 const h=harness({trialOrigin:ORIGIN,tabs:[[1,{id:1,windowId:10,url:ORIGIN+'/',active:true}]]});await tick();
 h.tabs.set(3,{id:3,windowId:20,url:'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=external-GenericFilingsSearch&tabRoute=business',active:true});
 h.tabs.set(4,{id:4,windowId:30,url:'https://charitable.illinoisattorneygeneral.gov/search',active:true});
 h.tabs.set(5,{id:5,windowId:40,url:'https://charities-search.ag.ny.gov/RegistrySearch',active:true});
 vm.runInContext('owned.add(3);owned.add(4);owned.add(5)',h.context);
 const bounds={left:20,top:30,width:1400,height:1000,state:'normal'};
 const windows=new Map([10,20,30,40,99].map(id=>[id,{id,...bounds,focused:id===10}]));const changes=[];
 h.chrome.windows.get=async id=>({...windows.get(id)});
 h.chrome.windows.getLastFocused=async()=>({...([...windows.values()].find(w=>w.focused)||windows.get(99))});
 h.chrome.windows.update=async(id,options)=>{changes.push({id,...options});if(options.focused)for(const w of windows.values())w.focused=false;return Object.assign(windows.get(id),options);};
 h.chrome.tabs.query=async q=>[...h.tabs.values()].filter(t=>(q.windowId===undefined||t.windowId===q.windowId)&&(q.active===undefined||t.active===q.active));
 const job={tab:3,sender:{tab:{id:1}},registryState:'NV',activeExpiresAt:70000,closed:false};
 return {h,job,windows,changes,focus:id=>{for(const w of windows.values())w.focused=w.id===id;}};
}
test('NV isolated stalled command exposes only its smaller owned window once, with no resubmission',async()=>{
 const {h,job,windows,changes}=await setup();let release,calls=0;
 h.chrome.tabs.sendMessage=async()=>{calls++;return new Promise(r=>release=r);};
 const pending=h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000});await tick();
 await h.advance(2999);assert.equal(changes.length,0);await h.advance(1);
 assert.equal(changes.length,1);assert.equal(changes[0].id,20);assert.equal(changes[0].focused,true);
 assert.ok(changes[0].width<1400&&changes[0].height<1000,'cannot cover the entire other collectors');
 assert.equal(windows.get(30).width,1400);assert.equal(windows.get(40).width,1400);
 release({ok:true});assert.equal((await pending).ok,true);assert.equal(calls,1);assert.equal(job.activeExpiresAt,70000);
 await h.context.registryRestoreNevadaVisibility(job);assert.deepEqual(changes.map(x=>x.id),[20,10]);
 assert.equal(h.tabs.get(4).active,true);assert.equal(h.tabs.get(5).active,true);
});
test('NV isolated quick command never changes focus or window geometry',async()=>{
 const {h,job,changes}=await setup();h.chrome.tabs.sendMessage=async()=>({ok:true});
 await h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000});await h.advance(4000);assert.deepEqual(changes,[]);
});
test('NV isolated recovery does not override switched, moved, canceled, expired, or user-owned pages',async()=>{
 for(const change of ['focus','source-tab','source-url','moved','shared','unowned','closed','expired','minimized']){
  const {h,job,windows,changes,focus}=await setup();
  const snapshot=await h.context.registryNevadaVisibleSnapshot(job);assert.ok(snapshot);
  if(change==='focus')focus(99);
  if(change==='source-tab'){h.tabs.get(1).active=false;h.tabs.set(9,{id:9,windowId:10,active:true,url:'https://example.org/'});}
  if(change==='source-url')h.tabs.get(1).url='https://example.org/';
  if(change==='moved')h.tabs.get(3).windowId=99;
  if(change==='shared')h.tabs.set(9,{id:9,windowId:20,active:false,url:'https://example.org/'});
  if(change==='unowned')vm.runInContext('owned.delete(3)',h.context);
  if(change==='closed')job.closed=true;
  if(change==='expired')job.activeExpiresAt=0;
  if(change==='minimized')windows.get(20).state='minimized';
  assert.equal(await h.context.registryNevadaMakeVisible(job,snapshot),null,change);assert.deepEqual(changes,[],change);
 }
});
test('NV restoration leaves a subsequent user window switch untouched',async()=>{
 const {h,job,changes,focus}=await setup();
 await h.context.registryNevadaMakeVisible(job,await h.context.registryNevadaVisibleSnapshot(job));
 assert.equal(changes.length,1);focus(99);await h.context.registryRestoreNevadaVisibility(job);assert.equal(changes.length,1);
});
test('NV recovery rechecks foreground after asynchronous geometry reads',async()=>{
 const {h,job,changes,focus}=await setup();const snapshot=await h.context.registryNevadaVisibleSnapshot(job);
 const get=h.chrome.windows.get;h.chrome.windows.get=async id=>{focus(99);return get(id);};
 assert.equal(await h.context.registryNevadaMakeVisible(job,snapshot),null);assert.deepEqual(changes,[]);
});
test('NV distinguishes a concurrent owned Tennessee activation from a user tab switch',async()=>{
 const {h,job,changes}=await setup();const snapshot=await h.context.registryNevadaVisibleSnapshot(job);
 h.tabs.get(1).active=false;
 h.tabs.set(6,{id:6,windowId:10,active:true,url:'https://tncab.tnsos.gov/portal/registered-charities-search'});
 vm.runInContext('owned.add(6)',h.context);
 assert.ok(await h.context.registryNevadaMakeVisible(job,snapshot));
 assert.equal(job.nvPreviousVisible.id,6);assert.equal(changes.length,1);
 await h.context.registryRestoreNevadaVisibility(job);assert.deepEqual(changes.map(x=>x.id),[20,10]);
 assert.equal(h.tabs.get(6).active,true);
});
test('NV never claims an unrelated tab or a non-Nevada job',async()=>{
 for(const reason of ['personal-tab','NY','IL','NC']){
  const {h,job,windows,focus}=await setup();
  if(reason==='native-app')for(const w of windows.values())w.focused=false;
  else if(reason==='personal-tab'){focus(99);h.tabs.set(9,{id:9,windowId:99,active:true,url:'https://example.org/'});}
  else job.registryState=reason;
  assert.equal(await h.context.registryNevadaVisibleSnapshot(job),null,reason);
 }
});

test('NV may activate an initially unfocused owned browser once without a reload or deadline change',async()=>{
 const {h,job,windows,changes,focus}=await setup();focus(10);
 for(const w of windows.values())w.focused=false;
 h.chrome.windows.getLastFocused=async()=>({...windows.get(10)});
 const snapshot=await h.context.registryNevadaVisibleSnapshot(job);
 assert.equal(snapshot.browserFocused,false);
 assert.ok(await h.context.registryNevadaMakeVisible(job,snapshot));
 assert.equal(changes.length,1);assert.equal(changes[0].id,20);assert.equal(changes[0].focused,true);
 assert.equal(job.activeExpiresAt,70000);assert.equal(h.repairs.length,0);assert.equal(h.queries.length,0);
 assert.equal(await h.context.registryNevadaMakeVisible(job,snapshot),null);
 assert.equal(changes.length,1);
});

test('NV cancels activation if browser focus changes after the captured lease',async()=>{
 for(const initiallyFocused of [true,false]){
  const {h,job,windows,changes}=await setup();windows.get(10).focused=initiallyFocused;
  h.chrome.windows.getLastFocused=async()=>({...windows.get(10)});
  const snapshot=await h.context.registryNevadaVisibleSnapshot(job);assert.ok(snapshot);
  windows.get(10).focused=!initiallyFocused;
  assert.equal(await h.context.registryNevadaMakeVisible(job,snapshot),null);
  assert.equal(changes.length,0);
 }
});
test('NV may recover from an unchanged owned collector without editing its page or restoring a closed collector',async()=>{
 const {h,job,changes,focus}=await setup();focus(30);
 await h.context.registryNevadaMakeVisible(job,await h.context.registryNevadaVisibleSnapshot(job));assert.equal(changes.length,1);
 assert.equal(h.tabs.get(4).url,'https://charitable.illinoisattorneygeneral.gov/search');
 h.tabs.delete(4);await h.context.registryRestoreNevadaVisibility(job);assert.equal(changes.length,1);
});
test('NV isolated stalled command retains its deadline and restores after timeout',async()=>{
 const {h,job,changes}=await setup();h.chrome.tabs.sendMessage=()=>new Promise(()=>{});
 const pending=assert.rejects(h.context.registryMessage(job,{action:'registry-nv',budgetMs:45000}),/NV_COMMAND_TIMEOUT/);
 await tick();await h.advance(60000);await pending;assert.deepEqual(changes.map(x=>x.id),[20,10]);assert.equal(job.activeExpiresAt,70000);
});

test('NV detail permits one new guarded visibility recovery after search, with no extra registry command',async()=>{
 const {h,job,changes,focus}=await setup();job.nvVisibilityAttempted=true;focus(30);
 let release,commands=0;
 h.chrome.tabs.sendMessage=async(id,m)=>m.action==='registry-ready'?{page_visibility:'hidden'}:(commands++,new Promise(r=>release=r));
 const pending=h.context.registryMessage(job,{action:'registry-nv',query:{operation:'detail'},budgetMs:45000});await tick();await h.advance(3000);
 assert.equal(changes.length,1);assert.equal(job.nvDetailVisibilityChecked,true);assert.equal(commands,1);
 release({ok:true});await pending;
 focus(30);h.chrome.tabs.sendMessage=async()=>({ok:true});
 await h.context.registryMessage(job,{action:'registry-nv',query:{operation:'detail'},budgetMs:45000});await h.advance(3000);
 assert.equal(changes.length,1);assert.equal(job.activeExpiresAt,70000);
});
test('NV detail recovery preserves a user window switch',async()=>{
 const {h,job,changes,focus}=await setup();job.nvVisibilityAttempted=true;focus(99);
 h.chrome.tabs.sendMessage=async(id,m)=>m.action==='registry-ready'?{page_visibility:'hidden'}:{ok:true};
 await h.context.registryMessage(job,{action:'registry-nv',query:{operation:'detail'},budgetMs:45000});await h.advance(3000);
 assert.equal(changes.length,0);
});
