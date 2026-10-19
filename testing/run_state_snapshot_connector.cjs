const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const root=process.env.CC_CONNECTOR_ROOT||path.join(__dirname,'../browser-connector');
function fixture(changes={}) {
  const calls=[],id=1,query={state:'NC',operation:'detail',identifier:'SL000448'};
  const job={tab:id,generation:2,pending:'command123',command:{id:'command123',query},registryState:'NC',activeExpiresAt:Date.now()+30000};
  const state={url:'https://www.sosnc.gov/online_services/search/charities_profile/123456',text:"America's Charities SL000448",...changes};
  const ctx={URL,Date,JSON,Promise,setTimeout,clearTimeout,
    owned:new Set([1]),isActive:()=>true,P:{TRIAL_ORIGIN:'https://fixture.onrender.com',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)},
    registryOrigin:()=> 'https://www.sosnc.gov',
    chrome:{tabs:{get:async()=>({url:state.url}),sendMessage:async(_tab,message)=>{
      if(message.action==='registry-snapshot-view'){calls.push(['view:'+message.view,{tabId:_tab}]);state.view=message.view;if(state.viewError)return {ok:false};return {ok:true};}
      return {url:state.url,public_text:state.text,...(state.modal?{capture_views:state.views||['top','expiration','financial']}:{})};}},
      debugger:{attach:async target=>{calls.push(['attach',target]);if(state.attachError)throw Error('refused');},
        sendCommand:async(target,command)=>{calls.push([command,target]);if(state.throwCommand)throw Error('capture error');
          if(state.mutate)job.generation++;
          if(command==='Page.getLayoutMetrics')return {cssContentSize:{width:1000,height:state.height||1200},cssLayoutViewport:{clientWidth:640,clientHeight:400}};
          if(state.captureHook)state.captureHook(job);
          return {data:state.imageData||(state.modal?{top:'AA==',expiration:'AQ==',financial:'Ag=='}[state.view]:'AA==')};},
        detach:async target=>calls.push(['detach',target])}}};
  vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(root,'state-snapshot-worker.js'),'utf8'),ctx);
  return {ctx,job,query,calls,state,run:()=>ctx.captureStateSnapshot(job,query,'command123')};
}
test('30 organization workflow captures keep source query and original deadlines',async()=>{
  const orgs=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/oct19-cohort.json'))).slice(0,30);
  for(const org of orgs){const h=fixture({text:org.name+' SL000448'}),expires=h.job.activeExpiresAt;
    const out=await h.run();assert.equal(out.source_url,h.state.url);assert.deepEqual(JSON.parse(JSON.stringify(out.query)),h.query);
    assert.equal(h.job.activeExpiresAt,expires);assert.equal(h.job.pending,'command123');
    assert.deepEqual(h.calls.map(x=>x[0]),['attach','Page.getLayoutMetrics','Page.captureScreenshot','detach']);
    assert.ok(h.calls.every(x=>x[1].tabId===1));}
});

test('30 Tennessee modal captures preserve three actual views, restore scroll, retain all original deadlines',async()=>{
  const orgs=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/oct19-cohort.json'))).slice(0,30);
  for(const org of orgs){const h=fixture({text:org.name+' CO42115',url:'https://tncab.tnsos.gov/portal/registered-charities-search',modal:true});
    Object.assign(h.query,{state:'TN',identifier:'CO42115'});h.job.registryState='TN';h.ctx.registryOrigin=()=> 'https://tncab.tnsos.gov';
    const expires=h.job.activeExpiresAt,out=await h.run();assert.deepEqual(Array.from(out.images),['AA==','AQ==','Ag==']);
    assert.equal(h.job.activeExpiresAt,expires);assert.equal(h.job.pending,'command123');assert.equal(h.job.snapshotCaptures,1);
    assert.deepEqual(h.calls.filter(c=>c[0].startsWith('view:')).map(c=>c[0]),['view:top','view:expiration','view:financial','view:restore']);
    assert.ok(h.calls.every(c=>c[1].tabId===1));assert.equal(h.calls.at(-1)[0],'detach');}
});

test('modal source failure is fail-soft and restores only its own source tab',async()=>{
  const h=fixture({text:'LOCAL CO42115',url:'https://tncab.tnsos.gov/portal/registered-charities-search',modal:true,viewError:true});
  Object.assign(h.query,{state:'TN',identifier:'CO42115'});h.job.registryState='TN';h.ctx.registryOrigin=()=> 'https://tncab.tnsos.gov';
  assert.equal(await h.run(),null);assert.deepEqual(h.calls.filter(c=>c[0].startsWith('view:')).map(c=>c[0]),['view:top','view:restore']);
  assert.equal(h.calls.at(-1)[0],'detach');
});

test('ordinary single-image size bound is unchanged by the TN-only page cap',async()=>{
  const data='A'.repeat(3500000),h=fixture({imageData:data});
  assert.equal((await h.run()).image,data);
});
for(const guard of ['foreign-tab','unowned','closed','inactive','wrong-command','changed-query','expired','near-expiry','wrong-host','captcha','no-permission','limit','oversized-page','attach-error','capture-error','new-generation','cancelled']){
  test('snapshot guard: '+guard,async()=>{
    const h=fixture();
    if(guard==='foreign-tab')h.job.tab=2;
    if(guard==='unowned')h.ctx.owned.clear();
    if(guard==='closed')h.job.closed=true;
    if(guard==='inactive')h.ctx.isActive=()=>false;
    if(guard==='wrong-command')h.job.command.id='another';
    if(guard==='changed-query')h.job.command.query={...h.query,identifier:'SL999999'};
    if(guard==='expired')h.job.activeExpiresAt=Date.now()-1;
    if(guard==='near-expiry')h.job.activeExpiresAt=Date.now()+2000;
    if(guard==='wrong-host')h.state.url='https://example.com/';
    if(guard==='captcha')h.state.text='Verify you are human';
    if(guard==='no-permission')delete h.ctx.chrome.debugger;
    if(guard==='limit')h.job.snapshotCaptures=4;
    if(guard==='oversized-page')h.state.height=50000;
    if(guard==='attach-error')h.state.attachError=true;
    if(guard==='capture-error')h.state.throwCommand=true;
    if(guard==='new-generation')h.state.mutate=true;
    if(guard==='cancelled')h.state.captureHook=job=>job.closed=true;
    assert.equal(await h.run(),null);
    if(h.calls.some(x=>x[0]==='attach') && guard!=='attach-error')assert.equal(h.calls.at(-1)[0],'detach');
  });
}
test('slow Chrome callback cannot publish after timeout and detaches its own tab',async()=>{
  const h=fixture();let release;
  h.ctx.chrome.debugger.attach=()=>new Promise(resolve=>release=resolve);
  const out=await h.run();assert.equal(out,null);release();
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(h.calls.map(x=>x[0]),['detach']);
});
test('UI exposes only saved same-origin PDF links and removes expiring source links',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../web-staging/identity-review.js'),'utf8');
  const elements=[];
  const node=()=>({children:[],appendChild(x){this.children.push(x);elements.push(x);},setAttribute(){},addEventListener(){}});
  const ctx={window:{},document:{createElement:node}};vm.createContext(ctx);vm.runInContext(source,ctx);
  const parent=node(),api=ctx.window.CCIdentityReview;
  for(const url of ['https://example.com/expired','javascript:alert(1)','//example.com/state.pdf','/state-snapshots/../x.pdf'])api.renderEvidence(parent,{evidence_url:url});
  assert.equal(parent.children.length,0);
  api.renderEvidence(parent,{evidence_url:'/state-snapshots/'+'a'.repeat(64)+'.pdf'});
  assert.equal(parent.children.length,1);assert.equal(parent.children[0].textContent,'View State Snapshot (PDF)');
  assert.equal(parent.children[0].rel,'noopener noreferrer');
  assert.equal(source.includes('View state record'),false);
});
