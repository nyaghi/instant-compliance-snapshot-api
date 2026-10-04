/* Execute the real form adapter; only the state page and transport are fixtures. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const root=path.join(__dirname,'..','browser-connector');
async function run({alreadyVerified=false,rejectFirst=false,failSearch=false,verificationDelay=0,trial=false,resetOnClear=false,dirtyFields=false,initialFields={},verifyStatus=200,verifyPayload={verified:true},networkError=false,forceMature=false}={}) {
  const origin='https://charities-search.ag.ny.gov',calls=[],listeners={};let searches=0,resolve,clears=0;
  const completed=new Promise(r=>resolve=r);
  class Input {constructor(){this.v='';}get value(){return this.v;}set value(v){this.v=v;}dispatchEvent(){}}
  const inputs=Object.fromEntries(['ein','orgName','orgID','city'].map(k=>[k,new Input()]));
  if(dirtyFields)for(const input of Object.values(inputs))input.value='Previous organization';
  for(const [key,value] of Object.entries(initialFields))inputs[key].value=value;
  const buttons=[{textContent:'Clear fields',click:()=>{clears++;Object.values(inputs).forEach(x=>x.value='');if(resetOnClear){buttons[2].disabled=true;buttons[1].disabled=false;}}},
    {textContent:'Verify',disabled:alreadyVerified,click:()=>{calls.push('verify');buttons[2].disabled=false;context.window.fetch('https://charities-search-api.ag.ny.gov/api/recaptcha/verify',{method:'POST'}).catch(()=>{});}},
    {textContent:'Search',disabled:!alreadyVerified,click:()=>{calls.push('search');context.window.fetch('https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch?ein='+inputs.ein.value);}}];
  class XHR {open(){}send(){}}
  const checkpoints=[];
  const window={addEventListener:(name,fn)=>listeners[name]=fn,postMessage:m=>{if(m.direction==='diagnostic')checkpoints.push(m);else resolve(m);}};window.top=window;
  window.fetch=async url=>{
    const verify=url.includes('/recaptcha/verify');let status=200,payload;
    if(verify){if(networkError)throw Error("SECRET-NETWORK");status=verifyStatus;if(verificationDelay)await new Promise(r=>setTimeout(r,verificationDelay/1000));payload=verifyPayload;}
    else {
      searches++;status=rejectFirst&&searches===1?401:200;
      if(status===401)buttons[1].disabled=false;
      payload={success:!failSearch,statusCode:200,data:[]};
    }
    return {status,clone:()=>({json:async()=>payload})};
  };
  const context=vm.createContext({URL,window,location:{origin},XMLHttpRequest:XHR,HTMLInputElement:Input,Event:class{},
    document:{querySelectorAll:()=>buttons,getElementById:id=>inputs[id]},Date,
    setTimeout:(fn,ms)=>setTimeout(fn,ms/1000),clearTimeout});
  for(const file of ['protocol.js','ny-main.js']){
    let source=fs.readFileSync(path.join((!forceMature&&process.env.CC_TEST_TRIAL_DIR)||root,file),'utf8');
    if(process.env.CC_TEST_TRIAL_DIR)source=source.replaceAll('cc-final-four-ny-page-v1','cc-ny-page-v1');
    if(trial&&file==='protocol.js')source=source.replace('const TRIAL_ORIGIN = "";','const TRIAL_ORIGIN = "https://fixture-final-four.onrender.com";');
    vm.runInContext(source,context);
  }
  listeners.message({source:window,origin,data:{channel:'cc-ny-page-v1',direction:'request',id:'12345678-1234-4234-9234-123456789012',query:{ein:'123456789'}}});
  const reply=await completed;return {reply,calls,clears,inputs,checkpoints};
}

test('trial verified form replaces the same field without resetting verification',async()=>{
 const {reply,calls,clears,inputs}=await run({trial:true,alreadyVerified:true,resetOnClear:true,initialFields:{ein:'987654321'}});
 assert.equal(reply.ok,true);assert.equal(clears,0);assert.deepEqual(calls,['search']);
 assert.equal(inputs.ein.value,'123456789');
 for(const key of ['orgName','orgID','city'])assert.equal(inputs[key].value,'');
});

test('trial adapter refuses cross-field edits until the worker supplies a fresh form',async()=>{
 const {reply,calls,clears}=await run({trial:true,alreadyVerified:true,resetOnClear:true,dirtyFields:true});
 assert.equal(reply.ok,false);assert.equal(reply.reason,'NY_CONNECTOR_SEARCH_FORM_CHANGED');
 assert.deepEqual(calls,[]);assert.equal(clears,0);
});
test('trial unverified form still uses normal Clear and Verify',async()=>{
 const {reply,calls,clears}=await run({trial:true,resetOnClear:true});
 assert.equal(reply.ok,true);assert.equal(clears,1);assert.deepEqual(calls,['verify','search']);
});
test('trial rejected search does not reuse the invalid verified state',async()=>{
 const {reply,calls,clears}=await run({trial:true,alreadyVerified:true,resetOnClear:true,rejectFirst:true});
 assert.equal(reply.ok,true);assert.equal(clears,1);assert.deepEqual(calls,['search','verify','search']);
});
test('enabled normal Search reuses valid verification without waiting for disabled Verify',async()=>{
  const {reply,calls}=await run({alreadyVerified:true});assert.equal(reply.ok,true);assert.deepEqual(calls,['search']);
});
test('unverified page still performs its normal Verify then Search',async()=>{
  const {reply,calls}=await run();assert.equal(reply.ok,true);assert.deepEqual(calls,['verify','search']);
});
test('401 after reused verification forces one normal verification before retry',async()=>{
  const {reply,calls}=await run({alreadyVerified:true,rejectFirst:true});assert.equal(reply.ok,true);assert.deepEqual(calls,['search','verify','search']);
});
test('unsuccessful response remains a retrieval failure, never an empty result',async()=>{
  const {reply}=await run({alreadyVerified:true,failSearch:true});assert.equal(reply.ok,false);assert.equal(reply.reason,'NY_CONNECTOR_SEARCH_UNSUCCESSFUL');
});
test('verification finishing after the portal execution window is still observed',async()=>{
  const {reply,calls}=await run({verificationDelay:35000});assert.equal(reply.ok,true);assert.deepEqual(calls,['verify','search']);
});
test('verification remains bounded when the portal never finishes in time',async()=>{
  const {reply,calls}=await run({verificationDelay:60000});assert.equal(reply.ok,false);assert.equal(reply.reason,'NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT');assert.deepEqual(calls,['verify']);
});

for(const status of [200,401,403,429,500])test('trial NY diagnostics retain verification HTTP '+status+' without private payload',async()=>{
 const {reply,calls}=await run({trial:true,verifyStatus:status,verifyPayload:{verified:status===200,token:'SECRET-TOKEN',message:'SECRET-MESSAGE','error-codes':['timeout-or-duplicate','SECRET-CODE']}});
 const responses=reply.ny_diagnostics.filter(e=>e.stage==='verify'&&e.event==='response');
 assert.ok(responses.length>0);assert.ok(responses.every(e=>e.http_status===status));
 assert.deepEqual([...responses[0].error_codes],['timeout-or-duplicate']);
 assert.ok(!JSON.stringify(reply).includes('SECRET'));
 assert.equal(reply.ok,status===200);assert.equal(calls.filter(c=>c==='verify').length,status===401?2:1);
});
test('trial NY diagnostics capture network failure without leaking exception',async()=>{
 const {reply}=await run({trial:true,networkError:true});assert.equal(reply.ok,false);
 assert.ok(reply.ny_diagnostics.some(e=>e.event==='network_error'));assert.ok(!JSON.stringify(reply).includes('SECRET'));
});
test('trial NY timeout diagnostics preserve deadline behavior',async()=>{
 const {reply}=await run({trial:true,verificationDelay:60000});assert.equal(reply.reason,'NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT');
 assert.ok(reply.ny_diagnostics.some(e=>e.stage==='verify'&&e.event==='timeout'));
});
test('mature adapter does not emit trial diagnostics',async()=>{
 if(process.env.CC_TEST_TRIAL_DIR)return;
 const {reply}=await run();assert.equal(reply.ny_diagnostics,undefined);
});

test('trial NY checkpoints arrive before completion and exclude private response fields',async()=>{
 const {reply,checkpoints}=await run({trial:true,verifyPayload:{verified:true,token:'PRIVATE',cookie:'PRIVATE'}});
 assert.equal(reply.ok,true);assert.ok(checkpoints.some(p=>p.ny_diagnostics[0].event==='click'));
 assert.ok(checkpoints.some(p=>p.ny_diagnostics[0].http_status===200));
 assert.ok(!JSON.stringify(checkpoints).includes('PRIVATE'));
});
test('mature NY adapter does not emit trial checkpoints',async()=>{
 assert.deepEqual((await run({forceMature:true})).checkpoints,[]);
});
