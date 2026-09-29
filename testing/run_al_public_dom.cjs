/* Alabama's observed public grid; no live requests or CAPTCHA solver. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../browser-connector/registry-content.js'),'utf8')
 .replace('  async function handle(m) {','  globalThis.testAL={alPage,alSearch};\n  async function handle(m) {');
const headers=['Name','License/Registration#','Status','Registration Type','Issued Date','Expiration Date','Address','City','State','Zip','Print'];
const row=['YWCA of the USA National Board','AL97-431','Active','Charitable Organization','08/29/2001','03/28/2027','1400 I Street NW','Washington','DC','20005','Print'];
const txt=innerText=>({innerText,getClientRects:()=>[{}]});
function harness({rows=[row],total=rows.length,page=1,pages=1,from=1,to=rows.length,verification='user-entered-test-placeholder',outcome='success'}={}){
 let table=null,alert=null,observer=null,clicks=0,pageValue=page,filters=[];
 const labels={pgfrm:from,pgto:to,tot_pgs:total,totpg:pages};
 class Input{get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){}}
 class Select extends Input{};
 Object.defineProperty(Select.prototype,'value',Object.getOwnPropertyDescriptor(Input.prototype,'value'));
 const inputs=Object.fromEntries(['txt_verify','txt_linum','txtcity','txt_businessname','ddl_county','ddl_lictype'].map(id=>[id,new (id.startsWith('ddl')?Select:Input)()]));
 inputs.txt_verify.value=verification;
 const makeTable=()=>{
  const nodes=rows.map(r=>({children:r.map(v=>({...txt(v),tagName:'TD'}))}));
  const selector=new Select();selector.value=String(pageValue);selector.options=Array.from({length:pages},(_,i)=>({value:String(i+1)}));
  selector.dispatchEvent=e=>{if(e.type==='change') {pageValue=Number(selector.value);labels.pgfrm=2;labels.pgto=2;rows=[[...row.slice(0,1),'AL97-999',...row.slice(2)]];table=makeTable();observer?.();}};
  return {...txt('grid'),querySelectorAll:s=>s==='thead tr:first-child th'?headers.map(txt):s==='thead input'?filters:s==='tbody tr.grid_tr'?nodes:[],querySelector:()=>selector};
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
 return {api:context.testAL,inputs,clicks:()=>clicks,load:()=>{table=makeTable();},filters:v=>{filters=v;},headers};
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
test('AL incomplete count, changed columns and residual filters are rejected',()=>{
 const h=harness({total:3});h.load();assert.throws(()=>h.api.alPage());
 const f=harness();f.load();f.filters([{value:'Active'}]);assert.throws(()=>f.api.alPage());
 const c=harness();c.load();c.headers[1]='Other ID';assert.throws(()=>c.api.alPage());c.headers[1]='License/Registration#';
});
