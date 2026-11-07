const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const src=fs.readFileSync('deployment/staging_connector/registry-worker.js','utf8');
const code=src.slice(src.indexOf('function registryNmHttpFailureProof('),src.indexOf('async function registryReady('));
function fixture(options={}){
 const calls=[],frame={url:'chrome-error://chromewebdata/',unreachableUrl:'https://secure.nmdoj.gov/CharitySearch/',loaderId:'loaded',...options.frame};
 const job={registryState:'NM',tab:7,generation:1,pending:{},closed:false,...options.job};
 const page={url:'chrome-error://chromewebdata/',text:'This page isn’t working\nHTTP ERROR 522',...options.page};
 const ctx=vm.createContext({URL,JSON,Date,Promise,setTimeout,clearTimeout,P:{TRIAL_ORIGIN:true},registryOrigin:()=> 'https://secure.nmdoj.gov',chrome:{tabs:{get:async()=>({url:'https://secure.nmdoj.gov/CharitySearch/',status:'complete',...options.tab})},debugger:{
 attach:async()=>{calls.push('attach');if(options.attachFail)throw Error('attached elsewhere');if(options.delay)await new Promise(r=>setTimeout(r,options.delay));},
 detach:async()=>calls.push('detach'),sendCommand:async(_,method)=>{calls.push(method);if(options.mutate)options.mutate(job,method);return method==='Page.getFrameTree'?{frameTree:{frame:{...frame,...(options.changed&&calls.filter(x=>x===method).length>1?{loaderId:'new'}:{})}}}:{result:{value:JSON.stringify(page)}};}}}});
 vm.runInContext(code,ctx);return {ctx,job,calls,frame,page};
}
test('exact current NM browser 522 yields proof and detaches',async()=>{const h=fixture();assert.equal(await h.ctx.registryNmHttpFailure(h.job,Date.now()+5000),true);assert.equal(h.calls.at(-1),'detach');});
for(const [name,opts]of Object.entries({normal:{frame:{url:'https://secure.nmdoj.gov/CharitySearch/'}},otherOrigin:{frame:{unreachableUrl:'https://other.invalid/CharitySearch/'}},otherRoute:{frame:{unreachableUrl:'https://secure.nmdoj.gov/account'}},http403:{page:{text:'HTTP ERROR 403'}},http404:{page:{text:'HTTP ERROR 404'}},challenge:{page:{text:'Verify you are human'}},timeout:{page:{text:'ERR_CONNECTION_TIMED_OUT'}},loaderChanged:{changed:true},otherState:{job:{registryState:'NC'}},closed:{job:{closed:true}},loading:{tab:{status:'loading'}},attachFailure:{attachFail:true},staleTab:{mutate:(j,m)=>{if(m==='Runtime.evaluate')j.tab=9;}}}))
 test(name+' cannot become NM outage',async()=>{const h=fixture(opts);assert.equal(await h.ctx.registryNmHttpFailure(h.job,Date.now()+5000),false);if(h.calls.includes('attach')&&!opts.attachFail)assert.equal(h.calls.at(-1),'detach');});
test('late attach cleans up after bounded deadline',async()=>{const h=fixture({delay:600});assert.equal(await h.ctx.registryNmHttpFailure(h.job,Date.now()+550),false);await new Promise(r=>setTimeout(r,100));assert.equal(h.calls.at(-1),'detach');});
test('actual recorded522 fixture passes exact predicate',()=>{const h=fixture();const f=JSON.parse(fs.readFileSync(process.env.NM_SOURCE_FIXTURE,'utf8'));assert.equal(h.ctx.registryNmHttpFailureProof(f.frame.frameTree.frame,f.page),true);});
test('real registryReady propagates proven HTTP error instead of waiting for timeout',async()=>{
 const h=fixture();h.job.activeExpiresAt=Date.now()+30000;
 Object.assign(h.ctx,{wfAwait:(_j,_s,f)=>f(),registryNevadaVisibleSnapshot:async()=>null,
   registryReadinessMessage:async()=>{throw Error('Could not establish connection. Receiving end does not exist.');},nap:async()=>{throw Error('Unexpected continued polling');}});
 vm.runInContext(src.slice(src.indexOf('async function registryReady('),src.indexOf('async function registryNavigate(')),h.ctx);
 await assert.rejects(h.ctx.registryReady(h.job,null,'/CharitySearch/',30000),/NY_CONNECTOR_REGISTRY_NM_HTTP_ERROR/);
 assert.equal(h.calls.at(-1),'detach');
});
