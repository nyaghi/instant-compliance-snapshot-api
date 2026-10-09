import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import vm from 'node:vm';

const context = {
  window: {},
  location: { origin: 'https://staging.compliance-express.com' },
  crypto: { randomUUID },
  setTimeout,
  Date,
};
vm.runInNewContext(readFileSync(process.argv[2], 'utf8'), context);
assert.ok(context.window.CCOptimized);

const states = ['AL', 'GA', 'IL', 'MS', 'NC', 'NV', 'TN', 'NM', 'NY'];
async function exercise(mode, signal) {
  let active = 0;
  let peak = 0;
  const launched = [];
  const names = [];
  const results = await context.window.CCOptimized.run({
    name: 'Independent control', ein: '00-0000001', states,
    aliases: ['Corroborated alternate'], mode, signal,
    credentials: { admin_passcode: 'unused' }, apiBase: 'https://unused.invalid',
    externalLookup: async (state, suppliedNames) => {
      active++;
      peak = Math.max(peak, active);
      launched.push(state);
      names.push([...suppliedNames]);
      await new Promise(resolve => setTimeout(resolve, 10));
      active--;
      return { state, status: 'Not Registered', success: true };
    },
  });
  return { peak, launched, names, results };
}

const standard = await exercise('standard');
assert.equal(standard.peak, 4);
assert.deepEqual(standard.launched.slice(0, 4), ['GA', 'MS', 'NM', 'AL']);
assert.deepEqual(Array.from(standard.results, r => r.state), states);
assert.ok(standard.results.every(r => r.status === 'Not Registered'));
assert.ok(standard.names.every(x => x.length === 1 && x[0] === 'Corroborated alternate'));

const sales = await exercise('sales');
assert.equal(sales.peak, states.length);
assert.deepEqual(sales.launched, states);
assert.ok(sales.names.every(x => x.length === 0));

const controller = new AbortController();
const launchedAfterCancel = [];
const cancelRun = context.window.CCOptimized.run({
  name: 'Cancellation control', ein: '00-0000002', states,
  mode: 'standard', signal: controller.signal,
  credentials: { admin_passcode: 'unused' }, apiBase: 'https://unused.invalid',
  externalLookup: async state => {
    launchedAfterCancel.push(state);
    await new Promise(resolve => setTimeout(resolve, 20));
    return { state, status: 'Not Registered', success: true };
  },
});
setTimeout(() => controller.abort(), 1);
await cancelRun.catch(() => {});
assert.deepEqual(launchedAfterCancel, ['GA', 'MS', 'NM', 'AL']);

console.log(JSON.stringify({ standard_peak: standard.peak,
  sales_peak: sales.peak, standard_first: standard.launched.slice(0, 4),
  canceled_launches: launchedAfterCancel.length, results_preserved: true }));
