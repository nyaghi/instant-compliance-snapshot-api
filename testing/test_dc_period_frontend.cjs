/* Actual run transport with real backend fixture updates; no browser/source requests. */
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process'),{webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..'),loaded=spawnSync('python',['-m','testing.dc_period_frontend_cases'],{cwd:root,encoding:'utf8'});
assert.equal(loaded.status,0,loaded.stderr);const cases=JSON.parse(loaded.stdout),copy=x=>JSON.parse(JSON.stringify(x));
const filingKeys=['value','type','label','source_url','note'].map(k=>'renewal_filing_'+k);
async function checkActualPresentation(result){
 let checked=0;
 for(const file of ['index.html','instant-compliance-snapshot.html']){
  const html=fs.readFileSync(path.join(root,'web-staging',file),'utf8');
  const render=html.slice(html.indexOf('    function renderResults('),html.indexOf('    function downloadLeadLog('));
  const excel=html.slice(html.indexOf('    function downloadExcel('),html.indexOf('    function fallbackResult('));
  assert.ok(render.startsWith('    function renderResults('));assert.ok(excel.startsWith('    function downloadExcel('));
  const rows=[];let blob;
  const classList={toggle(){},remove(){}};
  const context=vm.createContext({input:copy(result),window:{},Date,Blob,internalUnlocked:true,
   latestResults:[],generateReportButton:{classList},reportMessage:{},resultTimestamp:{},
   resultRows:{set innerHTML(v){rows.length=0;},appendChild(row){rows.push(row);}},
   resultPanel:{classList},downloadPackageButton:{classList},downloadExcelButton:{classList},downloadLeadLogButton:{classList},fullPictureCta:{classList},
   document:{createElement:()=>({innerHTML:'',lastElementChild:{},click(){}})},
   URL:{createObjectURL(value){blob=value;return 'blob:local-fixture';},revokeObjectURL(){}},
   escapeHtml:value=>String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;'),
   formatEin:value=>value,statusClass:()=>'',boldStatuses:value=>value,commentsWithRegistryFooter:value=>value.comments});
  vm.runInContext(render+'\n'+excel+'\nrenderResults([input],true);downloadExcel();',context);
  const cells=Array.from(rows[0].innerHTML.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g),m=>m[1].replace(/<[^>]*>/g,''));
  assert.equal(cells[4],result.registration_date+(result.registration_date_source_label||''),file);
  assert.equal(cells[5],'2026-10-30Current registration issued',file);
  const exported=Array.from((await blob.text()).matchAll(/<td>([\s\S]*?)<\/td>/g),m=>m[1]);
  assert.equal(exported[7],'2026-10-30',file);assert.equal(exported[11],'Current registration issued',file);
  assert.equal(exported[12],result.renewal_date_note,file);assert.equal(exported[13],result.source_url,file);checked++;
 }
 return checked;
}
async function run(input,mode,ack='lost'){
 const listeners=new Set(),base=copy(input.base),update=copy(input.update),calls=[];let polls=0,stored;
 const mutate=saved=>{
  if(mode==='wrong-ein')saved.ein='000000001';
  if(mode==='wrong-id')saved.matched_registry_identifier='999999999999';
  if(mode==='wrong-name')saved.organization_name='Unrelated';
  if(mode==='wrong-version')saved.execution_version='old';
  if(mode==='review')saved.confirmation_required=true;
  if(mode==='missing-proof')delete saved.dc_source_reconciliation;
  if(mode==='wrong-prior-status')saved.dc_source_reconciliation.prior_status='Delinquent';
  if(mode==='wrong-prior-period')saved.dc_source_reconciliation.prior_expiration='2025-10-31';
  if(mode==='wrong-prior-issue')saved.dc_source_reconciliation.prior_renewal_date='2020-01-01';
  if(mode==='wrong-comments-binding')saved.dc_source_reconciliation.prior_comments_sha256='0'.repeat(64);
  if(mode==='wrong-new-period')saved.computed_due_date='2029-10-31';
  if(mode==='wrong-new-issue')saved.renewal_date='2026-01-01';
  if(mode==='wrong-source')saved.source_url='https://external.invalid/detail';
  if(mode==='old-image')saved.evidence_captured_at=1;
  if(mode==='unavailable')saved.evidence_capture='unavailable';
  for(const key of filingKeys){
   if(mode==='stale-'+key)saved[key]=base[key];
   if(mode==='missing-'+key)delete saved[key];
  }
  return saved;
 };
 const window={__CCLabStateTrace:[],addEventListener:(k,f)=>listeners.add(f),removeEventListener:(k,f)=>listeners.delete(f),postMessage(m){
  queueMicrotask(()=>{for(const fn of [...listeners])fn({source:window,origin:'https://staging.compliance-express.com',data:{...m,direction:'response',result:{ok:true}}});});
 }};
 const ctx=vm.createContext({window,location:{origin:'https://staging.compliance-express.com'},crypto:webcrypto,AbortSignal,performance,Date,setTimeout,clearTimeout,
  fetch:async(url,options)=>{
   const data=JSON.parse(options.body);calls.push(url.endsWith('/api/source-evidence')?'archive':data.action);
   if(url.endsWith('/api/source-evidence')){
    stored=mutate({...copy(base),...copy(update)});delete stored.desktop_evidence_request;
    if(mode!=='normal'&&ack!=='normal')throw new DOMException('Modeled lost acknowledgement','TimeoutError');
    return {ok:true,json:async()=>mode==='normal'?copy(update):copy(stored)};
   }
   if(data.action==='start')return {ok:true,json:async()=>({token:'same-workflow'})};
   if(data.action==='poll'){
    polls++;let rows=polls===1?[copy(base)]:[stored];
    if(mode==='duplicate'&&polls>1)rows.push(copy(stored));
    return {ok:true,json:async()=>({results:rows,finished:1})};
   }
   return {ok:true,json:async()=>({ok:true})};
  }});
 vm.runInContext(fs.readFileSync(path.join(root,'web-staging/optimized-workflows.js'),'utf8'),ctx);
 const results=await window.CCOptimized.run({apiBase:'https://fixture.invalid',name:base.organization_name,ein:base.ein,states:['DC'],credentials:{}});
 return {result:copy(results[0]),calls};
}
(async()=>{
 const counts={contexts:cases.length,normal:0,lost_ack:0,rejections:0,actual_page_and_excel_pairs:0,live_queries:0};
 for(const fixture of cases){
  for(const mode of ['normal','lost-ack']){
   const r=await run(fixture,mode);assert.equal(r.result.status,fixture.update.status);assert.equal(r.result.comments,fixture.update.comments);
   assert.equal(r.result.renewal_date,'2026-10-30');assert.equal(r.result.computed_due_date,'2028-10-31');assert.ok(r.result.evidence_url);
   assert.equal(r.result.renewal_filing_value,'2026-10-30');
   counts.actual_page_and_excel_pairs+=await checkActualPresentation(r.result);
   assert.equal(r.result.registration_date,fixture.base.registration_date);assert.equal(r.calls.filter(x=>x==='archive').length,1);
   counts[mode==='normal'?'normal':'lost_ack']++;
  }
  for(const mode of ['wrong-ein','wrong-id','wrong-name','wrong-version','review','missing-proof','wrong-prior-status','wrong-prior-period','wrong-prior-issue','wrong-comments-binding','wrong-new-period','wrong-new-issue','wrong-source','old-image','unavailable','duplicate',...filingKeys.flatMap(k=>['stale-'+k,'missing-'+k])]){
   for(const ack of (mode==='duplicate'?['lost']:['normal','lost'])){
    const r=await run(fixture,mode,ack);assert.equal(r.result.evidence_url,'',mode+':'+ack);assert.equal(r.result.status,fixture.base.status,mode);
    assert.equal(r.result.comments,fixture.base.comments,mode);assert.equal(r.result.renewal_date,fixture.base.renewal_date,mode);counts.rejections++;
    for(const key of filingKeys)assert.equal(r.result[key],fixture.base[key],mode);
   }
  }
 }
 console.log(JSON.stringify(counts));
})().catch(error=>{console.error(error);process.exitCode=1;});
