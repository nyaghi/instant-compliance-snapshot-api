const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs'),path=require('node:path');
const {harness,tick,id}=require('./run_ny_connector_lifecycle.cjs');
const origin='https://fixture-final-four.onrender.com';
function lane(h,state,n){
 const listeners=[],disconnects=[],p={name:`cc-${state.toLowerCase()}-lookup-v1:${id(n)}`,
 sender:{id:h.chrome.runtime.id,frameId:0,url:origin+'/',tab:{id:1}},messages:[],
 onMessage:{addListener:f=>listeners.push(f)},onDisconnect:{addListener:f=>disconnects.push(f)},
 postMessage:m=>p.messages.push(m),disconnect:()=>disconnects.forEach(f=>f())};
 p.send=m=>listeners.forEach(f=>f(m));h.chrome.runtime.onConnect.emit(p);return p;
}
test('trial admits independent states while preserving same-state FIFO and original deadlines',async()=>{
 const h=harness({trialOrigin:origin});h.tabs.get(1).url=origin+'/';
 const ny=lane(h,'NY',1),nv=lane(h,'NV',2),tn=lane(h,'TN',3),nv2=lane(h,'NV',4);
 await tick();for(const [p,n] of [[ny,10],[nv,11],[tn,12],[nv2,13]])p.send({action:'acquire',id:id(n)});await tick();
 assert.ok(ny.messages.some(m=>m.id===id(10)&&m.ok));
 assert.ok(nv.messages.some(m=>m.id===id(11)&&m.ok));
 assert.ok(tn.messages.some(m=>m.id===id(12)&&m.ok));
 assert.ok(!nv2.messages.some(m=>m.id===id(13)&&m.ok));
 const before=JSON.parse(JSON.stringify(h.data.session.ccnyRuntime.queue));
 nv.send({action:'finish',id:id(20)});await tick();await h.advance(3000);
 assert.ok(nv2.messages.some(m=>m.id===id(13)&&m.ok));
 for(const p of [ny,tn])assert.equal(h.data.session.ccnyRuntime.queue.find(j=>j.id===p.name.split(':')[1]).activeExpiresAt,
   before.find(j=>j.id===p.name.split(':')[1]).activeExpiresAt);
});
test('canceling one registry cannot release or close a different registry job',async()=>{
 const h=harness({trialOrigin:origin});h.tabs.get(1).url=origin+'/';
 const a=lane(h,'NV',1),b=lane(h,'TN',2);await tick();
 a.send({action:'finish',id:id(3)});await tick();
 assert.deepEqual(h.data.session.ccnyRuntime.queue.map(j=>j.registryState),['TN']);
 assert.equal(vm.runInContext("activeLanes.has('TN')",h.context),true);
});

test('all eight trial browser registries can be admitted independently',async()=>{
 const h=harness({trialOrigin:origin});h.tabs.get(1).url=origin+'/';
 const ports=['NY','IL','GA','AL','NC','NV','TN','NM'].map((s,i)=>lane(h,s,i+1));await tick();
 for(const [i,p] of ports.entries())p.send({action:'acquire',id:id(20+i)});await tick();
 assert.equal(vm.runInContext('activeLanes.size',h.context),8);
 for(const [i,p] of ports.entries())assert.ok(p.messages.some(m=>m.id===id(20+i)&&m.ok));
});

test('NM cleanup closes only an owned public registry tab and preserves the user tab',async()=>{
 for(const pathname of ['/CharitySearch/','/CharitySearch/CharityDetail.aspx?FEIN=12-3456789','/charitysearch/GenericError.htm?aspxerrorpath=/CharitySearch/default.aspx']){
  const h=harness({trialOrigin:origin});await tick();
  h.tabs.set(3,{id:3,windowId:10,url:'https://secure.nmdoj.gov'+pathname});
  h.tabs.set(4,{id:4,windowId:10,url:'https://secure.nmdoj.gov'+pathname});
  vm.runInContext('owned.add(3)',h.context);await h.context.removeOwned(3);
  assert.equal(h.tabs.has(3),false);assert.equal(h.tabs.has(4),true);
 }
});

function nmContent(){
 const table=cells=>({rows:cells.map(row=>({cells:row.map(innerText=>({innerText}))}))});
 const fields=new Map();
 for(const [id,value] of [['CharityName',''],['City',''],['Zip',''],['FEIN','46-1349584']])
  fields.set('#MainContent_TextBox'+id,{value});
 fields.set('#MainContent_DropDownListPageSize',{value:'1000'});
 fields.set('#MainContent_LabelRecCount',{innerText:'Charities Found: 0'});
 fields.set('#MainContent_GridView1',{querySelectorAll:()=>[]});
 const window={};window.top=window;
 const ctx=vm.createContext({window,location:{origin:'https://secure.nmdoj.gov',pathname:'/CharitySearch/',href:'https://secure.nmdoj.gov/CharitySearch/'},
  crypto:{randomUUID:()=>id(20)},URL,document:{querySelector:s=>fields.get(s)},
  chrome:{runtime:{id:'fixture',onMessage:{addListener(){}}}}});
 const content=fs.readFileSync(path.join(process.env.CC_TEST_TRIAL_DIR||path.join(__dirname,'../browser-connector'),'registry-content.js'),'utf8')
  .replace('  async function handle(m) {','  globalThis.nmTest={handle};\n  async function handle(m) {');
 vm.runInContext(content,ctx);return {api:ctx.nmTest,fields,table};
}
test('NM collector refuses a stale filter and incomplete pagination before reporting zero',async()=>{
 const h=nmContent(),query={state:'NM',operation:'search',ein:'461349584',name:''};
 assert.equal((await h.api.handle({action:'registry-nm-rows',query})).evidence.total,0);
 h.fields.get('#MainContent_TextBoxFEIN').value='12-3456789';
 await assert.rejects(h.api.handle({action:'registry-nm-rows',query}),/INCOMPLETE/);
 h.fields.get('#MainContent_TextBoxFEIN').value='46-1349584';
 h.fields.get('#MainContent_LabelRecCount').innerText='Charities Found: 1001';
 await assert.rejects(h.api.handle({action:'registry-nm-rows',query}),/INCOMPLETE/);
});

test('NM error-page readiness distinguishes an explicit source error from an unsettled form',async()=>{
 const h=nmContent();
 h.fields.set('h1',{innerText:'New Mexico Charity Search'});
 h.fields.set('p',{innerText:'We apologize. An unexpected error has occurred. Please try your request again.'});
 const failed=await h.api.handle({action:'registry-ready'});
 assert.equal(failed.source_failure,'REGISTRY_NM_SOURCE_ERROR');assert.equal(failed.ready,false);
 h.fields.delete('p');
 assert.equal((await h.api.handle({action:'registry-ready'})).source_failure,undefined);
});
test('NM collector exports only EIN-bound history and fiscal periods, excluding financial amounts',async()=>{
 const h=nmContent(),query={state:'NM',operation:'detail',identifier:'752556496',name:'Fixture Foundation'};
 h.fields.set('#MainContent_FormViewCharityDetail_LabelCharityName',{innerText:'Fixture Foundation (75-2556496)'});
 h.fields.set('#MainContent_GridViewStatuses',h.table([['Tax Year','Registration Details','Status Date'],['2024','Registration Submitted 20244922536459055','12/30/2025']]));
 h.fields.set('#MainContent_GridViewFinancials',h.table([['Fiscal Period','Revenue'],['2024 1/1/2024 - 12/31/2024 IRS Document Filed: 990','$123456 private-unneeded']]));
 const result=await h.api.handle({action:'registry-nm-detail',query});
 assert.equal(result.evidence.financial_periods[0].period_end,'12/31/2024');
 assert.ok(!JSON.stringify(result).includes('123456'));assert.ok(!JSON.stringify(result).includes('Revenue'));
 await assert.rejects(h.api.handle({action:'registry-nm-detail',query:{...query,identifier:'123456789'}}),/INCOMPLETE/);
});
