const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ctx = vm.createContext({window:{}, location:{origin:'https://example.org'}, URL, Blob, TextEncoder, Uint8Array, DataView});
for (const file of ['identity-review.js','excel-export.js']) {
  vm.runInContext(fs.readFileSync('web-staging/'+file,'utf8'),ctx);
}
const ui = ctx.window.CCIdentityReview;
const orgs = process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2],'utf8')).map(x=>x.org) : [{name:'Example University',ein:'12-3456789'}];
const base = {state:'NV',status:'Unable to Confirm',success:false};
const cases = [
 ['NV','LICENSED_CHARITY_SOURCE','Nevada returned a business license. Aurora could not verify a charitable solicitation registration or exemption.','Nevada filing history'],
 ['CA','CA_REGISTRY_EIN_CONFLICT','','Compare the EIN'],
 ['MA','MA_MATCHED_FILING_PERIOD_UNVERIFIED','','most recent filing'],
 ['TN','NY_CONNECTOR_TN_VERIFICATION_PENDING','','verification step'],
 ['AR','AR_REQUIRED_SEARCH_INCOMPLETE','','stopped before'],
 ['NC','NY_CONNECTOR_REGISTRY_NC_CARD_CHANGED','','required details'],
 ['MS','NY_CONNECTOR_MS_DETAIL_UNAVAILABLE','','required details'],
 ['GA','NY_CONNECTOR_UPDATE_REQUIRED','','browser connector'],
 ['SC','PORTAL_ERROR','The state returned multiple records sharing the name.','Compare the state records'],
 ['WA','PORTAL_ERROR','','recorded cause']
];
for (const org of orgs) {
  for (const [state,code,note,want] of cases) {
    const r = {...base,state,organization_name:org.name,ein:org.ein,status_reason:code,source_note:note};
    const before=JSON.stringify(r),s=ui.reviewHandoff(r);
    assert.ok(s.includes(want),s);
    assert.ok(s.includes(org.ein));assert.ok(s.includes('Next step'));assert.equal(JSON.stringify(r),before);
  }
  for(const status of ['Current','Delinquent','Not Registered','Exempt'])assert.equal(ui.reviewHandoff({...base,status}), '');
  assert.equal(ui.reviewHandoff({...base,identity_review:{candidates:[{name:org.name}]}}),'');
  assert.equal(ui.reviewHandoff({...base,status:'Site Not Reachable',source_availability:{schema:1,kind:'transport_error'}}),'');
}
const row={...base,organization_name:'Example',ein:'12-3456789',matched_registry_identifier:'NV123',source_note:cases[0][2]};
const sample=ui.reviewHandoff(row);
assert.ok(sample.includes('NV123'));assert.ok(!sample.includes('linked state snapshot'));
assert.ok(ui.reviewHandoff({...row,evidence_url:'/state-snapshots/'+'a'.repeat(64)+'.pdf'}).includes('linked state snapshot'));
for(const page of ['index.html','instant-compliance-snapshot.html']){
 const html=fs.readFileSync('web-staging/'+page,'utf8'), fn=html.match(/function commentsWithRegistryFooter\(result\) \{[\s\S]*?\n    \}/)[0];
 vm.runInContext(fn,ctx);assert.equal(ctx.commentsWithRegistryFooter(row),sample);
}
(async()=>{const bytes=Buffer.from(await ctx.window.CCExcelExport.build([row]).arrayBuffer());assert.ok(bytes.includes(Buffer.from(sample)));console.log(orgs.length+' organizations passed review handoff and unchanged-status controls. Results and Excel agree.');})().catch(e=>{console.error(e);process.exitCode=1;});
