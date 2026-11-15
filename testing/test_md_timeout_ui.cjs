const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(
  process.argv[2] || path.join(__dirname, '../web-staging/identity-review.js'), 'utf8');
const context = {window: {}};
vm.runInNewContext(script, context);
const {statusLabel} = context.window.CCIdentityReview;

test('Maryland displays the failed search status and retains identity review', () => {
  const outage = {
    state: 'MD',
    status: 'Site Not Reachable',
    success: false,
    raw_status_text: 'Maryland registry search did not complete',
    reason_code: 'PORTAL_ERROR'
  };
  assert.equal(statusLabel(outage), 'Site Not Reachable');
  assert.equal(statusLabel({...outage, reason_code: 'RUNNER_TIMEOUT'}), 'Site Not Reachable');
  assert.equal(statusLabel({...outage, status: 'Unable to Confirm'}), 'Review required');
  assert.equal(statusLabel({...outage, raw_status_text: 'Registry identity ambiguous'}), 'Review required');
  assert.equal(statusLabel({...outage, identity_review: {candidates: [{name: 'Example'}]}}), 'Confirm match');
  assert.equal(statusLabel({...outage, status: 'Current', success: true}), 'Current');
});
