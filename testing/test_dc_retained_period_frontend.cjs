/* Actual failed live response, actual transport and actual table/Excel renderers. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),cp=require('node:child_process'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),file='web-staging/optimized-workflows.js';
const data=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/dc-retained-period-live.json'),'utf8'));
const old=cp.execFileSync('git',['show','fcb271897cd7826db2a642397dbcfebe2a03e277:'+file],{cwd:root,encoding:'utf8'});
let harness=fs.readFileSync(path.join(__dirname,'test_dc_period_frontend.cjs'),'utf8').split('(async()=>{')[0];
harness=harness.replace("'2026-10-30Current registration issued'","result.renewal_filing_value+result.renewal_filing_label")
 .replace("exported[7],'2026-10-30'","exported[7],result.renewal_filing_value")
 .replace("exported[11],'Current registration issued'","exported[11],result.renewal_filing_label")
 .replace('exported[13],result.source_url',"exported[13].replace(/&amp;/g,'&'),result.renewal_filing_source_url");
function load(source){const module={exports:{}};const wrapped={...fs,readFileSync(p,...rest){return String(p).endsWith('optimized-workflows.js')?source:fs.readFileSync(p,...rest);}};
 vm.runInNewContext(harness+'\nmodule.exports={run,checkActualPresentation};',{module,require:n=>n==='fs'?wrapped:require(n),__dirname,console,Blob,DOMException,AbortSignal,performance,queueMicrotask,setTimeout,clearTimeout});return module.exports;}
const baseline=load(old),candidate=load(fs.readFileSync(path.join(root,file),'utf8')),copy=x=>JSON.parse(JSON.stringify(x));
(async()=>{
 assert.equal((await baseline.run(data,'normal')).result.evidence_url,'','actual first candidate failure reproduced');
 let accepted=0,rejected=0,presentations=0;
 for(let i=0;i<30;i++){
  for(const mode of ['normal','lost-ack']){const r=await candidate.run(data,mode);assert.equal(r.result.evidence_url,data.update.evidence_url);assert.equal(r.result.comments,data.update.comments);assert.equal(r.result.renewal_date,data.base.renewal_date);assert.equal(r.result.status,data.base.status);assert.equal(r.calls.filter(x=>x==='archive').length,1);presentations+=await candidate.checkActualPresentation(r.result);accepted++;}
  for(const mode of ['wrong-ein','wrong-id','wrong-name','wrong-version','review','missing-proof','wrong-prior-status','wrong-prior-period','wrong-prior-issue','wrong-comments-binding','wrong-new-period','wrong-new-issue','wrong-source','old-image','unavailable','duplicate']){assert.equal((await candidate.run(data,mode)).result.evidence_url,'',mode);rejected++;}
  for(const key of ['renewal_date','renewal_date_type','renewal_date_source_url','renewal_date_source_label','renewal_date_note',...['value','type','label','source_url','note'].map(k=>'renewal_filing_'+k)]){
   for(const remove of [false,true]){const broken=copy(data);if(remove)delete broken.update[key];else broken.update[key]='changed';const r=(await candidate.run(broken,'normal')).result;if(remove){assert.equal(r.evidence_url,data.update.evidence_url,key);assert.equal(r[key],data.base[key],key);}else{assert.equal(r.evidence_url,'',key);rejected++;}}
  }
  for(const change of ['type','flag','issue']){const broken=copy(data);if(change==='type')delete broken.base.desktop_evidence_request.prior_renewal_date_type;if(change==='flag')delete broken.update.dc_source_reconciliation.period_effective_date_retained;if(change==='issue')broken.update.dc_source_reconciliation.issue_date=broken.base.renewal_date;assert.equal((await candidate.run(broken,'normal')).result.evidence_url,'',change);rejected++;}
 }
 console.log(JSON.stringify({actual_failed_response_baseline_reproduced:1,accepted,rejected,actual_table_excel_pairs:presentations,source_queries:0}));
})().catch(e=>{console.error(e);process.exitCode=1;});
