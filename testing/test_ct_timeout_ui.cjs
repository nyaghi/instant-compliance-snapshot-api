const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = {window:{}};
vm.runInNewContext(fs.readFileSync('web-staging/identity-review.js','utf8'), context);
const label = context.window.CCIdentityReview.statusLabel;
test('CT transport failure stays unavailable; identity and partial evidence are not outages', () => {
  const result = {state:'CT',status:'Site Not Reachable',success:false,
    raw_status_text:'Connecticut direct registry lookup could not be completed',reason_code:'PORTAL_ERROR'};
  assert.equal(label(result),'Site Not Reachable');
  assert.equal(label({...result,reason_code:'RUNNER_TIMEOUT'}),'Site Not Reachable');
  assert.equal(label({...result,status:'Unable to Confirm',reason_code:'CT_RESULTS_INCOMPLETE'}),'Review required');
  assert.equal(label({...result,identity_review:{candidates:[{name:'Example'}]}}),'Confirm match');
  assert.equal(label({...result,state:'AL'}),'Review required');
  for (const status of ['Current','Delinquent','Not Registered'])
    assert.equal(label({...result,status,success:true}),status);
});
