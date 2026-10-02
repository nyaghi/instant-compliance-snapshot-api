const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),cases=[];const tick=()=>new Promise(r=>setImmediate(r));
async function lateVerification(delay, enableDelay=0, searchDelay=0, {clearDelay=0,timerClamp=0}={}){
 let now=0;const timers=[],listeners={},calls=[],observers=new Set();
 const timeout=(fn,ms)=>{const t={fn,due:now+ms,clear:false};timers.push(t);return t;};
 const cancel=t=>{if(t)t.clear=true;};
 class Clock extends Date{static now(){return now;}}
 class Input{constructor(){this.v='';}get value(){return this.v;}set value(v){this.v=v;}dispatchEvent(){}}
 const inputs=Object.fromEntries(['ein','orgName','orgID','city'].map(k=>[k,new Input()]));
 let reply;
 const window={addEventListener:(k,fn)=>listeners[k]=fn,postMessage:m=>{reply=m;}};window.top=window;
 const origin='https://charities-search.ag.ny.gov';
 if(clearDelay)inputs.orgName.value='Previous Charity';
 const buttons=[{textContent:'Clear fields',click:()=>{const clear=()=>{Object.values(inputs).forEach(x=>x.value='');for(const o of observers)o.fn();};if(clearDelay)timeout(clear,clearDelay);else clear();}},
 {textContent:'Verify',disabled:false,click:()=>{calls.push('verify');window.fetch('https://charities-search-api.ag.ny.gov/api/recaptcha/verify',{method:'POST'});}},
 {textContent:'Search',disabled:true,click:()=>{calls.push('search');window.fetch('https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch?ein='+inputs.ein.value);}}];
 window.fetch=async url=>{
  const verify=url.includes('/recaptcha/verify');
  if(verify)await new Promise(resolve=>timeout(resolve,delay));
  else if(searchDelay)await new Promise(resolve=>timeout(resolve,searchDelay));
  // Network completion and the portal's rendered enabled state are separate.
  if(verify)timeout(()=>{buttons[2].disabled=false;for(const o of observers)o.fn();},enableDelay);
  const payload=verify?{verified:true}:{success:true,statusCode:200,data:[]};
  return {status:200,clone:()=>({json:async()=>payload})};
 };
 class XHR{open(){}send(){}}
 const context=vm.createContext({URL,window,location:{origin},XMLHttpRequest:XHR,HTMLInputElement:Input,Event:class{},document:{documentElement:{},querySelectorAll:()=>buttons,getElementById:k=>inputs[k]},Date:Clock,
 MutationObserver:class{constructor(fn){this.fn=fn;}observe(){observers.add(this);}disconnect(){observers.delete(this);}},
 setTimeout:(fn,ms)=>timeout(fn,Math.max(ms,timerClamp)),clearTimeout:cancel});
 for(const file of ['protocol.js','ny-main.js']){let source=fs.readFileSync(path.join(process.env.CC_TEST_TRIAL_DIR||path.join(root,'browser-connector'),file),'utf8');if(process.env.CC_TEST_TRIAL_DIR)source=source.replaceAll('cc-final-four-ny-page-v1','cc-ny-page-v1');vm.runInContext(source,context);}
 listeners.message({source:window,origin,data:{channel:'cc-ny-page-v1',direction:'request',id:'12345678-1234-4234-9234-123456789012',query:{ein:'123456789'}}});
 await tick();
 while(!reply){const t=timers.filter(t=>!t.clear).sort((a,b)=>a.due-b.due)[0];assert.ok(t);now=t.due;t.clear=true;t.fn();await tick();}
 const result={case:'Verification after '+delay+' ms; Search enabled '+enableDelay+' ms later',elapsed_ms:now,reply:JSON.parse(JSON.stringify(reply)),calls};
 // Approved 29.1 already waits 45 seconds for verification; search response
 // time remains 30 seconds. Keep their boundary controls independent.
 assert.equal(observers.size,0,'all observers cleaned up');
 if(clearDelay>3000){assert.equal(reply.reason,'NY_CONNECTOR_CLEAR_FIELDS_TIMEOUT');assert.deepEqual(calls,[]);}
 else if(delay>=45000){assert.equal(reply.reason,'NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT');assert.deepEqual(calls,['verify']);}
 else if(enableDelay>=15000){assert.equal(reply.reason,'NY_CONNECTOR_SEARCH_BUTTON_TIMEOUT');assert.deepEqual(calls,['verify']);assert.equal(now,delay+15000);}
 else if(searchDelay>=30000){assert.equal(reply.reason,'NY_CONNECTOR_SEARCH_RESPONSE_TIMEOUT');assert.deepEqual(calls,['verify','search']);}
 else {assert.equal(reply.ok,true);assert.deepEqual(calls,['verify','search']);}
 cases.push(result);
}
for(const delay of [14000,16000,29000,31000,44000,45000,46000,999999])test('Real verification response at '+delay+' ms',()=>lateVerification(delay));
for(const delay of [0,2000,4000,10000,14900,15000,999999])test('Search UI enables '+delay+' ms after successful verification',()=>lateVerification(1000,delay));
for(const delay of [16000,29000,31000,999999])test('Search response arrives '+delay+' ms after submit',()=>lateVerification(1000,0,delay));

test('normal clear render is observed within its deadline despite background timer throttling',()=>lateVerification(100,0,0,{clearDelay:100,timerClamp:60000}));
test('late clear render stays a failure even when its watchdog is throttled',()=>lateVerification(100,0,0,{clearDelay:4000,timerClamp:60000}));
