const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const event=()=>{const fs=[];return {addListener:f=>fs.push(f),emit:v=>fs.forEach(f=>f(v))};};
function bridge(trial=false){
 const requests=[],replies=[],ports=[],timers=[],packaged=trial&&process.env.CC_TEST_TRIAL_DIR,
 origin=trial?(packaged?process.env.CC_TEST_TRIAL_ORIGIN:'https://fixture-final-four.onrender.com'):'https://staging.compliance-express.com';let now=0;
 const window={top:null,addEventListener:(n,f)=>requests.push(f),postMessage:m=>replies.push(m)};window.top=window;
 const runtime={lastError:null,connect:o=>{const p={name:o.name,sent:[],onMessage:event(),onDisconnect:event(),postMessage:m=>p.sent.push(m),disconnect:()=>p.onDisconnect.emit()};ports.push(p);return p;}};
 const ctx={window,chrome:{runtime},location:{origin},setInterval:()=>0,clearInterval:()=>{},setTimeout:(fn,ms)=>{const t={fn,due:now+ms};timers.push(t);return t;},clearTimeout:t=>{if(t)t.clear=true;}};
 for(const f of ['protocol.js','staging-bridge.js']){
  let source=fs.readFileSync(path.join(packaged||path.join(__dirname,'../browser-connector'),f),'utf8');
  if(trial&&f==='protocol.js')source=source.replace('const TRIAL_ORIGIN = "";',`const TRIAL_ORIGIN = ${JSON.stringify(origin)};`)
   .replace('function registryAllowed(state, origin) {','function registryAllowed(state, origin) { if (origin !== TRIAL_ORIGIN || state === "NY") return false;');
  vm.runInNewContext(source,ctx);
 }
 return {ports,replies,runtime,send:m=>requests[0]({source:window,origin,data:{channel:packaged?'cc-final-four-trial-v1':'cc-ny-staging-v1',direction:'request',lookup_id:'original-lookup-1234',...m}}),advance:ms=>{now+=ms;for(const t of [...timers])if(!t.clear&&t.due<=now){t.clear=true;t.fn();}}};
}
test('bridge reconnect replays same search ID/query and reports diagnostic reason',()=>{
 const h=bridge(),m={action:'search',id:'original-command-1234',query:{ein:'123456789'}};h.send(m);h.runtime.lastError={message:'worker connection lost'};h.ports[0].disconnect();
 assert.equal(h.ports.length,2);assert.equal(h.ports[1].name,'cc-ny-resume-v1:original-lookup-1234');h.ports[1].onMessage.emit({action:'resumed'});
 assert.equal(h.ports[1].sent[0].disconnectReason,'worker connection lost');assert.equal(h.ports[1].sent[1].id,m.id);assert.deepEqual(h.ports[1].sent[1].query,m.query);
 h.ports[1].onMessage.emit({id:m.id,ok:true});assert.ok(h.replies.some(r=>r.id===m.id&&r.ok));h.send({action:'finish',id:'final-command-1234'});h.ports[1].disconnect();
});
test('bridge reconnect does not retransmit an acknowledged query',()=>{
 const h=bridge(),id='original-command-1234';h.send({action:'acquire',id});h.ports[0].onMessage.emit({id,ok:true});h.ports[0].disconnect();h.ports[1].onMessage.emit({action:'resumed'});
 assert.equal(h.ports[1].sent.length,1);h.send({action:'finish',id:'final-command-1234'});h.ports[1].disconnect();
});
test('missing restart handshake terminates after three reconnect attempts',()=>{
 const h=bridge(),id='original-command-1234';h.send({action:'acquire',id});h.ports[0].disconnect();
 h.advance(10000);h.advance(2000);h.advance(10000);h.advance(3000);h.advance(10000);
 assert.equal(h.ports.length,4);assert.ok(h.replies.some(r=>r.id===id&&r.reason==='NY_CONNECTOR_INTERRUPTED'));
});
for(const state of ['IL','GA','AL','NC','NV','TN'])test(`trial bridge retains ${state} after admission and refuses registry switching`,()=>{
 const h=bridge(true),acquire='acquire-command-1234',search='search-command-12345';
 h.send({action:'acquire',id:acquire,intent:state});h.ports[0].onMessage.emit({id:acquire,ok:true});
 const query=['IL','GA'].includes(state)?{state,orgName:'Example Foundation'}:{state,operation:'search',name:'Example Foundation'};
 h.send({action:'search',id:search,query});assert.equal(h.ports[0].sent.at(-1).id,search);
 assert.equal(h.replies.some(r=>r.id===search&&!r.ok),false);
 h.send({action:'search',id:'crossed-command-1234',intent:state==='NC'?'NV':'NC',query});
 assert.equal(h.replies.at(-1).reason,'NY_CONNECTOR_INVALID_SEQUENCE');
 h.ports[0].disconnect();h.ports[1].onMessage.emit({action:'resumed'});
 assert.deepEqual(h.ports[1].sent.at(-1).query,query);
});

test('trial bridge forwards observed Nevada reservation detail identifiers and their replies',()=>{
 for(const identifier of ['NV20121738342','C20190204-2019','NR20230725-22746']){
  const h=bridge(true),acquire='acquire-command-1234',id='detail-command-12345';
  h.send({action:'acquire',id:acquire,intent:'NV'});h.ports[0].onMessage.emit({id:acquire,ok:true});
  const query={state:'NV',operation:'detail',identifier};h.send({action:'search',id,query});
  assert.deepEqual(h.ports[0].sent.at(-1).query,query);
  h.ports[0].onMessage.emit({id,ok:true,evidence:{query,complete:true}});
  assert.equal(h.replies.at(-1).id,id);assert.equal(h.replies.at(-1).ok,true);
 }
});

test('invalid admitted trial NV commands fail promptly without sending a registry request',()=>{
 for(const identifier of ['C2019-1','NR20230725-22746/path','C20190204-2019?x=1','NV123/','https://example.com']){
  const h=bridge(true),acquire='acquire-command-1234',id='invalid-command-1234';
  h.send({action:'acquire',id:acquire,intent:'NV'});h.ports[0].onMessage.emit({id:acquire,ok:true});
  h.send({action:'search',id,query:{state:'NV',operation:'detail',identifier}});
  assert.equal(h.ports[0].sent.length,1);assert.equal(h.replies.at(-1).id,id);
  assert.equal(h.replies.at(-1).reason,'NY_CONNECTOR_INVALID_SEQUENCE');
 }
});

test('trial bridge transports the AL image-bound answer without changing its query',()=>{
 const h=bridge(true),acquire='acquire-command-1234',id='verify-command-12345';
 h.send({action:'acquire',id:acquire,intent:'AL'});h.ports[0].onMessage.emit({id:acquire,ok:true});
 const query={state:'AL',operation:'search',name:'Fixture Charity',verification:{id:'fixture-image-12345678',code:'ABC123'}};
 h.send({action:'search',id,query});assert.deepEqual(h.ports[0].sent.at(-1).query,query);
 h.ports[0].onMessage.emit({id,ok:true,evidence:{query:{state:'AL',operation:'search',name:'Fixture Charity'},complete:true}});
 assert.equal(h.replies.at(-1).ok,true);
});

test('trial bridge transports the approved Nevada narrowing plan and exact-match evidence unchanged',()=>{
 const h=bridge(true),acquire='acquire-command-1234',id='narrow-command-12345';
 h.send({action:'acquire',id:acquire,intent:'NV'});h.ports[0].onMessage.emit({id:acquire,ok:true});
 const query={state:'NV',operation:'search',name:'Example',exact_above:20};
 h.send({action:'search',id,query});assert.deepEqual(h.ports[0].sent.at(-1).query,query);
 const evidence={state:'NV',query,complete:true,total:0,rows:[],verification_pending:false,search_mode:'EXACT_MATCH',broad_total:5463};
 h.ports[0].onMessage.emit({id,ok:true,evidence});assert.equal(h.replies.at(-1).ok,true);assert.deepEqual(h.replies.at(-1).evidence,evidence);
});
