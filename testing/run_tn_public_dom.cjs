/* Tennessee collector: public table and modal fixtures, no browser/network. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../browser-connector/registry-content.js'),'utf8')
 .replace('  async function handle(m) {','  globalThis.testTN={tnPage,tnFields,tnFinancials,tnSearch,tnDetail};\n  async function handle(m) {');
const columns=[null,'Id','Id','FileNumber','DisplayName','OtherNames','Status','City','StateName','StateCode','RegistrationDate'];
const national=['Details','unused summary','2162','CO2559','YWCA USA, INC.',"YOUNG WOMEN'S CHRISTIAN ASSOCIATION OF THE UNITED STATES OF AMERICA, INC.\nYWCA OF THE U.S.A.",'Active','WASHINGTON','DC','DC','5/12/1995'];
const local=['Details','unused summary','3596572','CO224','YWCA NASHVILLE & MIDDLE TENNESSEE','','Active','NASHVILLE','TN','TN','11/14/1985'];
function fixture({rows=[local,national],activity=true,ready=true,responseDelay=100,detailId='CO2559',periods=['06/30/2024','06/30/2025'],count=2,closeDelay=0,closedInitially=true}={}) {
 let clock=1000,serial=0,loading=false,doneRows=[],dialogVisible=!closedInitially,opened=[];
 const events=new Map(),observers=new Set(),root={};
 const later=(fn,ms)=>{let id=++serial;events.set(id,{fn,at:clock+ms});return id;};
 const target={nodeType:1,closest:()=>({}),matches:()=>false,querySelector:()=>null};
 const mask={nodeType:1,matches:s=>s==='.k-loading-mask',querySelector:()=>null,getClientRects:()=>loading?[{}]:[]};
 const mutate=(added=[])=>{for(const o of [...observers])o.fn([{type:'childList',target,addedNodes:added,removedNodes:[]}]);};
 class Input {get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){}}
 const inputs=Object.fromEntries(['Name','Filenumber','City'].map(k=>[k,new Input()]));
 const txt=innerText=>({innerText});
 const h4s=[txt(''),txt('1400 I STREET NW, SUITE 540 WASHINGTON DC 20005'),txt('ERIC ROSENBERG'),txt('(480) 699-8270'),
  txt('Status: Active'),txt('CO Number: '+detailId),txt('Registration Date: 05/12/1995'),txt('Expiration Date: 12/31/2026')];
 const financial={querySelectorAll:q=>q==='thead th'?[txt('Fiscal Year End'),txt('Total Revenue')]:periods.map(p=>({children:[txt(p),txt('$12,345')]}))};
 const financialLink={innerText:`Financials (${count})`,parentElement:{getAttribute:()=> 'true'},click:()=>{}};
 const dialog={getClientRects:()=>dialogVisible?[{}]:[],parentElement:{querySelector:()=>({click:()=>{later(()=>{dialogVisible=false;mutate();},closeDelay);}})},
  querySelector:q=>q==='h2'?txt('YWCA USA, INC.'):q==='#DetailsTabStrip-1'?{querySelector:()=>financial}:null,
  querySelectorAll:q=>q==='h4'?h4s:q==='.col-md-6 > h4'?h4s.slice(0,4):q==='#DetailsTabStrip > li > a'?[financialLink]:[]};
 const table={querySelectorAll:q=>q==='thead th'?columns.map(c=>({getAttribute:()=>c})):doneRows.map(cells=>({children:cells.map(txt),
  querySelectorAll:q=>q==='button'?[{innerText:'Details',click:()=>{opened.push(cells[3]);later(()=>{dialogVisible=true;mutate();},50);}}]:[]}))};
 const grid={closest:()=>({}),get innerText(){return doneRows.length?'Public search results':'No Records Available';},
  querySelector:q=>q==='table[role="grid"]'?table:q==='.k-pager-info'?txt(doneRows.length?`1 - ${doneRows.length} of ${doneRows.length} items`:'No items to display'):
   q==='[aria-current="page"]'?txt(doneRows.length?'1':'0'):null};
 const search={innerText:'Search',disabled:false,getClientRects:()=>ready?[{}]:[],click:()=>{
  if(activity&&!dialogVisible){loading=true;mutate([mask]);later(()=>{doneRows=rows;loading=false;mutate();},responseDelay);}
 }};
 const document={documentElement:root,readyState:'complete',querySelector:q=>q==='#KendoWindowLevel1'?dialog:q.startsWith('input[id^=')?inputs[q.match(/="([^_]+)_/)[1]]:null,
  querySelectorAll:q=>q==='.k-grid'?[grid]:q==='button[id^="Search_"]'?[search]:q==='[id^="SearchResults_"] .k-loading-mask'?[mask]:[]};
 const win={};win.top=win;
 const context={window:win,document,location:{origin:'https://tncab.tnsos.gov'},Date:{now:()=>clock},crypto:{randomUUID:()=> 'fixture'},
  HTMLInputElement:Input,HTMLSelectElement:class{},Event:class{},
  MutationObserver:class{constructor(fn){this.fn=fn;}observe(){observers.add(this);}disconnect(){observers.delete(this);}},
  setTimeout:later,clearTimeout:id=>events.delete(id),chrome:{runtime:{id:'fixture',onMessage:{addListener:()=>{}}}}};
 vm.createContext(context);vm.runInContext(source,context);
 async function drive(p) {let done=false,value,error;p.then(v=>{done=true;value=v;},e=>{done=true;error=e;});
  for(let n=0;!done&&n<1000;n++){for(let i=0;i<20;i++)await Promise.resolve();if(done)break;const next=[...events].sort((a,b)=>a[1].at-b[1].at)[0];assert.ok(next);events.delete(next[0]);clock=next[1].at;next[1].fn();}
  assert.ok(done);assert.equal(observers.size,0);if(error)throw error;return value;
 }
 return {api:context.testTN,drive,h4s,dialog,grid,table,opened,
  search:()=>drive(context.testTN.tnSearch({state:'TN',operation:'search',name:'YWCA'},clock+45000)),
  detail:()=>drive(context.testTN.tnDetail({state:'TN',operation:'detail',identifier:'CO2559'},clock+45000))};
}
test('Tennessee retains national and local candidates with separate CO identifiers',async()=>{const f=fixture(),r=await f.search();assert.equal(r.total,2);assert.deepEqual(Array.from(r.rows,x=>x.identifier),['CO224','CO2559']);assert.equal(r.rows[1].aliases.length,2);assert.ok(!JSON.stringify(r).includes('unused summary'));});
test('initial zero grid cannot become Not Registered before source completion',async()=>{const f=fixture({rows:[],activity:false});await assert.rejects(f.search(),/SEARCH_NOT_STARTED/);});
test('completed zero results require the count, zero page, and explicit empty marker',async()=>{const f=fixture({rows:[]});assert.equal((await f.search()).total,0);});
test('verification/form readiness failure is distinct from no records',async()=>{const f=fixture({ready:false});await assert.rejects(f.search(),/VERIFICATION_OR_FORM_PENDING/);});
test('late response is not accepted',async()=>{const f=fixture({responseDelay:40000});await assert.rejects(f.search(),/RESPONSE_PENDING/);});
test('the next alias waits for the prior detail modal to finish closing',async()=>{const f=fixture({closedInitially:false,closeDelay:350});assert.equal((await f.search()).total,2);});
test('a modal that never closes cannot submit or accept a new search',async()=>{const f=fixture({closedInitially:false,closeDelay:5000});await assert.rejects(f.search(),/RESPONSE_INCOMPLETE/);});
test('duplicate CO identifiers make the result set incomplete',async()=>{const f=fixture({rows:[national,national]});await assert.rejects(f.search(),/PAGINATION_INCOMPLETE/);});
test('detail selects the requested national CO record, not the first local chapter',async()=>{const f=fixture();await f.search();const r=await f.detail();assert.deepEqual(f.opened,['CO2559']);assert.equal(r.fields.Address,'1400 I STREET NW, SUITE 540 WASHINGTON DC 20005');assert.equal(r.fields['Expiration Date'],'12/31/2026');assert.equal(r.fields.financial_count,2);assert.equal(r.fields.financial_periods[1],'06/30/2025');assert.ok(!JSON.stringify(r).includes('ERIC ROSENBERG'));assert.ok(!JSON.stringify(r).includes('$12,345'));});
test('wrong CO detail is not completed evidence',async()=>{const f=fixture({detailId:'CO999'});await f.search();await assert.rejects(f.detail(),/RESPONSE_INCOMPLETE/);});
test('incomplete optional financial table preserves core status but not a filed period',async()=>{const f=fixture({count:25});await f.search();const r=await f.detail();assert.equal(r.complete,true);assert.equal(r.fields.Status,'Active');assert.equal(r.fields.financial_count,-1);assert.equal(r.fields.financial_periods.length,0);});
test('unobserved identifier cannot open any record',async()=>{const f=fixture();await assert.rejects(f.detail(),/DETAIL_NOT_OBSERVED/);assert.equal(f.opened.length,0);});
test('candidate Tennessee access remains absent from approved installed manifest',()=>{const m=fs.readFileSync(path.join(__dirname,'../browser-connector/manifest.json'),'utf8');assert.ok(!m.includes('tncab.tnsos.gov'));});
