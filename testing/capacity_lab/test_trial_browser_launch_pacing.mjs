import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import { randomUUID } from 'node:crypto';
import vm from 'node:vm';

const source = readFileSync(process.argv[2], 'utf8');
const context = {
  window: {},
  location: { origin: 'https://staging.compliance-express.com' },
  crypto: { randomUUID },
  setTimeout,
  Date,
};
vm.runInNewContext(source, context);
assert.ok(context.window.CCOptimized);

async function exercise(mode) {
  const started = performance.now();
  const launches = [];
  const results = await context.window.CCOptimized.run({
    name: 'Independent control', ein: '00-0000001',
    states: ['GA', 'MS', 'NM'], aliases: ['Separate discovered name'],
    mode, credentials: { admin_passcode: 'unused' }, apiBase: 'https://unused.invalid',
    externalLookup: async (state, names) => {
      launches.push({ state, at: performance.now() - started, names: [...names] });
      return { state, status: 'Not Registered', success: true };
    },
  });
  assert.deepEqual(Array.from(results, r => r.state), ['GA', 'MS', 'NM']);
  assert.ok(results.every(r => r.status === 'Not Registered'));
  return launches;
}

const standard = await exercise('standard');
assert.deepEqual(standard.map(x => x.names), [
  ['Separate discovered name'], ['Separate discovered name'], ['Separate discovered name'],
]);
assert.ok(standard[1].at - standard[0].at >= 250, JSON.stringify(standard));
assert.ok(standard[2].at - standard[0].at >= 650, JSON.stringify(standard));

const sales = await exercise('sales');
assert.deepEqual(sales.map(x => x.names), [[], [], []]);
assert.ok(sales[2].at - sales[0].at < 250, JSON.stringify(sales));

const abort = new AbortController();
const afterAbort = [];
const canceledRun = context.window.CCOptimized.run({
  name: 'Cancellation control', ein: '00-0000002',
  states: ['GA', 'MS', 'NM'], mode: 'standard',
  credentials: { admin_passcode: 'unused' }, apiBase: 'https://unused.invalid',
  signal: abort.signal,
  externalLookup: async state => {
    afterAbort.push(state);
    return { state, status: 'Not Registered', success: true };
  },
});
setTimeout(() => abort.abort(), 50);
await canceledRun.catch(() => {});
assert.deepEqual(afterAbort, ['GA']);
console.log(JSON.stringify({ standard, sales, results_preserved: true }));
