// Execute the production bridge with a bounded DOM fixture; no registry/browser I/O.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const packet=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/connected-hospital/assessment.json'),'utf8'));
const source=fs.readFileSync(path.join(__dirname,'../deployment/insight/head-start-bridge.js'),'utf8');
function setup({sender='http://127.0.0.1:8000',nonce='4d43f91a-52fa-48f3-a4b4-ef7e04a690d3',stored,unlocked=true}={}){
  const elements={},listeners={},posts=[],requests=[],timers=new Map(),rendered=[];
  let nextTimer=0,storage=stored,replaced=null,reports=0;
  class Element{
    constructor(){this.events={};this.children=[];this.style={};this.value='';this.checked=false;this.textContent='';this.hidden=false;}
    setAttribute(){} append(...children){this.children.push(...children);for(const child of children)if(child.id)elements[child.id]=child;}
    before(child){elements.card=child;} addEventListener(type,handler){this.events[type]=handler;} dispatchEvent(event){this.events[event.type]?.(event);}
  }
  for(const id of ['snapshotForm','organizationName','ein','generateReportButton','ccSalesSelectedCount','ccSalesResults'])elements[id]=new Element();
  const boxes=['PA','HI','CA','CT','CO','WA','NY','AK'].flatMap(value=>[Object.assign(new Element(),{value}),Object.assign(new Element(),{value})]);
  const opener={postMessage:(...args)=>posts.push(args)};
  const config={apiBase:'http://127.0.0.1:8766',email:'test@example.test',passcode:'fixture',unlocked,renderResults:rows=>rendered.push(rows),generateReport:()=>reports++};
  const window={opener,CCHeadStartConfig:()=>config,addEventListener:(type,handler)=>listeners[type]=handler,removeEventListener:(type,handler)=>{if(listeners[type]===handler)delete listeners[type];}};
  const context={window,document:{createElement:()=>new Element(),getElementById:id=>elements[id],querySelectorAll:()=>boxes},location:{origin:'http://127.0.0.1:8766',pathname:'/instant-compliance-snapshot',search:'',hash:sender?'#'+new URLSearchParams({hs_sender:sender,hs_nonce:nonce}):''},URLSearchParams,structuredClone,AbortController,setTimeout:()=>1,clearTimeout(){},Event:class{constructor(type){this.type=type;}},sessionStorage:{getItem:()=>storage,setItem:(_key,value)=>storage=value},history:{replaceState:(_a,_b,value)=>replaced=value},setInterval:handler=>{timers.set(++nextTimer,handler);return nextTimer;},clearInterval:id=>timers.delete(id),fetch:async(url,options)=>{requests.push({url,body:JSON.parse(options.body)});return {ok:true};}};
  vm.createContext(context);vm.runInContext(source,context);
  const deliver=(overrides={})=>listeners.message?.({source:opener,origin:sender,data:{type:'cc.headstart.assessment',nonce,assessment:structuredClone(packet)},...overrides});
  return {window,elements,boxes,config,posts,requests,timers,rendered,deliver,listeners,get storage(){return storage;},get replaced(){return replaced;},get reports(){return reports;}};
}
test('origin, source and nonce must all match before accepting any organization facts',()=>{
  const c=setup();c.deliver({origin:'https://untrusted.example'});c.deliver({source:{}});c.deliver({data:{type:'cc.headstart.assessment',nonce:'wrong',assessment:packet}});
  assert.equal(c.window.CCHeadStart.hasAssessment(),false);assert.equal(c.elements.organizationName.value,'');assert.equal(c.requests.length,0);
  c.deliver();assert.equal(c.elements.organizationName.value,packet.organization_name);assert.equal(c.elements.ein.value,'01-2345678');assert.equal(c.timers.size,0);assert.equal(c.replaced,'/instant-compliance-snapshot');
});
test('ready and acknowledgement contain only a correlation nonce, not financial or identity facts',()=>{
  const c=setup();assert.deepEqual(Object.keys(c.posts[0][0]).sort(),['nonce','type']);c.deliver();assert.deepEqual(Object.keys(c.posts[1][0]).sort(),['nonce','type']);assert.equal(c.requests.length,0);
});
test('untrusted opener gets no message and cannot activate the assessment',()=>{
  const c=setup({sender:'https://untrusted.example'});assert.equal(c.posts.length,0);assert.equal(c.listeners.message,undefined);assert.equal(c.window.CCHeadStart.hasAssessment(),false);
});
test('all 51 requirements survive reload and Standard and Sales receive the same activity suggestions',()=>{
  const c=setup({sender:null,stored:JSON.stringify(packet)});assert.equal(c.window.CCHeadStart.hasAssessment(),true);
  const selected=c.boxes.filter(b=>b.checked).map(b=>b.value);assert.equal(selected.length,14);assert(!selected.includes('AK'));
  assert.equal(c.window.CCHeadStart.forResults([]).requirements.length,51);assert.equal(c.elements.generateReportButton.textContent,'Connect to Insight');
});
test('locked gate delays suggestions and later activation does not overwrite manual changes',()=>{
  const c=setup({unlocked:false});c.deliver();assert(c.boxes.every(b=>!b.checked));c.config.unlocked=true;c.window.CCHeadStart.applyStates();assert(c.boxes.some(b=>b.checked));c.boxes.forEach(b=>b.checked=false);c.window.CCHeadStart.applyStates();assert(c.boxes.every(b=>!b.checked));
});
test('identity mismatch cannot combine results or save another organization assessment',async()=>{
  const c=setup();c.deliver();const row={organization_name:packet.organization_name,ein:packet.ein};
  const cloned=c.window.CCHeadStart.forResults([row]);cloned.profile.fiscalActual=1;assert.equal(c.window.CCHeadStart.forResults([row]).profile.fiscalActual,250000);
  assert.throws(()=>c.window.CCHeadStart.forResults([{...row,ein:'999999999'}]),/different organizations/);
  c.elements.ein.value='999999999';await assert.rejects(c.window.CCHeadStart.save(),/same organization/);assert.equal(c.requests.length,0);
});
test('authenticated saving persists assessment only and never requests a state check',async()=>{
  const c=setup();c.deliver();await c.window.CCHeadStart.save();assert.equal(c.requests.length,1);assert.equal(c.requests[0].url,'http://127.0.0.1:8766/api/head-start');assert.equal(c.requests[0].body.head_start.requirements.length,51);assert.equal(c.requests[0].body.action,'save');
});
test('Sales completion passes settled raw evidence into existing report flow without an extra search',()=>{
  const c=setup();c.deliver();const results=[{organization_name:packet.organization_name,ein:packet.ein,state:'HI',status:'Site Not Reachable',comments:'Blocked'}];
  c.listeners['cc-sales-complete']({detail:{results}});assert.equal(c.rendered[0],results);assert.equal(c.requests.length,0);assert.equal(c.elements.ccSalesInsight.textContent,'Connect to Insight');c.elements.ccSalesInsight.events.click();assert.equal(c.reports,1);
});
