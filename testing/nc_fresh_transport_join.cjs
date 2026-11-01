const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');
const dir=process.argv[2],source=fs.readFileSync(path.join(dir,'source.js'),'utf8'),data=JSON.parse(fs.readFileSync(path.join(dir,'responses.json'),'utf8'));
const origin='https://fixture-final-four.onrender.com',extension='a'.repeat(32);
const caps=['lookup-tab-v1','verification-retry-v1','search-verification-retry-v1','search-schema-errors-v1','nullable-ein-v1','queue-v1','connection-recovery-v1','recovery-causes-v1','cleanup-ack-v1','timeout-recovery-v1','resume-v1','verified-detail-v1','detail-navigation-v1','il-ga-public-dom-v1','il-ga-complete-search-v2','il-session-reuse-v1','il-large-pages-v1','ga-exempt-record-v1','ga-legacy-rows-v1','final-four-public-v1','il-dom-events-v1'];
async function run(directive){
 let listener,active=null,searches=0,advanced=0,failed=0;const actions=[];
 const window={addEventListener:(kind,f)=>{if(kind==='message')listener=f;},postMessage(m){
  let r={ok:true};actions.push({action:m.action,intent:m.intent,lookup:m.lookup_id,query:m.query});
  if(m.action==='ping')r={ok:true,version:'0.6.135',capabilities:caps};
  if(m.action==='acquire')active={state:m.intent||'NY',lookup:m.lookup_id};
  if(m.action==='finish')active=null;
  if(m.action==='search'){
   searches++;
   if(searches===1){r={ok:false,reason:'NY_CONNECTOR_REGISTRY_NC_RESULT_COUNT_MISMATCH'};active=null;}
   else{
    active ||= {state:m.intent||'NY',lookup:m.lookup_id};
    if(active.state!=='NC'){r={ok:false,reason:'NY_CONNECTOR_INCOMPLETE'};active=null;}
    else{const expected=data.exchanges[advanced].payload;assert.deepEqual(m.query,JSON.parse(JSON.stringify(expected.evidence.query)));r={ok:true,evidence:expected.evidence};}
   }
  }
  queueMicrotask(()=>listener({source:window,origin,data:{...m,...r,direction:'response',il_transport:{protocol:'il-bound-replies-v1',extension_id:extension,lookup_id:m.lookup_id||null}}}));
 }};
 const context=vm.createContext({window,location:{origin},document:{visibilityState:'visible',querySelector:()=>null,getElementById:()=>null},crypto:webcrypto,setTimeout,clearTimeout,AbortSignal,Date,fetch:async(url,opts)=>{
  const p=JSON.parse(opts.body);let response;
  if(p.action==='start')response=data.start;
  else if(p.action==='fail'&&failed++===0){response=JSON.parse(JSON.stringify(data.narrow));if(!directive)delete response.recovery;}
  else if(p.action==='advance'){
   const expected=data.exchanges[advanced++];assert.equal(p.query_id,expected.payload.query_id);assert.equal(p.check_token,expected.payload.check_token);response=expected.response;
  }else if(p.action==='cancel')response={};
  else response={phase:'complete',result:{state:'NC',status:'Unable to Confirm'}};
  return {ok:true,json:async()=>response};
 }});
 vm.runInContext(source,context);
 const result=await window.CCNYConnector.lookup({state:'NC',organization_name:'Lobular Breast Cancer Alliance, Inc.',ein:'862260246',email:'fixture@example.invalid',admin_passcode:'fixture',device_id:'fixture-device'});
 return {result,actions,advanced,searches};
}
(async()=>{
 const baseline=await run(false);assert.equal(baseline.result.status,'Unable to Confirm');assert.equal(baseline.advanced,0);
 const candidate=await run(true);assert.equal(candidate.result.status,data.final.result.status);assert.equal(candidate.advanced,data.exchanges.length);
 const admitted=candidate.actions.filter(x=>x.action==='acquire');assert.equal(admitted.length,2);assert.ok(admitted.every(x=>x.intent==='NC'));assert.notEqual(admitted[0].lookup,admitted[1].lookup);
 assert.equal(candidate.actions.filter(x=>x.action==='search'&&x.query.state!=='NC').length,0);
 console.log('Actual assembled frontend + signed backend: baseline failed; candidate reacquired NC; complete signed evidence sequence retained. Port closure is modeled; no live requests.');
})().catch(e=>{console.error(e);process.exitCode=1;});
