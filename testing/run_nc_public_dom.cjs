/* Public NC labels observed 2026-09-29; fake DOM only, no live browser. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(process.env.CC_TEST_TRIAL_DIR||path.join(__dirname,'../browser-connector'),'registry-content.js'),'utf8')
 .replace('  async function handle(m) {','  globalThis.testNC={ncLabeled,ncForm,ncRetry,ncRows,ncProfile,ncFilings,registryDocumentReady,handle};\n  async function handle(m) {');
const origin='https://www.sosnc.gov',profile=origin+'/online_services/search/charities_profile/5700751';
const active={'CSL Legal Name':"America's Charities",'CSL Type':'Charitable Organization',Status:'Current Active – Filing Extension Granted',License:'SL000448','Expiration Date':'5/15/2026','Extension End Date':'11/15/2026'};
const exempt={'CSL Legal Name':'YWCA of the U.S.A.','CSL Type':'CSL Exempt Organization',Status:'CSL Exempt',License:'EX003050'};
const withdrawnApplication={'CSL Legal Name':'Generic Literacy Organization','CSL Type':'In-Process',Status:'Withdrawn',License:''};
const txt=innerText=>({innerText,querySelector:()=>null});
function labels(values){return Object.entries(values).map(([key,value])=>({innerText:key+':',parentElement:txt(key+': '+value)}));}
function harness({cards=[active],total=cards.length,query="America's Charities",searchMode='Starting With',url=origin+'/online_services/search/Charities_Results',fields=null,periods=null,uploadLink=false,extraLabels=[],displayName=null,addressCount=1,profileIds=null}={}){
 const panels=new Map(),buttons=[];let clicks=0,formClicks=0;
 for(const [i,row] of cards.entries()){
  let expanded=false;
  const panel={getClientRects:()=>expanded?[{}]:[],querySelectorAll:s=>s==='.para-small > .boldSpan'?[...labels(row),...extraLabels.flatMap(labels)]:s==='a[href]'?[{getAttribute:()=>new URL(profile).pathname.replace(/\d+$/,profileIds?.[i]||'5700751')}]:[]};
  panels.set('a'+i,panel);buttons.push({querySelector:s=>s==='.searchHeader'?txt(row['CSL Type']==='In-Process'&&!row.License?(displayName||row['CSL Legal Name']):`${displayName||row['CSL Legal Name']} • (${row.License})`):null,getAttribute:k=>k==='aria-controls'?'a'+i:expanded?'true':'false',click:()=>{clicks++;expanded=true;}});
 }
 const addressValues=['14200 Park Meadow Dr Ste 330s','Chantilly','VA','20151-4210'];
 const address={innerText:'Address',parentElement:{querySelectorAll:s=>(s===':scope > .para-small > span'?addressValues:s==='.para-small > span'?['Address',...addressValues]:[]).map(txt)}};
 const main={innerText:`Records Found: ${total} Words: ${searchMode} Organization Name ${query} Search Time 9/29/2026 03:50 PM`,
  querySelectorAll:s=>s==='#resultsSection .usa-accordion__button'?buttons:s==='.para-small > .boldSpan'?[...labels(fields||{}),...Array(addressCount).fill(address)]:s==='a[href]'?[{getAttribute:()=>new URL(profile).pathname.replace('charities_profile','charities_filings')}]:[]};
 class Input{get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){}}
 class Select extends Input{};
 Object.defineProperty(Select.prototype,'value',Object.getOwnPropertyDescriptor(Input.prototype,'value'));
 const input=new Input(),words=new Select();words.options=[{innerText:'Starting With',value:'0'},{innerText:'All Words',value:'1'}];
 const print={checked:true,click:()=>{print.checked=false;}},button={innerText:'Search',disabled:false,getClientRects:()=>[{}],click:()=>formClicks++};
 const win={};win.top=win;
 const context=vm.createContext({window:win,URL,location:{origin,pathname:new URL(url).pathname,href:url},crypto:{randomUUID:()=> 'fixture'},
  document:{readyState:'complete',documentElement:{},getElementById:id=>panels.get(id),
   querySelector:s=>s==='main'?main:s==='#SearchCriteria'?input:s==='#Words'?words:s==='#SubmitButton'?button:s==='#Print'?print:null,
   querySelectorAll:s=>periods===null?[]:[{children:periods.map(([type,date])=>({tagName:'LI',childNodes:[{nodeType:3,textContent:type}],querySelectorAll:()=>[...(date===null?[]:[txt(date)]),...(uploadLink?[{innerText:'Upload an Attachment',querySelector:s=>s==='a'?{}:null}]:[])]}))}]},
  MutationObserver:class{observe(){}disconnect(){}},HTMLInputElement:Input,HTMLSelectElement:Select,Event:class{},setTimeout,clearTimeout,
  chrome:{runtime:{id:'fixture',onMessage:{addListener(){}}}}});
 vm.runInContext(source,context);return {api:context.testNC,context,input,words,print,button,main,panels,addressValues,clicks:()=>clicks,formClicks:()=>formClicks};
}

test('NC retains a withdrawn unissued card and keeps an in-process card pending',async()=>{
 for(const status of ['Withdrawn','Withdrawn In Process','In-Process']) {
  const card={...withdrawnApplication,Status:status};
  const h=harness({cards:[card],query:card['CSL Legal Name']});
  const row=(await h.api.ncRows({state:'NC',operation:'search',name:card['CSL Legal Name']})).evidence.rows[0];
  assert.equal(row.Status,status);
  assert.equal(row.License,'');
 }
});

test('NC All Words uses only the public form and binds result mode and query',async()=>{
 const query={state:'NC',operation:'search',name:'Better World',search_mode:'ALL_WORDS'};
 const form=harness({url:origin+'/online_services/search/by_title/search_charities'});
 form.api.ncForm(query);
 assert.equal(form.words.value,'1');
 assert.equal(form.input.value,'Better World');
 assert.equal(form.formClicks(),1);
 const result=harness({query:'Better World',searchMode:'All Words',cards:[active]});
 const evidence=(await result.api.ncRows(query)).evidence;
 assert.equal(evidence.search_mode,'ALL_WORDS');
 assert.equal(evidence.rows.length,1);
 await assert.rejects(result.api.ncRows({...query,search_mode:undefined}),/QUERY_CHANGED/);
 const noRecord=harness({query:'Unmatched Charity',searchMode:'All Words',cards:[]});
 assert.equal((await noRecord.api.ncRows({...query,name:'Unmatched Charity'})).evidence.total,0);
});

test('NC passive timing separates completed HTTP failures from idle submission without leaking request data',async()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'});
 const q={state:'NC',operation:'search',name:'Achieving'};
 const entry=(change={})=>({name:origin+'/online_services/search/check?private=secret',startTime:101,duration:12.8,initiatorType:'xmlhttprequest',responseStatus:429,...change});
 h.context.performance={now:()=>100,getEntriesByType:()=>[
  entry({startTime:99}),entry({name:'https://elsewhere.example/token'}),entry({initiatorType:'img'}),entry(),
  entry({name:origin+'/public-action',responseStatus:200}),entry({responseStatus:undefined})]};
 h.api.ncForm(q);
 const r=await h.api.handle({action:'registry-ready',query:q});
 assert.equal(h.formClicks(),1);
 assert.deepEqual(JSON.parse(JSON.stringify(r.nc_readiness.requests)),[
  {after_ms:1,duration_ms:13,status:429,search_route:true},
  {after_ms:1,duration_ms:13,status:200,search_route:false},
  {after_ms:1,duration_ms:13,status:0,search_route:true}]);
 assert.doesNotMatch(JSON.stringify(r.nc_readiness),/secret|private|https|token/);
});

test('NC timing is optional and cannot break search when resource timing is unavailable',async()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'}),q={state:'NC',operation:'search',name:'Example'};
 h.api.ncForm(q);
 assert.equal((await h.api.handle({action:'registry-ready',query:q})).nc_readiness.requests.length,0);
 h.context.performance={now:()=>10,getEntriesByType:()=>{throw Error('unavailable');}};
 h.api.ncForm(q);
 assert.equal((await h.api.handle({action:'registry-ready',query:q})).nc_readiness.requests.length,0);
 assert.equal(h.formClicks(),2);
});

test('NC timing is bounded and restarts with each new query without extra requests',async()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'}),q={state:'NC',operation:'search',name:'Example'};
 let now=100;
 h.context.performance={now:()=>now,getEntriesByType:()=>Array.from({length:100},(_,i)=>({name:origin+'/online_services/search/result?x='+i,startTime:101+i,duration:1,initiatorType:'fetch',responseStatus:200}))};
 h.api.ncForm(q);assert.equal((await h.api.handle({action:'registry-ready',query:q})).nc_readiness.requests.length,8);
 now=300;h.api.ncForm({...q,name:'Second'});
 assert.equal((await h.api.handle({action:'registry-ready',query:{...q,name:'Second'}})).nc_readiness.requests.length,0);
});
test('NC collects only expanded, complete, query-bound cards and extension date',async()=>{
 const h=harness(),q={state:'NC',operation:'search',name:"America's Charities"};
 const r=await h.api.ncRows(q);assert.equal(r.evidence.total,1);assert.equal(h.clicks(),1);
 assert.equal(r.evidence.rows[0]['Extension End Date'],'11/15/2026');assert.equal(r.evidence.rows[0].profile_url,profile);
});
test('NC reports visible verification without collecting tokens or submitting the form',async()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'});
 h.context.document.title='Just a moment...';h.context.document.body=txt('Performing security verification');
 h.context.document.querySelector=()=>null;
 const r=await h.api.handle({action:'registry-ready'});
 assert.equal(r.ready,false);assert.equal(r.verification_pending,true);assert.equal(h.formClicks(),0);
 assert.deepEqual(Object.keys(r).sort(),['documentId','page_visibility','ready','url','verification_pending']);
 assert.equal(r.page_visibility,h.context.document.visibilityState);
 h.context.document.title='Search Charities';assert.equal((await h.api.handle({action:'registry-ready'})).verification_pending,false);
});
test('NC explicit exemption can omit expiration without omitting identity',async()=>{
 const h=harness({cards:[exempt],query:'YWCA'}),r=await h.api.ncRows({state:'NC',operation:'search',name:'YWCA'});
 assert.equal(r.evidence.rows[0]['Expiration Date'],'');assert.equal(r.evidence.rows[0].License,'EX003050');
});
test('NC preserves an explicitly In-Process application without inventing an issued license',async()=>{
 const row={'CSL Legal Name':'Junior League of Asheville, Inc.','CSL Type':'In-Process',Status:'In-Process'};
 const h=harness({cards:[row],query:'Junior'});
 const r=(await h.api.ncRows({state:'NC',operation:'search',name:'Junior'})).evidence;
 assert.equal(r.total,1);assert.equal(r.rows[0].License,'');assert.equal(r.rows[0]['Expiration Date'],'');
 assert.equal(r.rows[0].profile_url,profile);assert.equal(r.rows[0].Status,'In-Process');
 for(const bad of [{...row,Status:'Active'},{...row,'CSL Type':'Charitable Organization'}])
  await assert.rejects(harness({cards:[bad],query:'Junior'}).api.ncRows({state:'NC',operation:'search',name:'Junior'}),/CARD_CHANGED/);
});

test('NC repeated legal names and DBAs are retained as aliases on one identified card',async()=>{
 const q={state:'NC',operation:'search',name:"America's Charities"};
 for(const displayName of ["America's Charities",'Former Charity Name','Public DBA']) {
  const h=harness({displayName,extraLabels:[{'CSL Legal Name':'Former Charity Name'},{'CSL DBA Name':'Public DBA'},{'CSL DBA Name':'Second DBA'}]});
  const row=(await h.api.ncRows(q)).evidence.rows[0];
  assert.equal(row.display_name,displayName);assert.equal(row.License,active.License);
  assert.deepEqual(new Set([row.display_name,...row.aliases]),new Set(["America's Charities",'Former Charity Name','Public DBA','Second DBA']));
 }
});

test('NC duplicates remain errors for status/license/dates and unbound display names',async()=>{
 const q={state:'NC',operation:'search',name:"America's Charities"};
 for(const key of ['Status','License','Expiration Date','Extension End Date'])
  await assert.rejects(harness({extraLabels:[{[key]:active[key]}]}).api.ncRows(q),/DUPLICATE_FIELD/);
 await assert.rejects(harness({displayName:'Different organization'}).api.ncRows(q),/CARD_CHANGED/);
});
test('NC refuses incomplete cards, partial pagination, duplicate licenses and wrong-query results',async()=>{
 const missing={...active};delete missing['Expiration Date'];
 for(const opts of [{cards:[missing]},{total:2},{cards:[active,active]},{query:'Unrelated Name'}]){
  const h=harness(opts);await assert.rejects(h.api.ncRows({state:'NC',operation:'search',name:"America's Charities"}));
 }
});
test('NC negative requires explicit completed count and matching searched name',async()=>{
 const h=harness({cards:[],query:'No Such Organization'});
 assert.equal((await h.api.ncRows({state:'NC',operation:'search',name:'No Such Organization'})).evidence.total,0);
 h.main.innerText='Loading';await assert.rejects(h.api.ncRows({state:'NC',operation:'search',name:'No Such Organization'}));
});
const profileFields={Name:"America's Charities",Status:active.Status,'Registration #':'SL000448','Expiration Date':'5/15/2026','Last Application Date':'5/13/2026','Extension End Date':'11/15/2026',Phone:'unrelated contact','Contact':'private person'};
test('NC profile retains office address, excludes contact information and binds license',()=>{
 const h=harness({url:profile,fields:profileFields}),q={state:'NC',operation:'detail',identifier:'SL000448',url:profile};
 const r=h.api.ncProfile(q);assert.equal(r.evidence.fields.City,'Chantilly');assert.equal(r.evidence.fields['Last Application Date'],'5/13/2026');
 assert.equal(r.evidence.fields.Contact,undefined);assert.equal(r.evidence.fields.Phone,undefined);
 assert.throws(()=>h.api.ncProfile({...q,identifier:'SL999999'}));
 assert.throws(()=>h.api.ncProfile({...q,url:profile+'1'}));
});
test('NC address label cannot displace the street and missing address values remain incomplete',()=>{
 const h=harness({url:profile,fields:profileFields}),q={state:'NC',operation:'detail',identifier:'SL000448',url:profile};
 const r=h.api.ncProfile(q);assert.equal(r.evidence.fields.Street,'14200 Park Meadow Dr Ste 330s');
 assert.equal(r.evidence.fields.Zip,'20151-4210');h.addressValues.pop();assert.throws(()=>h.api.ncProfile(q),/ADDRESS_INCOMPLETE/);
});
test('NC reads labeled filing types without confusing extension date for renewal',()=>{
 const h=harness({url:profile.replace('charities_profile','charities_filings'),periods:[['Renewal Charity','11/17/2025'],['Federal Extension','5/13/2026']]});
 const r=h.api.ncFilings({url:profile});assert.equal(r.filings.rows[0].type,'Renewal Charity');assert.equal(r.filings.rows[1].type,'Federal Extension');
 assert.equal(r.filings.rows.length,2);assert.throws(()=>h.api.ncFilings({url:profile+'1'}));
});
test('NC missing history entry date cannot be silently skipped',()=>{
 const h=harness({url:profile.replace('charities_profile','charities_filings'),periods:[['Renewal Charity',null]]});assert.throws(()=>h.api.ncFilings({url:profile}));
});

test('NC attachment links do not displace or invalidate the filing date',()=>{
 const url=profile.replace('charities_profile','charities_filings');
 const h=harness({url,periods:[['Holding','4/7/2008'],['Renewal Charity','8/13/2026']],uploadLink:true});
 const r=h.api.ncFilings({url:profile});assert.equal(r.filings.rows.length,2);assert.equal(r.filings.rows[1].date,'8/13/2026');
 for(const date of [null,'not a date'])assert.throws(()=>harness({url,periods:[['Holding',date]],uploadLink:true}).api.ncFilings({url:profile}),/FILINGS_INCOMPLETE/);
});
test('NC ordinary form resets search type and printable view, never calls a hidden endpoint',async()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'}),q={state:'NC',operation:'search',name:'Reviewed Alternate Name'};
 assert.equal(h.api.ncForm(q).phase,'submitted');assert.equal(h.input.value,q.name);assert.equal(h.words.value,'0');assert.equal(h.print.checked,false);
 assert.equal(h.formClicks(),1,'submission cannot be acknowledged before the ordinary click is dispatched');
 h.button.disabled=true;assert.throws(()=>h.api.ncForm(q));
});

test('NC query dispatch does not depend on a background-tab timer',()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'});
 h.context.setTimeout=()=>{throw Error('Background timer is suspended');};
 assert.equal(h.api.ncForm({state:'NC',operation:'search',name:'Reviewed Alternate Name'}).phase,'submitted');
 assert.equal(h.formClicks(),1);
});

test('NC submission observations distinguish visible processing from an idle hidden form',async()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'}),q={state:'NC',operation:'search',name:'Achieving'};
 h.api.ncForm(q);h.context.document.visibilityState='hidden';
 let value=(await h.api.handle({action:'registry-ready',query:q})).nc_readiness;
 assert.equal(value.visible,false);assert.equal(value.idle,true);assert.equal(value.query_matches,true);
 h.context.document.visibilityState='visible';h.button.disabled=true;h.button.innerText='Processing';
 value=(await h.api.handle({action:'registry-ready',query:q})).nc_readiness;
 assert.equal(value.visible,true);assert.equal(value.processing,true);assert.equal(value.idle,false);
 assert.ok(!JSON.stringify(value).includes('Achieving'));
 assert.deepEqual(Object.keys(value).sort(),['document_complete','idle','processing','query_matches','requests','results_page','search_form','visible']);
 assert.equal(value.requests.length,0);
});
test('NC retains an already selected mode without firing its source change handler',()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'});
 h.words.value='0';h.words.dispatchEvent=()=>{throw Error('Unnecessary search-type change');};
 assert.equal(h.api.ncForm({state:'NC',operation:'search',name:'Reviewed Alias'}).phase,'submitted');
 assert.equal(h.formClicks(),1);
});
test('NC recovery resubmits only the identical enabled ordinary form',()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'}),q={state:'NC',operation:'search',name:'Reviewed Alias'};
 h.api.ncForm(q);assert.equal(h.api.ncRetry(q).phase,'submitted');assert.equal(h.formClicks(),2);
 for(const change of [()=>h.button.disabled=true,()=>{h.button.disabled=false;h.button.innerText='Processing';},()=>{h.button.innerText='Search';h.input.value='Different Name';},()=>{h.input.value=q.name;h.words.value='exact';},()=>{h.words.value='0';h.print.checked=true;}]){
  change();assert.notEqual(h.api.ncRetry(q).phase,'submitted');assert.equal(h.formClicks(),2);
 }
});
test('NC recovery never operates a verification or another document',()=>{
 const q={state:'NC',operation:'search',name:'Reviewed Alias'},h=harness({url:origin+'/online_services/search/by_title/search_charities'});
 h.context.document.querySelector=()=>null;assert.equal(h.api.ncRetry(q).phase,'pending');assert.equal(h.formClicks(),0);
 assert.equal(harness().api.ncRetry(q).phase,'pending');
 assert.throws(()=>h.api.ncRetry({...q,state:'NV'}),/QUERY_INVALID/);
});

test('NC idle-form readiness is read-only and requires the exact query and enabled search controls',async()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'}),q={state:'NC',operation:'search',name:'Reviewed Alias'};
 h.api.ncForm(q);const before=h.formClicks();
 assert.equal((await h.api.handle({action:'registry-ready',query:q})).nc_search_idle,true);
 assert.equal(h.formClicks(),before);
 for(const change of [()=>h.button.disabled=true,()=>{h.button.disabled=false;h.button.innerText='Processing';},()=>{h.button.innerText='Search';h.input.value='Other';},()=>{h.input.value=q.name;h.words.value='exact';},()=>{h.words.value='0';h.print.checked=true;}]){
  change();assert.equal((await h.api.handle({action:'registry-ready',query:q})).nc_search_idle,false);
 }
 assert.equal(h.formClicks(),before);
});
test('NC document completion does not mistake a verification interstitial for its search form',()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'}),read=h.context.document.querySelector;
 h.context.document.querySelector=()=>null;assert.equal(h.api.registryDocumentReady(),false);
 h.context.document.querySelector=read;assert.equal(h.api.registryDocumentReady(),true);
 h.button.disabled=true;assert.equal(h.api.registryDocumentReady(),false);
});

test('NC visible form waits for document completion before its inline submit action',()=>{
 const h=harness({url:origin+'/online_services/search/by_title/search_charities'});
 h.context.document.readyState='interactive';assert.equal(h.api.registryDocumentReady(),false);assert.equal(h.formClicks(),0);
 h.context.document.readyState='complete';assert.equal(h.api.registryDocumentReady(),true);
});
test('NC results readiness requires a rendered count, including an explicit zero',()=>{
 const h=harness({cards:[]});h.main.innerText='Performing security verification';assert.equal(h.api.registryDocumentReady(),false);
 h.main.innerText='Records Found: 0';assert.equal(h.api.registryDocumentReady(),true);
});

test('NC completed explicit EX exemption can omit its entire address block',()=>{
 const fields={Name:'College of William & Mary',Status:'CSL Exempt','Registration #':'EX009484','Last Application Date':'8/17/2022'};
 const q={state:'NC',operation:'detail',identifier:'EX009484',url:profile};
 const h=harness({url:profile,fields,addressCount:0}),r=h.api.ncProfile(q);
 assert.equal(r.evidence.complete,true);assert.equal(r.evidence.fields.Name,fields.Name);
 for(const key of ['Street','City','State','Zip'])assert.equal(r.evidence.fields[key],'');
 for(const change of [{Status:'Current Active'},{'Registration #':'SL009484'}]) {
  const changed={...fields,...change};
  assert.throws(()=>harness({url:profile,fields:changed,addressCount:0}).api.ncProfile({...q,identifier:changed['Registration #']}));
 }
 for(const count of [1,2]) {
  const bad=harness({url:profile,fields,addressCount:count});bad.addressValues.pop();
  assert.throws(()=>bad.api.ncProfile(q),/ADDRESS_INCOMPLETE/);
 }
 assert.throws(()=>h.api.ncProfile({...q,identifier:'EX002017'}),/PROFILE_INCOMPLETE/);
});


test('NC grouped pending count retains every distinct pending application without dropping a card',async()=>{
 const pending={'CSL Legal Name':'Example Pending Chapter','CSL Type':'In-Process',Status:'In-Process'};
 const h=harness({cards:[active,pending,pending],total:2,profileIds:['5700751','15114421','20537566']});
 const r=await h.api.ncRows({state:'NC',operation:'search',name:"America's Charities"});
 assert.equal(r.evidence.total,3);assert.equal(r.evidence.rows.length,3);
 assert.equal(new Set(r.evidence.rows.map(row=>row.profile_url)).size,3);
 assert.equal(r.diagnostics[0].displayed,2);assert.equal(r.diagnostics[0].cards,3);
 for(const opts of [{total:1},{total:4},{total:2,profileIds:['5700751','15114421','15114421']},
   {total:2,cards:[active,pending,{...pending,'CSL Legal Name':'Different Pending Chapter'}]}]){
  await assert.rejects(harness({cards:[active,pending,pending],total:2,profileIds:['5700751','15114421','20537566'],...opts}).api.ncRows({state:'NC',operation:'search',name:"America's Charities"}));
 }
});

test('NC Achieving count groups a pending application with its exact existing legal name',async()=>{
 const licensed={...exempt,'CSL Legal Name':'Achieving Our Greatness, Inc.',License:'EX008905',Status:'Expired Exempt'};
 const pending={'CSL Legal Name':licensed['CSL Legal Name'],'CSL Type':'In-Process',Status:'In-Process'};
 const cards=[{...exempt,'CSL Legal Name':'Achieving the Best Life for Everyone (ABLE)',License:'EX012672'},licensed,pending,
  {...active,'CSL Legal Name':'Achieving Success on Purpose, Inc.',License:'SL008634'}];
 const q={state:'NC',operation:'search',name:'Achieving'};
 const opts={cards,total:3,query:q.name,profileIds:['100','101','102','103']};
 const r=await harness(opts).api.ncRows(q);
 assert.equal(r.evidence.rows.length,4);assert.equal(r.evidence.total,4);
 assert.equal(r.evidence.rows[2].Status,'In-Process');
 for(const change of [{total:2},{total:5},{cards:[...cards.slice(0,2),{...pending,'CSL Legal Name':'Different Name'},cards[3]]},
  {cards:[cards[0],licensed,{...licensed,License:'EX099999'},cards[3]]}])
  await assert.rejects(harness({...opts,...change}).api.ncRows(q));
});
