const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const {webcrypto}=require('node:crypto');
const source=fs.readFileSync(path.join(__dirname,'gate55-sr-ny-connector.js'),'utf8');
const baseCaps=['lookup-tab-v1','verification-retry-v1','search-verification-retry-v1','search-schema-errors-v1','nullable-ein-v1','queue-v1','connection-recovery-v1','recovery-causes-v1','cleanup-ack-v1','timeout-recovery-v1','resume-v1','verified-detail-v1','detail-navigation-v1','il-ga-public-dom-v1','il-ga-complete-search-v2','il-session-reuse-v1','il-large-pages-v1','ga-exempt-record-v1','ga-legacy-rows-v1','final-four-public-v1','il-dom-events-v1'];
async function run(state,capable){
 const origin='https://charityclarity-final-four-29-2.onrender.com',extension='a'.repeat(32),calls=[];let listener;
 const window={addEventListener:(kind,f)=>{if(kind==='message')listener=f},postMessage(m){const reply=m.action==='ping'?{ok:true,version:'0.6.135',capabilities:[...baseCaps,...capable?['nc-selected-history-v1']:[]]}:{ok:true};queueMicrotask(()=>listener({source:window,origin,data:{...m,...reply,direction:'response',il_transport:{protocol:'il-bound-replies-v1',extension_id:extension,lookup_id:m.lookup_id||null}}}));}};
 const context=vm.createContext({window,location:{origin},document:{visibilityState:'visible',querySelector:()=>null,getElementById:()=>null},crypto:webcrypto,setTimeout,clearTimeout,AbortSignal,Date,fetch:async(url,opts)=>{assert.ok(String(url).startsWith(origin+'/api/'));const body=JSON.parse(opts.body);calls.push(body);return {ok:true,json:async()=>({phase:'complete',result:{state,status:'Current'}})};}});
 vm.runInContext(source,context);const result=await window.CCNYConnector.lookup({state,organization_name:'Synthetic Contract Fixture',ein:'123456789',email:'fixture@example.invalid',admin_passcode:'fixture',device_id:'fixture'});
 assert.equal(result.status,'Current');return calls.find(x=>x.action==='start');
}
test('actual assembled frontend negotiates selected history only with a capable NC connector',async()=>{
 assert.equal((await run('NC',true)).evidence_protocol,'nc-selected-history-v1');
 assert.equal((await run('NC',false)).evidence_protocol,undefined);
 for(const state of ['TN','NV','GA','IL'])assert.equal((await run(state,true)).evidence_protocol,undefined);
});
