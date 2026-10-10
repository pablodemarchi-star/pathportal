const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const handlers = {};
const addHandlers = {};
const requests = [];
const node = () => ({ children: [], append(...children) { this.children.push(...children); }, replaceChildren() { this.children = []; } });
const preview = node();
const selectedChip = node();
const name = { value: '', focus() {} };
const standing = { value: 'Not applicable', selectedOptions: [{ value: 'Not applicable', dataset: {} }] };
const row = { querySelector(selector) { if (selector.includes('preview')) return preview; if (selector === 'select' || selector.includes('standing')) return standing; return name; } };
standing.closest = () => row;
standing.parentElement = { querySelector: () => selectedChip, classList: { toggle() {} } };
const list = { children: [], append(row) { this.children.push(row); this.lastElementChild = row; }, querySelectorAll() { return this.children; }, addEventListener() {} };
const primary = { value: 'Effective clearance', disabled: false };
const feedback = { classList: { add() {}, remove() {} } };
const form = {
  action: '/finance-control', closest(selector) { return selector === '.modal' ? null : { querySelectorAll: () => [] }; },
  querySelector(selector) {
    if (selector.includes('institution-list')) return list;
    if (selector.includes('add-institution')) return { addEventListener(event, fn) { addHandlers[event] = fn; } };
    if (selector.includes('institution-template')) return { content: { cloneNode: () => row } };
    if (selector.includes('auto-save-status')) return feedback;
    if (selector.includes('confirmed_with_admin')) return { checked: true };
    return primary;
  },
  querySelectorAll(selector) { return selector.includes('hidden') ? [{ name: 'csrf_token', value: 'token' }, { name: 'finance_institutions_form', value: '1' }] : []; },
  addEventListener(event, fn) { handlers[event] = fn; },
};
let resolveFirst;
const firstResponse = new Promise(resolve => { resolveFirst = resolve; });
const response = (ok) => ({ ok, headers: { get: () => 'application/json' }, json: async () => ({ ok, message: 'Earlier request failed', block_status: 'cleared', block_label: 'Cleared' }) });
const context = {
  document: { querySelectorAll: () => [form], createElement: node }, FormData, setTimeout, clearTimeout,
  fetch: async (url, options) => {
    requests.push(options.body);
    return requests.length === 1 ? firstResponse : response(true);
  },
};
const source = fs.readFileSync('app/static/js/app.js', 'utf8');
vm.runInNewContext(source.slice(source.lastIndexOf('document.querySelectorAll("[data-finance-institutions-form]")')), context);
(async () => {
  addHandlers.click();
  assert.equal(requests[0].get('institution_name'), '');
  name.value = 'New institution';
  standing.value = 'Mid-risk debt';
  standing.selectedOptions = [{ value: 'Mid-risk debt', dataset: { description: 'Debt description' } }];
  standing.matches = () => true;
  handlers.change({ target: standing });
  resolveFirst(response(false));
  await new Promise(resolve => setTimeout(resolve, 10));
  assert.equal(requests.length, 2);
  assert.equal(requests[1].get('institution_name'), 'New institution');
  assert.equal(requests[1].get('institution_standing'), 'Mid-risk debt');
  assert.equal(requests[1].get('institutions_confirmed_with_admin'), 'on');
  assert.equal(feedback.textContent, '');
  assert.equal(selectedChip.textContent, 'Mid-risk debt');
  assert.equal(preview.children.length, 1);
  assert.equal(preview.children[0].textContent, 'Debt description');
  console.log('Dynamic institution fields save; queued edits survive an earlier failed request.');
})().catch(error => { console.error(error); process.exitCode = 1; });
