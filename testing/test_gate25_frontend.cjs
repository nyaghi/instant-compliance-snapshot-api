/* Schema-two reconciliation through the actual client transport and guards. */
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process'),{webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..'),out=spawnSync('python',['-m','testing.gate25_frontend_case'],{cwd:root,encoding:'utf8'});
assert.equal(out.status,0,out.stderr);const fixture=JSON.parse(out.stdout),copy=x=>JSON.parse(JSON.stringify(x));
const filingKeys=['value','type','label','source_url','note'].map(k=>'renewal_filing_'+k);
const existing=fs.readFileSync(path.join(__dirname,'test_dc_period_frontend.cjs'),'utf8');
eval(existing.slice(existing.indexOf('async function run('),existing.indexOf('(async()=>')));
(async()=>{
  for(const mode of ['normal','lost-ack']) {
    const r=await run(fixture,mode);
    assert.equal(r.result.status,'Current');assert.equal(r.result.matched_registry_identifier,'400222000224');
    assert.equal(r.result.comments,fixture.update.comments);assert.ok(r.result.evidence_url);
    assert.equal(r.calls.filter(x=>x==='archive').length,1);
  }
  for(const mode of ['wrong-ein','wrong-id','wrong-name','wrong-version','review','missing-proof','wrong-new-period','wrong-new-issue','wrong-source','old-image','unavailable','duplicate',...filingKeys.flatMap(k=>['stale-'+k,'missing-'+k])]) {
    const r=await run(fixture,mode);assert.equal(r.result.status,'Delinquent',mode);assert.equal(r.result.evidence_url,'',mode);
  }
  const changed=copy(fixture);delete changed.update.dc_source_reconciliation.identity_method;
  assert.equal((await run(changed,'lost-ack')).result.status,'Delinquent');
  console.log('Gate25 linked corporate frontend: 2 successful acknowledgement paths and 23 rejection controls passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
