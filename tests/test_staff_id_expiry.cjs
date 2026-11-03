const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/staff_id_documents.js', 'utf8');
const elements = new Map();
const element = () => ({hidden: false, textContent: '', classes: new Set(), classList: {toggle(name, enabled) { this.owner.classes[enabled ? 'add' : 'delete'](name); }}});
const find = key => {
  if (!elements.has(key)) { const node = element(); node.classList.owner = node; elements.set(key, node); }
  return elements.get(key);
};
let now = Date.parse('2026-12-20T02:59:59Z'), scheduled;
const opener = find('opener');
opener.dataset = {staffIdExpiry: '2026-12-20T00:00:00-03:00'};
const context = {documentInfo: {expires_at: opener.dataset.staffIdExpiry, expiry_date: '20/12/2026'},
  issued: true, opener, find, expiryTimer: undefined, dialog: {open: true, dataset: {canEdit: 'true'}},
  Date: {now: () => now, parse: Date.parse}, Math, Number,
  setTimeout: (fn, delay) => { scheduled = {fn, delay}; return 1; }, clearTimeout() {},
  document: {querySelectorAll: () => [opener], addEventListener() {}}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('  const isExpired ='), source.indexOf('  const status =')),
  context);
assert.equal(find('unissue').hidden, true);
assert.equal(opener.classes.has('is-expired'), false);
assert.equal(scheduled.delay, 1020);
now = Date.parse('2026-12-20T03:00:00Z');
scheduled.fn();
assert.equal(opener.classes.has('is-expired'), true);
assert.equal(find('unissue').hidden, false);
context.issued = false;
scheduled.fn();
assert.equal(find('unissue').hidden, true);
assert.equal(opener.classes.has('is-expired'), true);
context.dialog.dataset.canEdit = 'false'; context.issued = true;
scheduled.fn();
assert.equal(find('unissue').hidden, true);
const mask = source.slice(source.indexOf("    const digits = expiryInput.value"), source.indexOf("  input?.addEventListener('change'"));
const maskBody = mask.slice(0, mask.lastIndexOf('  });'));
for (const [value, expected] of [['20122026', '20/12/2026'], ['2012', '20/12'], ['20/12/2026', '20/12/2026']]) {
  const state = {expiryInput: {value}};
  vm.runInNewContext(maskBody, state);
  assert.equal(state.expiryInput.value, expected);
}
console.log('Staff ID expiry: midnight GMT-3, open-page updates, permissions and automatic date separators verified.');
