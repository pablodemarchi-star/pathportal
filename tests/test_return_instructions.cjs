const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const rows = ['1','2','3'].map(id => {
  const html = {value: '', defaultValue: ''}, title = {value: '', defaultValue: ''};
  const button = {replaceChildren(...children) {this.children = children;}};
  return {dataset: {sessionId: id}, html, title, button,
    querySelector: selector => selector.includes('title-value') ? title : selector.includes('instructions-value') ? html : button};
});
let saved;
const context = {window: {}, document: {addEventListener: (event, fn) => {saved = fn;},
  querySelectorAll: () => rows, createElement: tag => ({tagName: tag})}, Set};
vm.runInNewContext(fs.readFileSync('app/static/js/return_instructions.js','utf8'), context);
saved({target: {closest: () => rows[0]}, detail: {title:'Shared title', html:'<p>Shared</p>', sessionIds:[1,2]}});
for (const row of rows.slice(0,2)) {
  assert.equal(row.html.value, '<p>Shared</p>');
  assert.equal(row.html.defaultValue, '<p>Shared</p>');
  assert.equal(row.title.value, 'Shared title');
  assert.equal(row.button.children[0], 'Instructions (');
  assert.equal(row.button.children[1].tagName, 'em');
  assert.equal(row.button.children[1].textContent, 'added');
}
assert.equal(rows[2].html.value, '');
context.window.syncReturnInstructions({title:'', html:'', session_ids:[1,2]});
assert.equal(rows[0].button.children[1].textContent, 'empty');
assert.equal(rows[1].html.value, '');
console.log('Return instruction chips: lowercase italic state, shared updates, deletion and unrelated session isolation passed.');
