// Execute the real staging page and extension bridge together. Transport only
// is simulated; no state data, matching, or registration results are patched.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
const events=()=>{const list=[];return {addListener:f=>list.push(f),emit:(...args)=>list.forEach(f=>f(...args))};};
async function run(count,delay,{disconnect=false,failFirst=false}={}){
  const listeners=[],ports=[],trace=[],jobs=new Map();
  const origin='https://staging.compliance-express.com';
  const window={top:null,addEventListener:(name,f)=>{if(name==='message')listeners.push(f);},
    postMessage:data=>queueMicrotask(()=>listeners.forEach(f=>f({source:window,origin,data}))),dispatchEvent:()=>{}};
  window.top=window;
  const capabilities=['lookup-tab-v1','verification-retry-v1','search-verification-retry-v1','search-schema-errors-v1','nullable-ein-v1','queue-v1','connection-recovery-v1','recovery-causes-v1','cleanup-ack-v1','timeout-recovery-v1','resume-v1','verified-detail-v1'];
  const chrome={runtime:{lastError:null,sendMessage:async()=>({ok:true,version:'0.4.1',capabilities}),connect:()=>{
    const port={onMessage:events(),onDisconnect:events(),closed:false,
      disconnect(){if(!this.closed){this.closed=true;this.onDisconnect.emit();}},
      postMessage(m){
        trace.push(m.action);
        if(m.action==='acquire')queueMicrotask(()=>this.onMessage.emit({id:m.id,ok:true}));
        if(m.action==='search')queueMicrotask(()=>this.onMessage.emit({id:m.id,ok:true,evidence:{query:m.query,rows:[]}}));
        if(m.action==='finish')setTimeout(()=>{
          if(this.closed)return;
          if(disconnect)this.disconnect();
          else {this.onMessage.emit({id:m.id,ok:true});setTimeout(()=>this.disconnect(),10);}
        },delay);
      }};ports.push(port);return port;
  }}};
  let sequence=0;
  const fetch=async(url,options)=>{
    const m=JSON.parse(options.body);let value;
    if(m.action==='start'){
      const token=String(++sequence);jobs.set(token,m);
      value={phase:'search',query:{ein:m.ein},query_id:'query-'+token,check_token:token};
    }else if(m.action==='advance'){
      const input=jobs.get(m.check_token);
      assert.equal(m.evidence.query.ein,input.ein);
      value={phase:'complete',result:{state:'NY',ein:input.ein,status:failFirst&&m.check_token==='1'?'Unable to Confirm':'Current'}};
    }else if(m.action==='fail')value={phase:'complete',result:{state:'NY',status:'Unable to Confirm',reason:m.reason}};
    else value={phase:'complete'};
    return {ok:true,json:async()=>value};
  };
  const context=vm.createContext({window,location:{origin},document:{querySelector:()=>null,getElementById:()=>null},chrome,fetch,
    crypto:crypto.webcrypto,URL,AbortSignal,Date,Map,Set,CustomEvent:class{},setTimeout,clearTimeout,setInterval,clearInterval});
  for(const file of ['browser-connector/protocol.js','browser-connector/staging-bridge.js','web-staging/ny-connector.js'])
    vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context,{filename:file});
  const inputs=Array.from({length:count},(_,i)=>({organization_name:'Fixture '+i,ein:String(100000001+i),email:'test@example.invalid',admin_passcode:'fixture',device_id:'fixture'}));
  try{
    const results=await Promise.all(inputs.map(input=>window.CCNYConnector.lookup(input)));
    assert.deepEqual(results.map(r=>r.ein),inputs.map(r=>r.ein));
    assert.deepEqual(trace,inputs.flatMap(()=>['acquire','search','finish']));
    return results;
  }finally{ports.forEach(port=>port.disconnect());}
}
test('cleanup beyond old 1.5-second limit does not fail the next lookup',async()=>{
  const results=await run(2,2500);assert.ok(results.every(r=>r.status==='Current'));
});
for(const count of [5,10,15])test(`${count} page requests queue without cross-organization evidence`,async()=>{
  assert.ok((await run(count,20)).every(r=>r.status==='Current'));
});
test('disconnect during finish releases the page slot',async()=>{
  assert.ok((await run(3,20,{disconnect:true})).every(r=>r.status==='Current'));
});
test('a failed check does not strand subsequent queued checks',async()=>{
  const rows=await run(3,20,{failFirst:true});assert.equal(rows[0].status,'Unable to Confirm');
  assert.ok(rows.slice(1).every(r=>r.status==='Current'));
});
