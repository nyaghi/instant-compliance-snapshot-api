const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname,'..','browser-connector');
const context = vm.createContext({URL});
vm.runInContext(fs.readFileSync(path.join(root,'protocol.js'),'utf8'),context);
const P=context.CCNYProtocol;
const normal=value=>JSON.parse(JSON.stringify(value));
const search='https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch';
const row={orgID:'10-20-30',orgName:'Example Foundation',ein:'123456789'};
test('normal formatted EIN is canonical; token never retained',()=>{
  const parsed=P.publicRequest(search+'?ein=12-3456789&token=never-retain-this');
  assert.deepEqual(normal(parsed),{kind:'search',query:{ein:'123456789'}});
  assert.equal(P.sameQuery(parsed.query,{ein:'123456789'}),true);
});
test('different official path/host cannot provide evidence',()=>{
  for(const url of ['https://example.com/api/FileNet/RegistrySearch?ein=123456789',search.replace('RegistrySearch','RegistryDetail')+'?ein=123456789',search.replace('https:','http:')+'?ein=123456789'])assert.equal(P.publicRequest(url),null);
});
test('stale, duplicate and extra-filter queries never match current request',()=>{
  for(const q of ['ein=987654321','ein=123456789&ein=123456789','ein=123456789&state=NY','ein=123456789&orgName=Different','ein=123456789&page=2','ein=123456789&status=active','ein=123456789&token=a&token=b']){
    const parsed=P.publicRequest(search+'?'+q);assert.equal(Boolean(parsed&&P.sameQuery(parsed.query,{ein:'123456789'})),false);
  }
  assert.equal(P.sameQuery({ein:'123456789',orgName:'Example'},{orgName:'Example'}),false);
});
test('complete empty response is distinguishable from failed or incomplete data',()=>{
  const request={kind:'search',query:{ein:'123456789'}};
  assert.deepEqual(normal(P.publicResponse(request,200,{success:true,statusCode:200,data:[]})),{kind:'search',query:request.query,http_status:200,success:true,statusCode:200,rows:[]});
  assert.throws(()=>P.publicResponse(request,200,{success:true,statusCode:200,data:null}));
  assert.throws(()=>P.publicResponse(request,401,{success:false,statusCode:401,data:[]}),/NY_CONNECTOR_SEARCH_HTTP_ERROR/);
});
test('only public row identity fields cross the bridge',()=>{
  const result=P.publicResponse({kind:'search',query:{ein:'123456789'}},200,{success:true,statusCode:200,data:[{...row,token:'secret',email:'not-needed',address:'not-needed'}]});
  assert.deepEqual(normal(result.rows),[row]);assert.equal(JSON.stringify(result).includes('secret'),false);
});
test('malformed/oversized rows fail instead of disappearing from a negative',()=>{
  for(const data of [[{...row,ein:123456789}],[{...row,orgID:'https://example.com'}],[{...row,orgName:''}],Array(1001).fill(row)])assert.throws(()=>P.publicResponse({kind:'search',query:{ein:'123456789'}},200,{success:true,statusCode:200,data}));
});
test('verification exposes only its outcome',()=>{
  assert.deepEqual(normal(P.publicResponse({kind:'verify'},401,{verified:false,token:'secret'})),{kind:'verify',http_status:401,verified:false});
});
test('only bounded master EIN or name queries are permitted',()=>{
  for(const value of [{ein:'123'}, {ein:'000000000'},{orgID:'10-20-30'},{orgName:''},{orgName:'x'.repeat(501)},{ein:'123456789',orgName:'Example'},[]])assert.equal(P.validQuery(value),false);
});
test('manifest is restricted to staging and NY; no credential/debugger permissions',()=>{
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8'));
  assert.deepEqual(manifest.host_permissions,['https://staging.compliance-express.com/*','https://charities-search.ag.ny.gov/*']);
  assert.equal(manifest.permissions,undefined);
  for(const source of ['worker.js','staging-bridge.js','ny-content.js','ny-main.js'])assert.equal(/admin_passcode|document\.cookie|chrome\.cookies|chrome\.debugger/.test(fs.readFileSync(path.join(root,source),'utf8')),false);
});

test('diagnostic reasons distinguish response failures without accepting incomplete evidence',()=>{
  const request={kind:'search',query:{ein:'123456789'}};
  const good={success:true,statusCode:200,data:[row]};
  const cases=[
    [503,good,'HTTP_ERROR'],[200,{...good,success:false},'UNSUCCESSFUL'],
    [200,{...good,data:null},'ROWS_INVALID'],
    [200,{...good,data:[{...row,orgID:'bad'}]},'IDENTITY_INVALID'],
    [200,{...good,data:[{orgID:row.orgID,orgName:row.orgName}]},'EIN_MISSING'],
    [200,{...good,data:[{...row,ein:null}]},'EIN_NULL'],
    [200,{...good,data:[{...row,ein:123456789}]},'EIN_TYPE'],
    [200,{...good,data:[{...row,ein:'invalid'}]},'EIN_FORMAT']
  ];
  for(const [status,payload,reason] of cases)assert.throws(()=>P.publicResponse(request,status,payload),new RegExp('NY_CONNECTOR_SEARCH_'+reason));
  assert.deepEqual(normal(P.publicResponse(request,200,{...good,data:[{...row,ein:''}]}).rows),[{...row,ein:''}]);
});
