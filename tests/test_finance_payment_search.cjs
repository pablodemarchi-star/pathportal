const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const rows = ['PAY-2026-0090 London Services', 'PAY-2026-0091 Other Supplier'].map(text => ({dataset: {paymentSearchText: text}, hidden: false}));
const empty = {hidden: true};
const panel = {querySelectorAll: () => rows, querySelector: () => empty};
let update, lastUrl;
const input = {value: '', closest: () => panel, addEventListener: (event, fn) => { assert.equal(event, 'input'); update = fn; }};
vm.runInNewContext(fs.readFileSync('app/static/js/finance_payment_search.js', 'utf8'), {
  document: {querySelectorAll: () => [input]}, URL,
  window: {location: {href: 'http://localhost/finance-requests?tab=payment_requests'}, history: {replaceState: (state, title, url) => {lastUrl = url;}}}
});
input.value = 'LONDON'; update();
assert.deepEqual(rows.map(row => row.hidden), [false, true]);
input.value = '0091'; update();
assert.deepEqual(rows.map(row => row.hidden), [true, false]);
input.value = 'no match'; update(); assert.equal(empty.hidden, false);
input.value = ''; update();
assert.deepEqual(rows.map(row => row.hidden), [false, false]);
assert.equal(empty.hidden, true);
assert.equal(lastUrl.searchParams.has('payment_search'), false);
assert.equal(lastUrl.searchParams.get('tab'), 'payment_requests');
console.log('Live payment search: Payee, number, empty results and clearing verified.');
