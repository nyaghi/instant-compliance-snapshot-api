const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../web-staging/ny-connector.js'),'utf8').replace(/\r/g,'');
const begin=source.indexOf('    async function api(fields, cleanup = false) {');
const end=source.indexOf('    try {\n      let connection =',begin);
assert.ok(begin>0&&end>begin);
const fn=source.slice(begin,end);
const roster=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/gate55/LOCAL-70.json')));
const results=[];
function fixture({timeoutFirst=false,state='GA',origin='https://charityclarity-final-four-29-2.onrender.com',callerAbort=false}={}){
 const calls=[],progress=[],controller=new AbortController();
 const ctx={ORIGIN:origin,registryState:state,API:'https://fixture.invalid',credentials:{email:'test@example.invalid'},
  label:state,signal:controller.signal,alEvidenceDeadline:Date.now()+10000,
  onProgress:(s,detail)=>progress.push(detail),Date,JSON,Error,
  AbortSignal:{timeout:ms=>AbortSignal.timeout(Math.max(5,ms/1000)),any:AbortSignal.any},
  fetch:async(url,options)=>{
   calls.push({url,body:options.body});
   if(callerAbort){controller.abort();throw Error('caller canceled');}
   if(timeoutFirst&&calls.length===1)return await new Promise((resolve,reject)=>{
    options.signal.addEventListener('abort',()=>reject(Error('headers stalled')),{once:true});
   });
   return {status:200,ok:true,json:async()=>({phase:'complete',result:{status:'Current'}})};
  }};
 vm.createContext(ctx);vm.runInContext(fn+';this.run=api;',ctx);
 return {ctx,calls,progress};
}
test('GA 70 completed-result contracts replay only identical payload after header stall',async()=>{
 const keepAlive=setInterval(()=>{},1000);
 try{for(const c of roster){
  const h=fixture({timeoutFirst:true});
  const result=await h.ctx.run({action:'advance',query_id:c.ein,evidence:{rows:[{name:c.name,ein:c.ein}]}},false);
  assert.equal(result.phase,'complete');assert.equal(h.calls.length,2);
  assert.equal(h.calls[0].body,h.calls[1].body);
  assert.equal(h.progress[0].reason,'DELIVERY_HEADERS_TIMEOUT');
  results.push({state:'GA',...c,passed:true,scenario:'one same-payload delivery replay; no browser query'});
 }}finally{clearInterval(keepAlive);}
});
test('healthy responses, images, other states and caller cancellation keep prior behavior',async()=>{
 for(const config of [{},{state:'TN'},{state:'IL'},{origin:'https://staging.compliance-express.com'}]){
  const h=fixture(config);await h.ctx.run({action:'advance',evidence:{rows:[]}});assert.equal(h.calls.length,1);
 }
 const h=fixture({callerAbort:true});await assert.rejects(()=>h.ctx.run({action:'advance',evidence:{rows:[]}}));assert.equal(h.calls.length,1);
 const image=fixture();await image.ctx.run({action:'advance',evidence:{rows:[]},state_snapshot:{image:'original'}});assert.equal(image.calls.length,1);
});
test.after(()=>fs.writeFileSync(path.join(__dirname,'gate55-handoff-results.json'),JSON.stringify({kind:'offline fault-injection contracts with seventy distinct recorded identities',cases:results},null,2)));
