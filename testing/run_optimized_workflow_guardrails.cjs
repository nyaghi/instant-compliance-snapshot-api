const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),crypto=require('node:crypto');
function setup(fetch){const window={};vm.runInNewContext(fs.readFileSync('web-staging/optimized-workflows.js','utf8'),{
 window,location:{origin:'https://staging.compliance-express.com'},fetch,crypto,AbortSignal,performance,setTimeout:(f)=>setImmediate(f)});return window.CCOptimized;}
const base={apiBase:'https://staging.test',name:'Control',ein:'123456789',credentials:{email:'control',admin_passcode:'fixture',device_id:'one'}};
const response=data=>({ok:true,json:async()=>data});
test('one submission preserves aliases, streams completed rows and reserves/releases connector slots',async()=>{
 const calls=[],seen=[];const cc=setup(async(url,o)=>{const p=JSON.parse(o.body);calls.push(p);
  if(p.action==='start')return response({token:'signed'});
  if(p.action==='release-external')return response({ok:true});
  return response({finished:1,results:[{state:'PA',status:'Delinquent',success:true}]});});
 const r=await cc.run({...base,states:['PA','IL','GA'],aliases:['Former Control'],onResult:x=>seen.push(x),
  externalLookup:async state=>({state,status:'Current',success:true})});
 assert.equal(calls.filter(p=>p.action==='start').length,1);assert.deepEqual(calls[0].alternate_names,['Former Control']);
 assert.equal(calls[0].states.length,3);assert(calls.some(p=>p.action==='release-external'));
 assert.equal(r.length,3);assert.equal(seen.length,3);assert.equal(r[0].status,'Delinquent');
});
test('retrying an interrupted submission uses the same request identity',async()=>{
 const ids=[];const cc=setup(async(u,o)=>{let p=JSON.parse(o.body);if(p.action==='start'){
 ids.push(p.request_id);if(ids.length===1)throw Error('transport');return response({token:'signed'});}
 return response({finished:1,results:[{state:'CO',status:'Current'}]});});
 await cc.run({...base,states:['CO']});assert.equal(ids.length,2);assert.equal(ids[0],ids[1]);
});

test('Standard progress requests retain a network deadline without a caller signal',async()=>{
 const cc=setup(async(u,o)=>{assert(o.signal instanceof AbortSignal);const p=JSON.parse(o.body);
  return response(p.action==='start'?{token:'signed'}:{finished:1,results:[{state:'CO',status:'Current'}]});});
 const r=await cc.run({...base,states:['CO']});assert.equal(r[0].status,'Current');
});
test('progress failure preserves earlier evidence and never becomes Not Registered',async()=>{
 let count=0;const calls=[];const cc=setup(async(u,o)=>{let p=JSON.parse(o.body);calls.push(p.action);
 if(p.action==='start')return response({token:'signed'});if(p.action==='cancel')return response({ok:true});
 if(!count++)return response({finished:null,results:[{state:'CO',status:'Current',success:true}]});throw Error('temporary');});
 const r=await cc.run({...base,states:['CO','PA']});assert.equal(r[0].status,'Current');
 assert.equal(r[1].status,'Unable to Confirm');assert.equal(r[1].success,false);assert(calls.includes('cancel'));
});
test('caller deadline cancels worker tasks and rejects later evidence',async()=>{
 const ctrl=new AbortController(),calls=[],seen=[];let deliver;
 const cc=setup(async(u,o)=>{let p=JSON.parse(o.body);calls.push(p.action);
 if(p.action==='start')return response({token:'signed'});if(p.action==='cancel')return response({ok:true});
 return new Promise(resolve=>{deliver=()=>resolve(response({finished:1,results:[{state:'CO',status:'Current'}]}));});});
 const pending=cc.run({...base,states:['CO'],signal:ctrl.signal,onResult:r=>seen.push(r)});
 await new Promise(setImmediate);ctrl.abort();deliver();await pending;
 assert.equal(seen.length,0);assert(calls.includes('cancel'));
});
