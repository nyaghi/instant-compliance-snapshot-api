const {test}=require('node:test');
const assert=require('node:assert/strict');
const {harness,tick,id}=require('./run_ny_connector_lifecycle.cjs');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');

test('Georgia public pager advances only to the visible next page in page context',()=>{
  let listener,clicks=0;const sent=[];
  const link={innerText:'2',getClientRects:()=>[{}],getAttribute:()=>"javascript:__doPostBack('datagrid_results$_ctl44$_ctl1','')",click:()=>clicks++};
  const pager={children:[{}],querySelectorAll:s=>s==='span'?[{innerText:'1'}]:[link]};
  const win={addEventListener:(type,fn)=>listener=fn,postMessage:m=>sent.push(m)};win.top=win;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../browser-connector/registry-ga-main.js'),'utf8'),{
    window:win,location:{origin:'https://verify.sos.ga.gov',pathname:'/verification/SearchResults.aspx'},
    document:{querySelector:()=>({querySelectorAll:()=>[pager]})},setTimeout:fn=>fn()
  });
  const message={channel:'cc-ga-public-pager-v1',direction:'request',id:'12345678-1234-1234-1234-123456789abc',page:2};
  listener({source:win,origin:'https://verify.sos.ga.gov',data:message});
  assert.equal(clicks,1);assert.equal(sent.at(-1).ok,true);
  listener({source:win,origin:'https://evil.example',data:message});assert.equal(clicks,1);
  listener({source:win,origin:'https://verify.sos.ga.gov',data:{...message,page:3}});assert.equal(clicks,1);assert.equal(sent.at(-1).ok,false);
  link.getAttribute=()=>"javascript:unexpected()";
  listener({source:win,origin:'https://verify.sos.ga.gov',data:message});assert.equal(clicks,1);assert.equal(sent.at(-1).ok,false);
});
function event(){const list=[];return {addListener:f=>list.push(f),emit:(...a)=>list.forEach(f=>f(...a))};}
function connect(h,state,n=1,origin='https://staging.compliance-express.com/') {
  const p={name:`cc-${state.toLowerCase()}-lookup-v1:`+id(n),sender:{id:h.chrome.runtime.id,frameId:0,url:origin,tab:{id:1}},onMessage:event(),onDisconnect:event(),messages:[],disconnected:false,
    postMessage:m=>p.messages.push(JSON.parse(JSON.stringify(m))),disconnect:()=>{p.disconnected=true;p.onDisconnect.emit();}};
  h.chrome.runtime.onConnect.emit(p);return p;
}
function registryFixture(h) {
  let serial=0;const docs=new Map();
  const create=h.chrome.tabs.create,update=h.chrome.tabs.update;
  h.chrome.tabs.create=async options=>{const t=await create(options);docs.set(t.id,++serial);return t;};
  h.chrome.tabs.update=async (id,options)=>{docs.set(id,++serial);return update(id,options);};
  h.chrome.tabs.reload=async id=>{docs.set(id,++serial);};
  h.chrome.tabs.sendMessage=async(tab,m)=>{
    const t=h.tabs.get(tab);
    if(m.action==='registry-ready')return {ready:true,url:t.url,documentId:String(docs.get(tab))};
    if(m.action==='registry-il')return {ok:true,evidence:{query:m.query,complete:true,total:0,rows:[]}};
    if(m.action==='registry-ga-form'){t.url='https://verify.sos.ga.gov/verification/SearchResults.aspx';docs.set(tab,++serial);return {ok:true,phase:'submitted'};}
    if(m.action==='registry-ga-rows')return {ok:true,rows:[],page:1,next:false};
    throw Error('Unexpected action: '+m.action);
  };
}
test('IL exact EIN query returns complete evidence through the existing queue',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'IL');
  const result=await h.query(p,20,{state:'IL',ein:'363673599'});
  assert.equal(result.ok,true);assert.equal(result.evidence.complete,true);
  assert.match(h.tabs.get(h.created[0]).url,/illinoisattorneygeneral/);
  p.onMessage.emit({action:'finish',id:id(21)});await tick();assert.deepEqual(h.removed,h.created);assert.ok(h.tabs.has(2));
});
test('Illinois reuses the verified public form between name and EIN fallbacks',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'IL');
  assert.equal((await h.query(p,20,{state:'IL',ein:'363673599'})).ok,true);
  let reloaded=0;const reload=h.chrome.tabs.reload;
  h.chrome.tabs.reload=async id=>{reloaded++;return reload(id);};
  assert.equal((await h.query(p,21,{state:'IL',orgName:'Control Foundation'})).ok,true);
  assert.equal(reloaded,0);assert.equal(h.created.length,1);
});

test('Illinois starts a fresh form after an opened detail instead of reusing its dialog',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'IL');
  assert.equal((await h.query(p,20,{state:'IL',identifier:'01015532'})).ok,true);
  let reloaded=0;const reload=h.chrome.tabs.reload;
  h.chrome.tabs.reload=async id=>{reloaded++;return reload(id);};
  assert.equal((await h.query(p,21,{state:'IL',orgName:'Control Foundation'})).ok,true);
  assert.equal(reloaded,1);assert.equal(h.created.length,1);
});
test('Georgia normal form navigation produces a completed empty result',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'GA');
  const result=await h.query(p,20,{state:'GA',orgName:'Nonexistent Control'});
  assert.equal(result.ok,true);assert.equal(result.evidence.total,0);
});

test('Georgia collects both result pages before declaring complete',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'GA');
  const original=h.chrome.tabs.sendMessage;let page=1;
  h.chrome.tabs.sendMessage=async(tab,m)=>{
    if(m.action==='registry-ga-rows')return {ok:true,rows:[{identifier:'CH00000'+page}],page,next:page===1};
    if(m.action==='registry-ga-next'){assert.equal(m.page,2);page=2;return {ok:true};}
    const r=await original(tab,m);if(m.action==='registry-ready')r.documentId+='-page-'+page;return r;
  };
  const r=await h.query(p,20,{state:'GA',orgName:'Ronald McDonald House'});
  assert.equal(r.ok,true);assert.equal(r.evidence.complete,true);assert.equal(r.evidence.total,2);
  assert.deepEqual(r.evidence.rows.map(x=>x.identifier),['CH000001','CH000002']);
});

test('Georgia refreshes an expired detail link by the same search and license identifier',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'GA');
  const original=h.chrome.tabs.sendMessage;let searches=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>{
    if(m.action==='registry-ga-form')searches++;
    if(m.action==='registry-ga-rows')return {ok:true,rows:[{identifier:'CH002627',detail_key:searches===1?'11111111-1111-1111-1111-111111111111':'22222222-2222-2222-2222-222222222222'}],page:1,next:false};
    if(m.action==='registry-ga-detail'){
      assert.match(h.tabs.get(tab).url,/result=22222222-2222-2222-2222-222222222222$/);
      return {ok:true,evidence:{query:m.query,complete:true,body:'CH002627'}};
    }
    return original(tab,m);
  };
  assert.equal((await h.query(p,20,{state:'GA',orgName:'Ronald McDonald House'})).ok,true);
  const detail={state:'GA',identifier:'CH002627',detail_key:'11111111-1111-1111-1111-111111111111'};
  const r=await h.query(p,21,detail);assert.equal(r.ok,true);assert.equal(searches,2);assert.deepEqual(r.evidence.query,detail);
});

test('Illinois unopened detail gets one fresh-form retry and preserves final reason',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'IL');
  const original=h.chrome.tabs.sendMessage;let attempts=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='registry-il' ? (++attempts,{ok:false,reason:'NY_CONNECTOR_IL_DETAIL_NOT_OPENED'}) : original(tab,m);
  const result=await h.query(p,20,{state:'IL',identifier:'01015532'});
  assert.equal(attempts,2);assert.equal(result.ok,false);assert.equal(result.reason,'NY_CONNECTOR_IL_DETAIL_NOT_OPENED');
});

test('Illinois unanswered search retries once, without treating an old empty grid as evidence',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'IL');
  const original=h.chrome.tabs.sendMessage;let attempts=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='registry-il' && ++attempts===1 ? {ok:false,reason:'NY_CONNECTOR_IL_RESPONSE_TIMEOUT'} : original(tab,m);
  const r=await h.query(p,20,{state:'IL',orgName:'Commanding Heights Foundation'});
  assert.equal(r.ok,true);assert.equal(attempts,2);assert.equal(r.evidence.total,0);
});

test('Georgia unnumbered exemption refreshes by bound name and location, not first row',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'GA');
  const original=h.chrome.tabs.sendMessage;let searches=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>{
    if(m.action==='registry-ga-form')searches++;
    if(m.action==='registry-ga-rows')return {ok:true,rows:[
      {identifier:'',name:'Unrelated',location:'Boston MA',detail_key:'33333333-3333-3333-3333-333333333333'},
      {identifier:'',name:'USAFA Endowment, Inc.',location:'Colorado Springs CO',detail_key:searches===1?'11111111-1111-1111-1111-111111111111':'22222222-2222-2222-2222-222222222222'}
    ],page:1,next:false};
    if(m.action==='registry-ga-detail'){
      assert.match(h.tabs.get(tab).url,/result=22222222-2222-2222-2222-222222222222$/);
      return {ok:true,evidence:{query:m.query,complete:true,body:'USAFA Endowment, Inc. Exempt'}};
    }
    return original(tab,m);
  };
  assert.equal((await h.query(p,20,{state:'GA',orgName:'USAFA'})).ok,true);
  const q={state:'GA',identifier:'',record_name:'USAFA Endowment, Inc.',record_location:'Colorado Springs CO',detail_key:'11111111-1111-1111-1111-111111111111'};
  const r=await h.query(p,21,q);assert.equal(r.ok,true);assert.equal(searches,2);assert.deepEqual(r.evidence.query,q);
});

test('Georgia EXEMPT marker selects the bound name and location after link refresh',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'GA');
  const original=h.chrome.tabs.sendMessage;let searches=0;
  h.chrome.tabs.sendMessage=async(tab,m)=>{
    if(m.action==='registry-ga-form')searches++;
    if(m.action==='registry-ga-rows')return {ok:true,rows:[
      {identifier:'EXEMPT',name:'Unrelated Foundation',location:'Atlanta GA',detail_key:'33333333-3333-3333-3333-333333333333'},
      {identifier:'EXEMPT',name:'ACOEL Foundation',location:'Atlanta GA',detail_key:'44444444-4444-4444-4444-444444444444'},
      {identifier:'EXEMPT',name:'ACOEL Foundation',location:'Washington DC 20036',detail_key:searches===1?'11111111-1111-1111-1111-111111111111':'22222222-2222-2222-2222-222222222222'}
    ],page:1,next:false};
    if(m.action==='registry-ga-detail'){
      assert.match(h.tabs.get(tab).url,/result=22222222-2222-2222-2222-222222222222$/);
      return {ok:true,evidence:{query:m.query,complete:true,body:'ACOEL Foundation EXEMPT'}};
    }
    return original(tab,m);
  };
  assert.equal((await h.query(p,20,{state:'GA',orgName:'Foundation'})).ok,true);
  const q={state:'GA',identifier:'EXEMPT',record_name:'ACOEL Foundation',record_location:'Washington DC 20036',detail_key:'11111111-1111-1111-1111-111111111111'};
  const r=await h.query(p,21,q);assert.equal(r.ok,true);assert.equal(searches,2);assert.deepEqual(r.evidence.query,q);
});

test('Georgia EXEMPT detail cannot be requested with only its shared marker',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'GA');
  const r=await h.query(p,20,{state:'GA',identifier:'EXEMPT',detail_key:'11111111-1111-1111-1111-111111111111'});
  assert.equal(r,undefined);assert.equal(h.created.length,0);
});
test('a state-specific port rejects evidence requested for a different state',async()=>{
  const h=harness();registryFixture(h);const p=connect(h,'IL');
  const result=await h.query(p,20,{state:'GA',orgName:'Control'});
  assert.equal(result.ok,false);assert.equal(h.created.length,0);
});
test('new states are staging-only and cannot be opened from production',async()=>{
  const h=harness();registryFixture(h);
  for(const state of ['IL','GA'])assert.equal(connect(h,state,1,'https://www.compliance-express.com/').disconnected,true);
  assert.equal(h.created.length,0);
});
test('New York verification recovery does not block Illinois',async()=>{
  const h=harness({local:{ccnyRepair:{phase:'failed',nextAllowedAt:500000,reason:'NY_CONNECTOR_RECOVERY_REJECTED'}}});registryFixture(h);
  const p=connect(h,'IL');assert.equal((await h.query(p,20,{state:'IL',ein:'363673599'})).ok,true);
  assert.equal(h.repairs.length,0);
});
test('new states use the same FIFO queue and separate owned tabs',async()=>{
  const h=harness();registryFixture(h);const il=connect(h,'IL');
  assert.equal((await h.query(il,20,{state:'IL',ein:'363673599'})).ok,true);
  const ga=connect(h,'GA',2);ga.onMessage.emit({action:'acquire',id:id(21)});await tick();assert.equal(ga.messages.at(-1).position,1);
  il.onMessage.emit({action:'finish',id:id(22)});await tick();await h.advance(3000);
  assert.equal((await h.query(ga,23,{state:'GA',orgName:'Control'})).ok,true);
  assert.equal(h.created.length,2);assert.notEqual(h.created[0],h.created[1]);
});
