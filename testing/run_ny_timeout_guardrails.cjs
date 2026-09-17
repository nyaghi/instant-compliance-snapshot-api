/* Real worker lifecycle with synthetic transport delays and queue contention. */
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const sandbox=vm.createContext({URL,require:n=>n==='node:test'?{test:()=>{}}:require(n),__dirname,setImmediate});
vm.runInContext(fs.readFileSync(path.join(__dirname,'run_ny_connector_lifecycle.cjs'),'utf8'),sandbox);
const harness=()=>vm.runInContext('harness()',sandbox);
const id=n=>String(n).padStart(20,'0');const tick=()=>new Promise(r=>setImmediate(r));
test('usable form proceeds while Chrome still reports loading',async()=>{
 const h=harness(),create=h.chrome.tabs.create;
 h.chrome.tabs.create=async o=>{const tab=await create(o);tab.status='loading';return tab;};
 const p=h.connect(),r=await h.query(p,11);assert.equal(r.ok,true);assert.equal(h.created.length,1);
});
test('verification timeout retries once on a fresh owned tab and carries rejection budget',async()=>{
 const h=harness(),p=h.connect();let calls=0,carried;
 h.chrome.tabs.sendMessage=async(tab,m)=>{
  if(m.action==='ready')return {ready:true};
  if(++calls===1)return {ok:false,reason:'NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT',verificationRetryUsed:true};
  carried=m.verificationRetryUsed;return {ok:true,evidence:{query:m.query,rows:[]}};
 };
 await h.query(p,11);await h.advance(1000);
 const answer=p.messages.find(m=>m.id===id(11)&&!m.progress);
 assert.equal(answer.ok,true);assert.equal(carried,true);assert.equal(calls,2);
 assert.deepEqual([...h.created],[100,101]);assert.deepEqual([...h.removed],[100]);assert.ok(h.tabs.has(2));
});
test('persistent verification timeout stops after two attempts',async()=>{
 const h=harness(),p=h.connect();let calls=0;
 h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:(calls++,{ok:false,reason:'NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT'});
 await h.query(p,11);await h.advance(1000);
 assert.equal(calls,2);assert.equal(p.messages.find(m=>m.id===id(11)&&!m.progress).reason,'NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT');
 assert.equal(p.disconnected,true);assert.deepEqual([...h.removed],[100,101]);
});
test('never-ready form retries once and stays bounded',async()=>{
 const h=harness(),p=h.connect();h.chrome.tabs.sendMessage=async()=>({ready:false});
 await h.query(p,11);await h.advance(61000);
 assert.equal(p.messages.find(m=>m.id===id(11)&&!m.progress).reason,'NY_CONNECTOR_TAB_READY_TIMEOUT');
 assert.equal(p.disconnected,true);assert.equal(h.created.length,2);
});
test('cancellation during retry delay does not create a replacement tab',async()=>{
 const h=harness(),p=h.connect();
 h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true}:{ok:false,reason:'NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT'};
 await h.query(p,11);h.chrome.tabs.onRemoved.emit(1);await h.advance(1000);assert.equal(h.created.length,1);
});
for(const count of [5,10,15])test(count+' queued sessions survive a slow first verification without cross-organization evidence',async()=>{
 const h=harness(),ports=Array.from({length:count},(_,i)=>h.connect(i+1));let first=true;
 h.chrome.tabs.sendMessage=async(tab,m)=>{
  if(m.action==='ready')return {ready:true};
  if(first){first=false;await new Promise(resolve=>h.context.setTimeout(resolve,30000));return {ok:false,reason:'NY_CONNECTOR_VERIFY_RESPONSE_TIMEOUT'};}
  return {ok:true,evidence:{query:m.query,rows:[]}};
 };
 ports.forEach((p,i)=>p.onMessage.emit({action:'acquire',id:id(1000+i)}));await tick();
 for(let i=0;i<count;i++){
  assert.ok(ports[i].messages.some(m=>m.id===id(1000+i)&&m.ok));
  const query={ein:String(100000000+i)};await h.query(ports[i],2000+i,query);
  if(i===0){assert.ok(ports.slice(1).every(p=>!p.messages.some(m=>m.ok)));await h.advance(31000);}
  const reply=ports[i].messages.find(m=>m.id===id(2000+i)&&!m.progress);
  assert.equal(reply.ok,true);assert.equal(reply.evidence.query.ein,query.ein);
  ports[i].onMessage.emit({action:'finish',id:id(3000+i)});await tick();await h.advance(3000);
 }
 assert.equal(h.created.length,count+1);assert.deepEqual(h.created,h.removed);
});
