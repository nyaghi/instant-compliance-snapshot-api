// Pure DOM fixtures: no browser process or registry traffic.
const assert=require('node:assert/strict');
const api=require('../deployment/staging_connector/dc-boss-source.js');
const visible=e=>Object.assign(e,{getClientRects:()=>[{}]});
global.getComputedStyle=()=>({visibility:'visible',display:'block'});
global.location={href:'https://boss.dc.gov/business/business-license-search'};
const d={name:'Example National Museum',identifier:'400222000510'};
let rows=[],clicked=0;
const header=visible({querySelector:()=>null});
function row(id=d.identifier,name=d.name,activity='Charitable Solicitation',more=null){
  const link=visible({click(){clicked++;}});
  const cells={'.mat-column-licenseNumber':visible({innerText:id}),
    '.mat-column-licenseeName':visible({innerText:name}),'.mat-column-licenseActivity':visible({innerText:activity}),
    '.mat-column-licenseeName a':link};
  cells['td.mat-column-licenseNumber']=cells['.mat-column-licenseNumber'];
  cells['.mat-column-licenseActivity'].querySelectorAll=s=>!more?[]:s==='span'?[{innerText:more.label}]:s==='a[aria-label]'?[{innerText:more.count,getAttribute:()=>more.aria}]:[];
  return visible({querySelector:s=>cells[s]||null});
}
global.document={body:{innerText:''},getElementById:()=>visible({innerText:'License Number'}),
  querySelectorAll:s=>s==='table[aria-label="grid-table"] tr'?[header,...rows]:s==='.mat-column-licenseNumber'?[visible({innerText:'License Number'})]:[]};
assert.equal(api.pageStep({phase:'type',d}).next,'fill'); // ordinary non-reconciliation request
assert.equal(api.pageStep({phase:'row',d}).waiting,true); // header before rows
assert.equal(clicked,0);
rows=[row()];assert.equal(api.pageStep({phase:'row',d}).next,'metadata');assert.equal(clicked,1);
for(const bad of [[row('999')],[row(d.identifier,'Other Museum')],[row(d.identifier,d.name,'General Business')],[row(),row()]]){
  rows=bad;const before=clicked,out=api.pageStep({phase:'row',d});
  assert.equal(out.error,'selected_license_not_unique_or_absent');assert.equal(clicked,before);
  assert.equal(out.selection.rows,bad.length);
}
rows=[row(d.identifier,'THE '+d.name)];
assert.equal(api.pageStep({phase:'row',d}).error,'selected_license_not_unique_or_absent'); // no new identity relaxation
for(const count of ['+1','+12']){
 rows=[row(d.identifier,d.name,'Charitable Solicitation'+count,{label:'Charitable Solicitation',count,aria:count+' more activities'})];
 assert.equal(api.pageStep({phase:'row',d}).next,'metadata');
}
for(const more of [{label:'General Business',count:'+1',aria:'+1 more activities'},
 {label:'Charitable Solicitation',count:'+1',aria:'+2 more activities'},
 {label:'Charitable Solicitation',count:'+0',aria:'+0 more activities'}]){
 rows=[row(d.identifier,d.name,more.label+more.count,more)];
 assert.equal(api.pageStep({phase:'row',d}).error,'selected_license_not_unique_or_absent');
}
console.log(JSON.stringify({exact_license_without_reconciliation:1,header_readiness:1,selected_row:1,rejected_row_sets:5,browser_processes:0,live_queries:0}));
