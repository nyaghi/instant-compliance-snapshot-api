// Offline DOM contract, not a live-browser claim. No packages or browser launch.
const {readFileSync}=require('node:fs');
const vm=require('node:vm');const assert=require('node:assert/strict');
class Element {
  constructor(){this.children=[];this.handlers={};this.isConnected=true;this.nodes={};this.disabled=false;}
  set innerHTML(x){this.html=x;this.nodes={};for(const m of x.matchAll(/id="([^"]+)"/g))this.nodes['#'+m[1]]=new Element();}
  get innerHTML(){return this.html||'';}
  append(x){this.children.push(x);x.parent=this;}
  remove(){this.isConnected=false;}
  querySelector(q){return this.nodes[q]||null;}
  addEventListener(name,f){this.handlers[name]=f;}
}
async function main(){
  const panel=new Element(),rows=[{lastElementChild:new Element()},{lastElementChild:new Element()}];
  const ids={resultPanel:panel};const pending=[],calls=[];
  const document={createElement:()=>new Element(),querySelectorAll:q=>q==='#resultRows > tr'?rows:[],getElementById:id=>{
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
  console.log('PASS: synchronous render, metadata-only hydration, separate check, usable results, stale response guard, immutable statuses and unsupported rows.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
