const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const event=()=>{const fs=[];return {addListener:f=>fs.push(f),emit:v=>fs.forEach(f=>f(v))};};
function bridge(){
 const requests=[],replies=[],ports=[],timers=[],origin='https://staging.compliance-express.com';let now=0;
 const window={top:null,addEventListener:(n,f)=>requests.push(f),postMessage:m=>replies.push(m)};window.top=window;
 const runtime={lastError:null,connect:o=>{const p={name:o.name,sent:[],onMessage:event(),onDisconnect:event(),postMessage:m=>p.sent.push(m),disconnect:()=>p.onDisconnect.emit()};ports.push(p);return p;}};
 const ctx={window,chrome:{runtime},location:{origin},setInterval:()=>0,clearInterval:()=>{},setTimeout:(fn,ms)=>{const t={fn,due:now+ms};timers.push(t);return t;},clearTimeout:t=>{if(t)t.clear=true;}};
 for(const f of ['protocol.js','staging-bridge.js'])vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../browser-connector',f),'utf8'),ctx);
 return {ports,replies,runtime,send:m=>requests[0]({source:window,origin,data:{channel:'cc-ny-staging-v1',direction:'request',lookup_id:'original-lookup-1234',...m}}),advance:ms=>{now+=ms;for(const t of [...timers])if(!t.clear&&t.due<=now){t.clear=true;t.fn();}}};
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
