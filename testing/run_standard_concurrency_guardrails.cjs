const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const cp = require('node:child_process');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'web-staging/index.html'), 'utf8');
const start = html.indexOf('    async function runStateChecks(');
const end = html.indexOf('\n    stateCheckboxes.forEach', start);
const source = html.slice(start, end);
const states = [...html.matchAll(/name="states" value="([A-Z]{2})"/g)].map(x => x[1]);
const tick = () => new Promise(setImmediate);

function fixture() {
  let active = 0, peak = 0;
  const calls = [], pending = new Map(), completions = [];
  const context = vm.createContext({
    progressCount: {textContent: ''}, progressBar: {style: {}},
    stateLaneBases: (selected, ein, state) => [selected.length === 1 && state === 'CT' ? 'secondary' : 'primary'],
    checkSingleState: (lanes, ein, email, state, identity) => {
      active++; peak = Math.max(peak, active);
      calls.push({lanes, ein, email, state, name: identity.value, identity});
      return new Promise(resolve => pending.set(state, result => {
        active--; pending.delete(state); completions.push(state); resolve(result);
      }));
    },
  });
  vm.runInContext(source, context);
  return {context, calls, pending, completions, get peak() { return peak; }, get active() { return active; },
    run: (selected=states, name='Control Organization', ein='123456789') => context.runStateChecks(selected, ein, 'fixture@example.org', name),
    finish: (state, result={}) => pending.get(state)({state, status:'Current', organization_name:'Control Organization', registration_date:'2001-01-01', comments:'Verified registry evidence', ...result}),
    async drain(except=[]) {
      for (let i=0; i<40 && [...pending.keys()].some(s => !except.includes(s)); i++) {
        for (const state of [...pending.keys()].filter(s => !except.includes(s)).reverse()) this.finish(state);
        await tick();
      }
    },
  };
}

test('all 34 states use exactly 15 slots, including NY, and return the requested order once each', async () => {
  const f=fixture(), run=f.run();
  assert.equal(states.length,34); assert.equal(f.calls.length,15); assert.equal(f.calls[0].state,'NY');
  const firstNonNy=f.calls[1].state; f.finish(firstNonNy); await tick();
  assert.equal(f.calls.length,16); assert.equal(f.active,15); assert.equal(f.context.progressCount.textContent,'1 of 34');
  await f.drain(); const result=await run;
  assert.equal(f.peak,15); assert.equal(f.calls.length,34); assert.equal(new Set(f.calls.map(x=>x.state)).size,34);
  assert.deepEqual(Array.from(result,r=>r.state),states);
  assert.equal(f.context.progressCount.textContent,'34 of 34'); assert.equal(f.context.progressBar.style.width,'100%');
  assert(result.every(r=>r.registration_date==='2001-01-01' && r.comments==='Verified registry evidence'));
});

test('a slow NY occupies one slot without blocking the other 33 states', async () => {
  const f=fixture(); let done=false; const run=f.run().then(r=>{done=true;return r;});
  await f.drain(['NY']); assert.equal(done,false); assert.equal(f.completions.length,33);
  assert.equal(f.peak,15); assert.equal(f.context.progressCount.textContent,'33 of 34');
  f.finish('NY',{status:'Unable to Confirm',success:false,comments:'Verification did not complete'});
  const result=await run; assert.equal(result.find(r=>r.state==='NY').status,'Unable to Confirm'); assert.equal(result.length,34);
});

test('no NY, small selected subsets, single CT routing and empty input stay bounded', async () => {
  for (const selected of [states.filter(s=>s!=='NY'), ['DC','RI'], ['CT'], ['NY'], []]) {
    const f=fixture(), run=f.run(selected);
    assert.equal(f.calls.length,Math.min(15,selected.length));
    if (selected.length===1 && selected[0]==='CT') assert.deepEqual(Array.from(f.calls[0].lanes),['secondary']);
    await f.drain(); assert.deepEqual(Array.from(await run,r=>r.state),selected);
    assert.equal(f.calls.length,selected.length);
  }
});

test('one unavailable state cannot erase completed results or prevent queued states from running', async () => {
  const f=fixture(), run=f.run();
  f.finish('AK',{status:'Site Not Reachable',success:false,comments:'Registry unavailable; no negative conclusion'});
  await tick(); await f.drain(); const result=await run;
  assert.equal(result.length,34); assert.equal(result.find(r=>r.state==='AK').status,'Site Not Reachable');
  assert.equal(result.filter(r=>r.status==='Current').length,33); assert.equal(f.calls.length,34);
});

test('response names cannot replace the entered primary name in later queued requests', async () => {
  const f=fixture(), run=f.run(states,'Primary Legal Name','012345678');
  f.calls[0].identity.value='Different returned name';
  f.finish(f.calls[0].state,{organization_name:'Different returned name'}); await tick(); await f.drain(); await run;
  assert(f.calls.every(x=>x.name==='Primary Legal Name' && x.ein==='012345678'));
  assert.equal(new Set(f.calls.map(x=>x.identity)).size,34);
});

test('two organization workflows and a subsequent run retain separate inputs and results', async () => {
  const a=fixture(), b=fixture(), ar=a.run(states,'Alpha','111111111'), br=b.run(states,'Beta','222222222');
  await a.drain(); await b.drain(); await ar; await br;
  assert(a.calls.every(x=>x.name==='Alpha' && x.ein==='111111111'));
  assert(b.calls.every(x=>x.name==='Beta' && x.ein==='222222222'));
  const next=a.run(['CO'],'Gamma','333333333');a.finish('CO');const results=await next;
  assert.equal(results.length,1);assert.equal(a.context.progressCount.textContent,'1 of 1');
  assert.equal(a.calls.at(-1).name,'Gamma');
});

test('the 09.24.5 scheduler and existing NY page collectors remain unchanged', () => {
  const prior=file=>cp.execFileSync('git',['show','35e61ae:'+file],{cwd:root,maxBuffer:30*1024*1024}).toString().replaceAll('\r\n','\n');
  const current=file=>fs.readFileSync(path.join(root,file),'utf8').replaceAll('\r\n','\n');
  const scheduler=s=>s.slice(s.indexOf('    async function runStateChecks('),s.indexOf('\n    stateCheckboxes.forEach',s.indexOf('    async function runStateChecks(')));
  assert.equal(scheduler(current('web-staging/index.html')),scheduler(prior('web-staging/index.html')));
  for(const file of ['Charity_Checker_Script for 13_states.py','browser-connector/ny-content.js','browser-connector/ny-main.js','browser-connector/recovery.js'])assert.equal(current(file),prior(file),file);
});
