/* Regression of the two public table shapes observed on 2026-09-25.
 * Exercise the actual content-script message handler, not a copied parser. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const SOURCE=fs.readFileSync(path.join(__dirname,'../browser-connector/registry-content.js'),'utf8');
const combined=['Full Name','License #','Profession','License Type','Status','Address'];
const split=['Full Name','License Number','Profession','License Type','License Status','City','State',''];
function cell(value,tagName='TD',link=null){return {innerText:value,tagName,querySelector:()=>link};}
function row(values,header=false){return {children:values.map((v,i)=>cell(v,header?'TH':'TD',!header&&i===0?{href:'https://verify.sos.ga.gov/verification/Details.aspx?result=dc190d22-19e6-49ba-a65f-fd03cde1305d'}:null))};}
async function collect(headings,records=[],pagerPresent=true){
  let listener;
  const pager={children:[cell('1')],querySelectorAll:s=>s==='span'?[cell('1')]:[]};
  const rows=[row(headings,true),...records.map(r=>row(r)),...(pagerPresent?[pager]:[])];
  const table={querySelectorAll:()=>rows};
  const win={};win.top=win;
  const context={window:win,location:{origin:'https://verify.sos.ga.gov',pathname:'/verification/SearchResults.aspx'},crypto:{randomUUID:()=> 'fixture'},URL,
    chrome:{runtime:{id:'test-extension',onMessage:{addListener:fn=>listener=fn}}},
    document:{querySelector:selector=>selector==='#datagrid_results'?table:null},setTimeout,clearTimeout};
  vm.runInNewContext(SOURCE,context);
  return new Promise(resolve=>listener({action:'registry-ga-rows'},{id:'test-extension'},resolve));
}
test('six-column view preserves the qualified Young Life record even with no address',async()=>{
  const r=await collect(combined,[['Young Life (of Texas)','CH000861','Charities','Charity','Exempt','']]);
  assert.equal(r.ok,true);assert.equal(r.rows.length,1);assert.equal(r.rows[0].identifier,'CH000861');assert.equal(r.rows[0].name,'Young Life (of Texas)');
});
test('eight-column complaint view cannot erase Environmental Law Institute',async()=>{
  const r=await collect(split,[['Environmental Law Institute','CH08092','Charities','Charity','Active','','','Submit Complaint']]);
  assert.equal(r.ok,true);assert.equal(r.rows.length,1);assert.equal(r.rows[0].identifier,'CH08092');assert.equal(r.rows[0].location,'');
});
test('split city and state remain public identity evidence',async()=>{
  const r=await collect(split,[['Example Charity','CH12345','Charities','Charity','Active','Concord','CA','Submit Complaint']]);
  assert.equal(r.rows[0].location,'Concord, CA');assert.equal(r.rows[0].region,'CA');
});
test('completed empty six and eight-column tables remain empty searches',async()=>{
  for(const h of [combined,split]){const r=await collect(h);assert.equal(r.ok,true);assert.equal(r.rows.length,0);assert.equal(r.next,false);}
});
test('unknown headers or truncated rows are incomplete, never a negative result',async()=>{
  for(const [h,records] of [[['Unknown'],[]],[split,[['Environmental Law Institute','CH08092']]]]){
    const r=await collect(h,records);assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_INCOMPLETE');
  }
});
test('a missing pager cannot establish a completed search',async()=>{
  const r=await collect(combined,[['Example','CH123','Charities','Charity','Active','Boston, MA']],false);
  assert.equal(r.ok,false);
});
test('paid solicitors remain excluded from charity registrations',async()=>{
  const r=await collect(split,[['Example Solicitor','PS12345','Charities','Paid Solicitor','Active','Boston','MA','Submit Complaint']]);
  assert.equal(r.ok,true);assert.equal(r.rows.length,0);
});
