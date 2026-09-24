const {test}=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm'), path=require('node:path');
const context=vm.createContext({URL});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../browser-connector/protocol.js'),'utf8'),context);
const P=context.CCNYProtocol;
const query={orgID:'04-31-23'}, request={kind:'detail',query};
const data={orgID:query.orgID,orgName:'Example National Foundation',ein:'123456789',regStatute:'7A',
 documents:{'Annual Filing for Charitable Organizations':[{fiscalYearEnd:'12/31/2025',received:'05/01/2026',downloadUrl:'secret-token'}]}};
const response=value=>P.publicResponse(request,200,{success:true,statusCode:200,data:value});
test('detail query accepts only a single valid registry ID; endpoint is fixed',()=>{
 assert(P.validQuery(query));assert(!P.validQuery({...query,ein:'123456789'}));assert(!P.validQuery({orgID:'../../other'}));
 assert.equal(P.publicRequest('https://charities-search-api.ag.ny.gov/api/FileNet/RegistryDetail?orgID=04-31-23&token=private').kind,'detail');
 for(const url of ['https://other.example/api/FileNet/RegistryDetail?orgID=04-31-23',
 'https://charities-search-api.ag.ny.gov/api/FileNet/RegistryDetail?orgID=04-31-23&orgID=11-22-33',
 'https://charities-search-api.ag.ny.gov/api/FileNet/RegistryDetail?orgID=04-31-23&page=2'])assert.equal(P.publicRequest(url),null);
});
test('only public identity and filing dates leave browser, no state token or document URL',()=>{
 const result=response({...data,token:'private',cookies:'private',authorization:'private'});
 assert.equal(result.detail.ein,'123456789');assert.equal(result.detail.documents['Annual Filing for Charitable Organizations'][0].fiscalYearEnd,'12/31/2025');
 assert(!JSON.stringify(result).includes('private'));assert(!JSON.stringify(result).includes('downloadUrl'));
 assert(!JSON.stringify(P.publicRequest('https://charities-search-api.ag.ny.gov/api/FileNet/RegistryDetail?orgID=04-31-23&token=private')).includes('private'));
});
test('wrong ID, missing EIN, missing/incomplete history and HTTP errors stay inconclusive',()=>{
 for(const value of [{...data,orgID:'11-22-33'},{...data,ein:undefined},{...data,documents:null},
 {...data,documents:{annual:null}},{...data,documents:{annual:[null]}},{...data,documents:{annual:[{fiscalYearEnd:{}}]}}])assert.throws(()=>response(value),/NY_CONNECTOR_DETAIL_INCOMPLETE/);
 assert.throws(()=>P.publicResponse(request,401,{error:'Invalid recaptcha token.'}),/NY_CONNECTOR_DETAIL_INCOMPLETE/);
});
test('complete empty history differs from absent history; null EIN retains name-only controls',()=>{
 assert.equal(Object.keys(response({...data,documents:{}}).detail.documents).length,0);
 assert.equal(response({...data,ein:null}).detail.ein,'');
 assert.throws(()=>response({...data,documents:{annual:Array(1001).fill({})}}),/NY_CONNECTOR_DETAIL_INCOMPLETE/);
});

test('explicit exemption preserves existing rule when state omits document history',()=>{
 const {documents,...identity}=data;const result=response({...identity,regStatute:'Exempt'});
 assert.equal(result.detail.regStatute,'Exempt');assert(!Object.hasOwn(result.detail,'documents'));
 assert.throws(()=>response(identity),/NY_CONNECTOR_DETAIL_INCOMPLETE/);
});
