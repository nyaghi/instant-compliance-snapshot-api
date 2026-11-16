const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/registry-content.js'),'utf8');
const start=source.indexOf('  async function nvResumeDetail('),end=source.indexOf('  async function nvDetail(',start);
const query={state:'NV',operation:'detail',identifier:'NV123456'};
function fixture({observed=true,last=true,id='NV123456',name='Correct Charity',pending=false}={}) {
 let reads=0;
 const c={nvObserved:new Map(observed?[[query.identifier,{name:'Correct Charity'}]]:[]),nvLastSearch:last?{}:null,
  location:{href:'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business'},
  nvFields:()=>{reads++;return pending?null:{'NV Business ID':id,'Entity Name':name};},
  wait:async fn=>{const value=fn();if(!value)throw Error('REGISTRY_RESPONSE_INCOMPLETE');return value;}};
 vm.createContext(c);vm.runInContext(source.slice(start,end)+'this.run=nvResumeDetail;',c);
 return {run:q=>c.run(q,Date.now()+1000),get reads(){return reads;}};
}
test('pending detail reads the already observed record without navigation or another search',async()=>{
 const f=fixture(),result=await f.run(query);assert.equal(result.complete,true);assert.equal(f.reads,1);assert.equal(result.fields['NV Business ID'],query.identifier);
});
test('resume refuses unobserved, changed or incomplete detail',async()=>{
 for(const config of [{observed:false},{last:false},{id:'NV999'},{name:'Other Charity'},{pending:true}])await assert.rejects(fixture(config).run(query));
 for(const bad of [{...query,state:'TN'},{...query,operation:'search'},{...query,identifier:'E1234567-8'},{...query,extra:true}])await assert.rejects(fixture().run(bad),/COMMAND_INVALID/);
});
