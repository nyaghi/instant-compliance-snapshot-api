import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const html = readFileSync(new URL('../web-staging/index.html', import.meta.url), 'utf8');
const names = ['commentsWithRegistryFooter', 'fallbackResult', 'checkSingleState'];
const context = vm.createContext({progressLabel: {}, API_BASE:'https://staging.example', sleep:async()=>{}, requestSingleState:async()=>{throw new Error('network unavailable');}});
for (const name of names) {
  const marker = name === 'checkSingleState' ? '    async function ' : '    function ';
  const start = html.indexOf(marker + name + '(');
  assert.ok(start >= 0);
  const rest = html.slice(start + marker.length);
  const boundary = rest.search(/\n    (?:async )?function /);
  assert.ok(boundary >= 0);
  vm.runInContext(html.slice(start, start + marker.length + boundary), context);
}
assert.match(context.commentsWithRegistryFooter({status:'Current'}), /No explanation accompanied the Current result/);
assert.equal(context.commentsWithRegistryFooter({comments:'Evidence and date explain this status.'}), 'Evidence and date explain this status.');
assert.match(context.fallbackResult('OK','012345678').comments, /Registration status remains unconfirmed/);
assert.equal(context.fallbackResult('OK','012345678','The certificate could not be retrieved.').comments, 'The certificate could not be retrieved.');
let result = await context.checkSingleState(['https://staging.example'], '012345678', 'test@example.org', 'OK', {value:'Example'});
assert.equal(result.status, 'Site Not Reachable');
assert.match(result.comments, /response could not be received/);
context.requestSingleState = async()=>{const e = new Error(); e.name='AbortError'; throw e;};
result = await context.checkSingleState(['https://staging.example'], '012345678', 'test@example.org', 'OK', {value:'Example'});
assert.match(result.comments, /request timed out/);
assert.match(result.comments, /does not mean the organization is unregistered or delinquent/);
console.log('PASS 6 web comment scenarios; no network requests');
