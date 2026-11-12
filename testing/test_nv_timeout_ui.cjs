const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const script=fs.readFileSync(require('node:path').join(__dirname,'../web-staging/identity-review.js'),'utf8');
const c=vm.createContext({});vm.runInContext(script.slice(script.indexOf('  function boundedSourceFailure('),script.indexOf('  function add(')),c);
test('Nevada timeout shows Site Not Reachable without overriding identity or other states',()=>{
const base={state:'NV',status:'Site Not Reachable',status_reason:'NY_CONNECTOR_REGISTRY_NV_SEARCH_RESPONSE_TIMEOUT'};
assert.equal(c.boundedSourceFailure(base),true);
assert.equal(c.boundedSourceFailure({...base,status_reason:'NY_CONNECTOR_REGISTRY_NV_LOOKUP_TIMEOUT'}),true);
for(const change of [{state:'NC'},{status:'Unable to Confirm'},{status_reason:'NY_CONNECTOR_REGISTRY_NV_COLUMNS_CHANGED'},{identity_review:{candidates:[{name:'Example'}]}}])assert.equal(c.boundedSourceFailure({...base,...change}),false);
});
