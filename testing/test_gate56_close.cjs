const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const file=fs.readFileSync('deployment/staging_connector/worker.js','utf8');
function deferred(){let resolve,reject;const promise=new Promise((r,j)=>{resolve=r;reject=j;});return {promise,resolve,reject};}
function harness(){
 const removed=deferred(), durable=deferred(), timeline=[], messages=[], owned=new Set([42]);
 const job={registryState:'IL',tab:42,port:{disconnect(){}}}, lanes=new Map([['IL',job]]);
 const ctx={queue:[],owned,activeLanes:lanes,laneStarts:new Map(),PACE_MS:3000,P:{TRIAL_ORIGIN:true},
   Promise,Date,setTimeout,clearTimeout,post:(_j,m)=>messages.push(m),wfAwait:(_j,_s,fn)=>fn(),wfReturn:(_j,_s,v)=>v,
   isActive:j=>lanes.get('IL')===j,holdTnPosition(){},notifyQueue(){},pump(){timeline.push('pump');},
   removeOwned:async(id,persist)=>{assert.equal(id,42);assert.equal(persist,false);await removed.promise;owned.delete(id);},
   saveRuntime:()=>{timeline.push('checkpoint');assert.equal(owned.size,0);assert.equal(lanes.size,0);return durable.promise;}};
 vm.createContext(ctx);vm.runInContext(file.slice(file.indexOf('async function close(job,'),file.indexOf('async function lookupTab(job)')),ctx);
 return {ctx,removed,durable,job,timeline,messages,lanes};
}
test('confirmed tab removal frees a slot before storage returns and one ordered checkpoint confirms finish',async()=>{
 for(const fail of [false,true]){
   const h=harness(), pending=h.ctx.close(h.job,undefined,'finish');
   await new Promise(setImmediate);assert.equal(h.lanes.size,1);assert.deepEqual(h.timeline,[]);
   h.removed.resolve();await new Promise(setImmediate);
   assert.equal(h.lanes.size,0);assert.equal(h.messages.length,0);assert.deepEqual(h.timeline,['checkpoint','pump']);
   if(fail)h.durable.reject(Error('disk'));else h.durable.resolve();
   await pending;assert.equal(h.messages[0].cleanup_complete,!fail);
   assert.equal(h.timeline.filter(v=>v==='checkpoint').length,1);
 }
});
