const {test}=require('node:test');
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), path=require('node:path');
const roster=require('./fixtures/gate55/LOCAL-70.json');
const src=fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/registry-worker.js'),'utf8');
const url='https://charities.sos.ms.gov/online/portal/ch/page/charities-search/Portal.aspx';
test('70 recorded identities: only a completed Mississippi 520 host-error page terminates readiness',async()=>{
 for(const org of roster)for(const scenario of ['520','normal','loading','verification','other path']){
  const tab={id:7,url:scenario==='other path'?url+'?other=1':url,status:scenario==='loading'?'loading':'complete',
   title:['520','loading','other path'].includes(scenario)?'sos.ms.gov | 520: Web server is returning an unknown error':scenario==='verification'?'Just a moment...':org.name};
  let messages=0;const job={registryState:'MS',tab:7,activeExpiresAt:Date.now()+10000};
  const ctx={URL,Promise,Date,Set,Map,console,chrome:{tabs:{get:async()=>tab,sendMessage:async()=>{messages++;return {ready:true};}}},
   P:{TRIAL_ORIGIN:'https://staging.invalid'},wfAwait:(_j,_s,f)=>f(),wfReturn:(_j,_s,x)=>x,wfEvent(){}};
  vm.createContext(ctx);vm.runInContext(src,ctx);
  const result=ctx.registryMessage(job,{action:'registry-ready'});
  if(scenario==='520'){await assert.rejects(result,/NY_CONNECTOR_REGISTRY_MS_HOST_ERROR/);assert.equal(messages,0);}
  else {assert.ok((await result).ready);assert.equal(messages,1);}
 }
});
