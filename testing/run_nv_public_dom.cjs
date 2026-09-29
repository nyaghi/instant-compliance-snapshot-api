/* Candidate collector against observed public DOM shapes, with timed renders.
   This does not load the extension or control a live browser. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const original=fs.readFileSync(path.join(__dirname,'../browser-connector/registry-content.js'),'utf8');
const source=original.replace('  async function handle(m) {','  globalThis.testNV = {nvPage,nvFields,nvChanged,nvSearch,nvDetail,registryDocumentReady};\n  async function handle(m) {');
const headers=['Entity Name','NV Business Id #','Entity No.','Entity Type','Registered Agent Name','Formation Date','Status'];
const observed=[
 ['MAKE-A-WISH FOUNDATION OF AMERICA','NV19931054903','C6989-1993','Foreign Non-Profit Corporation (80)','C T CORPORATION SYSTEM**','06/16/1993 12:00 AM','Permanently Revoked'],
 ['MAKE-A-WISH FOUNDATION OF AMERICA','NV20121738342','E0634302012-0','Foreign Non-Profit Corporation (80)','REGISTERED AGENT SOLUTIONS, INC.*','12/10/2012 09:44 AM','Active'],
 ['MAKE-A-WISH FOUNDATION OF NORTHERN NEVADA, INC.','NV19821011791','C6552-1982','Domestic Non-Profit Corporation (82)','ALLISON MACKENZIE, LTD.','11/05/1982 12:00 AM','Dissolved'],
 ['MAKE-A-WISH NEVADA','NV19961252237','C26637-1996','Domestic Non-Profit Corporation (82)','Walls Law Firm','12/27/1996 12:00 AM','Active']
];
test('Nevada document readiness waits for the business form after the page shell loads',()=>{
 const h=fixture(),read=h.context.document.querySelector;
 h.context.document.querySelector=()=>null;assert.equal(h.api.registryDocumentReady(),false);
 h.context.document.querySelector=read;assert.equal(h.api.registryDocumentReady(),true);
 h.context.document.readyState='loading';assert.equal(h.api.registryDocumentReady(),false);
});
test('Nevada form readiness includes the hydrated Starts With search-type control',()=>{
 const h=fixture(),read=h.context.document.querySelectorAll;
 h.context.document.querySelectorAll=q=>q==='[role="combobox"]'?[]:read(q);
 assert.equal(h.api.registryDocumentReady(),false);
 h.context.document.querySelectorAll=read;assert.equal(h.api.registryDocumentReady(),true);
});
test('Nevada visible inputs and search type are not ready while the initial loader remains visible',()=>{
 const h=fixture(),read=h.context.document.querySelectorAll;
 h.context.document.querySelectorAll=q=>q==='.app-loader-pane .circle-loader'?[{getClientRects:()=>[{}]}]:read(q);
 assert.equal(h.api.registryDocumentReady(),false);
 h.context.document.querySelectorAll=read;assert.equal(h.api.registryDocumentReady(),true);
});
function fixture({rows=observed,activity=true,responseDelay=100,timerClamp=0,truncate=false,duplicate=false,oldPageDelay=80,detailId=null,returnFormDelay=600,returnName=null,returnRows=null,repeatSearchActivity=true,replaceSearchOnInput=false,returnGridDelay=0}={}) {
 let clock=1000,serial=0,listener,loading=false,rendered=[],page=1,detail=false,searchClicks=0,opened=[],formReady=true;
 const tasks=new Map(),observers=new Set(),root={};
 const schedule=(fn,ms)=>{let id=++serial;tasks.set(id,{at:clock+ms,fn});return id;};
 const node=selector=>({nodeType:1,matches:s=>s.split(',').map(x=>x.trim()).includes(selector),querySelector:()=>null,closest:s=>s.includes(selector)?{}:null});
 const gridTarget=node('casex-data-table'),loader=node('.circle-loader');
 const mutate=(target=gridTarget,addedNodes=[],removedNodes=[])=>{for(const o of [...observers])o.fn([{type:'childList',target,addedNodes,removedNodes}]);};
 const render=()=>{rendered=rows.slice((page-1)*2,page*2);if(duplicate&&page===2)rendered=rows.slice(0,2);loading=false;mutate(gridTarget,[],[loader]);};
 const begin=()=>{if(!activity)return;loading=true;mutate(root,[loader]);schedule(render,responseDelay);};
 let buttonCurrent=true,staleClicks=0;
 class Input {get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){if(replaceSearchOnInput){buttonCurrent=false;schedule(()=>{buttonCurrent=true;mutate();},100);}}}
 const inputs=Object.fromEntries(['entityName','entityNumber','nvBusinessId'].map(k=>[k,new Input()]));
 const searchButton={innerText:'Search',getClientRects:()=>[{}],disabled:false,click:()=>{page=1;searchClicks++;if(searchClicks===1||repeatSearchActivity)begin();}};
 const staleButton={...searchButton,click:()=>staleClicks++};
 const textEl=innerText=>({innerText});
 const backButton={innerText:'Return To Results',getClientRects:()=>[{}],click:()=>{
  detail=false;formReady=false;context.location.hash='screen=external-GenericFilingsSearch&tabRoute=business';mutate();
  if(returnGridDelay){rendered=[];schedule(render,returnGridDelay);}
  schedule(()=>{formReady=true;if(returnName!==null)inputs.entityName.value=returnName;if(returnRows)rendered=returnRows;mutate();},returnFormDelay);
 }};
 const fieldValues={'Entity Name':observed[1][0],'NV Business ID':detailId||observed[1][1],'Entity Status':'Active','Entity Type':observed[1][3],FEIN:'-',
  'Solicits Charitable Contribution?':'No','IRS Registered Name':'-','Campaign Name':'-','Formation Date in Nevada':'12/10/2012',
  'Annual Renewal Due Date/Expiration Date':'12/31/2026'};
 const paragraphs=()=>[...Object.entries(fieldValues).map(([label,value])=>({tagName:'P',querySelector:q=>q==='strong'?textEl(label):null,nextElementSibling:{tagName:'P',innerText:value}})),
  {tagName:'H4',innerText:'Agent Information'},
  {tagName:'P',querySelector:()=>textEl('NV Business ID'),nextElementSibling:{tagName:'P',innerText:'AGENT-ID'}},
  {tagName:'P',querySelector:()=>textEl('Entity Status'),nextElementSibling:{tagName:'P',innerText:'Inactive'}}];
 const form={querySelectorAll:q=>q==='h4'?[textEl('Entity Information'),textEl('Agent Information')]:paragraphs()};
 const grid={getAttribute:k=>k==='aria-rowcount'?String(rendered.length+1):null,
  querySelector:q=>q==='.k-grid-norecords'&&!rendered.length?{}:null,
  querySelectorAll:q=>{
   if(q==='[role="columnheader"]')return headers.map(h=>({getAttribute:k=>k==='aria-label'?h:null}));
   if(q==='tbody > tr[role="row"]')return rendered.map(cells=>{
    const tr={get isConnected(){return !detail;},querySelectorAll:q=>q==='[role="gridcell"]'?cells.map(v=>({innerText:v,querySelector:()=>textEl(': '+v)})):[]};
    tr.querySelector=q=>q==='[role="gridcell"]'?{}:q==='[role="gridcell"] a'?{innerText:cells[0],click:()=>{opened.push(cells[1]);detail=true;fieldValues['NV Business ID']=detailId||cells[1];fieldValues['Entity Status']=cells[6];context.location.hash='screen=Manage-Business&id=fixture';schedule(()=>mutate(),10);}}:null;
    return tr;
   });
   throw Error('Unexpected grid selector '+q);
  }};
 const pager={getAttribute:k=>k==='aria-label'?`Page ${page} of ${Math.max(1,Math.ceil(rows.length/2))}`:null};
 const table={querySelectorAll:q=>q==='h4'?[textEl('Search Results')]:[],querySelector:q=>{
  if(q==='[role="grid"]')return grid;
  if(q==='kendo-datapager')return rendered.length?pager:null;
  if(q==='kendo-datapager-info')return textEl(`${(page-1)*2+1} - ${Math.min(page*2,rows.length)} of ${rows.length} items`);
  if(q==='button[aria-label="Go to the next page"]')return {disabled:truncate,getAttribute:()=>truncate?'true':'false',click:()=>{
   page++;mutate();schedule(()=>{rendered=rows.slice((page-1)*2,page*2);if(duplicate)rendered=rows.slice(0,2);mutate();},oldPageDelay);
  }};
  if(q==='button[aria-label="Go to the previous page"]')return {disabled:false,click:()=>{page--;schedule(render,oldPageDelay);}};
  return null;
 }};
 const doc={documentElement:root,readyState:'complete',querySelectorAll:q=>{
  if(q==='casex-data-table')return detail?[]:[table];
  if(q==='[role="tab"]')return [{innerText:'Business',getAttribute:()=> 'true'}];
  if(q==='[role="combobox"]')return !detail&&formReady?[textEl('Starts With')]:[textEl('STARTS_WITH')];
  if(q==='button')return detail?[backButton]:[buttonCurrent?searchButton:staleButton];
  if(q==='.app-loader-pane .circle-loader')return loading?[{getClientRects:()=>[{}]}]:[];
  if(q==='[role="form"]')return detail?[form]:[];
  throw Error('Unexpected document selector '+q);
 },querySelector:q=>!detail&&q.startsWith('input[id$=')?inputs[q.match(/-([A-Za-z]+)"/)[1]]:null};
 const win={};win.top=win;
 const context={window:win,document:doc,location:{origin:'https://orion.nv.gov',hash:'screen=external-GenericFilingsSearch&tabRoute=business',href:'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=d1b62c76-d5af-4ff3-b07d-038b7fa8d854'},
  Date:{now:()=>clock},crypto:{randomUUID:()=> 'fixture'},HTMLInputElement:Input,HTMLSelectElement:class{},Event:class{},
  MutationObserver:class{constructor(fn){this.fn=fn;}observe(){observers.add(this);}disconnect(){observers.delete(this);}},
  setTimeout:(fn,ms)=>schedule(fn,Math.max(ms,timerClamp)),clearTimeout:id=>tasks.delete(id),
  chrome:{runtime:{id:'test-extension',onMessage:{addListener:fn=>listener=fn}}}};
 vm.createContext(context);vm.runInContext(source,context);
 async function drive(promise) {
  let done=false,value,error;promise.then(v=>{value=v;done=true;},e=>{error=e;done=true;});
  for(let n=0;!done&&n<1000;n++) {
   for(let i=0;i<15;i++)await Promise.resolve();
   if(done)break;
   const next=[...tasks].sort((a,b)=>a[1].at-b[1].at)[0];assert.ok(next,'pending collector has event');tasks.delete(next[0]);clock=next[1].at;next[1].fn();
  }
  assert.ok(done);assert.equal(observers.size,0);if(error)throw error;return value;
 }
 return {context,drive,api:context.testNV,get opened(){return opened;},get clicks(){return searchClicks;},get staleClicks(){return staleClicks;},get time(){return clock;},
  search:()=>drive(context.testNV.nvSearch({state:'NV',operation:'search',name:'MAKE-A-WISH'},clock+45000)),
  detail:()=>{detail=true;context.location.hash='screen=Manage-Business&id=fixture';return context.testNV.nvFields('NV20121738342');},fieldValues,grid};
}

test('Nevada collects both national records and local chapters without choosing one',async()=>{
 const f=fixture();const r=await f.search();assert.equal(r.total,4);assert.deepEqual(Array.from(r.rows,x=>x.identifier),observed.map(x=>x[1]));
 assert.equal(f.clicks,1);assert.ok(r.rows.every(r=>!('detail_url' in r)&&!('address' in r)));assert.equal(r.verification_pending,false);
});

test('Nevada waits for Search replacement caused by filter input rendering',async()=>{
 const f=fixture({replaceSearchOnInput:true});const result=await f.search();
 assert.equal(result.total,4);assert.equal(f.clicks,1);assert.equal(f.staleClicks,0);
});
test('initial empty grid cannot establish non-registration without a response',async()=>{const f=fixture({activity:false,rows:[]});await assert.rejects(f.search(),/SEARCH_NOT_STARTED/);});
test('completed empty response is accepted only after observed loading cycle',async()=>{const f=fixture({rows:[]});const r=await f.search();assert.equal(r.total,0);assert.equal(r.complete,true);});
test('truncated pagination cannot become a partial positive or negative',async()=>{const f=fixture({truncate:true});await assert.rejects(f.search(),/PAGINATION_INCOMPLETE/);});
test('pager changing before rows does not repeat the previous page',async()=>{const f=fixture({oldPageDelay:600});const r=await f.search();assert.equal(r.total,4);assert.ok(f.time>=1700);});
test('repeated rows across pages cannot pass as complete results',async()=>{const f=fixture({duplicate:true});await assert.rejects(f.search(),/RESPONSE_INCOMPLETE|RESULTS_INCOMPLETE/);});
test('late source response is rejected against its original command budget',async()=>{const f=fixture({responseDelay:40000});await assert.rejects(f.search(),/RESPONSE_PENDING/);});
test('zero-result response observed only after timer throttling is not invented',async()=>{const f=fixture({activity:false,timerClamp:60000,rows:[]});await assert.rejects(f.search(),/SEARCH_NOT_STARTED/);});
test('wrong column schema is incomplete',async()=>{const f=fixture();const prior=f.grid.querySelectorAll;f.grid.querySelectorAll=q=>q==='[role="columnheader"]'?[]:prior(q);await assert.rejects(f.search(),/COLUMNS_CHANGED/);});
test('Nevada extracts corporation fields and stops before registered-agent duplicates',()=>{const f=fixture();const fields=f.detail();assert.equal(fields['NV Business ID'],'NV20121738342');assert.equal(fields['Entity Status'],'Active');assert.equal(fields['Annual Renewal Due Date/Expiration Date'],'12/31/2026');assert.ok(!('Street Address' in fields));});
test('wrong detail business ID cannot be accepted',()=>{assert.equal(fixture({detailId:'NV19931054903'}).detail(),null);});
test('unobserved business ID cannot trigger a guessed navigation',async()=>{const f=fixture();await assert.rejects(f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:'NV999'},45000)),/NOT_OBSERVED/);assert.equal(f.opened.length,0);});
test('detail opens the requested business ID after returning to its result page',async()=>{
 const f=fixture();await f.search();const r=await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:'NV20121738342'},45000));
 assert.deepEqual(f.opened,['NV20121738342']);assert.equal(r.fields['Entity Status'],'Active');assert.equal(r.complete,true);
 assert.equal(r.filings.complete,false,'optional unavailable history leaves core detail intact');
});
test('opened detail with a different business ID never returns completed evidence',async()=>{
 const f=fixture({detailId:'NV999'});await f.search();await assert.rejects(f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:'NV20121738342'},45000)),/RESPONSE_INCOMPLETE/);
});

test('Nevada waits for search type after returning from one matching detail to another',async()=>{
 const f=fixture({rows:observed.slice(0,2)});await f.search();
 const old=await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[0][1]},45000));
 assert.equal(old.fields['Entity Status'],'Permanently Revoked');const started=f.time;
 const current=await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[1][1]},45000));
 assert.equal(current.fields['NV Business ID'],observed[1][1]);assert.equal(current.fields['Entity Status'],'Active');
 assert.equal(f.clicks,1);assert.ok(f.time-started>=600);assert.deepEqual(f.opened,[observed[0][1],observed[1][1]]);
});

test('Nevada reuses a verified restored result set without requiring another loading cycle',async()=>{
 const f=fixture({rows:observed.slice(0,2),repeatSearchActivity:false});await f.search();
 await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[0][1]},45000));
 const result=await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[1][1]},45000));
 assert.equal(result.fields['NV Business ID'],observed[1][1]);assert.equal(f.clicks,1);
});

test('Nevada restores all pages and locates the second identity after returning from a detail',async()=>{
 const f=fixture({repeatSearchActivity:false});await f.search();
 await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[0][1]},45000));
 const result=await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[1][1]},45000));
 assert.equal(result.fields['NV Business ID'],observed[1][1]);assert.equal(f.clicks,1);
 assert.deepEqual(f.opened,[observed[0][1],observed[1][1]]);
});

test('Nevada waits for restored rows after the form is ready without issuing a new search',async()=>{
 const f=fixture({rows:observed.slice(0,2),returnGridDelay:1200,repeatSearchActivity:false});await f.search();
 await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[0][1]},45000));
 const started=f.time,result=await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[1][1]},45000));
 assert.equal(result.fields['NV Business ID'],observed[1][1]);assert.ok(f.time-started>=1200);assert.equal(f.clicks,1);
});

test('Nevada refuses a restored result list for a changed search name',async()=>{
 const f=fixture({rows:observed.slice(0,2),returnName:'OTHER ORGANIZATION'});await f.search();
 await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[0][1]},45000));
 await assert.rejects(f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[1][1]},45000)),/RESTORED_QUERY_CHANGED/);
 assert.equal(f.clicks,1);assert.deepEqual(f.opened,[observed[0][1]]);
});

test('Nevada refuses changed identities or statuses in the restored result list',async()=>{
 for(const column of [0,1,3,6]) {
  const replacement=observed.slice(0,2).map(r=>[...r]);replacement[1][column]='CHANGED';
  const f=fixture({rows:observed.slice(0,2),returnRows:replacement});await f.search();
  await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[0][1]},45000));
  await assert.rejects(f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[1][1]},45000)),/RESTORED_RESULTS_CHANGED/);
  assert.equal(f.clicks,1);assert.deepEqual(f.opened,[observed[0][1]]);
 }
});

test('Nevada does not search a partially mounted return form beyond its command budget',async()=>{
 const f=fixture({rows:observed.slice(0,2),returnFormDelay:60000});await f.search();
 await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[0][1]},45000));
 await assert.rejects(f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[1][1]},f.time+1000)),/RESPONSE_INCOMPLETE/);
 assert.equal(f.clicks,1);
});
test('extra search filters are refused rather than narrowing the search invisibly',async()=>{const f=fixture();await assert.rejects(f.drive(f.api.nvSearch({state:'NV',operation:'search',name:'MAKE-A-WISH',status:'Active'},45000)),/COMMAND_INVALID/);assert.equal(f.clicks,0);});
test('candidate Nevada access remains absent from the approved connector manifest',()=>{const m=JSON.parse(fs.readFileSync(path.join(__dirname,'../browser-connector/manifest.json'),'utf8'));assert.equal(m.version,'0.5.10');assert.ok(!JSON.stringify(m).includes('orion.nv.gov'));});
