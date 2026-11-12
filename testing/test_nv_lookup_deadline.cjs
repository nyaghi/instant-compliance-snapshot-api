const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),{test}=require('node:test'),{webcrypto}=require('node:crypto');
const source=fs.readFileSync(process.argv[2]||require('node:path').join(__dirname,'../artifacts/nv-pf-served.js'),'utf8');
const caps=['lookup-tab-v1','verification-retry-v1','search-verification-retry-v1','search-schema-errors-v1','nullable-ein-v1','queue-v1','connection-recovery-v1','recovery-causes-v1','cleanup-ack-v1','timeout-recovery-v1','resume-v1','verified-detail-v1','detail-navigation-v1','il-ga-public-dom-v1','il-ga-complete-search-v2','il-session-reuse-v1','il-large-pages-v1','ga-exempt-record-v1','ga-legacy-rows-v1','final-four-public-v1','il-dom-events-v1'];
async function scenario({state='NV',delays=[Infinity],cancelAt=null}={}){
 let now=0,seq=0,listener,count=0,advances=0;const timers=new Map(),messages=[],calls=[];
 const timer=(fn,delay)=>{const id=++seq;timers.set(id,{at:now+delay,fn});return id;};
 const timeout=ms=>{const c=new AbortController();timer(()=>c.abort(new DOMException('Timeout','TimeoutError')),ms);return c.signal;};
 const origin='https://staging.compliance-express.com',extension='a'.repeat(32);
 const window={addEventListener:(type,fn)=>{if(type==='message')listener=fn;},postMessage:m=>{
  messages.push({action:m.action,at:now,lookup:m.lookup_id});
  const reply=r=>listener({source:window,origin,data:{...m,...r,direction:'response',il_transport:{protocol:'il-bound-replies-v1',extension_id:extension,lookup_id:m.lookup_id||null}}});
  if(m.action==='search'){
   const delay=delays[count++];
   if(Number.isFinite(delay))timer(()=>reply({ok:true,evidence:{complete:true,rows:[],total:0,query:m.query}}),delay);
   // Progress must not reset the deadline, even while a worker retries.
   for(const d of [10000,20000,30000,40000])timer(()=>reply({progress:true,retrying:true}),d);
  } else queueMicrotask(()=>reply({ok:true,version:'0.6.135',capabilities:caps,cleanup_complete:true}));
 }};
 const query=()=>({phase:'search',check_token:'fixture',query_id:String(advances),lookup_remaining_ms:300000,query:{state,operation:'search',name:'Example '+advances}});
 const ctx={window,location:{origin},document:{visibilityState:'visible',querySelector:()=>null,getElementById:()=>null},crypto:webcrypto,Date:{now:()=>now},setTimeout:timer,clearTimeout:id=>timers.delete(id),AbortSignal:{timeout,any:AbortSignal.any.bind(AbortSignal)},fetch:async(url,options)=>{
  const p=JSON.parse(options.body);calls.push({action:p.action,reason:p.reason,at:now});
  let data;
  if(p.action==='start')data=query();
  else if(p.action==='advance'){advances++;data=advances>=delays.length?{phase:'complete',result:{state,status:'Not Registered',success:true}}:query();}
  else if(p.action==='fail')data={phase:'complete',result:{state,status:p.reason==='NY_CONNECTOR_REGISTRY_NV_LOOKUP_TIMEOUT'?'Site Not Reachable':'Unable to Confirm',success:false}};
  else data={};
  return {ok:true,status:200,json:async()=>data};
 }};
 vm.runInNewContext(source,ctx);
 const cancel=new AbortController();if(cancelAt!==null)timer(()=>cancel.abort(),cancelAt);
 let done=false,result,error,finished;
 window.CCNYConnector.lookup({state,organization_name:'Example',ein:'123456789',email:'qa@example.invalid',admin_passcode:'fixture',device_id:'fixture',signal:cancel.signal}).then(r=>{result=r;finished=now;done=true;},e=>{error=e;finished=now;done=true;});
 for(let i=0;!done&&i<500;i++){
  for(let m=0;m<100;m++)await Promise.resolve();if(done)break;
  const next=[...timers].sort((a,b)=>a[1].at-b[1].at)[0];assert.ok(next,'pending task must have timer');timers.delete(next[0]);now=next[1].at;next[1].fn();
 }
 assert.ok(done,'lookup must finish');return{result,error,finished,messages,calls,count};
}
test('NV hung transport ends at 180 seconds, with one failure and owned cleanup',async()=>{
 const r=await scenario();assert.equal(r.result.status,'Site Not Reachable');assert.equal(r.finished,180000);assert.equal(r.count,1);assert.equal(r.calls.filter(c=>c.action==='fail').length,1);assert.equal(r.messages.at(-1).action,'finish');
});
test('NV successful earlier name does not restart the total budget',async()=>{
 const r=await scenario({delays:[70000,70000,70000]});assert.equal(r.result.status,'Site Not Reachable');assert.equal(r.finished,180000);assert.equal(r.count,3);assert.equal(r.calls.filter(c=>c.action==='advance').length,2);
});
test('NV healthy results within the deadline remain conclusive',async()=>{
 const r=await scenario({delays:[10000,10000]});assert.equal(r.result.status,'Not Registered');assert.equal(r.finished,20000);assert.equal(r.calls.filter(c=>c.action==='fail').length,0);
});
test('user cancellation stays cancellation and does not invent an outage result',async()=>{
 const r=await scenario({cancelAt:12000});assert.equal(r.error.name,'AbortError');assert.equal(r.result,undefined);assert.equal(r.finished,12000);assert.equal(r.calls.filter(c=>c.action==='fail').length,0);assert.equal(r.messages.at(-1).action,'finish');
});
test('other registry source budgets are unchanged',async()=>{
 const r=await scenario({state:'TN',delays:[60000]});assert.equal(r.result.status,'Not Registered');assert.equal(r.finished,60000);
});

test('observed slow successes survive the former 45-second cutoff',async()=>{for(const delay of [54000,65000]){const r=await scenario({delays:[delay,5000]});assert.equal(r.finished,delay+5000);assert.equal(r.result.status,'Not Registered');assert.equal(r.count,2);}});
test('observed 83-second multi-search progress completes within the shared budget',async()=>{const r=await scenario({delays:[24000,14000,10000,7000,7000,7000,7000,7000]});assert.equal(r.finished,83000);assert.equal(r.result.status,'Not Registered');});
