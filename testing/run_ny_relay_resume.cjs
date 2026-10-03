const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function relay(){
 const NY='https://charities-search.ag.ny.gov',listeners=[],requests=[],timers=[],handlers=[];
 const window={top:null,addEventListener:(n,f)=>listeners.push(f),postMessage:m=>requests.push(m)};window.top=window;
 const chrome={runtime:{id:'fixture',onMessage:{addListener:f=>handlers.push(f)}}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../browser-connector/ny-content.js'),'utf8'),{window,location:{origin:NY},chrome,document:{querySelector:()=>({})},setTimeout:(f,ms)=>{const t={f,ms};timers.push(t);return t;},clearTimeout:t=>t.cleared=true});
 const send=(m,fn,sender={id:'fixture'})=>handlers[0](m,sender,fn);
 const response=(id,query)=>listeners[0]({source:window,origin:NY,data:{channel:'cc-ny-page-v1',direction:'response',id,ok:true,evidence:{query,rows:[]},verificationRetryUsed:true}});
 return {send,response,requests,timers};
}
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
