const {test}=require('node:test');
const assert=require('node:assert/strict'),vm=require('node:vm');
const {harness,tick}=require('./run_ny_connector_lifecycle.cjs');
const origin='https://fixture-final-four.onrender.com';
test('NC explicit 429 stops before same-form retry',async()=>{
 const url='https://www.sosnc.gov/online_services/search/by_title/search_charities';
 const h=harness({trialOrigin:origin,tabs:[[1,{id:1,windowId:10,url:origin+'/',active:true}],[3,{id:3,windowId:20,url,active:true}]]});await tick();
 vm.runInContext('owned.add(3)',h.context);let retries=0;
 h.chrome.tabs.sendMessage=async(id,m)=>{if(m.action==='registry-nc-retry'){retries++;return {ok:true,phase:'submitted'};}
 return {ready:true,url,documentId:'same',nc_search_idle:true,nc_readiness:{requests:[{status:429,search_route:true}]}};};
 const job={tab:3,sender:{tab:{id:1}},registryState:'NC',activeExpiresAt:70000,closed:false};
 await assert.rejects(h.context.registryReady(job,'same','/online_services/search/Charities_Results',45000,{state:'NC',operation:'search',name:'Example Foundation'}),/NC_RATE_LIMITED/);
 assert.equal(retries,0);assert.equal(job.ncSubmissionObservations[0].requests[0].status,429);
});
test('NY streams only sanitized checkpoints from the owned pending top-frame command',async()=>{
 const h=harness({trialOrigin:origin});await tick();const messages=[];
 const job={registryState:'NY',tab:3,pending:'12345678901234567890',port:{postMessage:m=>messages.push(m)}};
 h.context.testJob=job;vm.runInContext('owned.add(3);activeLanes.set("NY",testJob)',h.context);
 const sender={id:h.chrome.runtime.id,frameId:0,tab:{id:3},url:'https://charities-search.ag.ny.gov/RegistrySearch'};
 const message={action:'ny-diagnostic',id:job.pending,ny_diagnostics:[{stage:'verify',event:'click',elapsed_ms:1,visibility:'hidden',token:'SECRET'}]};
 h.chrome.runtime.onMessage.emit(message,{...sender,tab:{id:9}},()=>{});assert.equal(messages.length,0);
 h.chrome.runtime.onMessage.emit(message,{...sender,frameId:1},()=>{});assert.equal(messages.length,0);
 h.chrome.runtime.onMessage.emit(message,sender,()=>{});assert.equal(messages.length,1);assert.ok(!JSON.stringify(messages).includes('SECRET'));
 assert.equal(job.pending,message.id);assert.equal(messages[0].progress,true);
 job.closed=true;h.chrome.runtime.onMessage.emit(message,sender,()=>{});assert.equal(messages.length,1);
});
