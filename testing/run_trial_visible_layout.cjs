const {test}=require('node:test');
const assert=require('node:assert/strict');
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
