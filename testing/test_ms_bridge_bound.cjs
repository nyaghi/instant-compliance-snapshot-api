// Exercise the actual installed bridge with synthetic ports, never registry traffic.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path');
const source=fs.readFileSync(process.env.CC_MS_BRIDGE_SOURCE||path.join(__dirname,'../deployment/staging_connector/staging-bridge.js'),'utf8');
const roster=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/ms-bound-recovery/LOCAL-70.json')));
function harness(){
  const ports=[],replies=[],listeners=[];
  const origin='https://charityclarity-final-four-29-2.onrender.com';
  const window={innerWidth:1200,outerWidth:1200,innerHeight:800,outerHeight:900,screenX:0,screenY:0,
    addEventListener:(kind,fn)=>{if(kind==='message')listeners.push(fn);},postMessage:m=>replies.push(m)};
  window.top=window;
  const chrome={runtime:{id:'test-extension',onMessage:{addListener:()=>{}},
    sendMessage:async()=>({ok:true}),connect:({name})=>{
      let onMessage;const port={name,sent:[],onMessage:{addListener:fn=>onMessage=fn},onDisconnect:{addListener:()=>{}},
        postMessage(m){port.sent.push(m);onMessage({id:m.id,ok:true});},
        emit(m){onMessage(m);},disconnect(){}};ports.push(port);return port;
    }}};
  const context=vm.createContext({window,location:{origin,pathname:'/'},document:{visibilityState:'visible'},chrome,
    CCNYProtocol:{TRIAL_ORIGIN:origin,allowedOrigin:()=>true,validId:x=>typeof x==='string'&&x.length>0,
      validQuery:q=>q?.state==='MS'||!!q?.ein,registryAllowed:()=>true},
    setInterval:()=>1,clearInterval:()=>{},setTimeout:()=>1,clearTimeout:()=>{},console,Date,Map,Set});
  vm.runInContext(source,context);
  async function send(action,lookup_id,query,intent){
    const data={channel:'cc-final-four-trial-v1',direction:'request',id:`request-${replies.length}`,action,lookup_id,query,intent};
    for(const fn of listeners)await fn({source:window,origin,data});return replies.at(-1);
  }
  return {ports,replies,send};
}
(async()=>{
  const cases=[];
  for(const org of roster){
    const h=harness(),q={state:'MS',operation:'search',name:org.name};
    await h.send('acquire','first',null,'MS');
    await h.send('search','first',q);
    assert.match(h.ports[0].name,/^cc-ms-lookup/);
    // Worker closes itself after the first incomplete response.
    h.ports[0].emit({action:'closed',reason:'NY_CONNECTOR_INCOMPLETE'});
    const n=h.ports.length;
    const rejected=await h.send('search','first',q);
    assert.equal(rejected.ok,false);assert.equal(rejected.reason,'NY_CONNECTOR_INVALID_SEQUENCE');
    assert.equal(h.ports.length,n,'orphaned MS query must not create a NY port');
    await h.send('finish','first');
    await h.send('acquire','second',null,'MS');await h.send('search','second',q);
    assert.match(h.ports.at(-1).name,/^cc-ms-lookup/);
    assert.ok(!h.ports.some(p=>p.name.startsWith('cc-ny-lookup')));
    cases.push({...org,orphan_rejected:true,reacquired_state:'MS'});
  }
  // Preserve mature NY admission/default behavior and refuse no valid MS work.
  const h=harness();await h.send('acquire','ny',null);await h.send('search','ny',{ein:'123456789'});
  assert.match(h.ports[0].name,/^cc-ny-lookup/);
  if(process.env.CC_MS_BRIDGE_REPORT)fs.writeFileSync(process.env.CC_MS_BRIDGE_REPORT,JSON.stringify({passed:true,cases,scope:'70 recorded inputs, synthetic port lifecycle; no live source queries.'},null,2));
  console.log(`PASS 70 MS bridge lifecycle cases; normal NY control unchanged`);
})().catch(e=>{console.error(e);process.exitCode=1;});
