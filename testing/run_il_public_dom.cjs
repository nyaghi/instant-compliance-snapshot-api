/* Actual content handler: reused empty grids, full pagination, and failures. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../browser-connector/registry-content.js'),'utf8');
async function run({total=0,activity=true,truncated=false,ready=true,largePages=false,resizeTotalChange=false}={}) {
  let clock=1000,listener,observe,loading=false,page=0,pending=false,size=10,menu=false,nextClicks=0;
  class Input {get value(){return this.v||'';} set value(v){this.v=v;} dispatchEvent(){} }
  const inputs=Object.fromEntries(['Name','Address','City','StateCode','Zip','County','FEIN','FileNumber'].map(k=>[k,new Input()]));
  const renderTarget={nodeType:1,closest:()=>renderTarget};
  const mutate=type=>observe?.([{type,target:renderTarget}]);
  const begin=()=>{if(activity){loading=true;pending=true;mutate('attributes');}};
  const button={innerText:'Search',getClientRects:()=>ready?[{}]:[],disabled:false,click:begin};
  const fields=['Name','FileNumber','Street1','City','State','PostalCode'];
  const grid={
    querySelectorAll(selector){
      if(selector==='.k-loading-mask')return [{getClientRects:()=>loading?[{}]:[]}];
      if(selector==='.k-grid-header thead th')return fields.map(field=>({dataset:{field}}));
      if(selector==='.k-grid-content tbody > tr[data-uid]')return Array.from({length:Math.min(size,Math.max(0,total-page*size))},(_,i)=>({children:[`Veterans organization ${page*size+i}`,String(10000000+page*size+i),'Street','Chicago','IL','60601'].map(innerText=>({innerText}))}));
      throw Error('Unexpected selector '+selector);
    },
    querySelector(selector){
      if(selector==='.k-pager-info')return {innerText:total?`${page*size+1} - ${Math.min(total,(page+1)*size)} of ${total} items`:'No items to display'};
      if(selector==='[role="combobox"][aria-label="Page sizes drop down"]')return largePages?{innerText:String(size),getAttribute:()=> 'sizes',click:()=>{menu=true;}}:null;
      if(selector==='button[aria-label="Go to the next page"]')return {getAttribute:()=>truncated?'true':'false',click:()=>{page++;nextClicks++;begin();}};
      throw Error('Unexpected selector '+selector);
    }
  };
  const document={
    querySelectorAll:()=>[button],
    getElementById:()=>({querySelectorAll:()=>[{innerText:'100',getClientRects:()=>menu?[{}]:[],click:()=>{size=100;page=0;menu=false;if(resizeTotalChange)total++;begin();}}]}),
    querySelector(selector){
      if(selector.startsWith('input['))return inputs[selector.match(/name="([^"]+)"/i)[1]];
      if(selector.startsWith('.k-grid'))return grid;
      throw Error('Unexpected document selector '+selector);
    }
  };
  const win={};win.top=win;
  vm.runInNewContext(source,{
    window:win,document,location:{origin:'https://charitable.illinoisattorneygeneral.gov'},
    Date:{now:()=>clock},crypto:{randomUUID:()=> 'fixture'},HTMLInputElement:Input,HTMLSelectElement:class {},Event:class {},
    MutationObserver:class{constructor(fn){observe=fn;}observe(){}disconnect(){observe=null;}},
    setTimeout(fn,ms){clock+=ms;if(pending){pending=false;loading=false;mutate('attributes');}queueMicrotask(fn);},
    chrome:{runtime:{id:'test-extension',onMessage:{addListener:fn=>listener=fn}}}
  });
  const result=await new Promise(resolve=>listener({action:'registry-il',query:{state:'IL',orgName:'Veterans'}},{id:'test-extension'},resolve));
  return {...result,nextClicks};
}
test('a reused empty grid completes after an attribute-only loading cycle',async()=>{
  const r=await run();assert.equal(r.ok,true);assert.equal(r.evidence.complete,true);assert.equal(r.evidence.total,0);
});
test('an initial empty grid without a response is never a completed negative',async()=>{
  const r=await run({activity:false});assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_IL_RESPONSE_TIMEOUT');
});
test('a broad fallback collects all 151 rows beyond the old ten-page limit',async()=>{
  const r=await run({total:151});assert.equal(r.ok,true);assert.equal(r.evidence.total,151);assert.equal(r.evidence.rows.length,151);assert.equal(r.evidence.rows.at(-1).identifier,'10000150');
});

test('the public 100-row option collects 154 rows in two pages',async()=>{
  const r=await run({total:154,largePages:true});assert.equal(r.ok,true);assert.equal(r.evidence.rows.length,154);assert.equal(r.nextClicks,1);assert.equal(r.evidence.rows.at(-1).identifier,'10000153');
});

test('a changed total during public page resize is incomplete',async()=>{
  const r=await run({total:154,largePages:true,resizeTotalChange:true});assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_IL_TOTAL_CHANGED');
});
test('truncated pagination stays incomplete',async()=>{
  const r=await run({total:151,truncated:true});assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_IL_PAGINATION_INCOMPLETE');
});
test('missing search controls are distinct from an unanswered submitted search',async()=>{
  const r=await run({ready:false});assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_IL_FORM_READY_TIMEOUT');
});
