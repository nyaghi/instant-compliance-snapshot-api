const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../deployment/staging_connector/registry-worker.js'), 'utf8');
const snippet = source.slice(source.indexOf('async function registryNorthCarolinaQuery('), source.indexOf('async function registryGaSearch('));
const warning = 'NY_CONNECTOR_REGISTRY_NC_PROFILE_SOURCE_ERROR';
const identifier = 'SL001850';
const url = 'https://www.sosnc.gov/online_services/search/charities_profile/123';

async function fixture(options = {}) {
  const calls = [];
  const job = { tab: 1, activeExpiresAt: options.budget ?? 30000, ncProfiles: { [identifier]: url } };
  const run = vm.runInNewContext('(' + snippet.trim() + ')', {
    Date: { now: () => 0 }, P: { TRIAL_ORIGIN: options.staging ?? true },
    owned: new Set(options.owned === false ? [] : [1]), diagnostic() {},
    chrome: { tabs: { get: async () => ({url: options.actual ?? url}) } },
    wfAwait: (_, __, run) => run(), wfReturn: (_, __, result) => result,
    registryMessage: async (_, { action }) => {
      calls.push(action);
      return { ok: true, evidence: { license: identifier } };
    },
    registryNavigate: async (_, request, budget) => {
      calls.push([request, budget]);
      if (options.errors?.length) throw new Error(options.errors.shift());
    }
  });
  let error;
  try { await run(job, { operation: 'detail', identifier, url }); } catch (e) { error = e.message; }
  return { calls, error };
}

test('NC first successful profile does not retry', async () => {
  assert.deepEqual((await fixture()).calls, [[url, undefined], 'registry-nc-profile']);
});
test('NC source warning retries only the exact owned license profile within six seconds', async () => {
  const result = await fixture({errors: [warning]});
  assert.deepEqual(result.calls, [[url, undefined], [url, 6000], 'registry-nc-profile']);
  assert.equal(result.error, undefined);
});
test('NC persistent error stops after one retry and never yields a completed result', async () => {
  const result = await fixture({errors: [warning, warning]});
  assert.deepEqual(result.calls, [[url, undefined], [url, 6000]]);
  assert.equal(result.error, warning);
});
test('NC other errors, insufficient time and unrelated or unowned tabs do not retry', async () => {
  for (const options of [
    {errors: ['NY_CONNECTOR_NC_RATE_LIMITED']}, {budget: 8999}, {actual: url + '4'},
    {owned: false}, {staging: false}
  ]) {
    const result = await fixture({errors: [warning], ...options});
    assert.deepEqual(result.calls, [[url, undefined]]);
    assert.ok(result.error);
  }
});
