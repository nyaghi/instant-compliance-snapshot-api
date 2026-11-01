const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),cp=require('node:child_process');
const root=path.join(__dirname,'..'),file='deployment/staging_connector/state-snapshot-worker.js';
const candidate=fs.readFileSync(path.join(root,file),'utf8');
const baseline=cp.execFileSync('git',['show','412f58a7e997e121435ce58d3793d43e5393d8f1:'+file],{cwd:root,encoding:'utf8'});
function fixture(source,options={}){
 const calls=[],q={state:'NM',operation:'detail',identifier:'86-0481941',name:'Make-A-Wish Foundation of America'};
 const url='https://secure.nmdoj.gov/CharitySearch/CharityDetail.aspx?FEIN=86-0481941';
 const job={tab:1,generation:2,pending:'command123',command:{id:'command123',query:q},registryState:'NM',activeExpiresAt:Date.now()+30000,snapshotCaptures:options.captures??4,requiredCaptureSpentByState:{NM:options.spent??0}};
 let width=1000,height=1200;
 const meta=()=>({url,document_id:'retained-local-document',public_text:'LOCAL MODELED FIXTURE Make-A-Wish Foundation of America 86-0481941 Registration History',source_detail:true,source_fields_visible:true,source_viewport_width:width,source_record_bottom:1200,source_page_fits:true,...options.meta});
 const ctx={URL,Date,JSON,Promise,setTimeout,clearTimeout,owned:new Set([1]),isActive:()=>true,
  wfAwait:(_job,_stage,fn)=>fn(),wfReturn:(_job,_stage,value)=>value,wfEvent:()=>{},
  P:{TRIAL_ORIGIN:'https://local-fixture.onrender.com',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)},registryOrigin:()=> 'https://secure.nmdoj.gov',
  chrome:{tabs:{get:async()=>({url}),sendMessage:async()=>meta()},debugger:{attach:async()=>calls.push('attach'),detach:async()=>calls.push('detach'),sendCommand:async(_target,method,params)=>{
   calls.push(method);
   if(method==='Emulation.setDeviceMetricsOverride'){width=params.width;height=params.height;return {};}
   if(method==='Emulation.clearDeviceMetricsOverride')return {};
   if(method==='Page.getLayoutMetrics')return {cssContentSize:{width,height:1200},cssLayoutViewport:{clientWidth:width,clientHeight:height,pageX:0,pageY:0}};
   if(method==='Page.captureScreenshot')return {data:'AA=='};
   return {};
  }}}};
 vm.createContext(ctx);vm.runInContext(source,ctx);return {ctx,job,q,calls,run:()=>ctx.captureStateSnapshot(job,q,'command123')};
}
test('NM selected detail retains its existing reserve after four earlier images; baseline rejects',async()=>{
 for(let i=0;i<30;i++){
  const old=fixture(baseline),next=fixture(candidate),expires=next.job.activeExpiresAt;
  assert.equal(await old.run(),null);const out=await next.run();assert.ok(out);assert.equal(out.source_url,'https://secure.nmdoj.gov/CharitySearch/CharityDetail.aspx?FEIN=86-0481941');assert.equal(out.image,'AA==');assert.equal(next.job.activeExpiresAt,expires);assert.equal(next.calls.filter(x=>x==='Page.captureScreenshot').length,1);assert.equal(next.calls.at(-1),'detach');
 }
});
test('NM fast-path pixels and deadline are unchanged; search cap and detail guards remain',async()=>{
 for(let i=0;i<30;i++){
  const old=fixture(baseline,{captures:0}),next=fixture(candidate,{captures:0});
  const a=await old.run(),b=await next.run();assert.ok(a&&b);assert.equal(a.image,b.image);assert.equal(a.source_url,b.source_url);assert.deepEqual(old.calls,next.calls);
 }
 for(const options of [{spent:19500},{captures:24},{meta:{url:'https://secure.nmdoj.gov/other'}},{meta:{source_record_bottom:0}},{meta:{public_text:'Verify you are human'}}]){
  const h=fixture(candidate,options);assert.equal(await h.run(),null);assert.ok(!h.calls.includes('Page.captureScreenshot'));
 }
 const search=fixture(candidate);search.q.operation='search';assert.equal(await search.run(),null);assert.equal(search.calls.length,0);
 const wrong=fixture(candidate);wrong.ctx.owned.clear();assert.equal(await wrong.run(),null);assert.equal(wrong.calls.length,0);
});
test('DC real detail date ordering is accepted only with typed effective-period provenance',()=>{
 const current=require(path.join(root,'deployment/staging_connector/dc-boss-source.js'));
 const data=JSON.parse(fs.readFileSync(path.join(root,'testing/fixtures/combined-nf-retained.json'),'utf8'));
 for(const entry of data.dc){const d={...entry.result._worker_desktop_evidence,prior_renewal_date_type:'current_effective_date'};
  assert.ok(current.fields(entry.source.url,entry.source.text,d));
  const old={...d};delete old.prior_renewal_date_type;assert.equal(current.fields(entry.source.url,entry.source.text,old),null);
  for(const type of ['other',true,1])assert.equal(current.valid({...d,issued_at:Date.now()/1000-1,expires_at:Date.now()/1000+50,prior_renewal_date_type:type}),false);
 }
});
