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
  const h=harness(enabled?{trialOrigin:TRIAL,trialOnly:true}:{});let serial=0;
  if (enabled) h.tabs.get(1).url=TRIAL+'/';
  const docs=new Map(),calls=[],reloads=[];
  const create=h.chrome.tabs.create,update=h.chrome.tabs.update;
  h.chrome.tabs.create=async options=>{const tab=await create(options);docs.set(tab.id,++serial);return tab;};
  h.chrome.tabs.update=async(id,options)=>{
    const before=new URL(h.tabs.get(id).url),after=options.url&&new URL(options.url);
    // Chrome preserves the content-script document during hash-only SPA navigation.
    if(after&&(before.origin!==after.origin||before.pathname!==after.pathname||before.search!==after.search))docs.set(id,++serial);
    return update(id,options);
  };
  h.chrome.tabs.reload=async id=>{reloads.push(id);docs.set(id,++serial);};
  h.chrome.tabs.sendMessage=async(id,m)=>{
    const tab=h.tabs.get(id);
    if(m.action==='registry-ready')return {ready:true,documentId:String(docs.get(id)),url:tab.url};
    calls.push({id,...m});
    if(m.action==='registry-nv-return'){
     tab.url='https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=external-GenericFilingsSearch&tabRoute=business';
     return {ok:true};
    }
    if(m.query.operation==='detail'&&m.query.state==='NV')tab.url='https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=12345678-1234-1234-1234-123456789abc';
    return {ok:true,evidence:{query:m.query,complete:true}};
  };
  return Object.assign(h,{calls,reloads});
}

test('NM public error aborts readiness immediately rather than consuming thirty seconds',async()=>{
 const h=fixture();h.tabs.set(3,{id:3,windowId:10,url:'https://secure.nmdoj.gov/CharitySearch/'});
 let checks=0;h.chrome.tabs.sendMessage=async()=>{checks++;return {ready:false,source_failure:'REGISTRY_NM_SOURCE_ERROR'};};
 const job={tab:3,registryState:'NM',activeExpiresAt:70000,closed:false};
 await assert.rejects(h.context.registryReady(job),/NY_CONNECTOR_REGISTRY_NM_SOURCE_ERROR/);
 assert.equal(checks,1);assert.equal(job.activeExpiresAt,70000);
});

test('NV unsettled mode or bound filters reopen only its owned form once within the original deadline',async()=>{
 for(const reason of ['NY_CONNECTOR_REGISTRY_NV_MODE_NOT_SELECTED','NY_CONNECTOR_REGISTRY_NV_FORM_NOT_SETTLED']){
 for(const remaining of [60000,7000]){
  const h=fixture(),query={state:'NV',operation:'search',name:'Reviewed Alias'};await tick();
  h.tabs.set(3,{id:3,windowId:10,url:vm.runInContext("registryStart('NV')",h.context)});
  vm.runInContext('owned.add(3)',h.context);
  const job={tab:3,sender:{url:TRIAL,tab:{id:1}},registryState:'NV',activeExpiresAt:10000+remaining,closed:false,finalFourReusableForm:true};
  const send=h.chrome.tabs.sendMessage;let attempts=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>{
   if(m.action==='registry-nv'){attempts++;assert.deepEqual(m.query,query);return {ok:false,reason};}
   return send(tab,m);
  };
  assert.equal((await h.context.performRegistryQuery(job,query)).ok,false);
  assert.equal(attempts,remaining>8000?2:1);assert.equal(h.reloads.length,remaining>8000?1:0);
  assert.equal(job.activeExpiresAt,10000+remaining);assert.equal(job.finalFourSearchComplete,false);
 }
 }
});

test('NV completed searches and unrelated incomplete evidence do not trigger form recovery',async()=>{
 for(const reason of ['', 'NY_CONNECTOR_REGISTRY_RESPONSE_INCOMPLETE','NY_CONNECTOR_REGISTRY_NV_FORM_CHANGED']){
  const h=fixture(),query={state:'NV',operation:'search',name:'Reviewed Alias'};await tick();
  h.tabs.set(3,{id:3,windowId:10,url:vm.runInContext("registryStart('NV')",h.context)});
  vm.runInContext('owned.add(3)',h.context);
  const job={tab:3,sender:{url:TRIAL,tab:{id:1}},registryState:'NV',activeExpiresAt:70000,closed:false,finalFourReusableForm:true};
  const send=h.chrome.tabs.sendMessage;let attempts=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>{
   if(m.action==='registry-nv'){attempts++;return reason?{ok:false,reason}:{ok:true,evidence:{query,complete:true}};}
   return send(tab,m);
  };
  const response=await h.context.performRegistryQuery(job,query);
  assert.equal(response.ok,!reason);assert.equal(attempts,1);assert.equal(h.reloads.length,0);
  assert.equal(job.activeExpiresAt,70000);
 }
});

test('AL worker carries fresh verification through a second command in the same owned session',async()=>{
 const h=fixture(),p=connect(h,'AL');await tick();
 const original=h.chrome.tabs.sendMessage;let calls=0;
 h.chrome.tabs.sendMessage=async(tab,m)=>{
  if(m.action!=='registry-al')return original(tab,m);
  calls++;assert.equal(m.automaticVerification,true);
  const query={state:'AL',operation:'search',name:m.query.name};
  return {ok:true,evidence:calls===1?{query,complete:false,verification_pending:true,
   verification_image:'data:image/png;base64,fixture',verification_id:'fixture-image-12345678'}:
   {query,complete:true,verification_pending:false,total:0,rows:[]}};
 };
 const query={state:'AL',operation:'search',name:'Fixture Charity'};
 const first=await h.query(p,21,query);assert.equal(first.ok,true);assert.equal(first.evidence.complete,false);
 const ownedTab=h.created[0];
 const second=await h.query(p,22,{...query,verification:{id:'fixture-image-12345678',code:'ABC123'}});
 assert.equal(second.ok,true);assert.equal(second.evidence.complete,true);
 assert.equal(h.created.length,1);assert.equal(h.created[0],ownedTab);assert.equal(h.reloads.length,0);
 assert.ok(!JSON.stringify(h.data).includes('ABC123'));assert.ok(!JSON.stringify(h.data).includes('base64,fixture'));
});

test('NM name fallback reuses the owned form but requires a new query postback',async()=>{
 const h=fixture(),p=connect(h,'NM');let document=0;const submitted=[];
 const original=h.chrome.tabs.sendMessage;
 h.chrome.tabs.sendMessage=async(tab,m)=>{
  if(m.action==='registry-ready')return {ready:true,documentId:String(document),url:h.tabs.get(tab).url};
  if(m.action==='registry-nm-form'){const prior=String(document);document++;submitted.push(m.query);
   return {ok:true,documentId:prior};}
  if(m.action==='registry-nm-rows')return {ok:true,evidence:{query:m.query,complete:true,total:0,rows:[]}};
  return original(tab,m);
 };
 for(const [i,name] of ['', 'Human Trafficking Legal Center'].entries()){
  const result=await h.query(p,30+i,{state:'NM',operation:'search',ein:'461349584',name});
  assert.equal(result.ok,true);assert.equal(result.evidence.complete,true);
 }
 assert.equal(h.created.length,1);assert.equal(h.reloads.length,0);
 assert.deepEqual(submitted.map(q=>q.name),['','Human Trafficking Legal Center']);
});
test('NV search margin never extends the job deadline or another state allowance',async()=>{
 for(const state of ['NV','TN'])for(const remaining of [300000,60000,30000]) {
  const h=fixture(),query={state,operation:'search',name:'Reviewed Alias'};
  const deadline=10000+remaining;
  h.tabs.set(3,{id:3,windowId:10,url:vm.runInContext(`registryStart('${state}')`,h.context)});
  const job={tab:3,sender:{url:TRIAL,tab:{id:1}},registryState:state,activeExpiresAt:deadline,closed:false,finalFourReusableForm:true};
  assert.equal((await h.context.performRegistryQuery(job,query)).ok,true);
  const request=h.calls.find(m=>m.query);
  assert.equal(request.budgetMs,Math.min(state==='NV'?150000:45000,remaining));
  assert.equal(job.activeExpiresAt,deadline);
 }
});
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
    assert.equal(valid({...search,exact_above:20}),state==='NV');
    for(const exact_above of [0,10,21,'20',null])assert.equal(valid({...search,exact_above}),false);
    for(const q of [{...search,name:''},{...search,name:'a'.repeat(501)},{...search,city:'Other'},
      {...detail,url:'https://example.com/'},{...detail,identifier:'GA123'}, {state,ein:'123456789'}, {...detail,operation:'delete'}])assert.equal(valid(q),false);
  });
  test(`${state} uses one owned source tab and preserves the command budget`,async()=>{
    const h=fixture(),p=connect(h,state);
    assert.equal((await h.query(p,2,search)).ok,true);assert.equal((await h.query(p,3,detail)).ok,true);
    assert.equal(h.created.length,1);assert.equal(h.calls[0].action,`registry-${state.toLowerCase()}`);
    assert.equal(h.calls.every(c=>c.budgetMs>0&&c.budgetMs<=(state==='NV'&&c.query?.operation==='search'?150000:45000)),true);
    assert.equal(h.tabs.get(h.created[0]).active,false);
    p.onMessage.emit({action:'finish',id:id(4)});await tick();
    if(state==='TN')await h.advance(300001);
    assert.deepEqual(h.removed,h.created);assert.ok(h.tabs.has(2));
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
test('NV uses native Return To Search after a detail; TN retains its result form',async()=>{
  for(const state of ['NV','TN']){
    const h=fixture(),p=connect(h,state),search={state,operation:'search',name:'Example National Foundation'};
    await h.query(p,2,search);await h.query(p,3,{state,operation:'detail',identifier:state==='NV'?'NV1234':'CO1234'});
    const next=await h.query(p,4,{...search,name:'Reviewed Former Name'});
    assert.equal(next?.ok,true,'The next query must complete after a same-document route change');
    assert.equal(h.created.length,1);
    assert.equal(h.calls.filter(c=>c.query).length,3);
    assert.equal(h.calls.filter(c=>c.action==='registry-nv-return').length,state==='NV'?1:0);
    if(state==='NV')assert.equal(h.calls.find(c=>c.action==='registry-nv-return').budgetMs,8000);
    assert.equal(vm.runInContext(`activeLanes.get('${state}').finalFourReusableForm`,h.context),true);
    if(state==='NV')assert.match(h.tabs.get(h.created[0]).url,/external-GenericFilingsSearch/);
  }
});
test('NV native return still waits for its rendered search form before issuing the next query',async()=>{
 const h=fixture(),p=connect(h,'NV'),search={state:'NV',operation:'search',name:'Example National Foundation'};
 await h.query(p,2,search);await h.query(p,3,{state:'NV',operation:'detail',identifier:'NV1234'});
 const send=h.chrome.tabs.sendMessage;let ready=false;
 h.chrome.tabs.sendMessage=async(id,m)=>{
  const response=await send(id,m);
  if(m.action==='registry-ready'&&h.tabs.get(id).url.includes('external-GenericFilingsSearch'))response.ready=ready;
  return response;
 };
 assert.equal(await h.query(p,4,{...search,name:'Reviewed Former Name'}),undefined);
 assert.equal(h.calls.filter(c=>c.query).length,2);ready=true;await h.advance(300);
 assert.equal(p.messages.find(m=>m.id===id(4)&&!m.progress)?.ok,true);
 assert.equal(h.calls.filter(c=>c.query).length,3);assert.equal(h.reloads.length,0);
});

test('NV refuses a new alias when the native Return To Search action fails',async()=>{
 const h=fixture(),p=connect(h,'NV'),search={state:'NV',operation:'search',name:'Example National Foundation'};
 await h.query(p,2,search);await h.query(p,3,{state:'NV',operation:'detail',identifier:'NV1234'});
 const send=h.chrome.tabs.sendMessage;
 h.chrome.tabs.sendMessage=async(id,m)=>m.action==='registry-nv-return'?{ok:false,reason:'NY_CONNECTOR_REGISTRY_NV_RETURN_SEARCH_MISSING'}:send(id,m);
 const r=await h.query(p,4,{...search,name:'Reviewed Former Name'});
 assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_REGISTRY_NV_RETURN_SEARCH_MISSING');
 assert.equal(h.calls.filter(c=>c.query).length,2);assert.equal(h.reloads.length,0);
});

test('NV recovers one stalled return then uses a fresh form for remaining signed aliases',async()=>{
 const h=fixture(),p=connect(h,'NV'),q={state:'NV',operation:'search',name:'Example National Foundation'};
 await h.query(p,2,q);await h.query(p,3,{state:'NV',operation:'detail',identifier:'NV1234'});
 const send=h.chrome.tabs.sendMessage;let returns=0;
 h.chrome.tabs.sendMessage=async(id,m)=>{
  if(m.action==='registry-nv-return'){returns++;return {ok:false,reason:'NY_CONNECTOR_REGISTRY_NV_RETURN_READY_TIMEOUT'};}
  return send(id,m);
 };
 assert.equal((await h.query(p,4,{...q,name:'Reviewed Former Name'})).ok,true);
 assert.equal(h.data.session.ccnyRuntime.queue.find(j=>j.active).nvReturnRecoveryUsed,true);
 assert.equal(h.reloads.length,1);
 await h.query(p,5,{state:'NV',operation:'detail',identifier:'NV1234'});
 const r=await h.query(p,6,{...q,name:'Another Reviewed Name'});
 assert.equal(r.ok,true);
 assert.equal(returns,1);
 assert.equal(h.reloads.length,2);
 assert.equal(h.calls.filter(c=>c.query).at(-1).query.name,'Another Reviewed Name');
 assert.equal(h.created.length,1);
});

test('NV larger search allowance cannot extend the active lookup lifetime',async()=>{
 const h=fixture(),p=connect(h,'NV'),q={state:'NV',operation:'search',name:'Example Foundation'};
 await h.query(p,2,q);await h.advance(260000);await h.query(p,3,{...q,name:'Another Foundation'});
 assert.ok(h.calls.at(-1).budgetMs<=40000);
 await h.advance(40001);assert.equal(p.disconnected,true);
 assert.equal(p.messages.at(-1).reason,'NY_CONNECTOR_TIMEOUT');
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
function ncStalledSubmission({recover=true,processing=false}={}) {
 const f=ncFixture(),{h}=f,send=h.chrome.tabs.sendMessage;let submitted=false,retries=0;
 h.chrome.tabs.sendMessage=async(id,m)=>{
  if(m.action==='registry-nc-form'){submitted=true;return {ok:true,phase:'submitted'};}
  if(m.action==='registry-nc-retry'){
   retries++;if(recover)h.tabs.get(id).url='https://www.sosnc.gov/online_services/search/Charities_Results';
   return {ok:true,phase:'submitted'};
  }
  const r=await send(id,m);if(m.action==='registry-ready'&&submitted&&processing&&h.tabs.get(id).url.endsWith('/search_charities'))r.ready=false;
  return r;
 };
 return {...f,retries:()=>retries};
}
test('NC retries one acknowledged search only on its same enabled form',async()=>{
 const {h,search,retries}=ncStalledSubmission(),p=connect(h,'NC');
 assert.equal(await h.query(p,2,search),undefined);await h.advance(2900);assert.equal(retries(),0);
 await h.advance(300);assert.equal(retries(),1);await h.advance(250);
 assert.equal(p.messages.find(m=>m.id===id(2)&&!m.progress)?.ok,true);assert.equal(h.reloads.length,0);
});
test('NC a failed resubmission neither loops nor extends the original deadline',async()=>{
 const {h,search,retries}=ncStalledSubmission({recover:false}),p=connect(h,'NC');
 await h.query(p,2,search);await h.advance(3100);assert.equal(retries(),1);
 await h.advance(42001);assert.equal(retries(),1);
 assert.equal(p.messages.find(m=>m.id===id(2)&&!m.progress)?.reason,'NY_CONNECTOR_TAB_READY_TIMEOUT');assert.equal(h.reloads.length,0);
});
test('NC a visible Processing state is not resubmitted',async()=>{
 const {h,search,retries}=ncStalledSubmission({processing:true}),p=connect(h,'NC');
 await h.query(p,2,search);await h.advance(45001);assert.equal(retries(),0);
 assert.equal(p.messages.find(m=>m.id===id(2)&&!m.progress)?.reason,'NY_CONNECTOR_TAB_READY_TIMEOUT');
});
test('NC persistent visible verification is identified separately from a registry timeout',async()=>{
 const {h,search}=ncFixture(),send=h.chrome.tabs.sendMessage;
 h.chrome.tabs.sendMessage=async(id,m)=>m.action==='registry-ready'
  ?{...(await send(id,m)),ready:false,verification_pending:true}:send(id,m);
 const p=connect(h,'NC');assert.equal(await h.query(p,2,search),undefined);await h.advance(45001);
 const r=p.messages.find(m=>m.id===id(2)&&!m.progress);
 assert.equal(r?.ok,false);assert.equal(r?.reason,'NY_CONNECTOR_NC_VERIFICATION_PENDING');
 assert.equal(h.calls.length,0);assert.equal(h.reloads.length,0);
});

function ncVisibilityFixture({persistent=false,missingContent=false}={}){
 const f=ncFixture(),{h}=f,send=h.chrome.tabs.sendMessage,update=h.chrome.tabs.update,changes=[];
 h.tabs.get(1).active=true;
 h.chrome.tabs.query=async q=>[...h.tabs.values()].filter(t=>t.active&&t.windowId===q.windowId);
 h.chrome.tabs.update=async(id,options)=>{
  if(options.active){for(const t of h.tabs.values())if(t.windowId===h.tabs.get(id).windowId)t.active=false;changes.push(id);}
  return update(id,options);
 };
 h.chrome.tabs.sendMessage=async(id,m)=>{
  const tab=h.tabs.get(id);
  if(m.action==='registry-ready'&&tab.url.endsWith('/search_charities')&&(!tab.active||persistent)){
   tab.title='Just a moment...';
   if(missingContent)throw Error('Content receiver is not ready');
   return {...(await send(id,m)),ready:false,verification_pending:true};
  }
  tab.title='Search Charities';return send(id,m);
 };
 return {...f,changes};
}

test('NC passive verification reuses its owned document and restores the prior active tab',async()=>{
 for(const missingContent of [false,true]){
  const {h,search,changes}=ncVisibilityFixture({missingContent}),p=connect(h,'NC');
  await h.query(p,2,search);await h.advance(250);
  assert.equal(p.messages.find(m=>m.id===id(2)&&!m.progress)?.ok,true);
  assert.deepEqual(changes,[h.created[0],1]);assert.equal(h.tabs.get(1).active,true);
  assert.equal(h.created.length,1);assert.equal(h.reloads.length,0);
 }
});

test('NC persistent verification is not reloaded, retried, or given a fresh time budget',async()=>{
 const {h,search,changes}=ncVisibilityFixture({persistent:true}),p=connect(h,'NC');
 await h.query(p,2,search);await h.advance(45001);
 assert.equal(p.messages.find(m=>m.id===id(2)&&!m.progress)?.reason,'NY_CONNECTOR_NC_VERIFICATION_PENDING');
 assert.deepEqual(changes,[h.created[0],1]);assert.equal(h.reloads.length,0);assert.equal(h.calls.length,0);
});

test('NC verification recovery does not override a user switching to another tab',async()=>{
 const {h,search,changes}=ncVisibilityFixture({persistent:true}),p=connect(h,'NC');
 await h.query(p,2,search);
 h.tabs.get(h.created[0]).active=false;h.tabs.set(3,{id:3,windowId:10,url:'https://example.com',active:true});
 await h.advance(45001);
 assert.deepEqual(changes,[h.created[0]]);assert.equal(h.tabs.get(3).active,true);
});

test('NC visibility recovery does not take a source tab in another window',async()=>{
 const {h,search,changes}=ncVisibilityFixture({persistent:true}),send=h.chrome.tabs.sendMessage,p=connect(h,'NC');
 h.chrome.tabs.sendMessage=async(id,m)=>{h.tabs.get(id).windowId=99;return send(id,m);};
 await h.query(p,2,search);await h.advance(45001);
 assert.deepEqual(changes,[]);assert.equal(h.reloads.length,0);
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

test('TN consecutive workflows reuse an initialized owned page with fresh query evidence',async()=>{
 const h=fixture(),p=connect(h,'TN'),query={state:'TN',operation:'search',name:'First Charity'};
 assert.equal((await h.query(p,2,query)).ok,true);
 p.onMessage.emit({action:'finish',id:id(3)});await tick();
 assert.equal(h.removed.length,0);
 const p2=connect(h,'TN',TRIAL,2);await h.advance(3000);
 const next={...query,name:'Different Charity'};
 assert.deepEqual((await h.query(p2,4,next)).evidence.query,next);
 assert.equal(h.created.length,1);assert.equal(h.calls.length,2);assert.equal(h.reloads.length,0);
 p2.onMessage.emit({action:'finish',id:id(5)});await tick();await h.advance(300001);
 assert.deepEqual(h.removed,h.created);assert.ok(h.tabs.has(2));
});

test('TN idle reuse never carries prior search completion into a new workflow detail',async()=>{
 const h=fixture(),p=connect(h,'TN'),q={state:'TN',operation:'search',name:'First Charity'};
 await h.query(p,2,q);p.onMessage.emit({action:'finish',id:id(3)});await tick();
 const p2=connect(h,'TN',TRIAL,2);await h.advance(3000);
 const r=await h.query(p2,4,{state:'TN',operation:'detail',identifier:'CO1234'});
 assert.equal(r.ok,false);assert.equal(r.reason,'NY_CONNECTOR_INVALID_SEQUENCE');
 assert.equal(h.calls.length,1);
});

test('TN failed readiness and canceled workflows do not retain a reusable page',async()=>{
 for(const failed of [true,false]) {
  const h=fixture(),p=connect(h,'TN'),send=h.chrome.tabs.sendMessage;
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='registry-tn'&&failed?{ok:false,reason:'NY_CONNECTOR_TN_VERIFICATION_OR_FORM_PENDING'}:send(tab,m);
  await h.query(p,2,{state:'TN',operation:'search',name:'First Charity'});
  if(!failed) await vm.runInContext("close(activeLanes.get('TN'),'NY_CONNECTOR_INTERRUPTED')",h.context);
  await tick();assert.deepEqual(h.removed,h.created);assert.equal(h.data.session.ccnyRuntime.trialTnIdle,undefined);
 }
});

test('TN idle reuse preserves user navigation and rejects a moved window',async()=>{
 for(const move of [true,false]) {
  const h=fixture(),p=connect(h,'TN'),q={state:'TN',operation:'search',name:'First Charity'};
  await h.query(p,2,q);p.onMessage.emit({action:'finish',id:id(3)});await tick();const old=h.created[0];
  if(move)h.tabs.get(1).windowId=44;else h.tabs.get(old).url='https://example.com/';
  const p2=connect(h,'TN',TRIAL,2);await h.advance(3000);
  assert.equal((await h.query(p2,4,{...q,name:'Different Charity'})).ok,true);
  assert.equal(h.created.length,2);if(!move)assert.ok(h.tabs.has(old));assert.ok(h.tabs.has(2));
 }
});

test('TN initialized idle state survives restart only with live ownership, origin and expiry',async()=>{
 for(const change of ['none','expired','source-origin','window']) {
  const idle={id:3,sourceTabId:1,windowId:10,expiresAt:change==='expired'?9999:310000};
  const h=harness({trialOrigin:TRIAL,trialOnly:true,
   session:{ccnyRuntime:{schema:2,ownedTabs:[3],queue:[],trialTnIdle:idle}},
   tabs:[[1,{id:1,windowId:change==='window'?99:10,url:change==='source-origin'?'https://example.com/':TRIAL+'/'}],
    [3,{id:3,windowId:10,url:'https://tncab.tnsos.gov/portal/registered-charities-search'}]]});
  await tick();
  assert.equal(h.data.session.ccnyRuntime.trialTnIdle?.id,change==='none'?3:undefined);
  if(change==='none') {assert.equal(h.removed.length,0);await h.advance(300001);assert.deepEqual(h.removed,[3]);}
  else assert.deepEqual(h.removed,[3]);
 }
});

test('TN source closure retires only its own initialized idle page',async()=>{
 const h=fixture(),p=connect(h,'TN');await h.query(p,2,{state:'TN',operation:'search',name:'First Charity'});
 p.onMessage.emit({action:'finish',id:id(3)});await tick();
 h.chrome.tabs.onRemoved.emit(1);await tick();
 assert.deepEqual(h.removed,h.created);assert.equal(h.data.session.ccnyRuntime.trialTnIdle,undefined);assert.ok(h.tabs.has(2));
});

test('AL retained verification survives an authorized caller moving to another window',async()=>{
 const h=fixture(),p=connect(h,'AL'),q={state:'AL',operation:'search',name:'Example Foundation'};
 await h.query(p,2,q);h.tabs.get(1).windowId=44;
 p.onMessage.emit({action:'finish',id:id(3)});await tick();
 assert.equal(h.removed.length,0);
 const p2=connect(h,'AL',TRIAL,2);await h.advance(3000);
 const r=await h.query(p2,4,{...q,name:'Different Foundation'});
 assert.equal(r.ok,true);assert.equal(h.created.length,1);assert.equal(h.reloads.length,0);
 assert.equal(r.evidence.query.name,'Different Foundation');
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
for(const state of ['AL','NV','TN'])test(`${state} trial reconnect resumes its admitted registry without enabling New York`,async()=>{
 const h=fixture(),p=connect(h,state),query={state,operation:'search',name:'Example Foundation'};
 assert.equal((await h.query(p,2,query)).ok,true);p.disconnect();await tick();
 const resumed=h.connect(1,undefined,false,true);await tick();
 assert.equal(resumed.disconnected,false);assert.ok(resumed.messages.some(m=>m.action==='resumed'));
 assert.equal((await h.query(resumed,2,query)).ok,true);assert.equal(h.created.length,1);
 assert.equal(h.connect(99).disconnected,true);
});
