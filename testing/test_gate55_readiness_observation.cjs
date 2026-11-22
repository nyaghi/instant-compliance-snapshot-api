const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const roster=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/gate55/LOCAL-70.json'),'utf8'));
const worker=fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/workflow-observation.js'),'utf8');
const content=fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/registry-content.js'),'utf8');
const start=content.indexOf('  function ncSourceObservation() {'),end=content.indexOf('  function registryDocumentReady()',start);
const fn=content.slice(start,end);assert.ok(start>=0&&end>start);
test('70 recorded identities: source observations are read-only and expose no URL or body',()=>{
 for(const org of roster)for(const phase of ['search','profile','filings'])for(const challenge of [false,true]){
  const document={title:challenge?'Just a moment...':org.name,readyState:challenge?'interactive':'complete',body:{textContent:challenge?'Performing security verification':'PUBLIC '+org.name}};
  const nav={responseStatus:challenge?403:200,requestStart:10,responseStart:60,responseEnd:80,domInteractive:100,loadEventEnd:challenge?0:150};
  const ctx={document,location:{pathname:'/online_services/search/charities_'+phase+'/123'},performance:{getEntriesByType:type=>{assert.equal(type,'navigation');return[nav]}},text:x=>x.textContent};
  vm.createContext(ctx);vm.runInContext(fn+';this.observe=ncSourceObservation',ctx);
  const before=JSON.stringify({document,nav}),out=ctx.observe();
  assert.equal(out.verification,challenge);assert.equal(out.source_status,challenge?403:200);assert.equal(out.route,phase);
  assert.equal(out.responseEnd_ms,80);assert.equal(JSON.stringify({document,nav}),before);
  assert.ok(!JSON.stringify(out).includes(org.name));assert.ok(!JSON.stringify(out).includes('123'));
 }
});
test('70 recorded identities: longest waits survive ordinary trace overflow and remain bounded',async()=>{
 for(const org of roster){
  let clock=100000;const ctx={P:{TRIAL_ORIGIN:'https://fixture.invalid'},Date:{now:()=>clock},Math,Promise,allJobs:()=>[]};
  vm.createContext(ctx);vm.runInContext(worker+';this.begin=wfStart;this.finish=wfEnd;this.exported=wfExport;this.awaited=wfAwait',ctx);
  const job={lookupId:org.ein,registryState:'NC',activeExpiresAt:999999,generation:1};
  for(let n=0;n<900;n++){let s=ctx.begin(job,'routine');clock+=1;ctx.finish(job,s);}
  assert.ok(job.workflowObservation.dropped_events>0);
  for(let n=0;n<100;n++){let s=ctx.begin(job,'source-'+n);clock+=(n+1)*1000;ctx.finish(job,s);}
  const result=ctx.exported(job);assert.equal(result.longest_waits.length,64);assert.equal(result.longest_waits[0].duration_seconds,100);assert.equal(result.longest_waits[63].duration_seconds,37);
  const value={ok:true};assert.equal(await ctx.awaited(job,'healthy',()=>value),value);
  const failure=Error('fixture');await assert.rejects(ctx.awaited(job,'failure',()=>Promise.reject(failure)),x=>x===failure);
 }
});
