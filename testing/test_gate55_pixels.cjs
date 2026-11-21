const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.join(__dirname,'../deployment/staging_connector');
const roster=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/gate55/LOCAL-70.json')));
const results=[];
function fixture(caseData,changes={}){
 const listeners=new Set(),calls=[];
 let alive=true;
 const data=Buffer.from((caseData.name+' '+caseData.ein+' ').repeat(20)).toString('base64');
 const viewport={clientWidth:1280,clientHeight:1600,pageX:0,pageY:0};
 const chrome={debugger:{onEvent:{addListener:f=>listeners.add(f),removeListener:f=>listeners.delete(f)},sendCommand:async(target,method,params)=>{
  calls.push({target,method,params});
  if(method==='Page.getLayoutMetrics')return {cssVisualViewport:viewport};
  if(method==='Runtime.evaluate')return {result:{value:{width:1280+(changes.scrollbar?15:0),height:1600}}};
  if(method==='Page.startScreencast'){
   const meta={timestamp:Date.now()/1000,deviceWidth:1280+(changes.scrollbar?15:0),deviceHeight:1600,pageScaleFactor:1,scrollOffsetX:0,scrollOffsetY:0,offsetTop:0};
   if(changes.cancel)alive=false;
   for(const f of listeners){
    f({tabId:999},'Page.screencastFrame',{sessionId:1,data,metadata:meta});
    f({tabId:7},'Page.screencastFrame',{sessionId:2,data,metadata:{...meta,timestamp:meta.timestamp-60}});
    f({tabId:7},'Page.screencastFrame',{sessionId:3,data,metadata:{...meta,deviceHeight:500}});
    f({tabId:7},'Page.screencastFrame',{sessionId:4,data,metadata:{...meta,scrollOffsetY:300}});
    f({tabId:7},'Page.screencastFrame',{sessionId:5,data,metadata:{...meta,pageScaleFactor:0.5}});
    f({tabId:7},'Page.screencastFrame',{sessionId:6,data:'INVALID!',metadata:meta});
    f({tabId:7},'Page.screencastFrame',{sessionId:7,data,metadata:meta});
   }
  }
  return {};
 }}};
 const ctx={module:{exports:{}},chrome,Date,setTimeout,clearTimeout};vm.createContext(ctx);
 vm.runInContext(fs.readFileSync(path.join(root,'owned-source-pixels.js'),'utf8'),ctx);
 return {api:ctx.module.exports,chrome,listeners,calls,data,alive:()=>alive,viewport};
}
for(const state of ['AL','NC','NV','DC','WI'])test(state+' 70 recorded identities: same-tab original-frame capture and stale/wrong geometry rejection',async()=>{
 assert.equal(new Set(roster.map(x=>x.ein)).size,70);
 for(const c of roster){
  const h=fixture(c,{scrollbar:true}),deadline=Date.now()+5000;
  const image=await h.api.capture(7,{format:'jpeg',quality:80,captureBeyondViewport:false},{deadline,alive:h.alive});
  assert.equal(image.data,h.data);assert.equal(h.listeners.size,0);
  assert.equal(h.calls.at(-1).method,'Page.stopScreencast');
  assert.ok(h.calls.every(x=>x.target.tabId===7));
  assert.equal(h.calls.filter(x=>x.method==='Page.startScreencast').length,1);
  assert.ok(!h.calls.some(x=>/navigate|focus|setDeviceMetrics|captureScreenshot/.test(x.method)));
  assert.equal(h.api.coversViewport({clip:{x:0,y:0,width:1280,height:1700,scale:1}},{cssVisualViewport:h.viewport}),false);
  assert.equal(h.api.coversViewport({clip:{x:0,y:0,width:1280,height:1600,scale:1}},{cssVisualViewport:h.viewport}),true);
  results.push({state,...c,passed:true,scenario:'same-tab fresh original frame; six stale/foreign/invalid frame controls'});
 }
});
test('cancel, near deadline and oversized source never publish a frame',async()=>{
 for(const option of [{cancel:true},{near:true},{oversized:true}]){
  const h=fixture(roster[0],option);if(option.oversized)h.viewport.clientHeight=100000;
  await assert.rejects(()=>h.api.capture(7,{captureBeyondViewport:false},{deadline:Date.now()+(option.near?100:5000),alive:h.alive}));
  assert.equal(h.listeners.size,0);
 }
});
test('WI date-anchor expression equates zero padded dates without changing source text',()=>{
 const source=fs.readFileSync(path.join(root,'desktop-source-worker.js'),'utf8');
 const expression=source.match(/const norm=s=>String\(s\)[^\n]+/)[0].replace(/\\\\/g,'\\');
 const norm=vm.runInNewContext(expression+';norm');
 assert.equal(norm('8/1/2015'),norm('08/01/2015'));
 assert.notEqual(norm('8/1/2015'),norm('08/02/2015'));
});
test.after(()=>fs.writeFileSync(path.join(__dirname,'gate55-pixel-results.json'),JSON.stringify({kind:'offline original-frame driver contracts; recorded identities, synthetic callback conditions',cases:results},null,2)));
