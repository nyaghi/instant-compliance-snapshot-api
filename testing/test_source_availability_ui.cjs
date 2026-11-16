const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict'),{test}=require('node:test');
const path=require('node:path');
const context={window:{}, TextEncoder,Blob,URL,location:{origin:'https://staging.example'}};
vm.runInNewContext(fs.readFileSync('web-staging/identity-review.js','utf8'),context);
vm.runInNewContext(fs.readFileSync('web-staging/excel-export.js','utf8'),context);
const rows=JSON.parse(fs.readFileSync(path.join(__dirname,'source_availability_matrix.json'),'utf8'));
const label=context.window.CCIdentityReview.statusLabel;

function unzipStored(buffer){
 const files={};let at=0;
 while(buffer.readUInt32LE(at)===0x04034b50){
  assert.equal(buffer.readUInt16LE(at+8),0);
  const size=buffer.readUInt32LE(at+18),n=buffer.readUInt16LE(at+26),extra=buffer.readUInt16LE(at+28);
  const name=buffer.subarray(at+30,at+30+n).toString(),start=at+30+n+extra;
  files[name]=buffer.subarray(start,start+size).toString();at=start+size;
 }
 return files;
}

test('all 342 classified failures have the same status in UI and real Excel',async()=>{
 assert.equal(rows.length,342); assert.equal(new Set(rows.map(r=>r.state)).size,38);
 const original=JSON.stringify(rows);
 for(const row of rows)assert.equal(label(row),'Site Not Reachable',row.state);
 const files=unzipStored(Buffer.from(await context.window.CCExcelExport.build(rows).arrayBuffer()));
 const sheet=files['xl/worksheets/sheet1.xml'];
 const statuses=[...sheet.matchAll(/<c r="D(\d+)"[^>]*><is><t[^>]*>(.*?)<\/t><\/is><\/c>/g)].slice(1).map(m=>m[2]);
 assert.equal(statuses.length,342);assert.ok(statuses.every(s=>s==='Site Not Reachable'));
 assert.equal(JSON.stringify(rows),original,'export must not mutate results');
});

test('all states preserve healthy results, identity controls and unclassified failures',()=>{
 for(const state of new Set(rows.map(r=>r.state))){
  const outage=rows.find(r=>r.state===state);
  for(const status of ['Current','Delinquent','Not Registered','Exempt','Upcoming Filing'])
   assert.equal(label({...outage,status,success:true}),status);
  assert.equal(label({...outage,identity_review:{candidates:[{id:'1',name:'Candidate'}]}}),'Confirm match');
  const undecided={state,status:'Unable to Confirm',success:false,reason_code:'PARSER_ERROR'};
  assert.equal(label(undecided),state==='RI'?'Registry check incomplete':'Review required');
 }
});

test('malformed availability markers cannot override normal review',()=>{
 for(const source_availability of [{schema:2,kind:'source_error'},{schema:1,kind:'identity_uncertain'}])
  assert.equal(label({state:'AL',status:'Site Not Reachable',success:false,source_availability}),'Review required');
});
