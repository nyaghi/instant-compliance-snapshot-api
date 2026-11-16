const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('deployment/staging_connector/worker.js','utf8');
const fn=source.slice(source.indexOf('function armEinLightNameLimit'),source.indexOf('async function performSearch'));
function fixture(state='IL'){
 let now=1000,seq=0;const timers=new Map(),closed=[];
 const context={P:{TRIAL_ORIGIN:'https://staging',sameQuery:(a,b)=>JSON.stringify(a)===JSON.stringify(b)},Date:{now:()=>now},Number,Boolean,
 setTimeout:(f,ms)=>{const id=++seq;timers.set(id,{f,at:now+ms});return id;},clearTimeout:id=>timers.delete(id),isActive:j=>j.active,
 close:async(j,reason)=>{j.closed=true;closed.push(reason);}};
 vm.createContext(context);vm.runInContext(fn,context);
 const job={registryState:state,active:true,closed:false};
 const arm=(query,id='q')=>{job.pending=id;job.command={id,query};return context.armEinLightNameLimit(job,query,id);};
 const tick=ms=>{now+=ms;for(const [id,t]of [...timers])if(t.at<=now){timers.delete(id);t.f();}};
 return{job,arm,tick,timers,closed,context};
}
for(const state of ['IL','NY','NM'])test(state+' EIN first, single name deadline, selected detail preserved',()=>{
 const f=fixture(state),ein=state==='NM'?{operation:'search',ein:'123456789',name:''}:{ein:'123456789'};
 f.arm(ein);assert.equal(f.timers.size,0);
 const name=state==='NM'?{operation:'search',ein:'123456789',name:'Example'}:{orgName:'Example'};
 f.arm(name);assert.equal(f.job.einLightNameStop,21000);f.tick(12000);
 f.arm({...name,...(state==='NM'?{name:'Alias'}:{orgName:'Alias'})},'q2');assert.equal(f.job.einLightNameStop,21000);
 f.tick(8000);assert.deepEqual(f.closed,['NY_CONNECTOR_EIN_LIGHT_NAME_LIMIT']);
 const d=fixture(state);d.arm(name);d.tick(19000);d.arm(state==='NM'?{operation:'detail',identifier:'123456789'}:state==='NY'?{orgID:'01-02-03'}:{identifier:'12345'},'detail');d.tick(20000);assert.equal(d.closed.length,0);
});
test('restored deadline is not reset',()=>{const f=fixture();f.job.einLightNameStop=5000;f.arm({orgName:'Example'});f.tick(4000);assert.equal(f.closed.length,1);});
test('late timer cannot close another command',()=>{const f=fixture();f.arm({orgName:'Example'});f.job.pending='different';f.tick(20000);assert.equal(f.closed.length,0);});
test('other states and production untouched',()=>{for(const s of ['GA','NV','TN']){const f=fixture(s);f.arm({orgName:'Example'});assert.equal(f.timers.size,0);}const f=fixture();f.context.P.TRIAL_ORIGIN=null;f.arm({orgName:'Example'});assert.equal(f.timers.size,0);});
test('deadline persisted and cleared before capture',()=>{assert.match(source,/einLightNameStop: j.einLightNameStop/);assert(source.indexOf('clearTimeout(job.einLightNameTimer);',source.indexOf('async function performSearch'))<source.indexOf('const preparedNvMetadata'));});
