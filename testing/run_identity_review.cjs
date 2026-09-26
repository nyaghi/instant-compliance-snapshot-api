const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web-staging/organization-identity.js'),'utf8');
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.events={};this.value='';this.textContent='';}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=[...nodes];}
 setAttribute(k,v){this[k]=v;} addEventListener(k,v){this.events[k]=v;} querySelectorAll(){return [];} focus(){} scrollIntoView(){}
}
const proof={source:'WA',type:'AKA / DBA',url:'https://state.example'};
const conflict={name:'Example Alternate Name',verified:false,evidence:[proof],identity_conflict:{candidate_name:'Different Entity',candidate_ein:'98-7654321',candidate_location:'Seattle, WA',source_url:'https://irs.example',explanation:'Confirm this state-listed alias before using it.'}};
async function setup(names,ny=null){
 const ids={};const element=id=>ids[id]??=(new Element());
 element('organizationName').value='Example Center';element('ein').value='12-3456789';
 const window={nyCalls:0,dispatchEvent(){},CCIdentityConfig:()=>({email:'qa@example.test',admin_passcode:'test-only',apiBase:'https://staging.example'}),CCNYConnector:{lookup:async({state})=>{if(state==='IL')return {identity:{names:[],complete:true}};window.nyCalls++;throw Error('NY discovery must not run')}}};
 const context={window,location:{origin:'https://staging.compliance-express.com'},document:{getElementById:element,createElement:t=>new Element(t),createTextNode:value=>({textContent:value})},Event:class{},performance,AbortController,setTimeout,clearTimeout,setInterval,clearInterval,fetch:async()=>({ok:true,json:async()=>({names:structuredClone(names),sources:[]})})};
 vm.runInNewContext(source,context);await element('findAlternateNames').events.click();return {ids,window};
}
test('conflicting source name is visible and unchecked, with its evidence',async()=>{
 const {ids,window}=await setup([conflict]);const row=ids.alternateNameList.children[0];
 assert.equal(row.children[0].children[0].checked,false);assert.equal(window.CCIdentity.names().length,0);
 assert.match(row.children[1].children[0].textContent,/98-7654321/);assert.equal(row.children[1].children[1].href,'https://irs.example');
});
test('user can explicitly select a reviewed flagged name',async()=>{
 const {ids,window}=await setup([conflict]);const box=ids.alternateNameList.children[0].children[0].children[0];box.checked=true;box.events.change();
 assert.equal(window.CCIdentity.names()[0],conflict.name);
});
test('discovery completes without the NY connector and retains unresolved review flags',async()=>{
 const {ids,window}=await setup([conflict]);assert.equal(ids.alternateNameList.children[0].children[0].children[0].checked,false);
 assert.equal(window.CCIdentity.ready(),true);assert.match(ids.identityElapsed.textContent,/Name discovery completed/);
 assert.equal(window.nyCalls,0);
});
test('fifteen independent discovery pages keep their own reviewed names and never queue NY',async()=>{
 const pages=await Promise.all(Array.from({length:15},(_,i)=>setup([{name:`Confirmed Alternate ${i}`,verified:true,evidence:[proof]}])));
 pages.forEach(({window},i)=>{assert.equal(window.CCIdentity.names().join(','),`Confirmed Alternate ${i}`);assert.equal(window.CCIdentity.ready(),true);assert.equal(window.nyCalls,0);});
});
test('ordinary and historical discovered names remain selected',async()=>{
 const {ids,window}=await setup([{name:'Former Example Name',verified:true,historical:true,evidence:[proof]}]);
 assert.equal(ids.alternateNameList.children[0].children[0].children[0].checked,true);assert.equal(window.CCIdentity.names()[0],'Former Example Name');
});
