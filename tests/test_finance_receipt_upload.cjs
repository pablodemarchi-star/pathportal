const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync('app/static/js/app.js', 'utf8');
const start = source.indexOf('const financeUploadFiles = new WeakMap();');
const end = source.indexOf('\ndocument.addEventListener("change", (event) => {\n  if (!event.target.closest?.("[data-finance-payment-method]"))', start);
const listeners = new Map();
class Node {
  constructor() {this.children = []; this.dataset = {};}
  replaceChildren(...nodes) {this.children = nodes;}
  setAttribute() {}
}
class DataTransfer {
  constructor() {this.files = []; this.items = {add: file => this.files.push(file)};}
}
const list = new Node(), text = {dataset: {financeUploadPlaceholder: 'Select one file or drop it here'}};
const row = {querySelector: selector => selector.includes('list') ? list : input};
const zone = {querySelector: selector => selector.includes('text') ? text : input,
  closest: () => row, classList: {add() {}, remove() {}}, contains: () => false};
const input = {files: [], multiple: false, disabled: false, validity: '',
  closest: selector => selector === 'fieldset' ? null : selector === '[data-finance-upload-input]' ? input : zone,
  setCustomValidity: message => {input.validity = message;}, reportValidity() {input.reported = true;}};
zone.closest = selector => selector === '[data-finance-upload-dropzone]' ? zone : row;
const document = {createElement: () => new Node(), addEventListener: (name, listener) => listeners.set(name, [...(listeners.get(name) || []), listener])};
vm.runInNewContext(source.slice(start, end), {document, DataTransfer});
const emit = (type, target, extra = {}) => (listeners.get(type) || []).forEach(fn => fn({target, preventDefault() {}, ...extra}));
const first = {name: 'first.pdf'}, next = {name: 'next.pdf'}, dropped = {name: 'dropped.pdf'};
input.files = [first]; emit('change', input);
assert.equal(input.files.length, 1); assert.equal(list.children[0].children[0].textContent, 'first.pdf');
input.files = [next]; emit('change', input);
assert.deepEqual(input.files, [next], 'A new selection replaces, rather than appends to, the replacement receipt');
emit('drop', zone, {dataTransfer: {files: [first, next]}});
assert.match(input.validity, /exactly one/); assert.deepEqual(input.files, [next]);
emit('drop', zone, {dataTransfer: {files: [dropped]}});
assert.equal(input.validity, ''); assert.deepEqual(input.files, [dropped]);
const remove = list.children[0].children[1];
remove.closest = selector => selector === '[data-finance-upload-remove]' ? remove : row;
emit('click', remove); assert.equal(input.files.length, 0); assert.equal(list.children.length, 0);
assert.equal(text.textContent, 'Select one file or drop it here');
input.multiple = true; input.files = [first]; emit('change', input); input.files = [next]; emit('change', input);
assert.deepEqual(input.files, [first, next], 'Existing multiple-document upload fields keep their behavior');
emit('reset', {querySelectorAll: () => [input]});
assert.equal(input.files.length, 0); assert.equal(list.children.length, 0);
input.disabled = true; emit('drop', zone, {dataTransfer: {files: [first]}}); assert.equal(input.files.length, 0);
console.log('Receipt uploads: picker/drop, one-file replacement, multiple-file rejection, remove/reset, read-only guard and existing multi-file inputs passed.');
