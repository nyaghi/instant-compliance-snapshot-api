/* Execute the real form adapter; only the state page and transport are fixtures. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const root=path.join(__dirname,'..','browser-connector');
async function run({alreadyVerified=false,rejectFirst=false,failSearch=false}={}) {
  const origin='https://charities-search.ag.ny.gov',calls=[],listeners={};let searches=0,resolve;
  const completed=new Promise(r=>resolve=r);
  class Input {constructor(){this.v='';}get value(){return this.v;}set value(v){this.v=v;}dispatchEvent(){}}
  const inputs=Object.fromEntries(['ein','orgName','orgID','city'].map(k=>[k,new Input()]));
  const buttons=[{textContent:'Clear fields',click:()=>Object.values(inputs).forEach(x=>x.value='')},
    {textContent:'Verify',disabled:alreadyVerified,click:()=>{calls.push('verify');buttons[2].disabled=false;context.window.fetch('https://charities-search-api.ag.ny.gov/api/recaptcha/verify',{method:'POST'});}},
    {textContent:'Search',disabled:!alreadyVerified,click:()=>{calls.push('search');context.window.fetch('https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch?ein='+inputs.ein.value);}}];
  class XHR {open(){}send(){}}
  const window={addEventListener:(name,fn)=>listeners[name]=fn,postMessage:resolve};window.top=window;
  window.fetch=async url=>{
    const verify=url.includes('/recaptcha/verify');let status=200,payload;
    if(verify)payload={verified:true};
    else {
      searches++;status=rejectFirst&&searches===1?401:200;
      if(status===401)buttons[1].disabled=false;
      payload={success:!failSearch,statusCode:200,data:[]};
    }
    return {status,clone:()=>({json:async()=>payload})};
  };
  const context=vm.createContext({URL,window,location:{origin},XMLHttpRequest:XHR,HTMLInputElement:Input,Event:class{},
    document:{querySelectorAll:()=>buttons,getElementById:id=>inputs[id]},Date,
    setTimeout:(fn,ms)=>setTimeout(fn,ms===1000?1:ms),clearTimeout});
  for(const file of ['protocol.js','ny-main.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
  listeners.message({source:window,origin,data:{channel:'cc-ny-page-v1',direction:'request',id:'12345678-1234-4234-9234-123456789012',query:{ein:'123456789'}}});
  const reply=await completed;return {reply,calls};
}
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
