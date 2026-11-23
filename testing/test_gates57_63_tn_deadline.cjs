/* Exercise the real TN optional capture and delivery watchdogs under a controlled clock. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const connector = path.join(__dirname, '../deployment/staging_connector');
const read = name => fs.readFileSync(path.join(connector, name), 'utf8');
const functionSource = (source, name, end) => source.slice(
  source.indexOf('async function ' + name), source.indexOf(end, source.indexOf('async function ' + name))
);
const open = () => {
  let resolve;
  return {
    promise: new Promise(accept => { resolve = accept; }),
    settle: value => resolve(value),
  };
};
const tick = () => new Promise(resolve => setImmediate(resolve));
const origin = 'https://tncab.tnsos.gov';

function makeFixture(name, {hungDetach = false, refusedDetach = false} = {}) {
  const events = [], timers = new Map(), logs = [];
  let clock = 1000, serial = 0;
  const pixels = open(), detach = open();
  const query = {state:'TN', operation:'search', name};
  const job = {registryState:'TN', tab:7, generation:0, pending:'first', command:{id:'first',query},
    activeExpiresAt:clock + 300000};
  const context = {
    URL, Promise, JSON, Date:{now:() => clock},
    setTimeout(fn, ms) { const id = ++serial; timers.set(id,{fn, ms}); return id; },
    clearTimeout(id) { timers.delete(id); },
    P:{TRIAL_ORIGIN:'https://fixture.onrender.com', sameQuery:(a,b) => JSON.stringify(a)===JSON.stringify(b)},
    owned:new Set([7]), isActive:() => true, registryOrigin:() => origin,
    wfAwait:(_job, _label, fn) => fn(), wfReturn:(_job, _label, value) => value,
    diagnostic:(type,_job,detail) => logs.push({type,detail}),
    chrome:{
      tabs:{
        get:async () => ({url:origin+'/portal/registered-charities-search'}),
        sendMessage:async () => ({url:origin+'/portal/registered-charities-search',document_id:'source',
          public_text:name,source_fields_visible:true}),
      },
      debugger:{
        attach:async () => events.push('attach'),
        detach:async () => {
          events.push('detach');
          if(hungDetach)await detach.promise;
          if(refusedDetach)throw Error('browser did not acknowledge detach');
        },
        sendCommand:async (_, method) => {
          events.push(method);
          if(method==='Page.getLayoutMetrics')return {cssContentSize:{width:1200,height:1200},
            cssLayoutViewport:{clientWidth:1200,clientHeight:900}};
          if(method==='Page.captureScreenshot')return pixels.promise;
          return {};
        },
      },
    },
  };
  vm.createContext(context);
  vm.runInContext(read('state-snapshot-worker.js'), context);
  vm.runInContext(functionSource(read('worker.js'), 'awaitSnapshotCleanup', 'function armEinLightNameLimit'), context);
  vm.runInContext(functionSource(read('registry-worker.js'), 'registryMessage', 'async function registryReadinessMessage'), context);
  return {job, query, context, events, logs, pixels, detach, advance(ms) {
    const timer = [...timers].find(([,t]) => t.ms === ms);
    assert.ok(timer, 'missing timer for ' + ms + ' ms');
    timers.delete(timer[0]); clock+=ms; timer[1].fn();
  }, now:() => clock};
}

async function timedOutGrid(name, hungDetach) {
  const f = makeFixture(name, {hungDetach});
  const capture = f.context.captureStateSnapshot(f.job,f.query,'first');
  await tick();
  assert.ok(f.events.includes('Page.captureScreenshot'));
  f.advance(1500);
  assert.equal(await capture, null);
  const next = {...f.query, name:'NU'};
  f.job.command={id:'next',query:next}; f.job.pending='next';
  const cleanup = f.context.awaitSnapshotCleanup(f.job,'next');
  if(hungDetach) {
    const rejected = assert.rejects(cleanup,/TN_OPTIONAL_CAPTURE_CLEANUP_TIMEOUT/);
    f.advance(1500);
    await rejected;
    assert.equal(f.job.snapshotCleanupBusy,true);
  } else {
    await cleanup;
    assert.equal(f.job.snapshotCleanupBusy,undefined);
  }
  // The old reply may arrive much later, after the next command or tab closure.
  f.pixels.settle({data:'AA=='});
  f.detach.settle();
  await tick();
  assert.equal(f.job.snapshotCaptures,undefined);
  assert.equal(f.events.filter(x=>x==='detach').length,1);
}

async function failedDetach(name) {
  const f = makeFixture(name, {refusedDetach:true});
  const capture=f.context.captureStateSnapshot(f.job,f.query,'first');
  await tick();
  f.advance(1500);
  await capture;
  f.pixels.settle({data:'AA=='});
  await tick();
  f.job.command={id:'next',query:f.query}; f.job.pending='next';
  await assert.rejects(f.context.awaitSnapshotCleanup(f.job,'next'),/TN_OPTIONAL_CAPTURE_CLEANUP_TIMEOUT/);
}

async function timedRegistryQuery(name) {
  const f = makeFixture(name);
  const pending = open();
  let dispatches = 0;
  f.context.chrome.tabs.sendMessage = async () => { dispatches++; return pending.promise; };
  const deadline = f.now()+35000;
  const request = f.context.registryMessage(f.job,{action:'registry-tn',query:f.query,
    searchDeadline:deadline,budgetMs:35000});
  await tick();
  f.advance(35000);
  const result = await request;
  assert.equal(result.ok,false);
  assert.equal(result.reason,'NY_CONNECTOR_TN_SEARCH_DELIVERY_TIMEOUT');
  assert.equal(dispatches,1);
  pending.settle({ok:true,evidence:{complete:true,rows:[],total:0}});
  await tick();
  assert.equal(dispatches,1);
  const expired = await f.context.registryMessage(f.job,{action:'registry-tn',query:f.query,
    searchDeadline:deadline,budgetMs:1});
  assert.equal(expired.reason,'NY_CONNECTOR_TN_VERIFICATION_OR_FORM_PENDING');
  assert.equal(dispatches,1);
}

async function completedRegistryQuery(name) {
  const f = makeFixture(name);
  const evidence = {complete:true, rows:[], total:0, query:f.query};
  f.context.chrome.tabs.sendMessage = async () => ({ok:true,evidence});
  const response = await f.context.registryMessage(f.job,{action:'registry-tn',query:f.query,
    searchDeadline:f.now()+35000,budgetMs:35000});
  assert.equal(response.ok,true);
  assert.equal(response.evidence,evidence);
}

const names = process.env.CC_GATE_REPAIR_ROSTER
  ? JSON.parse(fs.readFileSync(process.env.CC_GATE_REPAIR_ROSTER,'utf8')).map(row => row.name)
  : ['Northeastern University'];
test('optional TN grid cleanup is bounded and late pixels never return', async () => {
  for(const name of names) {
    await timedOutGrid(name,false);
    await timedOutGrid(name,true);
    await failedDetach(name);
  }
});
test('TN dispatch shares the original deadline and never replays a delivery timeout', async () => {
  for(const name of names) {
    await timedRegistryQuery(name);
    await completedRegistryQuery(name);
  }
});

