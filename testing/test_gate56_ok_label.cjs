const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('Oklahoma unavailable name-search form has the same label on screen and in both workbook sheets', async () => {
  const context = vm.createContext({ window: {}, Blob, TextEncoder, URL });
  for (const file of ['identity-review.js', 'excel-export.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../web-staging', file), 'utf8'), context);
  }
  const roster = require('./fixtures/gate55/LOCAL-70.json');
  assert.equal(new Set(roster.map(row => row.ein)).size, 70);
  const rows = roster.map(org => ({ organization_name: org.name, ein: org.ein, state: 'OK',
    status: 'Site Not Reachable', reason_code: 'PORTAL_ERROR', success: false,
    confirmation_required: false, error: 'Could not select Oklahoma Search by Name.' }));
  const label = context.window.CCIdentityReview.statusLabel;
  for (const row of rows) {
    assert.equal(label(row), 'Site Not Reachable');
    assert.equal(label({ ...row, status: 'Current', success: true }), 'Current');
    assert.equal(label({ ...row, error: 'Unexpected response' }), 'Review required');
    assert.equal(label({ ...row, identity_review: { candidates: [{}] } }), 'Confirm match');
  }
  const bytes = await context.window.CCExcelExport.build(rows).arrayBuffer();
  const xml = Buffer.from(bytes).toString('utf8');
  assert.equal((xml.match(/>Site Not Reachable</g) || []).length, 2 * rows.length);
});

