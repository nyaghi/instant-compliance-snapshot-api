const vm=require('node:vm'),{readFileSync}=require('node:fs'),assert=require('node:assert/strict');
const context={};vm.runInNewContext(readFileSync('deployment/staging_connector/tn-extension-account-worker.js','utf8'),context);
const parse=context.CCTNExtensionAccount.records;
const roster=JSON.parse(readFileSync('testing/fixtures/gate53/LOCAL-70.json','utf8')).slice(0,70),cases=[];
for(const [i,org] of roster.entries()){
 const co='CO'+(10000+i),tracking=String(9000000000+i),headers=['','Tracking Number','Registration Number','Description','Fee','Filing Type','Filing Status','Updated'];
 const row=['',tracking,co,'First Extension Request for '+org.name,'$0.00','Extension Request','Rejected','Test timestamp'];
 const actual=parse({headers,rows:[row]},co,[org.name],'https://tncab.tnsos.gov/portal/my-filings');assert.equal(actual.length,1);assert.equal(actual[0].tracking,tracking);assert.equal(actual[0].status,'Rejected');
 const other=[...row];other[2]='CO1';assert.equal(parse({headers,rows:[other]},co,[org.name],'source').length,0,'different CO overrides same name');
 const completedHeaders=['','Id','Tracking Number','Filing Status','Description','Filing Type','Updated'];
 const completed=['','test-id',tracking,'Accepted','First Extension Request for '+org.name,'Extension Request','Test timestamp'];
 const nameOnly=parse({headers:completedHeaders,rows:[completed]},co,[org.name],'source');assert.equal(nameOnly.length,1);assert.equal(nameOnly[0].identity_method,'exact_name');assert.equal(nameOnly[0].coid,'','missing CO remains missing');
 assert.equal(parse({headers:completedHeaders,rows:[completed]},co,['Different organization'],'source').length,0);
 assert.throws(()=>parse({headers:[...headers,'Tracking Number'],rows:[]},co,[org.name],'source'),/TABLE_CHANGED/);
 assert.throws(()=>parse({headers,rows:[row.slice(1)]},co,[org.name],'source'),/TABLE_CHANGED/);
 cases.push({ein:org.ein,name:org.name,passed:true,conditions:'Constructed account table rows on recorded identity; not actual private filing history'});
}
assert.equal(new Set(cases.map(c=>c.ein)).size,70);
context.location={origin:'https://tncab.tnsos.gov',pathname:'/portal/my-filings'};
context.document={body:{innerText:'You must be logged in to view this page'},querySelector:()=>null};
assert.equal(context.CCTNExtensionAccount.snapshotPage().state,'sign_in_required','observed signed-out account route is explicit, not a timeout');
const source=readFileSync('deployment/staging_connector/tn-extension-account-worker.js','utf8');
assert(!/runUserActionWorkflow|\.cookies\.|\.submit\(/.test(source),'no credentials, filing workflow actions or submissions');
assert(source.includes('button[aria-label="Go to the next page"]'),'only the observed read-only pager is clicked');
if(process.env.CC_TN_ACCOUNT_RESULTS)require('node:fs').writeFileSync(process.env.CC_TN_ACCOUNT_RESULTS,JSON.stringify(cases,null,2));
console.log('PASS: 70 recorded identities, exact CO/strict names, returned is not approval, malformed rows rejected; read-only account workflow.');
