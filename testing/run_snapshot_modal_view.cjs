/* Actual packaged handler; modeled source DOM only, no state/network requests. */
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../browser-connector/registry-content.js'),'utf8');
function fixture(name='LOCAL ORGANIZATION'){
 let listener;const state={identifier:'CO42115',visible:true,top:90,scrolls:[]};
 const field=(label,offset)=>({innerText:label,getClientRects:()=>[{}],getBoundingClientRect:()=>({top:100+offset-state.top})});
 const expiry=field('Expiration Date: 08/28/2023',400),financial=field('09/30/2020',720);
 const dialog={getClientRects:()=>state.visible?[{}]:[],scrollHeight:1000,clientHeight:250,
  getBoundingClientRect:()=>({top:100}),get scrollTop(){return state.top;},set scrollTop(v){state.top=Math.max(0,Math.min(750,v));state.scrolls.push(state.top);},
  querySelectorAll:q=>q==='h4'?[field('CO Number: '+state.identifier,0),expiry]:[],querySelector:q=>q==='#DetailsTabStrip-1 table tbody tr'?financial:null};
 const win={};win.top=win;
 const ctx={window:win,document:{body:{innerText:name+' CO42115 Expired Expiration Date: 08/28/2023'},querySelector:q=>q==='#KendoWindowLevel1'?dialog:null},
  location:{origin:'https://tncab.tnsos.gov',href:'https://tncab.tnsos.gov/portal/registered-charities-search'},crypto:{randomUUID:()=> 'local'},
  Date,Promise,setTimeout,clearTimeout,chrome:{runtime:{id:'local-extension',onMessage:{addListener:fn=>listener=fn}}}};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 const query={state:'TN',operation:'detail',identifier:'CO42115'};
 const request=m=>new Promise(resolve=>listener(m,{id:'local-extension'},resolve));
 return {state,dialog,query,request,listener};
}
test('30 modeled organization DOMs show top, expiry and financial views and restore source scroll',async()=>{
 const orgs=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/oct19-cohort.json'))).slice(0,30);
 for(const org of orgs){const f=fixture(org.name),meta=await f.request({action:'registry-snapshot-metadata',query:f.query});
  assert.deepEqual(Array.from(meta.capture_views),['top','expiration','financial']);assert.ok(meta.public_text.includes(org.name));
  for(const view of ['top','expiration','financial','restore'])assert.equal((await f.request({action:'registry-snapshot-view',query:f.query,command_id:'local-command',view})).ok,true);
  assert.deepEqual(f.state.scrolls,[0,384,704,90]);assert.equal(f.state.top,90);}
});
test('a stale restore cannot erase another command scroll binding',async()=>{
 const f=fixture();await f.request({action:'registry-snapshot-view',query:f.query,command_id:'current',view:'top'});
 assert.equal((await f.request({action:'registry-snapshot-view',query:f.query,command_id:'stale',view:'restore'})).ok,false);
 assert.equal((await f.request({action:'registry-snapshot-view',query:f.query,command_id:'current',view:'expiration'})).ok,true);
 assert.equal((await f.request({action:'registry-snapshot-view',query:f.query,command_id:'current',view:'restore'})).ok,true);
 assert.equal(f.state.top,90);
});
for(const guard of ['wrong-state','wrong-operation','wrong-identifier','hidden','unknown-view','wrong-command','foreign-sender']){
 test('source modal guard: '+guard,async()=>{const f=fixture();
  if(guard==='foreign-sender'){assert.equal(f.listener({action:'registry-snapshot-view',query:f.query,command_id:'x',view:'top'},{id:'another'},()=>assert.fail('foreign reply')),false);assert.deepEqual(f.state.scrolls,[]);return;}
  let query={...f.query},view='top',command_id='local-command';
  if(guard==='wrong-state')query.state='NC';if(guard==='wrong-operation')query.operation='search';if(guard==='wrong-identifier')query.identifier='CO99999';if(guard==='hidden')f.state.visible=false;if(guard==='unknown-view')view='arbitrary-action';
  if(guard==='wrong-command'){await f.request({action:'registry-snapshot-view',query,command_id,view:'top'});f.state.scrolls=[];command_id='other-command';view='expiration';}
  assert.equal((await f.request({action:'registry-snapshot-view',query,command_id,view})).ok,false);assert.deepEqual(f.state.scrolls,[]);
 });
}
