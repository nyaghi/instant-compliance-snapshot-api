const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const sandbox=vm.createContext({URL,module:{exports:{}},require:n=>n==='node:test'?{test:()=>{}}:require(n),__dirname,setImmediate});
vm.runInContext(fs.readFileSync(__dirname+'/run_ny_connector_lifecycle.cjs','utf8'),sandbox);
const harness=()=>vm.runInContext('harness()',sandbox);
for (const persistent of [false,true]) test(`detail timeout reloads exact observed page once; persistent=${persistent}`,async()=>{
  const h=harness(),p=h.connect();let doc=1,calls=0,reloads=0;
  const send=h.chrome.tabs.sendMessage;
  h.chrome.tabs.reload=async id=>{assert.equal(h.tabs.get(id).url,'https://charities-search.ag.ny.gov/RegistrySearch/12-34-56');reloads++;doc++;};
  h.chrome.tabs.sendMessage=async(tab,m)=>{
    if(m.action==='ready')return {ready:true,url:h.tabs.get(tab).url,documentId:String(doc)};
    if(m.action==='search'&&m.query.orgID){calls++;return persistent||calls===1?{ok:false,reason:'NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT'}:{ok:true,evidence:{query:m.query}};}
    return send(tab,m);
  };
  await h.query(p,10);await h.query(p,11,{orgID:'12-34-56'});await h.advance(100);
  const answer=p.messages.find(m=>m.id===String(11).padStart(20,'0')&&!m.progress);
  assert.equal(reloads,1);assert.equal(calls,2);assert.equal(answer.ok,!persistent);
  if(persistent)assert.equal(answer.reason,'NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT');
});
test('a stale content document is never treated as a completed reload',async()=>{
  const h=harness(),p=h.connect();let reloads=0,calls=0;const send=h.chrome.tabs.sendMessage;
  h.chrome.tabs.reload=async()=>{reloads++;};
  h.chrome.tabs.sendMessage=async(tab,m)=>m.action==='ready'?{ready:true,url:h.tabs.get(tab).url,documentId:'unchanged'}:
    m.action==='search'&&m.query.orgID?(calls++,{ok:false,reason:'NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT'}):send(tab,m);
  await h.query(p,10);await h.query(p,11,{orgID:'12-34-56'});await h.advance(10000);
  assert.equal(reloads,1);assert.equal(calls,1);
  assert.equal(p.messages.find(m=>m.id===String(11).padStart(20,'0')&&!m.progress).reason,'NY_CONNECTOR_DETAIL_RESPONSE_TIMEOUT');
});
