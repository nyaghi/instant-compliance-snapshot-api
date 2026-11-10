const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const dir=path.join(__dirname,'..','deployment','staging_connector');
const worker=fs.readFileSync(path.join(dir,'registry-worker.js'),'utf8');
const entry=worker.slice(worker.indexOf('async function registryTrialWindowOptions('),
  worker.indexOf('async function registryCreateOwnedTab('));
const origin={id:1,windowId:10,url:'https://example.test/?collector_layout=duo'};
async function placement({windowState='maximized',screenX=0,live=null,slot=0}={}){
 const logs=[];
 const env=vm.createContext({URL,Date,setTimeout,clearTimeout,
   chrome:{windows:{get:async()=>({left:-8,top:-8,width:1936,height:1048,state:windowState})},
     tabs:{get:async()=>origin,sendMessage:async()=>live}},
   registryTrialLayout:()=> 'duo',allJobs:()=>[],isActive:()=>true,
   diagnostic:(event,job,msg)=>logs.push([event,msg]),wfAwait:(_j,_id,fn)=>fn(),wfReturn:(_j,_id,value)=>value});
 vm.runInContext(entry,env);
 const bounds=await env.registryTrialWindowOptions({registryState:'AL',duoSlot:slot,activeExpiresAt:Date.now()+5000,
   trialDisplay:{outerWidth:1920,outerHeight:1032,viewportWidth:1695,chromeInsetTop:138,screenX,screenY:0}},origin);
 return {bounds,logs};
}
test('maximized frame replay keeps both collectors in the gray rail',async()=>{
 const a=await placement(),b=await placement({slot:1});
 for(const {bounds:r,logs} of [a,b]){
  assert.ok(logs.some(([key,value])=>key==='duo-placement-source'&&value==='acquire-maximized-frame'));
  assert.equal(r.left,1061);assert.equal(r.width,843);
  assert.ok(r.left+r.width<=1920&&r.top+r.height<=1032);
 }
 assert.ok(a.bounds.top+a.bounds.height<b.bounds.top);
});
test('normal and displaced windows do not borrow the maximized cache',async()=>{
 for(const args of [{windowState:'normal'},{screenX:20}]){
  const result=await placement(args);
  assert.ok(result.logs.some(([event])=>event==='duo-layout-fallback'));
 }
});
test('live reply still takes precedence',async()=>{
 const {bounds,logs}=await placement({live:{viewportWidth:1695,chromeInsetTop:138}});
 assert.ok(logs.some(([key,value])=>key==='duo-placement-source'&&value==='live'));
 assert.equal(bounds.left,1069);assert.equal(bounds.width,843);
});
