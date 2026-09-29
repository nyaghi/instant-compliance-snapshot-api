const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const {harness,tick,id}=require('./run_ny_connector_lifecycle.cjs');
const TRIAL='https://fixture-final-four.onrender.com';
function event(){const all=[];return {addListener:f=>all.push(f),emit:(...a)=>all.forEach(f=>f(...a))};}
function connect(h,state,origin=TRIAL,number=1){
  const p={name:`cc-${state.toLowerCase()}-lookup-v1:`+id(number),sender:{id:h.chrome.runtime.id,frameId:0,url:origin+'/',tab:{id:1}},onMessage:event(),onDisconnect:event(),messages:[],disconnected:false,
    postMessage:m=>p.messages.push(JSON.parse(JSON.stringify(m))),disconnect:()=>{p.disconnected=true;p.onDisconnect.emit();}};
  h.chrome.runtime.onConnect.emit(p);return p;
}
function fixture(enabled=true){
  const h=harness(enabled?{trialOrigin:TRIAL}:{});let serial=0;
  if (enabled) h.tabs.get(1).url=TRIAL+'/';
  const docs=new Map(),calls=[],reloads=[];
  const create=h.chrome.tabs.create,update=h.chrome.tabs.update;
  h.chrome.tabs.create=async options=>{const tab=await create(options);docs.set(tab.id,++serial);return tab;};
  h.chrome.tabs.update=async(id,options)=>{docs.set(id,++serial);return update(id,options);};
  h.chrome.tabs.reload=async id=>{reloads.push(id);docs.set(id,++serial);};
  h.chrome.tabs.sendMessage=async(id,m)=>{
    const tab=h.tabs.get(id);
    if(m.action==='registry-ready')return {ready:true,documentId:String(docs.get(id)),url:tab.url};
    calls.push({id,...m});
    if(m.query.operation==='detail'&&m.query.state==='NV')tab.url='https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=12345678-1234-1234-1234-123456789abc';
    return {ok:true,evidence:{query:m.query,complete:true}};
  };
  return Object.assign(h,{calls,reloads});
}
for(const state of ['NV','TN']) {
  const search={state,operation:'search',name:'Example National Foundation'};
  const detail={state,operation:'detail',identifier:state==='NV'?'NV123456':'CO1234'};
  test(`${state} remains disabled in the approved connector and all approved app origins`,async()=>{
    for(const enabled of [false,true])for(const origin of ['https://staging.compliance-express.com','https://www.compliance-express.com','https://compliance-express.com']){
      const h=fixture(enabled),p=connect(h,state,origin);assert.equal(p.disconnected,true);assert.equal(h.created.length,0);
    }
    const h=fixture(false);assert.equal(connect(h,state).disconnected,true);
  });
  test(`${state} query contract rejects alternate URLs and extra filters`,()=>{
    const h=fixture();const valid=q=>vm.runInContext(`P.validQuery(${JSON.stringify(q)})`,h.context);
    assert.equal(valid(search),true);assert.equal(valid(detail),true);
    for(const q of [{...search,name:''},{...search,name:'a'.repeat(501)},{...search,city:'Other'},
      {...detail,url:'https://example.com/'},{...detail,identifier:'GA123'}, {state,ein:'123456789'}, {...detail,operation:'delete'}])assert.equal(valid(q),false);
  });
  test(`${state} uses one owned source tab and preserves the command budget`,async()=>{
    const h=fixture(),p=connect(h,state);
    assert.equal((await h.query(p,2,search)).ok,true);assert.equal((await h.query(p,3,detail)).ok,true);
    assert.equal(h.created.length,1);assert.equal(h.calls[0].action,`registry-${state.toLowerCase()}`);
    assert.equal(h.calls.every(c=>c.budgetMs>0&&c.budgetMs<=45000),true);
    assert.equal(h.tabs.get(h.created[0]).active,false);
    p.onMessage.emit({action:'finish',id:id(4)});await tick();assert.deepEqual(h.removed,h.created);assert.ok(h.tabs.has(2));
  });
  test(`${state} cannot open a detail without a completed search`,async()=>{
    const h=fixture(),p=connect(h,state);const r=await h.query(p,2,detail);
    assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_INVALID_SEQUENCE');assert.equal(h.created.length,0);
  });
  test(`${state} rejects crossed query and registry origin`,async()=>{
    const h=fixture(),p=connect(h,state);await h.query(p,2,search);
    h.tabs.get(h.created[0]).url='https://example.com/';
    assert.equal((await h.query(p,3,detail)).ok,false);assert.equal(h.calls.length,1);
  });
  test(`${state} fails safely when verification remains pending`,async()=>{
    const h=fixture(),original=h.chrome.tabs.sendMessage;
    h.chrome.tabs.sendMessage=async(id,m)=>m.action==='registry-ready'?original(id,m):{ok:false,reason:'NY_CONNECTOR_TN_VERIFICATION_OR_FORM_PENDING'};
    const p=connect(h,state),r=await h.query(p,2,search);
    assert.equal(r.ok,false);assert.equal(r.evidence,undefined);assert.equal(h.reloads.length,0);
  });
}
test('NV starts a fresh search after a detail; TN retains its result form',async()=>{
  for(const state of ['NV','TN']){
    const h=fixture(),p=connect(h,state),search={state,operation:'search',name:'Example National Foundation'};
    await h.query(p,2,search);await h.query(p,3,{state,operation:'detail',identifier:state==='NV'?'NV1234':'CO1234'});
    await h.query(p,4,{...search,name:'Reviewed Former Name'});
    assert.equal(h.created.length,1);
    assert.equal(h.calls.length,3);
    assert.equal(vm.runInContext('active.finalFourReusableForm',h.context),true);
    if(state==='NV')assert.match(h.tabs.get(h.created[0]).url,/external-GenericFilingsSearch/);
  }
});
function ncFixture({history=true}={}) {
 const h=fixture(),original=h.chrome.tabs.sendMessage;
 const url='https://www.sosnc.gov/online_services/search/charities_profile/5700751';
 h.chrome.tabs.sendMessage=async(id,m)=>{
  if(m.action==='registry-nc-form'){
   h.tabs.get(id).url='https://www.sosnc.gov/online_services/search/Charities_Results';
   return {ok:true,phase:'submitted'};
  }
  if(m.action==='registry-ready'){
   const r=await original(id,m);return {...r,documentId:r.documentId+'-'+h.tabs.get(id).url};
  }
  h.calls.push({id,...m});
  if(m.action==='registry-nc-rows')return {ok:true,evidence:{query:m.query,complete:true,rows:[{License:'SL000448',profile_url:url}]}};
  if(m.action==='registry-nc-profile')return {ok:true,evidence:{query:m.query,complete:true,fields:{Name:"America's Charities"}},filings_url:url.replace('charities_profile','charities_filings')};
  if(m.action==='registry-nc-filings')return history?{ok:true,filings:{url:h.tabs.get(id).url,complete:true,rows:[{type:'Renewal Charity',date:'11/17/2025'}]}}:{ok:false};
  throw Error('Unexpected NC command '+m.action);
 };
 return {h,url,search:{state:'NC',operation:'search',name:"America's Charities"},detail:{state:'NC',operation:'detail',identifier:'SL000448',url}};
}
test('NC binds each profile navigation to a link actually returned by its completed search',async()=>{
 const {h,search,detail}=ncFixture(),p=connect(h,'NC');
 assert.equal((await h.query(p,2,search)).ok,true);
 const result=await h.query(p,3,detail);assert.equal(result.ok,true);assert.equal(result.evidence.filings.rows[0].date,'11/17/2025');
 p.onMessage.emit({action:'finish',id:id(4)});await tick();assert.deepEqual(h.removed,h.created);
});
test('NC disallows an unobserved profile even on the correct state origin',async()=>{
 const {h,search,detail}=ncFixture(),p=connect(h,'NC');await h.query(p,2,search);
 const result=await h.query(p,3,{...detail,url:detail.url+'1'});
 assert.equal(result.ok,false);assert.equal(result.reason,'NY_CONNECTOR_INVALID_SEQUENCE');
 assert.equal(h.calls.some(m=>m.action==='registry-nc-profile'),false);
});
test('NC missing optional filing history preserves the complete profile with incomplete-history evidence',async()=>{
 const {h,search,detail}=ncFixture({history:false}),p=connect(h,'NC');await h.query(p,2,search);
 const r=await h.query(p,3,detail);assert.equal(r.ok,true);assert.equal(r.evidence.complete,true);assert.equal(r.evidence.filings.complete,false);
});
test('NC production and staging remain unable to start the trial-only path',()=>{
 for(const enabled of [true,false])for(const origin of ['https://staging.compliance-express.com','https://www.compliance-express.com'])assert.equal(connect(fixture(enabled),'NC',origin).disconnected,true);
});
test('NC protocol accepts only observed-shape charity profile URLs and bounded name searches',()=>{
 const {h,search,detail}=ncFixture(),valid=q=>vm.runInContext(`P.validQuery(${JSON.stringify(q)})`,h.context);
 assert.equal(valid(search),true);assert.equal(valid(detail),true);
 for(const q of [{...detail,url:detail.url+'?token=secret'},{...detail,url:detail.url.replace('charities_profile','business_profile')},
  {...detail,identifier:'PF123'},{...detail,url:detail.url.replace('www.sosnc.gov','example.com')},{...search,ein:'123456789'}])assert.equal(valid(q),false);
});

test('AL ordinary searches reuse only the trial-owned verified page, not another organization response',async()=>{
 const h=fixture(),p=connect(h,'AL'),query={state:'AL',operation:'search',name:'Example National Foundation'};
 assert.equal((await h.query(p,2,query)).ok,true);
 p.onMessage.emit({action:'finish',id:id(3)});await tick();
 assert.equal(h.removed.length,0);assert.equal(h.data.session.ccnyRuntime.trialAlIdle.id,h.created[0]);
 const p2=connect(h,'AL',TRIAL,2);await h.advance(3000);
 const next={...query,name:'Another National Foundation'};
 assert.deepEqual((await h.query(p2,4,next)).evidence.query,next);
 assert.equal(h.created.length,1);assert.equal(h.calls.length,2);assert.equal(h.reloads.length,0);
 p2.onMessage.emit({action:'finish',id:id(5)});await tick();await h.advance(1800001);
 assert.deepEqual(h.removed,h.created);assert.ok(h.tabs.has(2));
});

test('AL verification-required response retains the owned page for human completion without submitting a code',async()=>{
 const h=fixture(),original=h.chrome.tabs.sendMessage;
 h.chrome.tabs.sendMessage=async(id,m)=>m.action==='registry-ready'?original(id,m):{ok:false,reason:'NY_CONNECTOR_AL_VERIFICATION_REQUIRED'};
 const p=connect(h,'AL'),r=await h.query(p,2,{state:'AL',operation:'search',name:'Example'});await tick();
 assert.equal(r.reason,'NY_CONNECTOR_AL_VERIFICATION_REQUIRED');assert.equal(h.removed.length,0);
 assert.equal(h.data.session.ccnyRuntime.trialAlIdle.id,h.created[0]);
});

test('AL pool never follows a user-navigated tab or takes an unrelated source tab',async()=>{
 const h=fixture(),p=connect(h,'AL'),q={state:'AL',operation:'search',name:'Example'};
 await h.query(p,2,q);p.onMessage.emit({action:'finish',id:id(3)});await tick();
 const old=h.created[0];h.tabs.get(old).url='https://example.com/';
 const p2=connect(h,'AL',TRIAL,2);await h.advance(3000);assert.equal((await h.query(p2,4,q)).ok,true);
 assert.equal(h.created.length,2);assert.ok(h.tabs.has(old));assert.ok(h.tabs.has(2));
});

test('AL is disabled outside the trial and cannot request unsupported detail or EIN operations',()=>{
 for(const enabled of [true,false])assert.equal(connect(fixture(enabled),'AL','https://staging.compliance-express.com').disconnected,true);
 const h=fixture(),valid=q=>vm.runInContext(`P.validQuery(${JSON.stringify(q)})`,h.context);
 assert.equal(valid({state:'AL',operation:'search',name:'Example'}),true);
 assert.equal(valid({state:'AL',operation:'detail',identifier:'CO123'}),false);assert.equal(valid({state:'AL',ein:'123456789'}),false);
});
