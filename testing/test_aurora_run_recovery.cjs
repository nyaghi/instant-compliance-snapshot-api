const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const assetRoot = process.env.CC_RECOVERY_ASSETS;
const origin = "https://recovery-test.example.com";
const source = assetRoot && fs.readFileSync(path.join(assetRoot, "optimized-workflows.js"), "utf8");
const ein = "131624103";
const row = state => ({state, ein, success:true, status:"Current", evidence_url:"/proof/"+state});
const tick = () => new Promise(resolve => setImmediate(resolve));

function workflowHarness({cleanupFails=false, rejectServer=false}={}) {
  const submissions = [], actions = [], recorded = [], lookedUp = [];
  const paused = new AbortController();
  const sourceAbort = new AbortController();
  let polls = 0, cancelled = false;
  let finishInitialLookups;
  const initialLookups=new Promise(resolve=>{finishInitialLookups=resolve;});
  const context = {
    window:{}, location:{origin,pathname:"/",search:""}, AbortSignal, AbortController, URLSearchParams,
    crypto, performance, console, Date, setTimeout:(fn)=>{setImmediate(fn);return 1;}, clearTimeout(){},
    localStorage:{getItem:()=>null,setItem(){}},
    fetch:async (url,config) => {
      const payload=JSON.parse(config.body);
      actions.push(payload.action);
      if(payload.action==="start") {
        submissions.push(payload);
        return {ok:true,json:async()=>({token:"test-workflow",progressive_external_release:true})};
      }
      if(payload.action==="cancel") {cancelled=true; return {ok:true,json:async()=>({ok:true})};}
      if(payload.action==="release-external")return {ok:true,json:async()=>({ok:true})};
      if(payload.action!=="poll")throw Error("Unexpected action");
      polls++;
      if(cancelled && rejectServer)throw Error("Cannot confirm the old server run");
      const complete=paused.signal.aborted||cancelled;
      if(rejectServer && !cancelled && complete)throw Error("Injected server interruption");
      const results=complete?[row("FL"),row("MD")]:[row("FL")];
      if(!rejectServer && complete && cancelled)results.push({
        state:"AR",ein,success:false,status:"Unable to Confirm",status_reason:"WORKFLOW_INCOMPLETE"
      });
      return {ok:true,json:async()=>({results,finished:complete?Date.now():null})};
    },
  };
  vm.runInNewContext(source,context);
  const ordinary={name:"YWCA USA, Inc",ein,credentials:{email:"test@example.com",admin_passcode:"fixture"},aliases:[],
    apiBase:"",signal:sourceAbort.signal,userStop:true,
    externalLookup:async (state,names,signal)=>{
      lookedUp.push(state);
      if(lookedUp.length===3)finishInitialLookups();
      if(state==="AL")return row(state);
      return new Promise((resolve,reject)=>{
        const stop=()=>reject(cleanupFails
          ? Object.assign(new Error("The browser did not confirm tab closure"),{stopCleanupFailed:true})
          : signal.reason);
        if(signal.aborted)stop();else signal.addEventListener("abort",stop,{once:true});
      });
    }};
  const recovery={signal:paused.signal,record:r=>recorded.push(r)};
  return {context,ordinary,recovery,recorded,lookedUp,submissions,actions,paused,sourceAbort,initialLookups};
}

test("pausing browser work preserves finished evidence and allows the existing server run to finish", {skip:!source}, async()=>{
  const h=workflowHarness();
  const promise=h.context.window.CCOptimized.run({...h.ordinary,states:["AL","FL","GA","MD","NY"],recovery:h.recovery});
  await h.initialLookups;
  await tick();
  h.paused.abort(new DOMException("Pause","AbortError"));
  const result=await promise;
  assert.equal(result.paused,true);
  assert.equal(result.cleanupConfirmed,true);
  assert.equal(h.actions.includes("cancel"),false);
  assert.equal(h.submissions.length,1);
  assert.deepEqual(Array.from(result.partialResults,x=>x.state).sort(),["AL","FL","MD"]);
  assert.deepEqual(Array.from(result.partialResults,x=>x.evidence_url).sort(),["/proof/AL","/proof/FL","/proof/MD"]);
  assert.deepEqual(h.recorded.map(r=>r.state).sort(),["AL","FL","MD"]);
});

test("an unacknowledged browser teardown never permits a resume", {skip:!source}, async()=>{
  const h=workflowHarness({cleanupFails:true});
  const promise=h.context.window.CCOptimized.run({...h.ordinary,states:["AL","FL","GA","MD","NY"],recovery:h.recovery});
  await h.initialLookups;
  h.paused.abort(new DOMException("Pause","AbortError"));
  assert.equal((await promise).cleanupConfirmed,false);
});

test("a paused run with an unconfirmed server terminal state is view-only", {skip:!source}, async()=>{
  const h=workflowHarness({rejectServer:true});
  const promise=h.context.window.CCOptimized.run({...h.ordinary,states:["AL","FL","GA","MD","NY"],recovery:h.recovery});
  await h.initialLookups;
  h.paused.abort(new DOMException("Pause","AbortError"));
  const result=await promise;
  assert.equal(result.paused,true);
  assert.equal(result.cleanupConfirmed,false);
  assert.equal(h.actions.includes("cancel"),true);
});

test("Stop saves any final server rows and excludes the cancelled placeholders",{skip:!source},async()=>{
  const h=workflowHarness();
  const run=h.context.window.CCOptimized.run({...h.ordinary,
    states:["AL","AR","FL","GA","MD","NY"],recovery:h.recovery});
  await h.initialLookups;
  await tick();
  h.sourceAbort.abort(new DOMException("Stop","AbortError"));
  await assert.rejects(run,error=>{
    assert.equal(error.runStopped,true);
    assert.deepEqual(Array.from(error.partialResults,r=>r.state).sort(),["AL","FL","MD"]);
    return true;
  });
});

test("watchdog requires delayed browser health twice and at least two unfinished browser states",()=>{
  let current=0, check, alerted=0, probeResult, probes=0;
  const context={window:{},performance:{now:()=>current},setInterval:fn=>{check=fn;return 1;},clearInterval(){}};
  const asset=fs.readFileSync(path.join(__dirname,"../web-staging/aurora-recovery.js"),"utf8");
  vm.runInNewContext(asset,context);
  const monitor=context.window.CCAuroraRecovery.monitor(["NY","IL","FL"],
    async()=>{probes++;current+=probeResult.ms;return {ok:probeResult.ok};},()=>alerted++);
  return (async()=>{
    probeResult={ok:true,ms:3200};
    current=20000;await check();assert.equal(probes,0);
    current=30001;await check();assert.equal(alerted,0);
    probeResult={ok:true,ms:20};await check();assert.equal(alerted,0);
    probeResult={ok:false,ms:5000};await check();assert.equal(alerted,0);
    await check();assert.equal(alerted,1);
    monitor.completed("IL");
    current+=60000;await check();assert.equal(probes,4);assert.equal(alerted,1);
    monitor.stop();
  })();
});
