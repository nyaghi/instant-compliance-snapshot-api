// Offline DOM contract, not a live-browser claim. No packages or browser launch.
const {readFileSync}=require('node:fs');
const vm=require('node:vm');const assert=require('node:assert/strict');
class Element {
  constructor(){this.children=[];this.handlers={};this.isConnected=true;this.nodes={};this.disabled=false;}
  set innerHTML(x){this.html=x;this.nodes={};for(const m of x.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){const node=new Element();node.disabled=/\bdisabled\b/.test(m[2]);node.tag=m[1];this.nodes['#'+m[3]]=node;}}
  get innerHTML(){return this.html||'';}
  append(x){this.children.push(x);x.parent=this;}
  remove(){this.isConnected=false;}
  querySelector(q){return this.nodes[q]||(q==='.tn-extension-row'?this.children.find(x=>x.className==='tn-extension-row'):null)||null;}
  querySelectorAll(q){return Object.values(this.nodes).filter(x=>x.tag===q);}
  showModal(){this.open=true;}
  addEventListener(name,f){this.handlers[name]=f;}
}
async function main(){
  const panel=new Element(),rows=[{lastElementChild:new Element()},{lastElementChild:new Element()}];
  const ids={resultPanel:panel};const pending=[],calls=[];
  const body=new Element();const document={body,createElement:()=>new Element(),querySelectorAll:q=>q==='#resultRows > tr'?rows:[],getElementById:id=>{
    if(ids[id])return ids[id];for(const c of panel.children){if(c.id===id&&c.isConnected)return c;if(c.nodes['#'+id])return c.nodes['#'+id];}return null;
  }};
  const context={document,window:{},AbortController,setTimeout,clearTimeout,console,fetch:(url,options)=>{
    calls.push({url,payload:JSON.parse(options.body)});return new Promise(resolve=>pending.push(resolve));
  }};
  vm.runInNewContext(readFileSync('web-staging/tn-extensions-demo.js','utf8'),context);
  const input=Object.freeze([Object.freeze({state:'CA',ein:'131610451',status:'Current'}),Object.freeze({state:'TN',ein:'131610451',organization_name:'USO',status:'Upcoming Filing'})]);
  assert.equal(context.window.CCTennesseeExtensions.render(input),undefined,'must return synchronously');
  assert.equal(calls.length,1);assert.equal(calls[0].payload.action,'status','initial request reads saved metadata only');
  assert.equal(calls[0].url,'/api/tn-extension-demo');
  const action=panel.children[0];assert(!action.querySelector('#tnCheckExtensions').disabled,'results stay usable with metadata response pending');
  assert(!action.innerHTML.includes('Try Tennessee demo'),'no separate demo entry');
  context.window.CCTennesseeExtensions.render([Object.freeze({state:'CA',ein:'012345678'})]);
  pending.shift()({ok:true,json:async()=>({requests:[],eligibility:{reasons:['Unverified']}})});
  await new Promise(resolve=>setImmediate(resolve));assert.equal(rows[1].lastElementChild.children.length,0,'stale response cannot decorate a newer result');
  context.window.CCTennesseeExtensions.render(input);
  const actions=panel.children.at(-1),button=actions.querySelector('#tnCheckExtensions');
  const checking=button.handlers.click.call(button);assert.equal(calls.at(-1).payload.action,'check');assert.equal(calls.at(-1).payload.ein,'131610451');
  pending.pop()({ok:true,json:async()=>({requests:[],eligibility:{reasons:['Filing period unverified']}})});await checking;
  assert.equal(button.disabled,false);assert.equal(input[1].status,'Upcoming Filing','extension state does not rewrite registry status');
  assert.equal(rows[0].lastElementChild.children.length,0,'unsupported state remains untouched');
  pending.pop()({ok:true,json:async()=>({requests:[],eligibility:{reasons:['Filing period unverified']}})});
  await new Promise(resolve=>setImmediate(resolve));
  context.window.CCTennesseeExtensions.render(input);
  const facts={name:'Global Impact',coid:'CO901',period_start:'2025-07-01',period_end:'2026-06-30',expiration:'2026-12-31',checked_at:'2026-11-18'};
  const candidate={requests:[],facts,needs_prior_confirmation:true,eligibility:{eligible:false,reasons:['Confirm prior filings']}};
  pending.pop()({ok:true,json:async()=>candidate});await new Promise(resolve=>setImmediate(resolve));
  let rowBox=rows[1].lastElementChild.children.at(-1);
  assert(rowBox.querySelector('#tnFileExtension').disabled,'File Extension stays disabled until explicit check');
  const checkButton=panel.children.at(-1).querySelector('#tnCheckExtensions');const checkPromise=checkButton.handlers.click.call(checkButton);
  pending.pop()({ok:true,json:async()=>candidate});await checkPromise;
  rowBox=rows[1].lastElementChild.children.at(-1);assert(!rowBox.querySelector('#tnFileExtension').disabled,'candidate opens the workflow after check');
  rowBox.querySelector('#tnFileExtension').handlers.click();const dialog=body.children.at(-1);
  assert(dialog.innerHTML.includes('Has a renewal or this extension request already been submitted'),'workflow asks prior filings first');
  assert(!dialog.innerHTML.includes('Test case<select'),'no synthetic scenario chooser');
  const prior=dialog.querySelector('#tnInitialPrior'),prepare=dialog.querySelector('#tnPrepareExtension');
  prior.value='yes';prior.handlers.change.call(prior);assert(prepare.disabled);
  prior.value='no';prior.handlers.change.call(prior);assert(!prepare.disabled);
  const history={requests:[{status:'Receipt acknowledged',documents:{application:'/api/tn-extension-demo/documents/'+'a'.repeat(32)},confirmation:'DEMO-TN-test',submitted_at:1}],facts,eligibility:{eligible:false,reasons:['Already submitted']}};
  context.window.CCTennesseeExtensions.render(input);
  pending.pop()({ok:true,json:async()=>history});await new Promise(resolve=>setImmediate(resolve));
  rowBox=rows[1].lastElementChild.children.at(-1);
  assert(!rowBox.innerHTML.includes('View submitted test extension'),'saved filing links stay hidden until Check for extensions');
  const explicitCheck=panel.children.at(-1).querySelector('#tnCheckExtensions');const historyCheck=explicitCheck.handlers.click.call(explicitCheck);
  pending.pop()({ok:true,json:async()=>history});await historyCheck;
  assert(rowBox.innerHTML.includes('View submitted test extension'),'existing filing links appear after the explicit extension check');
  console.log('PASS: nonblocking results, stale responses, unchanged statuses, Check -> File Extension -> prior-filing confirmation; no separate demo launcher.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
