/* Actual content handler with independently scheduled DOM and timer events. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../browser-connector/registry-content.js'),'utf8');
async function run({total=0,activity=true,truncated=false,ready=true,disabled=false,readyAt=null,largePages=false,resizeTotalChange=false,timerClamp=0,responseDelay=100,lateMutation=false,unrelatedMutation=false,detail=null,detailDelay=100}={}) {
 let clock=1000,listener,loading=false,page=0,size=10,menu=false,nextClicks=0,formReady=ready&&readyAt===null,serial=0,dialog=null,result,done=false;
 const tasks=new Map(),observers=new Set(),root={};
 const schedule=(fn,ms)=>{const id=++serial;tasks.set(id,{at:clock+ms,fn});return id;};
 const mutate=(type,target,addedNodes=[],removedNodes=[])=>{for(const o of [...observers])if(o.root===root||o.root===grid)o.fn([{type,target,addedNodes,removedNodes}]);};
 const target=selector=>({nodeType:1,closest:q=>q.includes(selector)?{}:null,matches:q=>q===selector,querySelector:()=>null});
 const renderTarget=target('.k-grid-content'),maskTarget=target('.k-loading-mask'),styleTarget=target('.unrelated');
 class Input {get value(){return this.v||'';}set value(v){this.v=v;}dispatchEvent(){}}
 const inputs=Object.fromEntries(['Name','Address','City','StateCode','Zip','County','FEIN','FileNumber'].map(k=>[k,new Input()]));
 const begin=()=>{if(activity){loading=true;mutate('attributes',maskTarget);schedule(()=>{loading=false;mutate('attributes',maskTarget);},responseDelay);
  if(lateMutation)schedule(()=>mutate('childList',renderTarget),36000);
  if(unrelatedMutation)for(let n=500;n<=40000;n+=500)schedule(()=>mutate('attributes',styleTarget),n);
 }};
 const button={innerText:'Search',getClientRects:()=>formReady?[{}]:[],disabled,click:begin};
 const fields=['Name','FileNumber','Street1','City','State','PostalCode'];
 const openDetail=()=>schedule(()=>{
  if(detail==='absent')return;
  const body=detail==='blank'?'':"Fixture Foundation\nCO Number: "+(detail==='wrong-id'?'99999999':'10000000')+"\nFEIN: 123456789\n"+(detail==='incomplete'?'':'Status: Good Standing')+"\n"+(detail==='missing-date'?'':'Annual Report Due Date: 12/31/2026');
  dialog={innerText:body,getClientRects:()=>[{}]};mutate('childList',renderTarget);
 },detailDelay);
 const grid={
  querySelectorAll(selector){
   if(selector==='.k-loading-mask')return [{getClientRects:()=>loading?[{}]:[]}];
   if(selector==='.k-grid-header thead th')return fields.map(field=>({dataset:{field}}));
   if(selector==='.k-grid-content tbody > tr[data-uid]')return Array.from({length:Math.min(size,Math.max(0,total-page*size))},(_,i)=>({
    children:['Veterans organization '+(page*size+i),String(10000000+page*size+i),'Street','Chicago','IL','60601'].map(innerText=>({innerText})),querySelector:()=>({click:openDetail})
   }));
   throw Error('Unexpected selector '+selector);
  },
  querySelector(selector){
   if(selector==='.k-pager-info')return {innerText:total?(page*size+1)+' - '+Math.min(total,(page+1)*size)+' of '+total+' items':'No items to display'};
   if(selector==='[role="combobox"][aria-label="Page sizes drop down"]')return largePages?{innerText:String(size),getAttribute:()=> 'sizes',click:()=>{menu=true;}}:null;
   if(selector==='button[aria-label="Go to the next page"]')return {getAttribute:()=>truncated?'true':'false',click:()=>{page++;nextClicks++;begin();}};
   throw Error('Unexpected selector '+selector);
  }
 };
 const document={documentElement:root,visibilityState:timerClamp?'hidden':'visible',querySelectorAll:()=>[button],
  getElementById:()=>({querySelectorAll:()=>[{innerText:'100',getClientRects:()=>menu?[{}]:[],click:()=>{size=100;page=0;menu=false;if(resizeTotalChange)total++;begin();}}]}),
  querySelector(selector){
   if(selector.startsWith('input['))return inputs[selector.match(/name="([^"]+)"/i)[1]];
   if(selector.startsWith('.k-grid'))return grid;
   if(selector==='#KendoWindowLevel1')return dialog;
   throw Error('Unexpected document selector '+selector);
  }
 };
 const win={};win.top=win;
 vm.runInNewContext(source,{window:win,document,location:{origin:'https://charitable.illinoisattorneygeneral.gov'},
  Date:{now:()=>clock},crypto:{randomUUID:()=> 'fixture'},HTMLInputElement:Input,HTMLSelectElement:class {},Event:class {},
  MutationObserver:class{constructor(fn){this.fn=fn;}observe(root){this.root=root;observers.add(this);}disconnect(){observers.delete(this);}},
  setTimeout:(fn,ms)=>schedule(fn,Math.max(ms,timerClamp)),clearTimeout:id=>tasks.delete(id),
  chrome:{runtime:{id:'test-extension',onMessage:{addListener:fn=>listener=fn}}}
 });
 if(readyAt!==null)schedule(()=>{formReady=true;button.disabled=false;mutate('attributes',styleTarget);},readyAt);
 listener({action:'registry-il',query:detail?{state:'IL',identifier:'10000000'}:{state:'IL',orgName:'Veterans'}},{id:'test-extension'},value=>{result=value;done=true;});
 for(let n=0;!done&&n<3000;n++){
  for(let i=0;i<12;i++)await Promise.resolve();
  if(done)break;
  const next=[...tasks].sort((a,b)=>a[1].at-b[1].at)[0];
  assert.ok(next,'unresolved handler without an event');tasks.delete(next[0]);clock=next[1].at;next[1].fn();
 }
 assert.ok(done,'handler terminates');assert.equal(observers.size,0,'observers disconnect');
 return {...result,nextClicks,elapsed:clock-1000};
}
test('reused empty grid completes after attribute-only loading',async()=>{const r=await run();assert.equal(r.ok,true);assert.equal(r.evidence.total,0);});
test('initial empty grid without response never becomes a negative',async()=>{assert.equal((await run({activity:false})).reason,'NY_CONNECTOR_IL_RESPONSE_TIMEOUT');});
test('all 151 rows beyond old ten-page limit are collected',async()=>{const r=await run({total:151});assert.equal(r.ok,true);assert.equal(r.evidence.rows.length,151);assert.equal(r.evidence.rows.at(-1).identifier,'10000150');});
test('public 100-row option collects 154 rows in two pages',async()=>{const r=await run({total:154,largePages:true});assert.equal(r.ok,true);assert.equal(r.evidence.rows.length,154);assert.equal(r.nextClicks,1);});
test('changed total during resize remains incomplete',async()=>{assert.equal((await run({total:154,largePages:true,resizeTotalChange:true})).reason,'NY_CONNECTOR_IL_TOTAL_CHANGED');});
test('truncated pagination remains incomplete',async()=>{assert.equal((await run({total:151,truncated:true})).reason,'NY_CONNECTOR_IL_PAGINATION_INCOMPLETE');});
test('missing controls and disabled button are distinguished',async()=>{assert.equal((await run({ready:false})).reason,'NY_CONNECTOR_IL_FORM_MISSING');assert.equal((await run({disabled:true})).reason,'NY_CONNECTOR_IL_FORM_DISABLED');});
test('in-time response survives 60-second timer delay',async()=>{const r=await run({timerClamp:60000});assert.equal(r.ok,true);assert.equal(r.evidence.total,0);assert.equal(r.diagnostics.find(e=>e.phase==='results'&&e.event==='observed').elapsed_ms,100);});
test('form readiness is observed immediately while timers are delayed',async()=>{const r=await run({readyAt:100,timerClamp:60000});assert.equal(r.ok,true);assert.equal(r.diagnostics.find(e=>e.phase==='form'&&e.event==='ready').elapsed_ms,100);});
test('absent response with delayed timers remains incomplete',async()=>{assert.equal((await run({activity:false,timerClamp:60000})).reason,'NY_CONNECTOR_IL_RESPONSE_TIMEOUT');});
test('response after original deadline is rejected',async()=>{assert.equal((await run({responseDelay:40000,timerClamp:60000})).reason,'NY_CONNECTOR_IL_RESPONSE_TIMEOUT');});
test('insufficient in-budget settling remains incomplete',async()=>{assert.equal((await run({responseDelay:34900,timerClamp:60000})).reason,'NY_CONNECTOR_IL_RESPONSE_TIMEOUT');});
test('late relevant mutation invalidates prior candidate',async()=>{assert.equal((await run({lateMutation:true,timerClamp:60000})).reason,'NY_CONNECTOR_IL_RESPONSE_TIMEOUT');});
test('unrelated styling does not reset settling',async()=>{assert.equal((await run({unrelatedMutation:true,timerClamp:60000})).ok,true);});
test('late form readiness is not accepted or mislabeled as a disabled button',async()=>{assert.equal((await run({readyAt:50000,timerClamp:60000})).reason,'NY_CONNECTOR_IL_FORM_READY_TIMEOUT');});
test('exact detail is observed despite delayed timers',async()=>{const r=await run({total:1,detail:'complete',timerClamp:60000});assert.equal(r.ok,true);assert.match(r.evidence.body,/CO Number: 10000000/);assert.equal(r.diagnostics.find(e=>e.phase==='detail'&&e.event==='ready').elapsed_ms,100);});
test('missing due date remains loaded evidence for master policy',async()=>{const r=await run({total:1,detail:'missing-date'});assert.equal(r.ok,true);assert.doesNotMatch(r.evidence.body,/Due Date/);});
test('unopened, blank, wrong-id and incomplete details stay failures',async()=>{for(const [detail,reason] of [['absent','NOT_OPENED'],['blank','BLANK'],['wrong-id','IDENTITY_INCOMPLETE'],['incomplete','IDENTITY_INCOMPLETE']]){const r=await run({total:1,detail});assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_IL_DETAIL_'+reason);}});
test('late detail is not accepted or mislabeled as missing identity',async()=>{assert.equal((await run({total:1,detail:'complete',detailDelay:30000,timerClamp:60000})).reason,'NY_CONNECTOR_IL_DETAIL_RESPONSE_TIMEOUT');});
