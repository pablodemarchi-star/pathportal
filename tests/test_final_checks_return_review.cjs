const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/app.js', 'utf8');
const start = source.indexOf('const syncReturnMaterialsOptions =');
const end = source.indexOf('document.addEventListener("click"', start);
const classes = new Map();
const url = {value: 'https://example.com/label', defaultValue: 'https://example.com/label'};
const field = {};
const upload = {dataset: {filePresent: 'true'}};
const box = {
  classList: {toggle: (name, value) => classes.set(name, Boolean(value))},
  querySelector: selector => selector === '[data-return-label-upload]' ? upload : selector.includes('data-return-label-field') ? field : null,
  querySelectorAll: () => []
};
const radio = {value: 'immediate_dispatch', checked: true, closest: () => box};
const form = {dataset: {returnReviewRequired: 'true'}, querySelectorAll: selector => selector.includes('radio') ? [radio] : []};
const context = vm.createContext({isValidReturnLabelUrl: value => value.startsWith('https://')});
vm.runInContext(source.slice(start, end) + '\nthis.sync = syncReturnMaterialsOptions;', context);
context.sync(form);
assert.equal(classes.get('needs-label'), true, 'A complete option stays yellow until the required review is confirmed');
form.dataset.returnReviewRequired = 'false'; context.sync(form);
assert.equal(classes.get('needs-label'), false);
upload.dataset.filePresent = 'false'; context.sync(form);
assert.equal(classes.get('needs-label'), true, 'Missing details stay yellow');
console.log('Return review: complete saved options stay yellow until explicit review confirmation.');
