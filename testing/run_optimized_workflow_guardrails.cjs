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

test('Sales connector waits for same-workflow reviewed names, including connector-only selection',async()=>{
 const calls=[],lookups=[];let polls=0;
 const cc=setup(async(u,o)=>{const p=JSON.parse(o.body);calls.push(p);
 if(p.action==='start')return response({token:'signed'});
 if(p.action==='release-external')return response({ok:true});
 if(!polls++){assert.equal(lookups.length,0);return response({finished:null,results:[]});}
 return response({finished:1,results:[],connector_identity:{ready:true,confirmed:true,names:['Former Legal Name']}});});
 const r=await cc.run({...base,mode:'sales',states:['GA'],externalLookup:async(state,names)=>{
 lookups.push({state,names:[...names]});return {state,status:'Exempt'};}});
 assert.deepEqual(lookups,[{state:'GA',names:['Former Legal Name']}]);
 assert.equal(calls.filter(p=>p.action==='start').length,1);assert.equal(r[0].status,'Exempt');
});

test('incomplete Sales identity preserves positives but cannot establish connector non-registration',async()=>{
 const cc=setup(async(u,o)=>{const p=JSON.parse(o.body);
 return response(p.action==='start'?{token:'signed'}:{finished:1,results:[],
 connector_identity:{ready:true,confirmed:false,names:['Verified Partial Name']}});});
 const r=await cc.run({...base,mode:'sales',states:['IL','GA'],
 externalLookup:async state=>({state,status:state==='IL'?'Current':'Not Registered',success:true})});
 assert.equal(r[0].status,'Current');assert.equal(r[1].status,'Unable to Confirm');assert.equal(r[1].success,false);
});

test('Sales cutoff during preparation never starts a late connector search',async()=>{
 const ctrl=new AbortController();let deliver,lookups=0;
 const cc=setup(async(u,o)=>{const p=JSON.parse(o.body);
 if(p.action==='start')return response({token:'signed'});if(p.action==='cancel')return response({ok:true});
 return new Promise(resolve=>{deliver=()=>resolve(response({finished:1,results:[],
 connector_identity:{ready:true,confirmed:true,names:['Former']}}));});});
 const pending=cc.run({...base,mode:'sales',states:['GA'],signal:ctrl.signal,
 externalLookup:async()=>{lookups++;return {state:'GA',status:'Current'};}});
 await new Promise(setImmediate);ctrl.abort();deliver();await pending;assert.equal(lookups,0);
});

test('negotiated progressive release returns a completed lane while its peer still runs',async()=>{
 let finishSlow, polls=0;const releases=[],seen=[];
 const cc=setup(async(u,o)=>{const p=JSON.parse(o.body);
  if(p.action==='start')return response({token:'signed',progressive_external_release:true});
  assert.notEqual(p.action,'release-external');
  if('settled_count' in p)releases.push(p.settled_count);
  if(++polls===2){assert.deepEqual(releases,[1]);finishSlow({state:'IL',status:'Current'});}
  return response({finished:polls>=3?1:null,results:polls>=3?[{state:'CO',status:'Current'}]:[]});
 });
 const r=await cc.run({...base,states:['CO','GA','IL'],aliases:['Reviewed name'],onResult:x=>seen.push(x.state),
  externalLookup:state=>state==='GA'?Promise.resolve({state,status:'Exempt'}):new Promise(resolve=>{finishSlow=resolve;})});
 assert.deepEqual(releases,[1,2]);assert.equal(r.length,3);assert.equal(new Set(seen).size,3);
});

test('progressive release retries the cumulative count after a lost acknowledgement',async()=>{
 let polls=0,failed=false,finishSlow;const releases=[];
 const cc=setup(async(u,o)=>{const p=JSON.parse(o.body);
  if(p.action==='start')return response({token:'signed',progressive_external_release:true});
  assert.notEqual(p.action,'release-external');
  if('settled_count' in p){
   releases.push(p.settled_count);if(!failed){failed=true;throw Error('ack lost');}
  }
  if(++polls===2)finishSlow({state:'IL',status:'Current'});
  return response({finished:polls>=3?1:null,results:polls>=3?[{state:'CO',status:'Current'}]:[]});
 });
 await cc.run({...base,states:['CO','GA','IL'],aliases:['Reviewed name'],externalLookup:state=>
  state==='GA'?Promise.resolve({state,status:'Current'}):new Promise(resolve=>{finishSlow=resolve;})});
 assert.deepEqual(releases,[1,1,2]);
});

test('failed connector releases capacity but preserves an inconclusive result',async()=>{
 const releases=[];let polls=0;
 const cc=setup(async(u,o)=>{const p=JSON.parse(o.body);
  if(p.action==='start')return response({token:'signed',progressive_external_release:true});
  assert.notEqual(p.action,'release-external');
  if('settled_count' in p)releases.push(p.settled_count);
  return response({finished:++polls>=2?1:null,results:[{state:'CO',status:'Current'}]});
 });
 const r=await cc.run({...base,states:['CO','GA'],aliases:['Reviewed name'],externalLookup:async()=>{throw Error('source unavailable');}});
 assert.deepEqual(releases,[1]);assert.equal(r[1].status,'Unable to Confirm');assert.equal(r[1].success,false);
});

test('older server retains the all-settled release protocol',async()=>{
 let finishSlow,polls=0;const releases=[];
 const cc=setup(async(u,o)=>{const p=JSON.parse(o.body);
  if(p.action==='start')return response({token:'signed'});
  if(p.action==='release-external'){releases.push(p);return response({ok:true});}
  if(++polls===2){assert.equal(releases.length,0);finishSlow({state:'IL',status:'Current'});}
  return response({finished:polls>=3?1:null,results:[{state:'CO',status:'Current'}]});
 });
 await cc.run({...base,states:['CO','GA','IL'],aliases:['Reviewed name'],externalLookup:state=>
  state==='GA'?Promise.resolve({state,status:'Current'}):new Promise(resolve=>{finishSlow=resolve;})});
 assert.equal(releases.length,1);assert(!('settled_count' in releases[0]));
});

test('canceled workflow cannot return browser reservations as new capacity',async()=>{
 const ctrl=new AbortController(),releases=[];let complete,deliver;
 const cc=setup(async(u,o)=>{const p=JSON.parse(o.body);
  if(p.action==='start')return response({token:'signed',progressive_external_release:true});
  if(p.action==='cancel')return response({ok:true});
  if(p.action==='release-external'){releases.push(p);return response({ok:true});}
  return new Promise(resolve=>{deliver=()=>resolve(response({finished:1,results:[]}));});
 });
 const pending=cc.run({...base,states:['CO','GA'],aliases:['Reviewed name'],signal:ctrl.signal,
  externalLookup:()=>new Promise(resolve=>{complete=resolve;})});
 await new Promise(setImmediate);ctrl.abort();complete({state:'GA',status:'Current'});deliver();await pending;
 assert.equal(releases.length,0);
});
