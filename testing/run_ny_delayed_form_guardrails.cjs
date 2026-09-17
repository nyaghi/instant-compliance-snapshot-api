const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),cases=[];const tick=()=>new Promise(r=>setImmediate(r));
async function lateVerification(delay){
 let now=0;const timers=[],listeners={},calls=[];
 const timeout=(fn,ms)=>{const t={fn,due:now+ms,clear:false};timers.push(t);return t;};
 const cancel=t=>{if(t)t.clear=true;};
 class Clock extends Date{static now(){return now;}}
 class Input{constructor(){this.v='';}get value(){return this.v;}set value(v){this.v=v;}dispatchEvent(){}}
 const inputs=Object.fromEntries(['ein','orgName','orgID','city'].map(k=>[k,new Input()]));
 let reply;
 const window={addEventListener:(k,fn)=>listeners[k]=fn,postMessage:m=>{reply=m;}};window.top=window;
 const origin='https://charities-search.ag.ny.gov';
 const buttons=[{textContent:'Clear fields',click:()=>Object.values(inputs).forEach(x=>x.value='')},
 {textContent:'Verify',disabled:false,click:()=>{calls.push('verify');window.fetch('https://charities-search-api.ag.ny.gov/api/recaptcha/verify',{method:'POST'});}},
 {textContent:'Search',disabled:true,click:()=>{calls.push('search');window.fetch('https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch?ein='+inputs.ein.value);}}];
 window.fetch=async url=>{
  const verify=url.includes('/recaptcha/verify');
  if(verify)await new Promise(resolve=>timeout(resolve,delay));
  if(verify)buttons[2].disabled=false;
  const payload=verify?{verified:true}:{success:true,statusCode:200,data:[]};
  return {status:200,clone:()=>({json:async()=>payload})};
 };
 class XHR{open(){}send(){}}
 const context=vm.createContext({URL,window,location:{origin},XMLHttpRequest:XHR,HTMLInputElement:Input,Event:class{},document:{querySelectorAll:()=>buttons,getElementById:k=>inputs[k]},Date:Clock,setTimeout:timeout,clearTimeout:cancel});
 for(const file of ['protocol.js','ny-main.js'])vm.runInContext(fs.readFileSync(path.join(root,'browser-connector',file),'utf8'),context);
 listeners.message({source:window,origin,data:{channel:'cc-ny-page-v1',direction:'request',id:'12345678-1234-4234-9234-123456789012',query:{ein:'123456789'}}});
 await tick();
 while(!reply){const t=timers.filter(t=>!t.clear).sort((a,b)=>a.due-b.due)[0];assert.ok(t);now=t.due;t.clear=true;t.fn();await tick();}
 const result={case:'Successful verification arrives after '+delay+' ms',elapsed_ms:now,reply:JSON.parse(JSON.stringify(reply)),calls};
 if(delay>30000){assert.equal(reply.reason,'NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT');assert.deepEqual(calls,['verify']);}
 else {assert.equal(reply.ok,true);assert.deepEqual(calls,['verify','search']);}
 cases.push(result);
}
for(const delay of [14000,16000,29000,31000,999999])test('Real verification response at '+delay+' ms',()=>lateVerification(delay));
