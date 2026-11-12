const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

const source = readFileSync('deployment/staging_connector/worker.js', 'utf8');
function model() {
  const start = source.indexOf('const tnRetryGrants = new Map();');
  const stop = source.indexOf('async function close(', start);
  let now = 10000;
  const ctx = {
    Date: { now: () => now }, P: { TRIAL_ORIGIN: 'test' }, queue: [], activeLanes: new Map(),
    laneStarts: new Map(), isDuoJob: () => true, pumpTimer: null, ACTIVE_TTL: 300000,
    CCSourceRail: { notify() {}, isReady: () => true, admissionSlots: () => [] },
    arm() {}, diagnostic() {}, notifyQueue() {}, saveRuntime: () => new Promise(() => {}),
  };
  vm.createContext(ctx);
  vm.runInContext(source.slice(start, stop) + '\nthis.allow=allowTnRetry; this.take=takeTnRetry; this.pump=pump;', ctx);
  return { ...ctx, advance: ms => { now += ms; } };
}

function job(state, tab = 1, doc = 'first') {
  return { registryState: state, sender: { tab: { id: tab }, documentId: doc }, port: {}, enqueuedAt: 1 };
}

const failure = { ok: false, reason: 'NY_CONNECTOR_TN_VERIFICATION_PENDING' };
test('Tennessee retry only follows an incomplete search and is consumed once by the same document', () => {
  const m = model();
  m.allow(job('TN'), { operation: 'search' }, failure);
  assert.equal(m.take(job('TN', 2)), false);
  assert.equal(m.take(job('TN', 1, 'navigated')), false);
  assert.equal(m.take(job('TN')), true);
  assert.equal(m.take(job('TN')), false);
  m.allow({ ...job('TN'), tnRetryAttempt: true }, { operation: 'search' }, failure);
  m.allow({ ...job('TN'), tnSearchCompleted: true }, { operation: 'search' }, failure);
  m.allow(job('TN'), { operation: 'detail' }, failure);
  assert.equal(m.take(job('TN')), false);
  m.allow(job('TN'), { operation: 'search' }, failure);
  m.advance(15001);
  assert.equal(m.take(job('TN')), false);
});

test('retry takes one free position ahead of its own work and respects other documents and capacity', () => {
  const m = model();
  m.activeLanes.set('NY', { ...job('NY'), duoSlot: 0 });
  m.queue.push(job('IL'), { ...job('TN'), tnRetryAttempt: true }, job('GA'));
  m.pump();
  assert.equal(m.activeLanes.get('TN').duoSlot, 1);
  m.pump();
  assert.equal(m.activeLanes.size, 2);
  const other = model();
  other.queue.push(job('IL'), job('GA', 2), { ...job('TN'), tnRetryAttempt: true });
  other.pump();
  assert.equal(other.activeLanes.has('IL'), true);
  assert.equal(other.activeLanes.has('TN'), false);
});
