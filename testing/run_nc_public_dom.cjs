/* Public NC labels observed 2026-09-29; fake DOM only, no live browser. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../browser-connector/registry-content.js'),'utf8')
 .replace('  async function handle(m) {','  globalThis.testNC={ncLabeled,ncForm,ncRows,ncProfile,ncFilings,registryDocumentReady,handle};\n  async function handle(m) {');
const origin='https://www.sosnc.gov',profile=origin+'/online_services/search/charities_profile/5700751';
const active={'CSL Legal Name':"America's Charities",'CSL Type':'Charitable Organization',Status:'Current Active – Filing Extension Granted',License:'SL000448','Expiration Date':'5/15/2026','Extension End Date':'11/15/2026'};
const exempt={'CSL Legal Name':'YWCA of the U.S.A.','CSL Type':'CSL Exempt Organization',Status:'CSL Exempt',License:'EX003050'};
const txt=innerText=>({innerText,querySelector:()=>null});
function labels(values){return Object.entries(values).map(([key,value])=>({innerText:key+':',parentElement:txt(key+': '+value)}));}
function harness({cards=[active],total=cards.length,query="America's Charities",url=origin+'/online_services/search/Charities_Results',fields=null,periods=null,uploadLink=false,extraLabels=[],displayName=null}={}){
 const panels=new Map(),buttons=[];let clicks=0,formClicks=0;
 for(const [i,row] of cards.entries()){
  let expanded=false;
  const panel={getClientRects:()=>expanded?[{}]:[],querySelectorAll:s=>s==='.para-small > .boldSpan'?[...labels(row),...extraLabels.flatMap(labels)]:s==='a[href]'?[{getAttribute:()=>new URL(profile).pathname}]:[]};
  panels.set('a'+i,panel);buttons.push({querySelector:s=>s==='.searchHeader'?txt(row['CSL Type']==='In-Process'&&!row.License?(displayName||row['CSL Legal Name']):`${displayName||row['CSL Legal Name']} • (${row.License})`):null,getAttribute:k=>k==='aria-controls'?'a'+i:expanded?'true':'false',click:()=>{clicks++;expanded=true;}});
 }
 const addressValues=['14200 Park Meadow Dr Ste 330s','Chantilly','VA','20151-4210'];
 const address={innerText:'Address',parentElement:{querySelectorAll:s=>(s===':scope > .para-small > span'?addressValues:s==='.para-small > span'?['Address',...addressValues]:[]).map(txt)}};
 const main={innerText:`Records Found: ${total} Words: Starting With Organization Name ${query} Search Time 9/29/2026 03:50 PM`,
  querySelectorAll:s=>s==='#resultsSection .usa-accordion__button'?buttons:s==='.para-small > .boldSpan'?[...labels(fields||{}),address]:s==='a[href]'?[{getAttribute:()=>new URL(profile).pathname.replace('charities_profile','charities_filings')}]:[]};
 class Input{get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){}}
 class Select extends Input{};
 Object.defineProperty(Select.prototype,'value',Object.getOwnPropertyDescriptor(Input.prototype,'value'));
 const input=new Input(),words=new Select();words.options=[{innerText:'Starting With',value:'0'}];
 const print={checked:true,click:()=>{print.checked=false;}},button={disabled:false,getClientRects:()=>[{}],click:()=>formClicks++};
 const win={};win.top=win;
 const context=vm.createContext({window:win,URL,location:{origin,pathname:new URL(url).pathname,href:url},crypto:{randomUUID:()=> 'fixture'},
  document:{readyState:'complete',documentElement:{},getElementById:id=>panels.get(id),
   querySelector:s=>s==='main'?main:s==='#SearchCriteria'?input:s==='#Words'?words:s==='#SubmitButton'?button:s==='#Print'?print:null,
   querySelectorAll:s=>periods===null?[]:[{children:periods.map(([type,date])=>({tagName:'LI',childNodes:[{nodeType:3,textContent:type}],querySelectorAll:()=>[...(date===null?[]:[txt(date)]),...(uploadLink?[{innerText:'Upload an Attachment',querySelector:s=>s==='a'?{}:null}]:[])]}))}]},
  MutationObserver:class{observe(){}disconnect(){}},HTMLInputElement:Input,HTMLSelectElement:Select,Event:class{},setTimeout,clearTimeout,
  chrome:{runtime:{id:'fixture',onMessage:{addListener(){}}}}});
 vm.runInContext(source,context);return {api:context.testNC,context,input,words,print,button,main,panels,addressValues,clicks:()=>clicks,formClicks:()=>formClicks};
}
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
 assert.deepEqual(Object.keys(r).sort(),['documentId','ready','url','verification_pending']);
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
