// Offline extracted production functions: no Chrome, state requests or screenshots.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('deployment/staging_connector/registry-content.js','utf8');
const worker=fs.readFileSync('deployment/staging_connector/registry-worker.js','utf8');
const roster=JSON.parse(fs.readFileSync('testing/fixtures/gate52/STATE-70.json','utf8'));
const results=[];
for(const org of roster){
  let mode='shell',selected=true,clicks=0;
  const profession={options:[{textContent:'Charities',value:'charity'}],get value(){return selected?'charity':'other'},disabled:false};
  const name={disabled:false},search={value:'Search',disabled:false,click(){clicks++}};
  const context={GA:true,AL:false,MS:false,NM:false,TN:false,NC:false,NV:false,
    document:{readyState:'complete',querySelectorAll:q=>mode==='shell'?[]:q==='select'?[profession]:mode==='complete'?[search]:[],
      querySelector:q=>q==='#t_web_lookup__full_name'&&mode==='complete'?name:null},
    location:{pathname:'/verification/Search.aspx'},text:el=>el?.textContent||'',visible:el=>!!el,
    set:(el,value)=>{assert(el);el.value=value},setTimeout:fn=>fn(),Error,URL,Date,
    wfcAwait:async(_label,fn)=>fn()};
  vm.createContext(context);vm.runInContext(src.slice(src.indexOf('  function gaFormReadiness()'),src.indexOf('  let snapshotScroll=')),context);
  assert.strictEqual(context.registryDocumentReady(),false);
  mode='profession';assert.strictEqual(context.registryDocumentReady(),false);
  selected=false;assert.strictEqual(context.registryDocumentReady(),true);selected=true;
  mode='complete';assert.strictEqual(context.registryDocumentReady(),true);
  context.location.pathname='/verification/SearchResults.aspx';assert.strictEqual(context.registryDocumentReady(),true);
  results.push({ein:org.ein,name:org.name,passed:true});
}
(async()=>{
for(const scenario of ['healthy','one-recovery','two-failures','post-submission-failure','profession']){
 let now=0,navigate=0,submitted=0,ready=0;const calls=[];
 const context={Date:{now:()=>now},P:{TRIAL_ORIGIN:true},diagnostic:()=>{},
  registryStart:()=> 'https://verify.sos.ga.gov/verification/Search.aspx',
  registryNavigate:async(job,url,budget)=>{navigate++;calls.push(budget);if(scenario==='two-failures'||scenario==='one-recovery'&&navigate===1){now+=budget;throw Error('NY_CONNECTOR_TAB_READY_TIMEOUT')}return {documentId:'initial'}},
  registryReady:async()=>{ready++;if(scenario==='post-submission-failure')throw Error('NY_CONNECTOR_TAB_READY_TIMEOUT');return {documentId:'next'}},
  registryMessage:async(job,m)=>{
   if(m.action==='registry-ga-form'){
    if(scenario==='profession'&&!job.selected){job.selected=true;return {ok:true,phase:'profession'}}
    submitted++;return {ok:true,phase:'submitted'};
   }
   return {ok:true,page:1,rows:[],next:false};
  },wfAwait:async(j,l,fn)=>fn(),wfReturn:(j,l,v)=>v,Error,Object};
 vm.createContext(context);vm.runInContext(worker.slice(worker.indexOf('async function registryGaSearch(')),context);
 let failed=false;try{await context.registryGaSearch({activeExpiresAt:60000,tab:1,generation:1},{orgName:'Recorded organization'})}catch{failed=true}
 assert.strictEqual(navigate,['one-recovery','two-failures'].includes(scenario)?2:1);
 assert.strictEqual(submitted,scenario==='two-failures'?0:1);
 assert.strictEqual(failed,['two-failures','post-submission-failure'].includes(scenario));
 assert(now<=45000);results.push({scenario,passed:true,navigate,submitted,elapsed:now});
}
fs.writeFileSync('testing/fixtures/gate52/CONNECTOR-RESULTS.json',JSON.stringify(results,null,2));
console.log('70 GA form input controls + 5 worker recovery/submission/deadline scenarios passed');
})().catch(e=>{console.error(e);process.exit(1)});
