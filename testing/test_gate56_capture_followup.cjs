const {test}=require('node:test');
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), path=require('node:path');
const organizations=require('./fixtures/gate55/LOCAL-70.json');
const source=fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/state-snapshot-worker.js'),'utf8');
function deferred(){let resolve,reject;const promise=new Promise((y,n)=>{resolve=y;reject=n});return {promise,resolve,reject};}
function fixture(state,org){
  const url=state==='NV'?'https://orion.nv.gov/detail':'https://verify.sos.ga.gov/search';
  const q=state==='NV'?{state,operation:'detail',identifier:'NV123456789'}:{state,orgName:org.name};
  const job={tab:7,generation:1,registryState:state,command:{id:'q',query:q},pending:'q',activeExpiresAt:Date.now()+30000};
  const meta={url,document_id:'doc1',source_detail:true,public_text:org.name,source_binding:q.identifier||'grid',
    source_view_shape:[0,1000,1200,1000,10,30,15,130],source_fields_visible:true,source_loading_visible:false,capture_views:['nv-0']};
  const layout={cssContentSize:{width:1200,height:1000},cssLayoutViewport:{clientWidth:1200,clientHeight:1000}};
  const expiration=new Map();let fresh=0,detaches=0,first=0;
  const ctx={Date,URL,Promise,P:{TRIAL_ORIGIN:'trial',sameQuery:(a,b)=>a===b},owned:new Set([7]),isActive:()=>true,
    registryOrigin:()=>new URL(url).origin,clearTimeout:key=>expiration.delete(key),setTimeout:(fn,ms)=>{if(ms<200){queueMicrotask(fn);return;}const key={};expiration.set(key,fn);return key;},
    wfAwait:(_j,_s,fn)=>fn(),wfEvent(){},wfReturn:(_j,_s,x)=>x,
    chrome:{tabs:{get:async()=>({url}),sendMessage:async(_,m)=>m.action==='registry-snapshot-view'?{ok:true,snapshot_metadata:meta}:meta},
      debugger:{attach:async()=>{},detach:async()=>{detaches++},sendCommand:async(_,c)=>{if(c==='Page.getLayoutMetrics')return layout;
        if(c==='Page.captureScreenshot'){fresh++;return {data:'AQ=='};}return {};}}},
    CCOwnedSourcePixels:{capture:async()=>{first++;return {data:'AA=='}},nvDetailVeiled:async data=>data==='AA=='}};
  vm.createContext(ctx);vm.runInContext(source,ctx);
  return {ctx,q,job,meta,layout,run:()=>ctx.captureStateSnapshot(job,q,'q'),expire:()=>[...expiration.values()].at(-1)(),
    counts:()=>({first,fresh,detaches})};
}
test('Nevada: clear original, stale frame, two veils and changed identity across 70 recorded organizations',async()=>{
 for(const org of organizations){
  for(const mode of ['clear','stale','persistent','wrong record']){
   const f=fixture('NV',org);
   f.ctx.CCOwnedSourcePixels.nvDetailVeiled=async data=>{
     if(mode==='wrong record'&&data==='AA=='){f.ctx.chrome.tabs.sendMessage=async()=>({...f.meta,source_binding:'other'});}
     return mode==='persistent'||mode!=='clear'&&data==='AA==';
   };
   const image=await f.run();
   if(mode==='clear'||mode==='stale'){assert.equal(image?.image,mode==='clear'?'AA==':'AQ==',org.name);}
   else assert.equal(image,null,org.name);
   assert.equal(f.counts().fresh,['stale','persistent'].includes(mode)?1:0);
  }
 }
});
test('Georgia: only acknowledged detach releases expired optional screenshot; late bytes never publish',async()=>{
 for(const org of organizations){
  for(const refused of [false,true]){
   const f=fixture('GA',org),pixel=deferred(),inCapture=deferred(),detach=deferred();
   const dbg=f.ctx.chrome.debugger,original=dbg.sendCommand;let detaches=0;
   dbg.sendCommand=async(t,c,o)=>{if(c==='Page.captureScreenshot'){inCapture.resolve();return pixel.promise;}return original(t,c,o);};
   dbg.detach=async()=>{if(++detaches===1)return detach.promise;};
   const result=f.run();await inCapture.promise;const cleanup=f.job.snapshotCleanupCompletion;f.expire();
   assert.equal(await result,null);assert.equal(f.job.snapshotCleanupBusy,true);assert.equal(detaches,1);
   if(refused){detach.reject(Error('busy'));await new Promise(setImmediate);assert.equal(f.job.snapshotCleanupBusy,true);pixel.resolve({data:'AA=='});}
   else detach.resolve();
   await cleanup;assert.ok(!f.job.snapshotCleanupBusy);assert.equal(detaches,refused?2:1);
   pixel.resolve({data:'AA=='});await new Promise(setImmediate);assert.equal(f.job.snapshotCaptures,undefined);assert.equal(detaches,refused?2:1);
  }
 }
});

test('Nevada: fresh original frame after a veil succeeds even when the direct screenshot would hang',async()=>{
 for(const org of organizations){
  const f=fixture('NV',org);let n=0;
  f.ctx.CCOwnedSourcePixels.capture=async()=>({data:++n===1?'AA==':'AQ=='});
  const old=f.ctx.chrome.debugger.sendCommand;
  f.ctx.chrome.debugger.sendCommand=async(t,c,o)=>{if(c==='Page.captureScreenshot')throw Error('direct path unavailable');return old(t,c,o);};
  const v=await f.run();assert.equal(v?.image,'AQ==');assert.equal(n,2);
 }
});
test('Nevada rechecks the settled visible group when a stale frame follows a scroll',async()=>{
  for(const org of organizations)for(const moved of [false,true]){
    const f=fixture('NV',org);f.meta.source_fields_visible=false;
    const settled=[0,1000,1200,1000,40,60,15,130];let painted=0,observed=0;
    f.ctx.chrome.tabs.sendMessage=async(_,m)=>{
      if(m.action==='registry-snapshot-view'&&m.view!=='restore'){
        observed++;
        const shape=moved&&painted?settled.map(a=>a+15):settled;
        return {ok:true,view_protocol:'worker-settle-1',view_ready:true,view_text:[org.name],view_shape:shape};
      }
      if(m.view==='restore')return {ok:true,snapshot_metadata:f.meta};
      return painted?{...f.meta,source_view_shape:settled}:f.meta;
    };
    f.ctx.CCOwnedSourcePixels.capture=async()=>({data:++painted===1?'AA==':'AQ=='});
    const image=await f.run();
    assert.equal(image?.image||null,moved?null:'AQ==',org.name);
    assert.ok(observed>=4);
  }
});
