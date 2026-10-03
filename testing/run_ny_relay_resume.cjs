const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function relay(options={}){
 const NY='https://charities-search.ag.ny.gov',listeners=[],requests=[],timers=[],handlers=[];
 const window={top:null,addEventListener:(n,f)=>listeners.push(f),postMessage:m=>requests.push(m)};window.top=window;
 const chrome={runtime:{id:'fixture',onMessage:{addListener:f=>handlers.push(f)}}};
 const navigation=[],microtasks=[];
 window.history={back:()=>navigation.push('back')};
 const identifier='15-71-26';
 const link={textContent:identifier,href:NY+'/RegistrySearch/'+identifier,click:()=>navigation.push('detail')};
 let source=fs.readFileSync(path.join(process.env.CC_TEST_TRIAL_DIR||path.join(__dirname,'../browser-connector'),'ny-content.js'),'utf8');
 if(process.env.CC_TEST_TRIAL_DIR)source=source.replaceAll('cc-final-four-ny-page-v1','cc-ny-page-v1');
 vm.runInNewContext(source,{window,location:{origin:NY,pathname:options.detail?'/RegistrySearch/'+identifier:'/RegistrySearch'},chrome,document:{querySelector:()=>({}),querySelectorAll:()=>[link]},queueMicrotask:f=>microtasks.push(f),setTimeout:(f,ms)=>{const t={f,ms,due:Math.max(ms,options.timerClamp||0)};timers.push(t);return t;},clearTimeout:t=>t.cleared=true});
 const send=(m,fn,sender={id:'fixture'})=>handlers[0](m,sender,fn);
 const response=(id,query)=>listeners[0]({source:window,origin:NY,data:{channel:'cc-ny-page-v1',direction:'response',id,ok:true,evidence:{query,rows:[]},verificationRetryUsed:true}});
 return {send,response,requests,timers,navigation,microtasks};
}

test('trial normal NY detail link navigates after acknowledgment without a throttled page timer',()=>{
 const h=relay({timerClamp:60000});const events=[];
 h.send({action:'open-detail',query:{orgID:'15-71-26'},trialNavigation:true},r=>{assert.equal(r.ok,true);events.push('ack');assert.deepEqual(h.navigation,[]);});
 for(const task of h.microtasks)task();
 assert.deepEqual(events,['ack']);assert.deepEqual(h.navigation,['detail']);
 assert.equal(h.timers.length,0,'normal link must not wait sixty seconds for a page timer');
});

test('trial normal NY return navigates after acknowledgment without a throttled page timer',()=>{
 const h=relay({detail:true,timerClamp:60000});let acknowledged=false;
 h.send({action:'back-to-results',trialNavigation:true},r=>{acknowledged=r.ok;assert.deepEqual(h.navigation,[]);});
 for(const task of h.microtasks)task();
 assert.equal(acknowledged,true);assert.deepEqual(h.navigation,['back']);assert.equal(h.timers.length,0);
});

test('approved NY navigation retains its existing timer and observed-link safeguards',()=>{
 for(const action of ['open-detail','back-to-results']){
  const h=relay({detail:action==='back-to-results'});let response;
  h.send({action,query:{orgID:'15-71-26'}},r=>response=r);
  assert.equal(response.ok,true);assert.equal(h.microtasks.length,0);
  assert.deepEqual(h.navigation,[]);assert.equal(h.timers.length,1);h.timers[0].f();
  assert.deepEqual(h.navigation,[action==='open-detail'?'detail':'back']);
 }
 const h=relay();let response;
 h.send({action:'open-detail',query:{orgID:'99-99-99'},trialNavigation:true},r=>response=r);
 assert.equal(response.reason,'NY_CONNECTOR_DETAIL_LINK_MISSING');
 assert.equal(h.microtasks.length,0);assert.equal(h.timers.length,0);
 assert.equal(h.send({action:'open-detail',query:{orgID:'15-71-26'},trialNavigation:true},()=>{throw Error('wrong sender');},{id:'other'}),false);
 assert.equal(h.microtasks.length,0);
});
test('relay reconnect joins existing search and keeps the original timeout',()=>{
 const h=relay(),q={ein:'123456789'},m={action:'search',id:'original-request-123',query:q};const replies=[];
 h.send(m,()=>{throw Error('worker exited');});h.send(m,r=>replies.push(r));
 assert.equal(h.requests.length,1);assert.equal(h.timers.length,1);h.response(m.id,q);
 assert.equal(replies.length,1);assert.equal(replies[0].verificationRetryUsed,true);assert.equal(h.timers[0].cleared,true);
 h.send(m,r=>replies.push(r));assert.equal(replies.length,2);assert.equal(h.requests.length,1);
});
test('relay cached result cannot be reused for another EIN or command',()=>{
 const h=relay(),q={ein:'123456789'},m={action:'search',id:'original-request-123',query:q};h.send(m,()=>{});h.response(m.id,q);
 for(const change of [{query:{ein:'987654321'}},{action:'verify'}]){
  let got;h.send({...m,...change},r=>got=r);assert.equal(got.reason,'NY_CONNECTOR_INVALID_SEQUENCE');
 }assert.equal(h.requests.length,1);
});
test('relay does not restart an exhausted timeout and rejects another extension',()=>{
 const h=relay(),m={action:'search',id:'original-request-123',query:{ein:'123456789'}};h.send(m,()=>{});h.timers[0].f();
 let got;h.send(m,r=>got=r);assert.equal(got.reason,'NY_CONNECTOR_RELAY_TIMEOUT');assert.equal(h.requests.length,1);
 assert.equal(h.send({...m,id:'another-request-123'},()=>{throw Error('must not reply');},{id:'other'}),false);
});
test('permitted retry has a new attempt while reconnect preserves its command',()=>{
 const h=relay(),m={action:'search',id:'x'.repeat(80),attempt:'0:0',query:{ein:'123456789'}};
 h.send(m,()=>{});h.response(m.id,m.query);h.send({...m,attempt:'0:1'},()=>{});
 assert.equal(h.requests.length,2);h.send({...m,attempt:'0:1'},()=>{});assert.equal(h.requests.length,2);
});
