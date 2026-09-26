const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const source = fs.readFileSync(path.join(__dirname,'../web-staging/ny-connector.js'),'utf8');
const capabilities = ['lookup-tab-v1','verification-retry-v1','search-verification-retry-v1','search-schema-errors-v1','nullable-ein-v1','queue-v1','connection-recovery-v1','recovery-causes-v1','cleanup-ack-v1','timeout-recovery-v1','resume-v1','verified-detail-v1','detail-navigation-v1','il-ga-public-dom-v1','il-ga-complete-search-v2','il-session-reuse-v1','il-large-pages-v1','ga-exempt-record-v1','ga-legacy-rows-v1'];

async function exercise({state='GA',commands=42,elapsedPerCommand=100,stopStatus='Delinquent'}={}) {
  const actions=[];let advance=0,clock=0,listener;
  const window={addEventListener:(kind,fn)=>{if(kind==='message')listener=fn;},postMessage(message){
    actions.push(message.action);
    queueMicrotask(()=>listener({source:window,origin:'https://staging.compliance-express.com',data:{
      ...message,direction:'response',ok:true,version:'0.5.7',capabilities,evidence:{complete:true,rows:[]}
    }}));
  }};
  const context=vm.createContext({window,location:{origin:'https://staging.compliance-express.com'},
    document:{querySelector:()=>null},crypto:webcrypto,setTimeout,clearTimeout,AbortSignal,
    Date:{now:()=>clock},fetch:async(_url,options)=>{
      const request=JSON.parse(options.body);actions.push('api:'+request.action);
      let payload;
      if(request.action==='cancel')payload={};
      else if(request.action==='fail')payload={phase:'complete',result:{state,status:'Unable to Confirm',reason:request.reason}};
      else {
        if(request.action==='advance'){advance++;clock+=elapsedPerCommand;}
        payload=advance>=commands?{phase:'complete',result:{state,status:stopStatus}}:
          {phase:'search',check_token:'test-only-token',query_id:'query-'+advance,query:{state,orgName:'Variant '+advance}};
      }
      return {ok:true,json:async()=>payload};
    }});
  vm.runInContext(source,context);
  let result,error;
  try {result=await window.CCNYConnector.lookup({state,organization_name:'Example Foundation',ein:'12-3456789',email:'test@example.invalid',admin_passcode:'test-only',device_id:'test-only'});}
  catch(e){error=e;}
  return {result,error,advance,actions};
}
test('GA full reviewed-name search completes beyond both former command caps',async()=>{
  const run=await exercise();assert.ifError(run.error);assert.equal(run.advance,42);assert.equal(run.result.status,'Delinquent');assert.ok(run.actions.includes('finish'));
});
test('IL long completed negative also follows the master continuation',async()=>{
  const run=await exercise({state:'IL',commands:61,stopStatus:'Not Registered / Non-Compliant'});assert.ifError(run.error);assert.equal(run.advance,61);assert.equal(run.result.status,'Not Registered / Non-Compliant');
});
test('master inconclusive completion is retained without a generic frontend exception',async()=>{
  const run=await exercise({commands:38,stopStatus:'Unable to Confirm'});assert.ifError(run.error);assert.equal(run.result.status,'Unable to Confirm');
});
test('a nonterminating IL/GA continuation fails conservatively at five minutes',async()=>{
  const run=await exercise({commands:1000,elapsedPerCommand:10000});assert.ifError(run.error);assert.equal(run.advance,30);assert.equal(run.result.status,'Unable to Confirm');assert.equal(run.result.reason,'NY_CONNECTOR_TIMEOUT');assert.ok(run.actions.includes('finish'));
});
test('New York retains its existing ten-command ceiling',async()=>{
  const run=await exercise({state:'NY',commands:20});assert.equal(run.advance,10);assert.match(run.error.message,/complete result/);assert.ok(run.actions.includes('finish'));
});
