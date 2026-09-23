const test = require('node:test');
const assert = require('node:assert/strict');
const sales = require('../web-staging/sales-mode.js');

test('uncertain, pending, exempt and restrictive states cannot turn into no-record or current', () => {
  for (const status of ['Unable to Confirm','Unable to Verify','Site Not Reachable','Needs Review','Unknown','Pending','Exempt','Suspended','Revoked']) {
    assert.equal(sales.displayStatus(status),status);
  }
  assert.equal(sales.displayStatus('Upcoming Filing'),'Current');
  assert.equal(sales.displayStatus('Not Registered'),'No record found');
});
test('scope contains current direct EIN implementations including MA and VA, excludes name-only CT',()=>{
  assert.equal(sales.EIN_STATES.length,16);
  assert(sales.EIN_STATES.includes('MA')); assert(sales.EIN_STATES.includes('VA'));
  assert(!sales.EIN_STATES.includes('CT'));
  assert.match(sales.scopeText(['CA'],['CA','AR'],1),/Not checked: AR/);
});
test('bounded work preserves request/result associations and never exceeds capacity',async()=>{
  let active=0,peak=0; const completed=[];
  const inputs=Array.from({length:30},(_,i)=>'state-'+i);
  const result=await sales.runBounded(inputs,3,async state=>{
    peak=Math.max(peak,++active);
    await new Promise(resolve=>setTimeout(resolve,state==='state-0'?20:1));
    active--;completed.push(state);return {state};
  });
  assert.equal(peak,3);assert.equal(new Set(completed).size,30);
  assert.deepEqual(result.map(r=>r.state),inputs);
  assert.notEqual(completed[0],'state-0');
});
test('operation mode keeps existing sequential state ordering',async()=>{
  const order=[]; await sales.runBounded(['A','B','C'],1,async state=>{order.push(state);});
  assert.deepEqual(order,['A','B','C']);
});
test('a failed operation is propagated, never synthesized into a negative',async()=>{
  await assert.rejects(sales.runBounded(['A'],3,async()=>{throw Error('unavailable');}),/unavailable/);
});
