/* Alabama's observed public grid; no live requests or CAPTCHA solver. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../browser-connector/registry-content.js'),'utf8')
 .replace('  async function handle(m) {','  globalThis.testAL={alPage,alSearch};\n  async function handle(m) {');
const headers=['Name','License/Registration#','Status','Registration Type','Issued Date','Expiration Date','Address','City','State','Zip','Print'];
const row=['YWCA of the USA National Board','AL97-431','Active','Charitable Organization','08/29/2001','03/28/2027','1400 I Street NW','Washington','DC','20005','Print'];
const txt=innerText=>({innerText,getClientRects:()=>[{}]});
function harness({rows=[row],total=rows.length,page=1,pages=1,from=1,to=rows.length,verification='user-entered-test-placeholder',outcome='success',delayedPage=false,allRows=null,resize='success'}={}){
 let table=null,alert=null,observer=null,clicks=0,pageValue=page,filters=[],pageSize=5,pageActions=0,sizeActions=0;
 const labels={pgfrm:from,pgto:to,tot_pgs:total,totpg:pages};
 class Input{get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){}}
 class Select extends Input{};
 Object.defineProperty(Select.prototype,'value',Object.getOwnPropertyDescriptor(Input.prototype,'value'));
 const inputs=Object.fromEntries(['txt_verify','txt_linum','txtcity','txt_businessname','ddl_county','ddl_lictype'].map(id=>[id,new (id.startsWith('ddl')?Select:Input)()]));
 inputs.txt_verify.value=verification;
 const makeTable=()=>{
  const nodes=rows.map(r=>({children:r.map(v=>({...txt(v),tagName:'TD'}))}));
  const selector=new Select();selector.value=String(pageValue);selector.options=Array.from({length:pages},(_,i)=>({value:String(i+1)}));
  const renderPage=()=>{labels.pgfrm=(pageValue-1)*pageSize+1;labels.pgto=Math.min(pageValue*pageSize,total);labels.totpg=pages;rows=allRows.slice(labels.pgfrm-1,labels.pgto);table=makeTable();observer?.();};
  selector.dispatchEvent=e=>{if(e.type==='change') {pageActions++;pageValue=Number(selector.value);const complete=()=>{if(allRows)return renderPage();labels.pgfrm=2;labels.pgto=2;rows=[[...row.slice(0,1),'AL97-999',...row.slice(2)]];table=makeTable();observer?.();};if(delayedPage){observer?.();setTimeout(complete,10);}else complete();}};
  const size=new Input();size.value=String(pageSize);size.getClientRects=()=>[{}];
  size.dispatchEvent=e=>{if(e.type!=='change')return;sizeActions++;if(resize==='stale')return;pageSize=Number(size.value);pages=Math.ceil(total/pageSize);pageValue=1;if(resize==='changed-total')labels.tot_pgs=total+1;renderPage();};
  return {...txt('grid'),querySelectorAll:s=>s==='thead tr:first-child th'?headers.map(txt):s==='thead input'?filters:s==='tbody tr.grid_tr'?nodes:[],querySelector:s=>s.includes('input')?(allRows?size:null):selector};
 };
 const search={...txt('Search'),disabled:false,click:()=>{
  clicks++; if(outcome==='stale')return;
  if(outcome==='success')table=makeTable();
  else {table=null;alert=txt(outcome==='negative'?'•No Records Found':outcome==='verification'?'Verification code incorrect':'Error:');}
  observer?.();
 }};
 inputs.btn_search=search;
 const win={};win.top=win;
 const context=vm.createContext({window:win,location:{origin:'https://ago.igovsolution.net',pathname:'/online/Lookups/Business.aspx'},crypto:{randomUUID:()=> 'fixture'},
  document:{documentElement:{},getElementById:id=>id.startsWith('ctl00_cntbdy_')?inputs[id.slice('ctl00_cntbdy_'.length)]:labels[id]===undefined?null:txt(String(labels[id])),
    querySelector:s=>s==='#altdialog'?alert:s==='table.table.table-responsive.table-bordered'?table:null,querySelectorAll:()=>[]},
  MutationObserver:class{constructor(fn){this.fn=fn;}observe(){observer=this.fn;}disconnect(){observer=null;}},
  HTMLInputElement:Input,HTMLSelectElement:Select,Event:class{constructor(type){this.type=type;}},setTimeout,clearTimeout,
  chrome:{runtime:{id:'fixture',onMessage:{addListener(){}}}}});
 vm.runInContext(source,context);
 return {api:context.testAL,inputs,clicks:()=>clicks,actions:()=>({pageActions,sizeActions}),load:()=>{table=makeTable();},filters:v=>{filters=v;},headers};
}
const q={state:'AL',operation:'search',name:'YWCA'};
test('AL clears restrictive filters and collects all public identity fields without verification material',async()=>{
 const h=harness(),r=await h.api.alSearch(q,Date.now()+1000);
 assert.equal(r.rows[0][1],'AL97-431');assert.equal(r.rows[0][10],'');assert.equal(r.total,1);
 assert.equal(h.inputs.ddl_lictype.value,'-1');assert.equal(h.inputs.ddl_county.value,'-1');
 assert.equal(h.inputs.txt_verify.value,'user-entered-test-placeholder');assert.ok(!JSON.stringify(r).includes('user-entered'));
});
test('AL explicit fresh no-record alert is conclusive source evidence',async()=>{
 const h=harness({outcome:'negative'}),r=await h.api.alSearch(q,Date.now()+1000);assert.equal(r.total,0);assert.equal(r.complete,true);
});
test('AL missing or rejected verification is never automated or accepted as no records',async()=>{
 const h=harness({verification:''});await assert.rejects(h.api.alSearch(q,Date.now()+1000),/VERIFICATION_REQUIRED/);assert.equal(h.clicks(),0);
 await assert.rejects(harness({outcome:'verification'}).api.alSearch(q,Date.now()+1000),/VERIFICATION_REQUIRED/);
});
test('AL source error and unchanged prior grid cannot be returned as completed results',async()=>{
 await assert.rejects(harness({outcome:'error'}).api.alSearch(q,Date.now()+1000));
 const h=harness({outcome:'stale'});h.load();await assert.rejects(h.api.alSearch(q,Date.now()+20));
});
test('AL pagination collects subsequent observed rows without skipping a page',async()=>{
 const h=harness({total:2,pages:2});const r=await h.api.alSearch(q,Date.now()+1500);
 assert.equal(r.total,2);assert.deepEqual(Array.from(r.rows,r=>r[1]),['AL97-431','AL97-999']);
});
test('AL final-page selector may change before its rows and counters arrive',async()=>{
 const h=harness({total:2,pages:2,delayedPage:true});const r=await h.api.alSearch(q,Date.now()+1500);
 assert.equal(r.total,2);assert.deepEqual(Array.from(r.rows,r=>r[1]),['AL97-431','AL97-999']);
});
test('AL incomplete count, changed columns and residual filters are rejected',()=>{
 const h=harness({total:3});h.load();assert.throws(()=>h.api.alPage());
 const f=harness();f.load();f.filters([{value:'Active'}]);assert.throws(()=>f.api.alPage());
 const c=harness();c.load();c.headers[1]='Other ID';assert.throws(()=>c.api.alPage());c.headers[1]='License/Registration#';
});
const manyRows=n=>Array.from({length:n},(_,i)=>[row[0],`AL-${i+1}`,...row.slice(2)]);
test('AL public page-size expansion collects every row across full and partial pages',async()=>{
 const allRows=manyRows(267),h=harness({allRows,rows:allRows.slice(0,5),total:267,pages:54});
 const result=await h.api.alSearch(q,Date.now()+2000);
 assert.equal(result.total,267);assert.equal(result.rows.length,267);
 assert.deepEqual(Array.from(result.rows,r=>r[1]),allRows.map(r=>r[1]));
 assert.deepEqual(h.actions(),{pageActions:2,sizeActions:1});
});
test('AL page-size expansion validates a complete small search without additional pages',async()=>{
 const allRows=manyRows(18),h=harness({allRows,rows:allRows.slice(0,5),total:18,pages:4});
 const result=await h.api.alSearch(q,Date.now()+1000);
 assert.equal(result.rows.length,18);assert.deepEqual(h.actions(),{pageActions:0,sizeActions:1});
});
test('AL unchanged rows or a changed total after resizing never establish a completed search',async()=>{
 const allRows=manyRows(267);
 for(const resize of ['stale','changed-total']){
  const h=harness({allRows,rows:allRows.slice(0,5),total:267,pages:54,resize});
  await assert.rejects(h.api.alSearch(q,Date.now()+300),/REGISTRY_/);
 }
});
