// Offline execution contract: no real browser, source requests or credentials.
const {readFileSync}=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');
class Element{
 constructor(){this.children=[];this.handlers={};this.nodes={};this.isConnected=true;this.disabled=false;}
 set innerHTML(s){this.html=s;this.nodes={};for(const m of s.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){const n=new Element();n.tag=m[1];n.disabled=/\bdisabled\b/.test(m[2]);this.nodes['#'+m[3]]=n;}}
 get innerHTML(){return this.html||'';}
 append(e){this.children.push(e);}
 remove(){this.isConnected=false;}
 querySelector(q){return this.nodes[q]||(q==='.tn-extension-row'?this.children.find(x=>x.className==='tn-extension-row'):null)||null;}
 querySelectorAll(q){return Object.values(this.nodes).filter(n=>n.tag===q);}
 addEventListener(name,f){this.handlers[name]=f;}
 showModal(){this.open=true;}
}
async function main(){
 const panel=new Element(),cell=new Element(),body=new Element(),handlers={},calls=[],messages=new Set();let releaseInitial,first=true,sourceCalls=0,sourceReady=false,failSource=false,holdSource=false,reusePublic=false;
 const facts={name:'Global Impact',coid:'CO901',period_start:'2025-07-01',period_end:'2026-06-30',expiration:'2026-12-31',checked_at:'2026-11-18',account_check:{state:'checked',records:[]}};
 const state=()=>({facts,requests:[],needs_prior_confirmation:sourceReady,eligibility:{eligible:false,reasons:[sourceReady?'Confirm prior filings':'Fresh source required']}});
 const document={body,createElement:()=>new Element(),addEventListener:(name,f)=>handlers[name]=f,querySelectorAll:q=>q==='#resultRows > tr'?[{lastElementChild:cell}]:[],getElementById:id=>{
   if(id==='resultPanel')return panel;for(const e of panel.children){if(e.id===id&&e.isConnected)return e;if(e.nodes['#'+id])return e.nodes['#'+id];}return null;
 }};
 const window={CCIdentityConfig:()=>({device_id:'offline-device'}),CCIdentity:{names:()=>[]},
   addEventListener:(n,f)=>{if(n==='message')messages.add(f);},removeEventListener:(n,f)=>messages.delete(f),
   postMessage:m=>setImmediate(()=>{for(const f of messages)f({source:window,origin:'https://staging.example',data:{...m,direction:'response',extension_id:'a'.repeat(32),observation:{state:'checked',records:[]}}});}),
   CCNYConnector:{lookup:async opts=>{sourceCalls++;assert.equal(opts.state,'TN');assert.equal(opts.extensionRefresh,'b'.repeat(48));
     if(failSource)throw new Error('Source unavailable');
     if(holdSource)await new Promise((resolve,reject)=>opts.signal.addEventListener('abort',()=>reject(new Error('Canceled')),{once:true}));
     sourceReady=true;return {state:'TN',success:true};}}
 };
 const context={window,document,location:{origin:'https://staging.example'},crypto:webcrypto,AbortSignal,AbortController,setTimeout,clearTimeout,console,
 fetch:async(url,options)=>{const p=JSON.parse(options.body);calls.push(p);
   if(first){first=false;const initial=state();return new Promise(resolve=>releaseInitial=()=>resolve({ok:true,json:async()=>initial}));}
   if(p.action==='begin-check'){sourceReady=reusePublic;return {ok:true,json:async()=>({nonce:'b'.repeat(48),ein:p.ein,name:'Global Impact',reuse_public:reusePublic})};}
   if(p.action==='refresh-failed')sourceReady=false;
   return {ok:true,json:async()=>state()};
 }};
 vm.runInNewContext(readFileSync('web-staging/tn-extensions-demo.js','utf8'),context);
 const input=Object.freeze([Object.freeze({state:'TN',ein:'521273585',organization_name:'Global Impact',status:'Upcoming Filing',extension_source_token:'signed-main-source'})]);
 window.CCTennesseeExtensions.render(input);assert.equal(sourceCalls,0,'main results must not wait for extension source work');assert.equal(calls[0].action,'status');
 const action=panel.children.at(-1),button=action.querySelector('#tnCheckExtensions');assert(!button.disabled);
 await button.handlers.click.call(button);
 releaseInitial();await new Promise(setImmediate);
 assert.equal(sourceCalls,1);assert.deepEqual(calls.slice(1).map(p=>p.action),['begin-check','status','account-observation','check']);assert.equal(input[0].status,'Upcoming Filing');
 assert(!cell.children.at(-1).querySelector('#tnFileExtension').disabled,'fresh first candidate can open prior-filing review');
 reusePublic=true;await button.handlers.click.call(button);assert.equal(sourceCalls,1,'fresh main result must not repeat a public lookup');assert.equal(calls.filter(p=>p.action==='begin-check').at(-1).source_token,'signed-main-source');assert.equal(calls.filter(p=>p.action==='account-observation').length,2,'account history must still be checked');reusePublic=false;
 failSource=true;await button.handlers.click.call(button);assert(cell.children.at(-1).querySelector('#tnFileExtension').disabled,'failed refresh cannot retain the prior eligible result');
 assert(calls.some(p=>p.action==='refresh-failed'));
 failSource=false;holdSource=true;const pending=button.handlers.click.call(button);await new Promise(setImmediate);
 handlers.submit({target:{id:'snapshotForm'}});await pending;assert(!button.disabled,'a new main run can cancel the extension check without blocking');
 console.log('PASS: post-results fresh TN lookup, scoped account observation, main status unchanged, source failure invalidates readiness, main-run cancellation.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
