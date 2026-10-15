const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {harness,tick,id}=require('./run_ny_connector_lifecycle.cjs');
const root=process.env.CC_TEST_TRIAL_DIR||path.join(__dirname,'../browser-connector');
const source=fs.readFileSync(path.join(root,'registry-tn-checkbox.js'),'utf8');
const TN='https://tncab.tnsos.gov',CF='https://challenges.cloudflare.com',TRIAL='https://fixture-final-four.onrender.com';
function frame(options={}){
 let clock=10000,clicks=0,observer,disconnected=false;const timers=[],messages=[];
 const target={isConnected:true,getBoundingClientRect:()=>({width:20,height:20,top:5,left:5,bottom:25,right:25}),
  click:()=>{clicks++;box.checked=true;}};
 const box={checked:!!options.checked,disabled:!!options.disabled,closest:()=>target,getAttribute:()=>null};
 const document={documentElement:{},visibilityState:options.hidden?'hidden':'visible',querySelectorAll:selector=>{
  assert.equal(selector,'input[type="checkbox"], [role="checkbox"]');return options.duplicate?[box,box]:[box];}};
 Object.defineProperty(box,'value',{get(){throw Error('Verification values must not be read');}});
 const window={top:options.top?null:{}};if(options.top)window.top=window;
 const location={origin:options.offsite?'https://example.org':CF,pathname:'/cdn-cgi/challenge-platform/test',ancestorOrigins:options.ancestors||[TN]};
 const context={window,document,location,Date:{now:()=>clock},crypto:{randomUUID:()=>id(900)},innerWidth:300,innerHeight:150,
  getComputedStyle:()=>({visibility:'visible',display:'block',pointerEvents:'auto'}),
  MutationObserver:class{constructor(fn){observer=this;this.fn=fn;}observe(){}disconnect(){disconnected=true;}},
  setTimeout:(fn,ms)=>{const t={fn,due:clock+ms};timers.push(t);return t;},clearTimeout:t=>{if(t)t.cleared=true;},
  chrome:{runtime:{sendMessage:async m=>{messages.push(m);if(m.action==='tn-checkbox-permission'){
    if(options.change)box.disabled=true;return {allowed:options.allowed!==false};}return {allowed:false};}}}};
 vm.runInNewContext(source,context);
 async function advance(ms){const end=clock+ms;await tick();for(;;){const t=timers.filter(t=>!t.cleared&&t.due<=end).sort((a,b)=>a.due-b.due)[0];if(!t)break;t.cleared=true;clock=t.due;t.fn();await tick();}clock=end;await tick();}
 return {messages,box,target,advance,mutate:()=>observer?.fn(),get clicks(){return clicks;},get stopped(){return disconnected;}};
}
test('TN helper makes one ordinary visible-checkbox click only after worker permission',async()=>{
 const f=frame();await tick();assert.equal(f.clicks,1);assert.equal(f.messages[0].action,'tn-checkbox-permission');
 assert.equal(f.messages[1].phase,'clicked');f.mutate();await f.advance(50000);assert.equal(f.clicks,1);assert.equal(f.stopped,true);
 assert.ok(!JSON.stringify(f.messages).includes('token'));
});
test('hidden, disabled, checked or ambiguous checkbox never receives a permission request or click',async()=>{
 for(const options of [{hidden:true},{disabled:true},{checked:true},{duplicate:true}]){
  const f=frame(options);await f.advance(45000);assert.equal(f.clicks,0);assert.equal(f.messages.length,0);assert.equal(f.stopped,true);
 }
});
test('other sites, top frames and unrelated ancestors never activate checkbox handling',async()=>{
 for(const options of [{offsite:true},{top:true},{ancestors:['https://example.org']},{ancestors:[CF,'https://example.org',TN]}]){
  const f=frame(options);await tick();assert.equal(f.clicks,0);assert.equal(f.messages.length,0);
 }
});
test('denial and changed checkbox cannot manufacture verification completion',async()=>{
 const denied=frame({allowed:false});await denied.advance(45000);assert.equal(denied.clicks,0);assert.equal(denied.stopped,true);
 const changed=frame({change:true});await tick();assert.equal(changed.clicks,0);assert.equal(changed.messages.at(-1).phase,'changed-before-click');
});

async function admitted(){
 const h=harness({trialOrigin:TRIAL});await tick();h.tabs.get(1).url=TRIAL+'/';
 h.tabs.set(3,{id:3,windowId:20,active:true,url:TN+'/portal/registered-charities-search'});
 vm.runInContext(`owned.add(3); const checkboxFixtureJob=newJob({url:'${TRIAL}/',tab:{id:1}},'${id(1)}',false,{registryState:'TN',tab:3,activeExpiresAt:70000});
 checkboxFixtureJob.pending='${id(2)}';checkboxFixtureJob.tnVerificationExpiresAt=55000;activeLanes.set('TN',checkboxFixtureJob);`,h.context);
 return h;
}
const sender=h=>({id:h.chrome.runtime.id,frameId:9,url:CF+'/cdn-cgi/challenge-platform/test',tab:{id:3}});
const request={action:'tn-checkbox-permission',id:id(900)};
test('worker binds one checkbox permission to an active owned TN workflow and persists its used attempt',async()=>{
 const h=await admitted();assert.equal((await h.context.registryTnCheckboxMessage(request,sender(h))).allowed,true);
 assert.equal((await h.context.registryTnCheckboxMessage(request,sender(h))).allowed,false);
 assert.equal(h.data.session.ccnyRuntime.queue.find(j=>j.registryState==='TN').tnCheckboxAttempted,true);
 const record=vm.runInContext('checkboxFixtureJob',h.context);record.tnVerificationExpiresAt=0;
 assert.equal((await h.context.registryTnCheckboxMessage({...request,id:id(901)},sender(h))).allowed,false);
});
test('worker rejects foreign extension/frame/origin/tab, expired verification and moved page',async()=>{
 for(const change of ['extension','top','origin','tab','expired','page','unowned']){
  const h=await admitted(),s=sender(h);
  if(change==='extension')s.id='other';if(change==='top')s.frameId=0;if(change==='origin')s.url='https://example.org/cdn-cgi/challenge-platform/test';if(change==='tab')s.tab.id=1;
  if(change==='expired')vm.runInContext('checkboxFixtureJob.tnVerificationExpiresAt=9999',h.context);
  if(change==='page')h.tabs.get(3).url='https://example.org/';if(change==='unowned')vm.runInContext('owned.delete(3)',h.context);
  assert.equal((await h.context.registryTnCheckboxMessage(request,s)).allowed,false,change);
 }
});

test('checkbox action succeeds only when the registry itself enables its form before the same deadline',async()=>{
 for(const unlock of [true,false]){
  const h=await admitted(),job=vm.runInContext('checkboxFixtureJob',h.context);let formReady=false;
  h.chrome.tabs.sendMessage=async()=>({ready:formReady,verification_pending:!formReady,documentId:'tn-form',url:TN+'/portal/registered-charities-search'});
  const pending=h.context.registryReady(job);
  const outcome=unlock?pending:assert.rejects(pending,/TN_VERIFICATION_PENDING/);
  await tick();assert.equal((await h.context.registryTnCheckboxMessage(request,sender(h))).allowed,true);
  if(unlock)formReady=true;
  await h.advance(unlock?200:45000);await outcome;
  assert.equal(job.tnVerificationExpiresAt,0);assert.equal(job.activeExpiresAt,70000);
 }
});

test('a restored used checkbox attempt cannot be granted again and other registry frames stay inactive',async()=>{
 const h=await admitted();vm.runInContext('checkboxFixtureJob.tnCheckboxAttempted=true',h.context);
 assert.equal((await h.context.registryTnCheckboxMessage(request,sender(h))).allowed,false);
 vm.runInContext("checkboxFixtureJob.registryState='NC';checkboxFixtureJob.tnCheckboxAttempted=false",h.context);
 assert.equal((await h.context.registryTnCheckboxMessage(request,sender(h))).allowed,false);
});
