const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('deployment/staging_connector/registry-worker.js','utf8');
const predicates=source.slice(source.indexOf('function auroraBackgroundTrial('),source.indexOf('function registryTrialLayout('));
const create=source.slice(source.indexOf('async function registryCreateOwnedTab('),source.indexOf('// Keep only the owned quiet NV document'));
function context(){const calls=[];const c={P:{TRIAL_ORIGIN:'https://staging.test'},URL,owned:new Set(),
 wfAwait:(_j,_s,f)=>f(),saveRuntime:async()=>{},registryNevadaBackgroundBegin:async()=>{},
 chrome:{tabs:{create:async o=>{calls.push(o);return{id:42,...o};}},windows:{create:()=>{throw Error('Unexpected popup');}}}};
 vm.createContext(c);vm.runInContext(predicates+create,c);return {c,calls};}
test('all nine connectors use inactive tabs on both regular staging aliases, including legacy duo links',async()=>{
 for(const path of ['/','/?collector_layout=duo','/instant-compliance-snapshot','/instant-compliance-snapshot/'])
 for(const state of ['AL','GA','IL','MS','NC','NM','NV','NY','TN']){
  const {c,calls}=context(),origin={url:'https://staging.test'+path,windowId:7},job={registryState:state,sender:origin};
  await c.registryCreateOwnedTab(job,'https://registry.test/search',origin);
  assert.equal(calls.length,1);assert.equal(calls[0].active,false);assert.equal(calls[0].windowId,7);assert.ok(c.owned.has(job.tab));
 }
});
test('explicit diagnostic popup and unrelated origins are not silently changed',()=>{
 const {c}=context();assert.equal(c.auroraBackgroundTrial({url:'https://staging.test/?aurora_connector_test=popup'}),false);
 assert.equal(c.auroraBackgroundTrial({url:'https://other.test/'}),false);
 assert.equal(c.auroraBackgroundTrial({url:'https://staging.test/connector/final-four-validation.html'}),false);
 assert.equal(c.registryQuietAlerts({sender:{url:'https://staging.test/alerts-runner.html'}}),true);
});
