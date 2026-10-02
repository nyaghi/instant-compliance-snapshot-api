/* Candidate collector against observed public DOM shapes, with timed renders.
   This does not load the extension or control a live browser. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const original=fs.readFileSync(process.env.CC_TEST_TRIAL_DIR?path.join(process.env.CC_TEST_TRIAL_DIR,'registry-content.js'):path.join(__dirname,'../browser-connector/registry-content.js'),'utf8');
const source=original.replace('  async function handle(m) {','  globalThis.testNV = {nvPage,nvPages,nvFields,nvReservationFields,nvChanged,nvSearch,nvDetail,nvReturnSearch,registryDocumentReady,handle};\n  async function handle(m) {');

test('Nevada detail and transitional routes are not ready public search forms',()=>{
 const h=fixture();
 for(const hash of ['screen=NameReservationDetails&id=fixture','screen=Manage-Business&id=fixture',
   'screen=ExistingBusinessFilings','screen=external-GenericFilingsSearch&tabRoute=agent','']) {
  h.context.location.hash=hash;
  assert.equal(h.api.registryDocumentReady(),false,hash);
 }
});
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

test('Nevada accepts a restored STARTS_WITH label only with the selected public choice identity',async()=>{
 const h=fixture(),read=h.context.document.querySelectorAll;
 const selected={getAttribute:k=>k==='data-value'?'STARTS_WITH':null,querySelector:()=>({})};
 const raw={innerText:'STARTS_WITH\nRemove item',querySelector:()=>selected};
 h.context.document.querySelectorAll=q=>q==='[role="combobox"]'?[raw]:read(q);
 assert.equal(h.api.registryDocumentReady(),true);
 const result=await h.search();assert.equal(result.total,4);assert.equal(h.clicks,1);
 raw.querySelector=()=>null;assert.equal(h.api.registryDocumentReady(),false);
 raw.querySelector=()=>({...selected,getAttribute:()=> 'CONTAINS'});assert.equal(h.api.registryDocumentReady(),false);
 raw.querySelector=()=>({...selected,querySelector:()=>null});assert.equal(h.api.registryDocumentReady(),false);
});
test('Nevada visible inputs and search type are not ready while the initial loader remains visible',()=>{
 const h=fixture(),read=h.context.document.querySelectorAll;
 h.context.document.querySelectorAll=q=>q==='.app-loader-pane .circle-loader'?[{getClientRects:()=>[{}]}]:read(q);
 assert.equal(h.api.registryDocumentReady(),false);
 h.context.document.querySelectorAll=read;assert.equal(h.api.registryDocumentReady(),true);
});
function fixture({rows=observed,activity=true,responseDelay=100,timerClamp=0,truncate=false,duplicate=false,oldPageDelay=80,detailId=null,returnFormDelay=600,returnName=null,returnRows=null,returnAttribute=null,repeatSearchActivity=true,replaceSearchOnInput=false,returnGridDelay=0,unrelatedMutations=false,ignoredSearches=0,changedQueryBeforeRetry=false,pageSizeControl=false,initialPageSize=2,pagingMissing=0,resizeIgnored=false,resizeTotalDrift=false,reservation=false,exactRows=null,ignoreModeChange=false}={}) {
 let clock=1000,serial=0,listener,loading=false,rendered=[],page=1,detail=false,searchClicks=0,opened=[],formReady=true,returnResultsClicks=0,returnSearchClicks=0;
 let pageSize=initialPageSize,sizeMenu=false,resizeClicks=0;
 const broadRows=rows;let searchMode='STARTS_WITH',modeMenu=false,modeClicks=0,pagingClicks=0;
 const tasks=new Map(),observers=new Set(),root={};
 const schedule=(fn,ms)=>{let id=++serial;tasks.set(id,{at:clock+ms,fn});return id;};
 const node=selector=>({nodeType:1,matches:s=>s.split(',').map(x=>x.trim()).includes(selector),querySelector:()=>null,closest:s=>s.includes(selector)?{}:null});
 const gridTarget=node('casex-data-table'),loader=node('.circle-loader');
 const mutate=(target=gridTarget,addedNodes=[],removedNodes=[])=>{for(const o of [...observers])o.fn([{type:'childList',target,addedNodes,removedNodes}]);};
 if(unrelatedMutations)for(let ms=50;ms<=4000;ms+=50)schedule(()=>mutate(root),ms);
 const render=()=>{rendered=rows.slice((page-1)*pageSize,page*pageSize);if(duplicate&&page===2)rendered=rows.slice(0,pageSize);if(pagingMissing&&page>1)rendered=rendered.slice(0,-pagingMissing);loading=false;mutate(gridTarget,[],[loader]);};
 const begin=()=>{if(!activity)return;loading=true;mutate(root,[loader]);schedule(render,responseDelay);};
 let buttonCurrent=true,staleClicks=0;
 class Input {get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){if(replaceSearchOnInput){buttonCurrent=false;schedule(()=>{buttonCurrent=true;mutate();},100);}}}
 const inputs=Object.fromEntries(['entityName','entityNumber','nvBusinessId'].map(k=>[k,new Input()]));
 const searchButton={innerText:'Search',getClientRects:()=>[{}],disabled:false,click:()=>{
  page=1;searchClicks++;rows=searchMode==='EXACT_MATCH'?(exactRows||[]):broadRows;
  if(changedQueryBeforeRetry&&searchClicks===1)schedule(()=>{inputs.entityName.value='OTHER ENTITY';mutate();},1000);
  if(searchClicks>ignoredSearches&&(searchClicks===1||repeatSearchActivity))begin();
 }};
 const staleButton={...searchButton,click:()=>staleClicks++};
 const textEl=innerText=>({innerText});
 const searchCombo={get innerText(){return searchMode==='EXACT_MATCH'?'Exact Match':'Starts With';},
  querySelector:q=>q==='select[name="data[searchType]"]'?{}:null,
  click:()=>{modeMenu=true;mutate();},querySelectorAll:q=>q==='[role="option"]'?['STARTS_WITH','EXACT_MATCH'].map(mode=>({
    textContent:mode==='EXACT_MATCH'?'Exact Match':'Starts With',
    getAttribute:k=>k==='data-value'?mode:null,getClientRects:()=>modeMenu?[{}]:[],click:()=>{modeMenu=!modeMenu;mutate();},
    dispatchEvent:event=>{
      if(event.type!=='mousedown'||!event.bubbles||event.button!==0)return;
      modeClicks++;modeMenu=false;if(!ignoreModeChange)searchMode=mode;mutate();
    }})):[]};
 const backButton={innerText:'Return To Results',getClientRects:()=>[{}],click:()=>{
  detail=false;formReady=false;context.location.hash='screen=external-GenericFilingsSearch&tabRoute=business';mutate();
  if(returnGridDelay){rendered=[];schedule(render,returnGridDelay);}
  schedule(()=>{formReady=true;if(returnName!==null)inputs.entityName.value=returnName;if(returnRows)rendered=returnRows;
   if(returnAttribute){for(const o of [...observers])if(o.options.attributes&&(!o.options.attributeFilter||o.options.attributeFilter.includes(returnAttribute)))o.fn([{type:'attributes',attributeName:returnAttribute,target:root}]);}
   else mutate();},returnFormDelay);
 }};
 const returnSearchButton={...backButton,innerText:'Return To Search',click:()=>{returnSearchClicks++;backButton.click();}};
 const originalBackClick=backButton.click;backButton.click=()=>{returnResultsClicks++;originalBackClick();};
 const fieldValues={'Entity Name':observed[1][0],'NV Business ID':detailId||observed[1][1],'Entity Status':'Active','Entity Type':observed[1][3],FEIN:'-',
  'Solicits Charitable Contribution?':'No','IRS Registered Name':'-','Campaign Name':'-','Formation Date in Nevada':'12/10/2012',
  'Annual Renewal Due Date/Expiration Date':'12/31/2026'};
 const paragraphs=()=>[...Object.entries(fieldValues).map(([label,value])=>({tagName:'P',querySelector:q=>q==='strong'?textEl(label):null,nextElementSibling:{tagName:'P',innerText:value}})),
  {tagName:'H4',innerText:'Agent Information'},
  {tagName:'P',querySelector:()=>textEl('NV Business ID'),nextElementSibling:{tagName:'P',innerText:'AGENT-ID'}},
  {tagName:'P',querySelector:()=>textEl('Entity Status'),nextElementSibling:{tagName:'P',innerText:'Inactive'}}];
 const reservationFields={'Reserved Name':rows[0]?.[0]||'','Entity Number':rows[0]?.[1]||'','Status':'Expired','Formation Date':'02/04/2019','Expiration Date':''};
 const form={querySelectorAll:q=>reservation?(q==='h4'?[textEl('Name Reservation Information'),textEl('Linked Entity Information')]:[
  ...Object.entries(reservationFields).map(([label,value])=>({tagName:'P',querySelector:s=>s==='strong'?textEl(label):null,nextElementSibling:{tagName:'P',innerText:value}})),
  {tagName:'H4',innerText:'Linked Entity Information'},{tagName:'P',innerText:'This name reservation has not been linked to a business'},
  {tagName:'H4',innerText:'Filing Information'}]):q==='h4'?[textEl('Entity Information'),textEl('Agent Information')]:paragraphs()};
 const grid={getAttribute:k=>k==='aria-rowcount'?String(rendered.length+1):null,
  querySelector:q=>q==='.k-grid-norecords'&&!rendered.length?{}:null,
  querySelectorAll:q=>{
   if(q==='[role="columnheader"]')return headers.map(h=>({getAttribute:k=>k==='aria-label'?h:null}));
   if(q==='tbody > tr[role="row"]')return rendered.map(cells=>{
    const tr={get isConnected(){return !detail && rendered.includes(cells);},querySelectorAll:q=>q==='[role="gridcell"]'?cells.map(v=>({innerText:v,querySelector:()=>textEl(': '+v)})):[]};
    tr.querySelector=q=>q==='[role="gridcell"]'?{}:q==='[role="gridcell"] a'?{innerText:cells[0],click:()=>{opened.push(cells[1]);detail=true;fieldValues['NV Business ID']=detailId||cells[1];fieldValues['Entity Status']=cells[6];context.location.hash='screen='+(reservation?'NameReservationDetails':'Manage-Business')+'&id=fixture';schedule(()=>mutate(),10);}}:null;
    return tr;
   });
   throw Error('Unexpected grid selector '+q);
  }};
 const pager={getAttribute:k=>k==='aria-label'?`Page ${page} of ${Math.max(1,Math.ceil(rows.length/pageSize))}`:null};
 const sizeCombo={getClientRects:()=>[{}],querySelector:q=>q==='.k-input-value-text'?textEl(String(pageSize)):null,
  getAttribute:k=>k==='aria-controls'&&sizeMenu?'page-sizes':null,click:()=>{sizeMenu=true;mutate();}};
 const sizeOptions={getClientRects:()=>sizeMenu?[{}]:[],getAttribute:k=>k==='role'?'listbox':null,
  querySelectorAll:q=>q==='[role="option"]'?[25,50,100].map(n=>({innerText:String(n),getClientRects:()=>[{}],click:()=>{
   resizeClicks++;sizeMenu=false;if(resizeIgnored)return;page=1;pageSize=n;schedule(render,responseDelay);
  }})):[]};
 const table={querySelectorAll:q=>q==='h4'?[textEl('Search Results')]:[],querySelector:q=>{
  if(q==='[role="grid"]')return grid;
  if(q==='kendo-datapager')return rendered.length?pager:null;
  if(q==='kendo-datapager-info')return textEl(`${(page-1)*pageSize+1} - ${(page-1)*pageSize+rendered.length} of ${rows.length+(resizeTotalDrift&&resizeClicks?1:0)} items`);
  if(q==='kendo-datapager [role="combobox"][aria-label="items per page"]')return pageSizeControl?sizeCombo:null;
  if(q==='button[aria-label="Go to the next page"]')return {disabled:truncate,getAttribute:()=>truncate?'true':'false',click:()=>{
   page++;pagingClicks++;mutate();schedule(render,oldPageDelay);
  }};
  if(q==='button[aria-label="Go to the previous page"]')return {disabled:false,click:()=>{page--;schedule(render,oldPageDelay);}};
  return null;
 }};
 const doc={documentElement:root,readyState:'complete',getElementById:id=>id==='page-sizes'&&sizeMenu?sizeOptions:null,querySelectorAll:q=>{
  if(q==='casex-data-table')return detail?[]:[table];
  if(q==='[role="tab"]')return [{innerText:'Business',getAttribute:()=> 'true'}];
  if(q==='[role="combobox"]')return !detail&&formReady?[searchCombo]:[textEl('STARTS_WITH')];
  if(q==='button')return detail?(reservation?[{...backButton,innerText:'Back'}]:[backButton,returnSearchButton]):[buttonCurrent?searchButton:staleButton];
  if(q==='.app-loader-pane .circle-loader')return loading?[{getClientRects:()=>[{}]}]:[];
  if(q==='[role="form"]')return detail?[form]:[];
  throw Error('Unexpected document selector '+q);
 },querySelector:q=>!detail&&q.startsWith('input[id$=')?inputs[q.match(/-([A-Za-z]+)"/)[1]]:null};
 const win={};win.top=win;
 const context={window:win,document:doc,location:{origin:'https://orion.nv.gov',hash:'screen=external-GenericFilingsSearch&tabRoute=business',href:'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=d1b62c76-d5af-4ff3-b07d-038b7fa8d854'},
  Date:{now:()=>clock},crypto:{randomUUID:()=> 'fixture'},HTMLInputElement:Input,HTMLSelectElement:class{},Event:class{},
  MouseEvent:class{constructor(type,options){this.type=type;Object.assign(this,options);}},
  MutationObserver:class{constructor(fn){this.fn=fn;}observe(root,options){this.options=options;observers.add(this);}disconnect(){observers.delete(this);}},
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
 return {context,drive,api:context.testNV,get opened(){return opened;},get clicks(){return searchClicks;},get returnResultsClicks(){return returnResultsClicks;},get returnSearchClicks(){return returnSearchClicks;},get modeClicks(){return modeClicks;},get modeMenuOpen(){return modeMenu;},get pagingClicks(){return pagingClicks;},get mode(){return searchMode;},get resizeClicks(){return resizeClicks;},get pageSize(){return pageSize;},get staleClicks(){return staleClicks;},get time(){return clock;},
  search:(budget=45000)=>drive(context.testNV.nvSearch({state:'NV',operation:'search',name:'MAKE-A-WISH'},clock+budget)),
  detail:()=>{detail=true;context.location.hash='screen=Manage-Business&id=fixture';return context.testNV.nvFields('NV20121738342');},fieldValues,reservationFields,grid};
}

test('Nevada opens an observed matching reservation, binds its identity and returns using Back',async()=>{
 const row=['CCA','C20190204-2019','C20190204-2019','','','','Expired'];
 const h=fixture({rows:[row],reservation:true});await h.search();
 const result=await h.drive(h.api.nvDetail({state:'NV',operation:'detail',identifier:row[1]},h.time+45000));
 assert.equal(result.fields['Entity Number'],row[1]);assert.equal(result.fields['Reserved Name'],'CCA');
 assert.equal(result.fields['Linked Entity Information'],'This name reservation has not been linked to a business');
 assert.ok(!('filings' in result));assert.equal(h.opened.length,1);
 await h.drive(h.api.nvReturnSearch(h.time+10000));assert.equal(h.api.registryDocumentReady(),true);
});

test('Nevada never reads a reservation as corporate status or accepts a changed reservation identity',async()=>{
 const row=['Example Charity','NR20230725-22746','NR20230725-22746','','','','Expired'];
 const h=fixture({rows:[row],reservation:true});await h.search();
 h.reservationFields['Entity Number']='C20190204-2019';
 await assert.rejects(h.drive(h.api.nvDetail({state:'NV',operation:'detail',identifier:row[1]},h.time+3000)),/REGISTRY_RESPONSE_INCOMPLETE/);
 assert.equal(h.api.nvFields(row[1]),null);
});

function manyPublicRows(n){return Array.from({length:n},(_,i)=>['Example Chapter '+i,'NV'+String(20000000+i),'E123456789-0','Foreign Non-Profit Corporation (80)','','01/01/2020','Active']);}

const adaptiveQuery={state:'NV',operation:'search',name:'Example',exact_above:20};
test('master-authorized broad Nevada query switches to Exact Match before paging and binds five complete rows',async()=>{
 const h=fixture({rows:manyPublicRows(5463),exactRows:manyPublicRows(5),initialPageSize:25});
 const result=await h.drive(h.api.nvSearch(adaptiveQuery,h.time+45000));
 assert.equal(result.total,5);assert.equal(result.broad_total,5463);assert.equal(result.search_mode,'EXACT_MATCH');
 assert.deepEqual(JSON.parse(JSON.stringify(result.query)),adaptiveQuery);assert.equal(h.clicks,2);assert.equal(h.modeClicks,1);assert.equal(h.pagingClicks,0);
 assert.equal(h.api.registryDocumentReady(),true);
});
test('Nevada changes the public mode without opening or reopening the animated menu',async()=>{
 const h=fixture({rows:manyPublicRows(21),exactRows:[],initialPageSize:25});
 const combo=h.context.document.querySelectorAll('[role="combobox"]')[0];
 combo.click=()=>{throw Error('Opening the menu is unnecessary');};
 await h.drive(h.api.nvSearch(adaptiveQuery,h.time+45000));
 assert.equal(h.mode,'EXACT_MATCH');assert.equal(h.modeMenuOpen,false);
 await h.search();assert.equal(h.mode,'STARTS_WITH');assert.equal(h.modeMenuOpen,false);
});
test('Nevada refuses a mode option with a changed public label or disabled state',async()=>{
 for(const changed of ['label','disabled']){
  const h=fixture({rows:manyPublicRows(21),exactRows:[],initialPageSize:25});
  const combo=h.context.document.querySelectorAll('[role="combobox"]')[0],read=combo.querySelectorAll;
  combo.querySelectorAll=q=>read(q).map(option=>option.getAttribute('data-value')!=='EXACT_MATCH'?option:{...option,
   textContent:changed==='label'?'Different mode':option.textContent,
   getAttribute:k=>changed==='disabled'&&k==='aria-disabled'?'true':option.getAttribute(k)});
  await assert.rejects(h.drive(h.api.nvSearch(adaptiveQuery,h.time+45000)),/MODE_MENU_INCOMPLETE/);
  assert.equal(h.mode,'STARTS_WITH');assert.equal(h.clicks,1);
 }
});
test('Nevada small result set stays Starts With and an ordinary command is never narrowed',async()=>{
 for(const size of [0,5,20]){
  const h=fixture({rows:manyPublicRows(size),initialPageSize:25});
  const r=await h.drive(h.api.nvSearch(adaptiveQuery,h.time+45000));
  assert.equal(r.total,size);assert.equal(r.search_mode,'STARTS_WITH');assert.equal(r.broad_total,null);assert.equal(h.clicks,1);assert.equal(h.modeClicks,0);
 }
 const h=fixture({rows:manyPublicRows(21),initialPageSize:25});assert.equal((await h.search()).total,21);assert.equal(h.modeClicks,0);
});
test('a second Nevada search explicitly resets Exact Match to Starts With before evaluating its threshold',async()=>{
 const h=fixture({rows:manyPublicRows(21),exactRows:[],initialPageSize:25});
 const r=await h.drive(h.api.nvSearch(adaptiveQuery,h.time+45000));assert.equal(r.total,0);assert.equal(r.search_mode,'EXACT_MATCH');
 const ordinary=await h.search();assert.equal(ordinary.total,21);assert.equal(h.mode,'STARTS_WITH');assert.equal(h.modeClicks,2);
});
test('ignored Exact Match selection or absent fresh response is incomplete, never an empty successful result',async()=>{
 for(const opts of [{ignoreModeChange:true},{repeatSearchActivity:false}]){
  const h=fixture({rows:manyPublicRows(21),exactRows:[],initialPageSize:25,...opts});
  await assert.rejects(h.drive(h.api.nvSearch(adaptiveQuery,h.time+10000)),opts.ignoreModeChange?/MODE_NOT_SELECTED/:/NOT_STARTED/);
 }
});
test('exact-match detail navigation preserves the selected mode and only opens observed record identities',async()=>{
 const h=fixture({rows:manyPublicRows(21),exactRows:observed.slice(0,2),initialPageSize:25});
 await h.drive(h.api.nvSearch(adaptiveQuery,h.time+45000));
 await h.drive(h.api.nvDetail({state:'NV',operation:'detail',identifier:observed[0][1]},h.time+45000));
 await h.drive(h.api.nvDetail({state:'NV',operation:'detail',identifier:observed[1][1]},h.time+45000));
 assert.equal(h.mode,'EXACT_MATCH');assert.deepEqual(h.opened,observed.slice(0,2).map(r=>r[1]));assert.equal(h.clicks,2);
});
test('Nevada exact narrowing accepts only the master-approved twenty-record threshold',async()=>{
 for(const exact_above of [0,10,21,'20',null]){
  const h=fixture();await assert.rejects(h.drive(h.api.nvSearch({...adaptiveQuery,exact_above},h.time+45000)),/COMMAND_INVALID/);assert.equal(h.clicks,0);
 }
});

test('Nevada opens a first-page reservation after collecting a 160-row two-page search',async()=>{
 const rows=manyPublicRows(160);rows[0]=['CCA','C20190204-2019','C20190204-2019','','','','Expired'];
 const h=fixture({rows,reservation:true,initialPageSize:25,pageSizeControl:true});
 const search=await h.search();assert.equal(search.total,160);
 const detail=await h.drive(h.api.nvDetail({state:'NV',operation:'detail',identifier:'C20190204-2019'},h.time+45000));
 assert.equal(detail.fields['Entity Number'],'C20190204-2019');
 assert.deepEqual(h.opened,['C20190204-2019']);assert.equal(h.clicks,1);
});

test('Nevada refuses an earlier-page record whose row changed before detail navigation',async()=>{
 const rows=manyPublicRows(160);rows[0]=['CCA','C20190204-2019','C20190204-2019','','','','Expired'];
 const h=fixture({rows,reservation:true,initialPageSize:100});await h.search();
 rows[0][6]='Active';
 await assert.rejects(h.drive(h.api.nvDetail({state:'NV',operation:'detail',identifier:'C20190204-2019'},h.time+45000)),/DETAIL_NOT_OBSERVED/);
 assert.deepEqual(h.opened,[]);
});

test('Nevada coalesces an identical source row repeated across otherwise distinct completed pages',async()=>{
 const rows=manyPublicRows(1322);
 const repeated=['Ronald Johnson','NV20121265330','','NT7 Business License Sole Proprietor','','04/26/2012 09:19 AM','Expired'];
 rows[598]=[...repeated];rows[601]=[...repeated];
 const h=fixture({rows,initialPageSize:100}),r=await h.search();
 assert.equal(r.complete,true);assert.equal(r.total,1321);assert.equal(r.rows.length,1321);
 assert.equal(r.rows.filter(x=>x.identifier==='NV20121265330').length,1);
});

test('Nevada conflicting cross-page duplicates remain incomplete',async()=>{
 for(const field of [0,3,4,5,6]){
  const rows=manyPublicRows(4);rows[2]=[...rows[0]];rows[2][field]+=' changed';
  await assert.rejects(fixture({rows}).search(),/RESULTS_INCOMPLETE/);
 }
});

test('Nevada identical rows within the same page do not silently establish completeness',async()=>{
 const rows=manyPublicRows(4);rows[1]=[...rows[0]];
 await assert.rejects(fixture({rows}).search(),/RESULTS_INCOMPLETE/);
 const later=manyPublicRows(6);later[2]=[...later[0]];later[3]=[...later[0]];
 await assert.rejects(fixture({rows:later}).search(),/RESULTS_INCOMPLETE/);
});

test('Nevada larger public page recovers a 38-result search whose 25-row final page omits two rows',async()=>{
 const rows=manyPublicRows(38);
 await assert.rejects(fixture({rows,initialPageSize:25,pagingMissing:2}).search(),/PAGINATION_INCOMPLETE/);
 const h=fixture({rows,initialPageSize:25,pagingMissing:2,pageSizeControl:true}),r=await h.search();
 assert.equal(r.total,38);assert.equal(r.rows.length,38);assert.equal(h.pageSize,50);assert.equal(h.resizeClicks,1);assert.equal(h.clicks,1);
 assert.equal(new Set(r.rows.map(x=>x.identifier)).size,38);
});

test('Nevada 100-row control retains complete bounded pagination for larger lists',async()=>{
 const h=fixture({rows:manyPublicRows(138),initialPageSize:25,pageSizeControl:true}),r=await h.search();
 assert.equal(r.total,138);assert.equal(h.pageSize,100);assert.equal(h.resizeClicks,1);
});

for(const count of [501,1322,5463,10000])test(`Nevada completes all ${count} rows without truncating a broad reviewed name`,async()=>{
 const h=fixture({rows:manyPublicRows(count),initialPageSize:25,pageSizeControl:true}),r=await h.search();
 assert.equal(r.total,count);assert.equal(r.rows.length,count);assert.equal(new Set(r.rows.map(x=>x.identifier)).size,count);
 assert.equal(h.pageSize,100);assert.equal(h.clicks,1);assert.ok(h.time<=46000);
});

test('Nevada completes a 5463-row alias with background timer clamping inside its bounded allowance',async()=>{
 const h=fixture({rows:manyPublicRows(5463),initialPageSize:25,pageSizeControl:true,timerClamp:1000});
 const r=await h.search(75000);
 assert.equal(r.total,5463);assert.equal(r.rows.length,5463);
 assert.equal(new Set(r.rows.map(x=>x.identifier)).size,5463);assert.ok(h.time<=75000);
});

test('Nevada slow large alias can finish within 110 seconds while the old 75-second command ends incomplete',async()=>{
 const options={rows:manyPublicRows(5463),initialPageSize:25,pageSizeControl:true,oldPageDelay:1700};
 await assert.rejects(fixture(options).search(75000),/INCOMPLETE/);
 const h=fixture(options),r=await h.search(110000);
 assert.equal(r.total,5463);assert.equal(r.rows.length,5463);assert.ok(h.time<=111000);
});

test('Nevada large alias gets source-latency margin through the real content command',async()=>{
 const options={rows:manyPublicRows(5463),initialPageSize:25,pageSizeControl:true,oldPageDelay:2300};
 await assert.rejects(fixture(options).search(110000),/INCOMPLETE/);
 const h=fixture(options),r=await h.drive(h.api.handle({action:'registry-nv',
  query:{state:'NV',operation:'search',name:'Example'},budgetMs:150000}));
 assert.equal(r.ok,true);assert.equal(r.evidence.total,5463);assert.equal(r.evidence.rows.length,5463);
 assert.ok(h.time>111000&&h.time<=151000);
 const limited=fixture(options);
 await assert.rejects(limited.drive(limited.api.handle({action:'registry-nv',
  query:{state:'NV',operation:'search',name:'Example'},budgetMs:60000})),/INCOMPLETE/);
 assert.ok(limited.time<=61000);
});
test('Nevada still refuses over-limit, missing, duplicate and slow large result pages',async()=>{
 for(const options of [{rows:manyPublicRows(10001)},{rows:manyPublicRows(1322),truncate:true},
     {rows:manyPublicRows(1322),duplicate:true},{rows:manyPublicRows(1322),oldPageDelay:5000}]){
  const h=fixture({initialPageSize:25,pageSizeControl:true,...options});
  await assert.rejects(h.search(),/INCOMPLETE/);assert.ok(h.time<=46000);
 }
});

test('Nevada never accepts a changed total or unacknowledged page-size selection',async()=>{
 for(const options of [{resizeIgnored:true},{resizeTotalDrift:true}]){
  const h=fixture({rows:manyPublicRows(38),initialPageSize:25,pageSizeControl:true,...options});
  await assert.rejects(h.search(),/INCOMPLETE/);assert.equal(h.resizeClicks,1);assert.equal(h.clicks,1);assert.ok(h.time<=46000);
 }
});

test('Nevada single-page searches do not touch the page-size control',async()=>{
 const h=fixture({rows:observed,initialPageSize:25,pageSizeControl:true}),r=await h.search();
 assert.equal(r.total,4);assert.equal(h.resizeClicks,0);
});

test('Nevada native Return To Search waits for the hydrated public form',async()=>{
 const h=fixture({returnFormDelay:900});h.detail();
 const r=await h.drive(h.api.nvReturnSearch(h.time+45000));
 assert.equal(r.ok,true);assert.equal(h.api.registryDocumentReady(),true);assert.ok(h.time>=1900);assert.equal(h.clicks,0);
 assert.equal(h.returnResultsClicks,1);assert.equal(h.returnSearchClicks,0);
});

test('Nevada reuses the ordinary results form after a slow hydration within its original allowance',async()=>{
 const h=fixture({returnFormDelay:12000});h.detail();
 const r=await h.drive(h.api.nvReturnSearch(h.time+45000));
 assert.equal(r.ok,true);assert.equal(h.time,13000);assert.equal(h.returnResultsClicks,1);assert.equal(h.returnSearchClicks,0);
});

test('Nevada return observes selection-only hydration without waiting for the watchdog',async()=>{
 for(const returnAttribute of ['aria-selected','data-value']){
  const h=fixture({returnFormDelay:900,returnAttribute});h.detail();
  const r=await h.drive(h.api.nvReturnSearch(h.time+10000));
  assert.equal(r.ok,true);assert.equal(h.api.registryDocumentReady(),true);
  assert.equal(h.time,1900);assert.equal(h.clicks,0);
 }
});

test('Nevada readiness diagnostics distinguish a detail route using only public booleans',async()=>{
 const h=fixture();h.detail();
 const result=await h.api.handle({action:'registry-ready'});
 assert.equal(result.ready,false);
 assert.equal(result.nv_readiness.search_route,false);
 assert.equal(result.nv_readiness.inputs_present,false);
 assert.deepEqual(Object.keys(result.nv_readiness).sort(),['business_selected','document_loaded','inputs_present','loader_clear','search_enabled','search_mode_selected','search_route']);
 assert.ok(Object.values(result.nv_readiness).every(value=>typeof value==='boolean'));
});

test('Nevada missing or incomplete native return cannot be accepted as a completed search',async()=>{
 const h=fixture();h.detail();const read=h.context.document.querySelectorAll;
 h.context.document.querySelectorAll=q=>q==='button'?[]:read(q);
 await assert.rejects(h.drive(h.api.nvReturnSearch(h.time+45000)),/RETURN_SEARCH_MISSING/);
 const delayed=fixture({returnFormDelay:46000});delayed.detail();
 await assert.rejects(delayed.drive(delayed.api.nvReturnSearch(delayed.time+45000)),/REGISTRY_NV_RETURN_READY_TIMEOUT/);
});

test('Nevada collects both national records and local chapters without choosing one',async()=>{
 const f=fixture();const r=await f.search();assert.equal(r.total,4);assert.deepEqual(Array.from(r.rows,x=>x.identifier),observed.map(x=>x[1]));
 assert.equal(f.clicks,1);assert.ok(r.rows.every(r=>!('detail_url' in r)&&!('address' in r)));assert.equal(r.verification_pending,false);
});

test('Nevada waits for Search replacement caused by filter input rendering',async()=>{
 const f=fixture({replaceSearchOnInput:true});const result=await f.search();
 assert.equal(result.total,4);assert.equal(f.clicks,1);assert.equal(f.staleClicks,0);
});

test('Nevada unrelated rendering cannot starve a stable current Search button',async()=>{
 const f=fixture({unrelatedMutations:true,replaceSearchOnInput:true});
 const r=await f.search();assert.equal(r.total,4);assert.equal(f.clicks,1);assert.equal(f.staleClicks,0);
});

test('Nevada retries a fresh form once when its first Search never starts a response',async()=>{
 const f=fixture({ignoredSearches:1}),r=await f.search();
 assert.equal(r.total,4);assert.equal(f.clicks,2);assert.ok(f.time<6000);
});

test('Nevada never repeats Search after loading has started, even for a slow response',async()=>{
 const f=fixture({responseDelay:6000}),r=await f.search();
 assert.equal(r.total,4);assert.equal(f.clicks,1);
});

test('Nevada no-activity retry does not extend the command budget or invent a negative',async()=>{
 const f=fixture({activity:false,rows:[]});await assert.rejects(f.search(),/SEARCH_NOT_STARTED/);
 assert.equal(f.clicks,2);assert.ok(f.time<=36200);
});

test('Nevada refuses to retry a Search whose name was changed after submission',async()=>{
 const f=fixture({ignoredSearches:1,changedQueryBeforeRetry:true});
 await assert.rejects(f.search(),/SEARCH_NOT_STARTED/);assert.equal(f.clicks,1);
});

test('Nevada throttled retry cannot execute beyond the original deadline',async()=>{
 const f=fixture({activity:false,timerClamp:60000,rows:[]});
 await assert.rejects(f.search(),/SEARCH_NOT_STARTED/);assert.equal(f.clicks,1);
});

test('Nevada retains observed NR rows without treating them as issued business identities',async()=>{
 const nr=['The Junior Swim League LLC','NR20230725-22746','NR20230725-22746','','','07/25/2023 01:17 PM','Expired'];
 const f=fixture({rows:[observed[1],nr]}),r=await f.search();
 assert.equal(r.total,2);assert.equal(r.rows[1].identifier,nr[1]);assert.equal(r.rows[1].entity_type,'');
 await assert.rejects(f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:nr[1]},45000)),/RESPONSE_INCOMPLETE/);
 for(const changed of [['NO-ID',''],['NR20230725-22746','Foreign Non-Profit Corporation (80)'],['NV123','']]){
  const row=[...nr];row[1]=changed[0];row[3]=changed[1];await assert.rejects(fixture({rows:[row]}).search(),/RESULTS_INCOMPLETE/);
 }
});

test('Nevada dated C rows without an entity type are retained only as unclassified identities',async()=>{
 const row=['MIRROR MAGIC FOTO BOOTH','C20180913-0530','C20180913-0530','','','','Expired'];
 const h=fixture({rows:[observed[1],row]}),r=await h.search();
 assert.equal(r.total,2);assert.equal(r.rows[1].identifier,row[1]);assert.equal(r.rows[1].entity_type,'');
 await assert.rejects(h.drive(h.api.nvDetail({state:'NV',operation:'detail',identifier:row[1]},45000)),/RESPONSE_INCOMPLETE/);
 for(const changed of [[...row.slice(0,2),'C20180914-0530',...row.slice(3)], [...row.slice(0,3),'Foreign Non-Profit Corporation (80)',...row.slice(4)], [...row.slice(0,6),'']])
  await assert.rejects(fixture({rows:[changed]}).search(),/RESULTS_INCOMPLETE/);
});

test('Nevada preserves a blank business ID with its observed entity number for master filtering',async()=>{
 const pending=['Ronald McDonald House Charities of Northeast Indiana','','E38494562024-0','Foreign Entities Not Required to Register In Nevada','','12/19/2023 12:00 AM','Expired'];
 const f=fixture({rows:[observed[1],pending]}),r=await f.search();
 assert.equal(r.total,2);assert.equal(r.rows[1].identifier,pending[2]);
 assert.equal(r.rows[1].entity_number,pending[2]);assert.equal(r.rows[1].business_identifier_missing,true);
 await assert.rejects(f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:pending[2]},45000)),/COMMAND_INVALID/);
 assert.equal(f.opened.length,0);
 for(const changes of [{1:'UNKNOWN'},{2:''},{3:''},{6:''}]){
  const row=[...pending];for(const [i,v] of Object.entries(changes))row[i]=v;
  await assert.rejects(fixture({rows:[row]}).search(),/RESULTS_INCOMPLETE/);
 }
 await assert.rejects(fixture({rows:[pending,pending]}).search(),/RESULTS_INCOMPLETE/);
});

test('Nevada retains an issued row with a visibly blank status without inventing status',async()=>{
 const row=['Something Local, LLC','NV20201884142','E8938352020-2','Domestic Limited Liability Company (86)','','08/26/2020 12:00 AM',''];
 const result=await fixture({rows:[observed[1],row]}).search();
 assert.equal(result.total,2);assert.equal(result.rows[1].raw_status,'');
 assert.equal(result.rows[1].identifier,row[1]);
 for(const changes of [{1:''},{3:''}]){
  const changed=[...row];for(const [i,v] of Object.entries(changes))changed[i]=v;
  await assert.rejects(fixture({rows:[changed]}).search(),/RESULTS_INCOMPLETE/);
 }
});

test('Nevada restores all row identities including a blank-business-ID row between two details',async()=>{
 const pending=['Unrelated charity','','E38494562024-0','Foreign Entities Not Required to Register In Nevada','','12/19/2023 12:00 AM','Expired'];
 const f=fixture({rows:[...observed.slice(0,2),pending]});await f.search();
 await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[0][1]},45000));
 const result=await f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:observed[1][1]},45000));
 assert.equal(result.fields['NV Business ID'],observed[1][1]);assert.equal(f.opened.length,2);
});
test('initial empty grid cannot establish non-registration without a response',async()=>{const f=fixture({activity:false,rows:[]});await assert.rejects(f.search(),/SEARCH_NOT_STARTED/);});
test('completed empty response is accepted only after observed loading cycle',async()=>{const f=fixture({rows:[]});const r=await f.search();assert.equal(r.total,0);assert.equal(r.complete,true);});
test('truncated pagination cannot become a partial positive or negative',async()=>{const f=fixture({truncate:true});await assert.rejects(f.search(),/PAGINATION_INCOMPLETE/);});
test('pager changing before rows does not repeat the previous page',async()=>{const f=fixture({oldPageDelay:600});const r=await f.search();assert.equal(r.total,4);assert.ok(f.time>=1700);});
test('repeated rows across pages cannot pass as complete results',async()=>{const f=fixture({duplicate:true});await assert.rejects(f.search(),/RESPONSE_INCOMPLETE|RESULTS_INCOMPLETE/);});
test('late source response is rejected against its original command budget',async()=>{const f=fixture({responseDelay:40000});await assert.rejects(f.search(35000),/RESPONSE_PENDING/);});
test('Nevada gives an already loading search bounded grace without resubmitting',async()=>{
 const f=fixture({responseDelay:40000});const r=await f.search(90000);
 assert.equal(r.total,4);assert.equal(r.complete,true);assert.equal(f.clicks,1);assert.ok(f.time<42000);
});
test('Nevada pending grace accepts a completed empty response but never a pending empty grid',async()=>{
 const f=fixture({rows:[],responseDelay:50000});const r=await f.search(90000);
 assert.equal(r.total,0);assert.equal(r.complete,true);assert.equal(f.clicks,1);
 const pending=fixture({rows:[],responseDelay:70000});await assert.rejects(pending.search(150000),/RESPONSE_PENDING/);
 assert.equal(pending.clicks,1);assert.ok(pending.time<=61200);
});
test('Nevada slow broad and exact searches share the original command deadline',async()=>{
 const query={state:'NV',operation:'search',name:'ELI',exact_above:20};
 const f=fixture({rows:manyPublicRows(25),exactRows:[],responseDelay:40000});
 const r=await f.drive(f.api.nvSearch(query,f.time+150000));assert.equal(r.total,0);assert.equal(r.search_mode,'EXACT_MATCH');assert.equal(f.clicks,2);
 const bounded=fixture({rows:manyPublicRows(25),exactRows:[],responseDelay:40000});
 await assert.rejects(bounded.drive(bounded.api.nvSearch(query,bounded.time+60000)),/RESPONSE_PENDING/);
 assert.equal(bounded.clicks,2);assert.ok(bounded.time<=61000);
});
test('zero-result response observed only after timer throttling is not invented',async()=>{const f=fixture({activity:false,timerClamp:60000,rows:[]});await assert.rejects(f.search(),/SEARCH_NOT_STARTED/);});
test('wrong column schema is incomplete',async()=>{const f=fixture();const prior=f.grid.querySelectorAll;f.grid.querySelectorAll=q=>q==='[role="columnheader"]'?[]:prior(q);await assert.rejects(f.search(),/COLUMNS_CHANGED/);});
test('Nevada extracts corporation fields and stops before registered-agent duplicates',()=>{const f=fixture();const fields=f.detail();assert.equal(fields['NV Business ID'],'NV20121738342');assert.equal(fields['Entity Status'],'Active');assert.equal(fields['Annual Renewal Due Date/Expiration Date'],'12/31/2026');assert.ok(!('Street Address' in fields));});
test('wrong detail business ID cannot be accepted',()=>{assert.equal(fixture({detailId:'NV19931054903'}).detail(),null);});
test('unobserved business ID cannot trigger a guessed navigation',async()=>{const f=fixture();await assert.rejects(f.drive(f.api.nvDetail({state:'NV',operation:'detail',identifier:'NV999'},45000)),/NOT_OBSERVED/);assert.equal(f.opened.length,0);});
test('Nevada waits for a delayed complete filing grid after entity fields load',async()=>{
 const h=fixture(),read=h.context.document.querySelectorAll;let gridReady=false;
 const filingHeaders=['Filed Date','Effective Date','Filing Number','Filing Type','Source','No. of Pages'];
 const cells=['06/18/2025','06/18/2025','20254979739','Charitable Solicitation Registration Statement','Email','5'];
 const grid={getAttribute:()=> '2',querySelector:()=>null,querySelectorAll:q=>q==='[role="columnheader"]'
  ?filingHeaders.map(label=>({getAttribute:()=>label})):q==='tbody > tr[role="row"]'
  ?[{querySelector:()=>({}),querySelectorAll:()=>cells.map(innerText=>({innerText,querySelector:()=>null}))}]:[]};
 const table={querySelectorAll:()=>[{innerText:'Filing History Details'}],querySelector:q=>q==='[role="grid"]'?grid:
  q==='kendo-datapager'?{getAttribute:()=> 'Page 1 of 1'}:q==='kendo-datapager-info'?{innerText:'1 - 1 of 1 items'}:null};
 h.context.document.querySelectorAll=q=>q==='casex-data-table'&&h.context.location.hash.includes('Manage-Business')
  ?gridReady?[table]:[]:read(q);
 await h.search();
 // The real render mutates the DOM. Feed that observation through the normal
 // fixture's scheduled detail mutation, rather than exposing application state.
 const Observer=h.context.MutationObserver;let notify;
 h.context.MutationObserver=class extends Observer {constructor(fn){super(fn);notify=fn;}};
 h.context.setTimeout(()=>{gridReady=true;notify?.([{target:h.context.document.documentElement,addedNodes:[],removedNodes:[]}]);},12000);
 const result=await h.drive(h.api.nvDetail({state:'NV',operation:'detail',identifier:'NV20121738342'},h.time+45000));
 assert.equal(result.filings.complete,true);assert.equal(result.filings.total,1);
 assert.equal(result.filings.rows[0][3],'Charitable Solicitation Registration Statement');
});

test('Nevada filing pagination waits for old rows to be replaced after the pager advances',async()=>{
 const h=fixture(),headers=['Filed Date','Effective Date','Filing Number','Filing Type','Source','No. of Pages'];
 const filing=id=>['06/02/2026','06/02/2026',String(id),'Charitable Solicitation Registration Statement','Online','1'];
 let page=1,rows=[filing(1),filing(2)],notify;
 const grid={querySelector:()=>null,querySelectorAll:q=>q==='[role="columnheader"]'
  ?headers.map(label=>({getAttribute:()=>label})):q==='tbody > tr[role="row"]'
  ?rows.map(cells=>({querySelector:()=>({}),querySelectorAll:()=>cells.map(innerText=>({innerText,querySelector:()=>null}))})):[]};
 const target={nodeType:1,closest:()=>({})};
 const table={querySelectorAll:()=>[{innerText:'Filing History Details'}],querySelector:q=>q==='[role="grid"]'?grid:
  q==='kendo-datapager'?{getAttribute:()=>`Page ${page} of 2`}:q==='kendo-datapager-info'
  ?{innerText:page===1?'1 - 2 of 4 items':'3 - 4 of 4 items'}:q==='button[aria-label="Go to the next page"]'
  ?{disabled:false,getAttribute:()=>null,click:()=>{
    page=2;rows=[filing(3),filing(2)];
    notify?.([{target,addedNodes:[],removedNodes:[]}]);
    h.context.setTimeout(()=>{rows=[filing(3),filing(4)];notify?.([{target,addedNodes:[],removedNodes:[]}]);},800);
  }}:null};
 h.context.document.querySelectorAll=q=>q==='casex-data-table'?[table]:q==='.app-loader-pane .circle-loader'?[]:[];
 const Observer=h.context.MutationObserver;
 h.context.MutationObserver=class extends Observer {constructor(fn){super(fn);notify=fn;}};
 const collected=await h.drive(h.api.nvPages('Filing History Details',headers,h.time+45000));
 assert.deepEqual(Array.from(collected,row=>row.cells[2]),['1','2','3','4']);
 assert.ok(h.time>=1800,'the old filing row is not accepted with the new pager');
});

test('Nevada filing placeholders never count as a completed filing page',()=>{
 const h=fixture(),headers=['Filed Date','Effective Date','Filing Number','Filing Type','Source','No. of Pages'];
 const grid={querySelectorAll:q=>q==='[role="columnheader"]'?headers.map(label=>({getAttribute:()=>label})):
  q==='tbody > tr[role="row"]'?[{querySelector:()=>({}),querySelectorAll:()=>headers.map(()=>({innerText:'',querySelector:()=>null}))}]:[]};
 const table={querySelectorAll:()=>[{innerText:'Filing History Details'}],querySelector:q=>q==='[role="grid"]'?grid:
  q==='kendo-datapager'?{getAttribute:()=> 'Page 1 of 1'}:q==='kendo-datapager-info'?{innerText:'1 - 1 of 1 items'}:null};
 h.context.document.querySelectorAll=()=>[table];
 assert.throws(()=>h.api.nvPage('Filing History Details',headers),/FILINGS_INCOMPLETE/);
});

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

test('Nevada source duplicates remain safely coalesced when returning between two details',async()=>{
 const rows=[...observed.map(r=>[...r]),[...observed[0]],[...observed[1]]];
 const f=fixture({rows,repeatSearchActivity:false});const search=await f.search();
 assert.equal(search.total,4);
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
