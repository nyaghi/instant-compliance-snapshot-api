const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/registry-worker.js'),'utf8');
const helpers=code.slice(code.indexOf('async function registryNevadaBackgroundBegin('),code.indexOf('async function registryTennesseeOwnedWindow('));
function fixture(options={}){
 const calls=[],job={registryState:'NV',tab:7,closed:false,activeExpiresAt:Date.now()+60000,quiet:true};
 const c={P:{TRIAL_ORIGIN:true},Date,setTimeout,clearTimeout,Promise,Error,owned:new Set([7]),registryQuietAlerts:j=>j.quiet,diagnostic:()=>{},chrome:{debugger:{attach:async(t)=>{calls.push(['attach',t.tabId]);if(options.reject)throw Error('attach rejected');},sendCommand:async(t,m,p)=>{calls.push([m,p.enabled]);},detach:async(t)=>{calls.push(['detach',t.tabId]);}}}};
 vm.createContext(c);vm.runInContext(helpers+'this.begin=registryNevadaBackgroundBegin;this.end=registryNevadaBackgroundEnd;',c);return{c,job,calls};
}
test('70 roster cases preserve query fields and release before evidence capture',async()=>{
 const roster=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/fresh-five/LOCAL-70.json'),'utf8'));const cases=Array.isArray(roster)?roster:roster.cases;assert.equal(cases.length,70);
 for(const org of cases){const f=fixture();f.job.query=JSON.parse(JSON.stringify(org));const before=JSON.stringify(f.job.query);await f.c.begin(f.job);await f.c.begin(f.job);await f.c.end(f.job);assert.equal(JSON.stringify(f.job.query),before);assert.deepEqual(f.calls.map(x=>x[0]),['attach','Emulation.setFocusEmulationEnabled','Emulation.setFocusEmulationEnabled','detach']);assert.equal(f.job.nvBackgroundLease,undefined);}
});
test('only owned quiet live NV jobs attach',async()=>{
 for(const patch of [{registryState:'TN'},{quiet:false},{closed:true},{tab:99},{activeExpiresAt:0}]){const f=fixture();Object.assign(f.job,patch);await f.c.begin(f.job);assert.equal(f.calls.length,0);}
});
test('failed optional attachment preserves ordinary lookup and records its release',async()=>{const f=fixture({reject:true});await f.c.begin(f.job);await f.c.end(f.job);assert.equal(f.job.nvBackgroundLease,undefined);});
test('query completion and cancellation share one cleanup',async()=>{const f=fixture();await f.c.begin(f.job);await Promise.all([f.c.end(f.job),f.c.end(f.job)]);assert.equal(f.calls.filter(x=>x[0]==='detach').length,1);assert.equal(f.job.nvBackgroundLease,undefined);});
test('cancellation during attachment holds lease until late attachment is detached',async()=>{const f=fixture();let release;f.c.chrome.debugger.attach=async()=>{f.calls.push(['attach',7]);await new Promise(r=>release=r);};await f.c.begin(f.job);f.job.closed=true;const end=f.c.end(f.job);assert.ok(f.job.nvBackgroundLease);release();await end;assert.deepEqual(f.calls,[['attach',7],['Emulation.setFocusEmulationEnabled',false],['detach',7]]);assert.equal(f.job.nvBackgroundLease,undefined);});

test('delayed attachment does not block source readiness or create another session',async()=>{const f=fixture();let release;f.c.chrome.debugger.attach=async()=>{f.calls.push(['attach',7]);await new Promise(r=>release=r);};await f.c.begin(f.job);await f.c.begin(f.job);assert.equal(f.calls.length,1);release();await f.job.nvBackgroundLease.pending;await f.c.end(f.job);assert.equal(f.job.nvBackgroundLease,undefined);});

test('cleanup timeout preserves ownership and rejects screenshot overlap',async()=>{const f=fixture();let release;f.c.chrome.debugger.detach=async()=>{await new Promise(r=>release=r);};await f.c.begin(f.job);f.job.activeExpiresAt=Date.now()+20;await assert.rejects(f.c.end(f.job),/CLEANUP_TIMEOUT/);assert.ok(f.job.nvBackgroundLease);const pending=f.job.nvBackgroundLease.cleanupPromise;await f.c.begin(f.job);assert.equal(f.calls.filter(x=>x[0]==='attach').length,1);release();await pending;assert.equal(f.job.nvBackgroundLease,undefined);});

test('snapshot entry rejects unsettled NV lease before attachment',()=>{const s=fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/state-snapshot-worker.js'),'utf8');assert.match(s,/if\(job.registryState==='NV' && job.nvBackgroundLease\).*return null;/);});

test('real screenshot entry preserves status and refuses pending rendering ownership',async()=>{const f=fixture();f.job.generation=1;f.job.pending='q';f.job.command={id:'q',query:{state:'NV',operation:'detail'}};f.job.nvBackgroundLease={released:true};f.c.P.sameQuery=()=>true;f.c.isActive=()=>true;f.c.wfReturn=(_j,_s,v)=>v;vm.runInContext(fs.readFileSync(path.join(__dirname,'../deployment/staging_connector/state-snapshot-worker.js'),'utf8'),f.c);assert.equal(await f.c.captureStateSnapshot(f.job,f.job.command.query,'q'),null);assert.equal(f.calls.length,0);});

test('actual 3.3-second acknowledgement no longer aborts a lookup',async()=>{const f=fixture();f.c.chrome.debugger.attach=async()=>{await new Promise(r=>setTimeout(r,3300));};const start=Date.now();await f.c.begin(f.job);assert.ok(Date.now()-start<500);await f.job.nvBackgroundLease.pending;await f.c.end(f.job);assert.equal(f.job.nvBackgroundLease,undefined);});
test('no tab activation, window creation, navigation or source modification API exists in helper',()=>{assert.doesNotMatch(helpers,/tabs\.(update|create)|windows\.|Runtime\.evaluate|Page\.navigate|setTimeout\([^]*60000/);});
