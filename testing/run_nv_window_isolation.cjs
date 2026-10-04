const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {harness,tick}=require('./run_ny_connector_lifecycle.cjs');
const TRIAL='https://fixture-final-four.onrender.com';

async function setup(trial=true){
  const h=harness(trial?{trialOrigin:TRIAL}:{});await tick();
  if(trial)h.tabs.get(1).url=TRIAL+'/';
  h.tabs.get(1).active=true;
  const windows=[];
  h.chrome.windows={create:async options=>{
    windows.push(options);
    const windowId=19+windows.length;
    const tab=await h.chrome.tabs.create({windowId,active:true,url:options.url});
    return {id:windowId,tabs:[tab]};
  }};
  h.chrome.tabs.query=async q=>[...h.tabs.values()].filter(t=>t.windowId===q.windowId&&t.active===q.active);
  h.chrome.tabs.update=async(id,options)=>{
    const tab=h.tabs.get(id);
    if(options.active)for(const other of h.tabs.values())if(other.windowId===tab.windowId)other.active=false;
    return Object.assign(tab,options);
  };
  h.chrome.tabs.sendMessage=async id=>({ready:true,documentId:'public-form',url:h.tabs.get(id).url});
  const job={tab:null,sender:{tab:{id:1}},registryState:'NV',activeExpiresAt:70000,closed:false};
  return {h,job,windows};
}

test('trial Nevada stays active when another state activates its own collector',async()=>{
  const {h,job,windows}=await setup();
  await h.context.registryNavigate(job,vm.runInContext("registryStart('NV')",h.context));
  const sourcePreserved=h.tabs.get(1).active;
  await h.context.registryNevadaMakeVisible(job,await h.context.registryNevadaVisibleSnapshot(job));
  h.tabs.set(4,{id:4,windowId:10,active:false,url:vm.runInContext("registryStart('TN')",h.context)});
  vm.runInContext('owned.add(4)',h.context);
  const tn={tab:4,sender:{tab:{id:1}},registryState:'TN',activeExpiresAt:70000,closed:false};
  await h.context.registryNorthCarolinaVisibility(tn);
  assert.equal(h.tabs.get(4).active,true);
  assert.equal(h.tabs.get(job.tab).active,true,'TN must not hide Nevada');
  assert.equal(windows.length,1);
  assert.equal(windows[0].focused,false);
  assert.equal(windows[0].type,'normal');
  assert.equal(sourcePreserved,true,'original active tab preserved');
  assert.notEqual(h.tabs.get(job.tab).windowId,h.tabs.get(4).windowId);
  assert.equal(job.activeExpiresAt,70000);
  const nvTab=job.tab;await h.context.close(job);
  assert.deepEqual(h.removed,[nvTab]);
  assert.ok(h.tabs.has(1)&&h.tabs.has(2)&&h.tabs.has(4),'no unrelated tab removed');
});

test('Nevada continuation reuses its window and ordinary states keep existing creation',async()=>{
  for(const [trial,state,expectedWindows] of [[true,'NV',1],[false,'NV',0],[true,'NC',1],[true,'TN',1],[true,'IL',1],[false,'IL',0]]){
    const {h,job,windows}=await setup(trial);job.registryState=state;
    const url=vm.runInContext(`registryStart('${state}')`,h.context);
    await h.context.registryNavigate(job,url);
    assert.equal(windows.length,expectedWindows,`${trial}/${state}`);
    assert.equal(h.created.length,1);
    assert.equal(h.tabs.get(job.tab).windowId,expectedWindows?20:10);
    if(expectedWindows){
      let document=1;
      h.chrome.tabs.reload=async()=>{document++;};
      h.chrome.tabs.sendMessage=async id=>({ready:true,documentId:String(document),url:h.tabs.get(id).url});
      await h.context.registryNavigate(job,url);
      assert.equal(windows.length,1);assert.equal(h.created.length,1);
    }
  }
});

test('North Carolina keeps its active form when Tennessee activates in the source window',async()=>{
 const {h,job,windows}=await setup();job.registryState='NC';
 await h.context.registryNavigate(job,vm.runInContext("registryStart('NC')",h.context));
 h.tabs.set(4,{id:4,windowId:10,active:false,url:vm.runInContext("registryStart('TN')",h.context)});
 vm.runInContext('owned.add(4)',h.context);
 await h.context.registryNorthCarolinaVisibility({tab:4,sender:{tab:{id:1}},registryState:'TN',closed:false});
 assert.equal(h.tabs.get(4).active,true);
 assert.equal(h.tabs.get(job.tab).active,true,'TN must not hide NC during submission');
 assert.notEqual(h.tabs.get(job.tab).windowId,h.tabs.get(4).windowId);
 assert.equal(windows[0].focused,false);assert.equal(job.activeExpiresAt,70000);
 const nc=job.tab;await h.context.close(job);assert.deepEqual(h.removed,[nc]);assert.ok(h.tabs.has(4)&&h.tabs.has(1));
});

test('Illinois trial verification can await its already active isolated form without focus changes',async()=>{
 const {h,job}=await setup();job.registryState='IL';job.activeExpiresAt=90000;
 await h.context.registryNavigate(job,vm.runInContext("registryStart('IL')",h.context));
 let allowance;
 const result=await h.context.registryIllinoisVerification(job,async ms=>{allowance=ms;return {ok:true};});
 assert.equal(result.ok,true);assert.equal(allowance,45000);assert.equal(job.activeExpiresAt,90000);
 assert.equal(h.tabs.get(1).active,true);assert.equal(h.tabs.get(job.tab).active,true);
});

test('cancellation during isolated window creation removes the owned tab',async()=>{
  const {h,job}=await setup();let release;
  h.deferCreate(new Promise(r=>{release=r;}));
  const pending=h.context.registryNavigate(job,vm.runInContext("registryStart('NV')",h.context));
  const rejected=assert.rejects(pending,/NY_CONNECTOR_TAB_READY_TIMEOUT|NY_CONNECTOR_INTERRUPTED/);
  await tick();const closing=h.context.close(job);release();await tick();await closing;await rejected;
  assert.equal(h.created.length,1);assert.deepEqual(h.removed,h.created);
  assert.ok(h.tabs.has(1)&&h.tabs.has(2));
});

test('NY trial verification retains an active page without changing mature NY placement',async()=>{
 for(const trial of [true,false]){
  const {h,job,windows}=await setup(trial);job.registryState='NY';
  await h.context.lookupTab(job);
  assert.equal(windows.length,trial?1:0);
  assert.equal(h.tabs.get(job.tab).windowId,trial?20:10);
  assert.equal(h.tabs.get(job.tab).active,trial);
  assert.equal(h.tabs.get(1).active,true);
  if(trial){
   assert.equal(windows[0].focused,false);
   h.tabs.set(4,{id:4,windowId:10,active:false,url:vm.runInContext("registryStart('TN')",h.context)});
   vm.runInContext('owned.add(4)',h.context);
   await h.context.registryNorthCarolinaVisibility({tab:4,sender:{tab:{id:1}},registryState:'TN',closed:false});
   assert.equal(h.tabs.get(job.tab).active,true);
  }
  const tab=job.tab;await h.context.close(job);assert.deepEqual(h.removed,[tab]);
 }
});

test('NV diagnostic identifies small geometry without relaxing recovery guards',async()=>{
 const {h,job}=await setup();
 const nv='https://orion.nv.gov/portal/public/';
 h.tabs.set(3,{id:3,windowId:20,url:nv,active:true});vm.runInContext('owned.add(3)',h.context);
 Object.assign(job,{tab:3,pending:'00000000000000000001'});
 const messages=[];job.port={postMessage:m=>messages.push(m)};
 h.chrome.tabs.query=async q=>[...h.tabs.values()].filter(t=>t.windowId===q.windowId&&(!q.active||t.active));
 h.chrome.windows.get=async id=>({id,left:0,top:0,width:id===10?545:700,height:id===10?400:800,state:'normal'});
 h.chrome.windows.getLastFocused=async()=>({id:10,focused:true});
 h.chrome.windows.update=async()=>{throw Error('guard must still refuse');};
 const previous={mode:'window',id:1,windowId:10,url:TRIAL+'/',nvWindowId:20,sourceWindowId:10,sourceUrl:TRIAL+'/'};
 assert.equal(await h.context.registryNevadaExposeWindow(job,previous),null);
 const d=messages[0].nv_diagnostic;
 assert.equal(d.phase,'visibility-refused');assert.equal(d.source_width_small,true);assert.equal(d.source_height_small,true);
 assert.equal(d.not_owned,false);assert.equal(d.prior_changed,false);assert.equal(d.source_width,545);
 assert.equal(job.activeExpiresAt,70000);assert.equal(job.nvVisibilityAttempted,undefined);
});

test('NV diagnostic is bounded and disabled for mature connector and other states',async()=>{
 for(const [trial,state,expected] of [[true,'NV',96],[false,'NV',0],[true,'NC',0]]) {
  const {h,job}=await setup(trial);h.tabs.set(3,{id:3,windowId:20,url:'https://orion.nv.gov/portal/public/',active:true});
  vm.runInContext('owned.add(3)',h.context);const messages=[];
  Object.assign(job,{tab:3,pending:'00000000000000000001',registryState:state,port:{postMessage:m=>messages.push(m)}});
  for(let i=0;i<110;i++)h.context.registryNevadaDiagnostic(job,'detail-clicked');
  assert.equal(messages.length,expected);assert.equal(job.activeExpiresAt,70000);
 }
});

test('NV diagnostic transport binds events to the owned active command and strips extra data',async()=>{
 const {h,job}=await setup();const messages=[];
 Object.assign(job,{tab:3,pending:'abcdef0123456789abcdef0123456789',port:{postMessage:m=>messages.push(m)}});
 h.context.fixtureJob=job;vm.runInContext("owned.add(3);activeLanes.set('NV',fixtureJob)",h.context);
 const sender={id:h.chrome.runtime.id,frameId:0,url:'https://orion.nv.gov/portal/public/',tab:{id:3}};
 const message={action:'nv-diagnostic',id:job.pending,nv_diagnostic:{phase:'detail-clicked',visibility:'hidden',name:'must not forward',cookie:'must not forward'}};
 h.chrome.runtime.onMessage.emit({...message,id:'wrong-command-123456'},sender,()=>{});
 h.chrome.runtime.onMessage.emit(message,{...sender,tab:{id:4}},()=>{});
 h.chrome.runtime.onMessage.emit(message,{...sender,frameId:1},()=>{});
 assert.equal(messages.length,0);
 h.chrome.runtime.onMessage.emit(message,sender,()=>{});
 assert.equal(messages.length,1);assert.equal(messages[0].progress,true);
 assert.deepEqual(JSON.parse(JSON.stringify(messages[0].nv_diagnostic)),{phase:'detail-clicked',visibility:'hidden'});
});
