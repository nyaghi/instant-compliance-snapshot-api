const fs=require('node:fs'),vm=require('node:vm'),test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../web-staging/organization-identity.js'),'utf8');
class Element {
 constructor(tag='div'){this.tag=tag;this.children=[];this.events={};this.value='';this.textContent='';}
 append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=[...nodes];}
 setAttribute(k,v){this[k]=v;} addEventListener(k,v){this.events[k]=v;} querySelectorAll(){return [];} focus(){} scrollIntoView(){}
}
const proof={source:'WA',type:'AKA / DBA',url:'https://state.example'};
const conflict={name:'Example Alternate Name',verified:false,evidence:[proof],identity_conflict:{candidate_name:'Different Entity',candidate_ein:'98-7654321',candidate_location:'Seattle, WA',source_url:'https://irs.example',explanation:'Confirm this state-listed alias before using it.'}};
async function setup(names,ny=null,response={}){
 const ids={};const element=id=>ids[id]??=(new Element());
 element('organizationName').value='Example Center';element('ein').value='12-3456789';
 const window={nyCalls:0,dispatchEvent(){},CCIdentityConfig:()=>({email:'qa@example.test',admin_passcode:'test-only',apiBase:'https://staging.example'}),CCNYConnector:{lookup:async()=>{window.nyCalls++;throw Error('Connector discovery must not run')}}};
 const context={window,location:{origin:'https://staging.compliance-express.com'},document:{getElementById:element,createElement:t=>new Element(t),createTextNode:value=>({textContent:value})},Event:class{},performance,AbortController,setTimeout,clearTimeout,setInterval,clearInterval,fetch:async()=>({ok:true,json:async()=>({names:structuredClone(names),sources:[],...response})})};
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

test('discovery displays at most seven names and explains the limit without reporting an outage',async()=>{
 const names=Array.from({length:32},(_,i)=>({name:`Confirmed Name ${i}`,verified:true,evidence:[proof]}));
 const {ids,window}=await setup(names);
 assert.equal(window.CCIdentity.names().length,7);assert.equal(ids.alternateNameList.children.length,7);
 assert.match(ids.identityMessage.textContent,/seven prioritized names/);
 assert.doesNotMatch(ids.identityMessage.textContent,/sources were unavailable/);
});

test('a capped backend response retains evidence and still permits adding a known name',async()=>{
 const names=Array.from({length:7},(_,i)=>({name:`Confirmed Name ${i}`,verified:true,evidence:[proof]}));
 const {ids,window}=await setup(names,null,{names_omitted:25,partial:true});
 assert.equal(window.CCIdentity.names().length,7);assert.match(ids.identityMessage.textContent,/seven prioritized names/);
 assert.equal(ids.addAlternateName.disabled,false);
});
test('address evidence is displayed safely and cleared when organization changes',async()=>{
 const {ids,window}=await setup([],null,{addresses:[{street:'1 Main St',city:'Boston',state:'MA',postal_code:'02110',historical:true,
  evidence:[{source:'IRS',source_date:'2024-12-31',checked_date:'2026-10-14',url:'https://irs.example/record'},
  {source:'Untrusted',url:'javascript:alert(1)'}]}]});
 const list=ids.identityAddressList;assert.equal(list.children[0].textContent,'EIN-verified organization addresses');
 const item=list.children[1];assert.equal(item.children[0].textContent,'1 Main St, Boston, MA, 02110');
 assert.equal(item.children[1].textContent,'Historical address');
 assert.equal(item.children[2].href,'https://irs.example/record');assert.match(item.children[2].textContent,/source 2024-12-31.*checked 2026-10-14/);
 assert.equal(item.children[3].href,undefined);assert.equal(window.CCIdentity.ready(),true);
 ids.organizationName.value='Another Entity';ids.organizationName.events.input();assert.equal(list.children.length,0);
});
