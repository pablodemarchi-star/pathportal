const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/app.js', 'utf8');
const start = source.indexOf('const returnShippingDimensions =');
const end = source.indexOf('document.addEventListener("click"', start);
const context = vm.createContext({isValidReturnLabelUrl: () => false, Set});
vm.runInContext(source.slice(start, end) + '\nthis.dimensions = returnShippingDimensions; this.sync = syncReturnMaterialsOptions;', context);
for (const [count, height, weight] of [[1,7,1],[2,14,1],[3,21,1],[4,28,2],[6,42,2],[7,49,3],[12,84,3],[13,91,4],[20,140,4]]) {
  const result = context.dimensions(count);
  assert.equal(result.height, height);
  assert.equal(result.weight, weight);
}
const height = {}, weight = {};
const info = {querySelector: selector => selector.includes('height') ? height : weight};
const selected = [{value:'2',checked:true,disabled:false}, {value:'2',checked:true,disabled:false},
  {value:'3',checked:true,disabled:true}, {value:'4',checked:false,disabled:false}];
const box = {classList: {toggle() {}}, querySelector: selector => selector.includes('shipping-info') ? info : null,
  querySelectorAll: () => selected};
const radio = {value:'combined_dispatch',checked:true,closest:()=>box};
const form = {dataset: {sessionId:'1'}, querySelectorAll: selector => selector.includes('radio') ? [radio] : []};
context.sync(form);
assert.equal(height.textContent, '14 cm', 'Count the current session and unique enabled selections');
assert.equal(weight.textContent, '1 kg');
selected.push({value:'5',checked:true,disabled:false}, {value:'6',checked:true,disabled:false});
context.sync(form);
assert.equal(height.textContent, '28 cm');
assert.equal(weight.textContent, '2 kg');
radio.value = 'immediate_dispatch'; context.sync(form);
assert.equal(height.textContent, '7 cm');
assert.equal(weight.textContent, '1 kg');
console.log('Shipping dimensions: weight thresholds, unique selected sessions, live changes and fixed immediate dispatch passed.');
