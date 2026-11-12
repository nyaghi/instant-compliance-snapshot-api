const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const element = () => ({children: [], appendChild(node) { this.children.push(node); }, addEventListener() {}, setAttribute() {}});
const ctx = {window: {}, URL, document: {createElement: element}};
vm.runInNewContext(fs.readFileSync('web-staging/identity-review.js', 'utf8'), ctx);
const ui = ctx.window.CCIdentityReview;
const row = {
  state: 'MA', status: 'Unable to Confirm', status_reason: 'MA_FORM_PC_ATTACHMENT_IDENTITY_CONFLICT',
  matched_registry_identifier: '027225',
  ma_filing_evidence: {ago_account: '027225', registry_status: 'Not Doing Business in Mass'},
  source_note: 'The FY2020 attachment shows a different EIN.'
};

test('Massachusetts activity is a display label with an unconfirmed filing note', () => {
  assert.equal(ui.statusLabel(row), 'Not Doing Business in Massachusetts');
  const container = element();
  ui.render(container, row, () => {}, () => {});
  const texts = node => [node.textContent || '', ...node.children.flatMap(texts)];
  assert.ok(texts(container).includes('Filing status unconfirmed'));
  assert.ok(texts(container).includes(row.source_note));
  assert.equal(row.status, 'Unable to Confirm');
});

test('Offers a retry for an incomplete filing read and routes confirmed attachment conflicts to the state', () => {
  const texts = node => [node.textContent || '', ...node.children.flatMap(texts)];
  const detail = {...row, status_reason: 'MA_FORM_PC_DETAIL_UNCONFIRMED', source_note: '', source_url: 'https://masscharities.my.site.com/FilingSearch/s/'};
  for (const [result, canRetry] of [
    [row, false],
    [{...detail, ma_filing_evidence: {...row.ma_filing_evidence, wrong_filing_year: 2020}}, false],
    [detail, true],
  ]) {
    const container = element();
    ui.render(container, result, () => {}, () => {});
    assert.equal(texts(container).includes('Retry MA'), canRetry);
    if (result.source_url) assert.ok(texts(container).includes('Open state lookup'));
  }
});

test('Does not overwrite a confirmed status, unmatched record, other state, or identity decision', () => {
  for (const changes of [
    {matched_registry_identifier: '019873'}, {state: 'AL'}, {ma_filing_evidence: {}},
    {status_reason: 'MA_CHARITY_SELECTION_UNCONFIRMED'}, {identity_review: {candidates: [{}]}},
    {status: 'Delinquent'}, {status: 'Not Registered'}
  ]) assert.notEqual(ui.statusLabel({...row, ...changes}), 'Not Doing Business in Massachusetts');
});
