const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..'),roster=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/gate55/LOCAL-70.json'),'utf8'));
const worker=fs.readFileSync(path.join(root,'deployment/staging_connector/registry-worker.js'),'utf8');
const begin=worker.indexOf('async function registryNcSelectedHistory('),end=worker.indexOf('async function registryGaSearch(',begin);
const code=worker.slice(begin,end);assert.ok(begin>0&&end>begin);
function fixture(org,{timeout=false}={}){
 let current='';const visits=[],reads=[],captures=[],job={ncProfiles:{},activeExpiresAt:Date.now()+300000,closed:false,command:{id:'bound-command'},generation:1,pending:'bound-command'};
 const queries=[1,2,3].map(n=>({state:'NC',operation:'detail',identifier:'SL'+n,url:'https://www.sosnc.gov/online_services/search/charities_profile/'+n,history:'profile'}));
 for(const q of queries)job.ncProfiles[q.identifier]=q.url;
 const ctx={P:{TRIAL_ORIGIN:'https://charityclarity-final-four-29-2.onrender.com'},Date,JSON,Object,Error,owned:new Set(),diagnostic:()=>{},wfAwait:async(j,s,fn)=>fn(),wfReturn:(j,s,x)=>x,
  registryNavigate:async(j,url,budget)=>{visits.push({url,budget});current=url;if(timeout&&url.includes('/charities_filings/'))throw Error('bounded optional failure');return {documentId:'doc-'+url}},
  registryMessage:async(j,m)=>{reads.push(m.action);if(m.action==='registry-nc-profile'){
   assert.equal(current,m.query.url);return {ok:true,filings_url:current.replace('/charities_profile/','/charities_filings/'),evidence:{query:m.query,complete:true,fields:{Name:org.name,'Registration #':m.query.identifier,profile_url:m.query.url,Status:'Current Active'}}};
  }if(m.action==='registry-nc-filings'){assert.equal(current,m.query.url.replace('/charities_profile/','/charities_filings/'));return {ok:true,filings:{url:current,complete:true,rows:[{type:'Renewal Charity',date:'10/01/2026'}]}};}throw Error('Unexpected source action');},
  captureStateSnapshot:async(j,q,id)=>{captures.push(q.identifier);return {original:'pixel-'+q.identifier}}};
 vm.createContext(ctx);vm.runInContext(code+';this.run=registryNorthCarolinaQuery;',ctx);return {ctx,job,queries,visits,reads,captures};
}
test('70 recorded identities: all candidate profiles/pixels retained, no preselection histories, one selected history',async()=>{
 for(const org of roster){
  const h=fixture(org);
  for(const q of h.queries){const r=await h.ctx.run(h.job,q);assert.equal(r.evidence.fields['Registration #'],q.identifier);assert.equal(r.evidence.filings,undefined);assert.ok(h.job.ncProfileSnapshot.snapshot.original);}
  assert.equal(h.visits.length,3);assert.equal(h.reads.length,3);assert.equal(h.captures.length,3);
  const selected={...h.queries[1],history:'selected'},r=await h.ctx.run(h.job,selected);
  assert.equal(h.visits.length,4);assert.equal(h.reads.filter(x=>x==='registry-nc-profile').length,3);
  assert.equal(h.reads.filter(x=>x==='registry-nc-filings').length,1);assert.equal(h.captures.length,3);
  assert.equal(r.evidence.query.history,'selected');assert.equal(r.evidence.fields['Registration #'],'SL2');assert.equal(r.evidence.filings.complete,true);
  assert.ok(h.visits[3].budget<=8000);
 }
});
test('70 recorded identities: optional timeout preserves exact complete selected fields; legacy remains unchanged',async()=>{
 for(const org of roster){
  const h=fixture(org,{timeout:true}),q=h.queries[0];await h.ctx.run(h.job,q);
  const r=await h.ctx.run(h.job,{...q,history:'selected'});assert.equal(r.ok,true);assert.equal(r.evidence.complete,true);assert.equal(r.evidence.filings.complete,false);assert.equal(r.evidence.fields.Name,org.name);
  const legacy=fixture(org);const old={...legacy.queries[0]};delete old.history;
  const original=await legacy.ctx.run(legacy.job,old);assert.equal(original.evidence.filings.complete,true);assert.equal(legacy.visits.length,2);assert.equal(legacy.captures.length,1);
  await assert.rejects(h.ctx.run(h.job,{...q,url:q.url+'9',history:'selected'}),/INVALID_SEQUENCE/);
 }
});
test('both protocol copies accept only the two exact NC detail modes',()=>{
 for(const file of ['protocol.js','ny-main.js']){
  const s=fs.readFileSync(path.join(root,'deployment/staging_connector',file),'utf8');
  const start=s.indexOf('  function validQuery('),stop=s.indexOf('  function sameQuery(',start);
  const ctx={TRIAL_ORIGIN:'https://charityclarity-final-four-29-2.onrender.com'};vm.createContext(ctx);vm.runInContext(s.slice(start,stop)+';this.validQuery=validQuery',ctx);
  const p=ctx;
  for(const org of roster){
   const q={state:'NC',operation:'detail',identifier:'SL'+org.ein,url:'https://www.sosnc.gov/online_services/search/charities_profile/123'};
   assert.equal(p.validQuery(q),true);for(const history of ['profile','selected'])assert.equal(p.validQuery({...q,history}),true);
   for(const history of ['other',true,1,null])assert.equal(p.validQuery({...q,history}),false);
   assert.equal(p.validQuery({...q,history:'selected',extra:true}),false);assert.equal(p.validQuery({...q,history:'selected',state:'NV'}),false);
   assert.equal(p.validQuery({...q,history:'selected',url:'https://example.invalid/123'}),false);
   assert.equal(p.validQuery({...q,identifier:'NCAPP-123',history:'selected'}),false);
   assert.equal(p.validQuery({...q,identifier:'NCAPP-123',history:'profile'}),true);
  }
 }
});
