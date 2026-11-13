const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const classes = () => ({ values: new Set(), toggle(key, enabled) { if (enabled) this.values.add(key); else this.values.delete(key); } });
const steps = Array.from({length: 6}, () => {
  const label = {classList: classes()};
  return {checked: false, disabled: false, handlers: {}, closest: () => label, addEventListener(name, callback) {this.handlers[name] = callback;}};
});
const timeline = {classList: classes(), querySelectorAll: () => steps};
const fields = {};
for (const name of ['outcome','reasons','facilities','comments','emergency-pack','emergency-reasons']) {
  fields[`[data-report-${name}]`] = {value: '', addEventListener() {}};
}
for (const name of ['reasons-field','comments-field','emergency-reasons-field','feedback']) fields[`[data-report-${name}]`] = {};
fields['[data-report-return-timeline]'] = timeline;
fields['[data-return-progress]'] = {};
fields['[type="submit"]'] = {};
fields['[data-review-count]'] = {classList: classes()};
const reviewRows = Array.from({length: 2}, () => {
  const selects = Array.from({length: 7}, () => ({value: '', addEventListener(name, callback) {this[name] = callback;}}));
  const note = {value: '', addEventListener(name, callback) {this[name] = callback;}};
  const indicator = {};
  const notes = {classList: classes(), querySelector: () => indicator};
  const status = {};
  return {classList: classes(), selects, note, indicator, notes, status, querySelectorAll: () => selects,
    querySelector: key => ({'[data-review-note]':note, '[data-review-notes]':notes, '[data-review-row-status]':status}[key])};
});
const form = {querySelector: (key) => fields[key], querySelectorAll: () => reviewRows, addEventListener() {}};
const dialog = {querySelector: () => form, querySelectorAll: () => [], addEventListener() {}};
const opener = {addEventListener() {}};
const section = {dataset: {}, querySelector: (key) => key === '[data-exam-day-report-link]' ? opener : dialog};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_session_report.js','utf8'), {document: {querySelectorAll: () => [section]}, window: {addEventListener() {}, setInterval() {}}});
assert.equal(steps[0].disabled, false);
assert.ok(steps.slice(1).every(step => step.disabled));
for (let index = 0; index < 6; index++) {
  assert.equal(steps[index].disabled, false);
  steps[index].checked = true;
  steps[index].handlers.change();
  assert.equal(timeline.classList.values.has('is-complete'), index === 5);
  if (index < 5) assert.ok(timeline.classList.values.has('is-in-progress'));
}
assert.equal(fields['[data-return-progress]'].textContent, '6 of 6 steps completed');
steps[2].checked = false;
steps[2].handlers.change();
assert.equal(steps[2].disabled, false);
assert.ok(steps.slice(3).every(step => step.disabled && !step.checked));
assert.equal(timeline.classList.values.has('is-complete'), false);
assert.equal(fields['[data-return-progress]'].textContent, '2 of 6 steps completed');
steps[0].checked = false;
steps[0].handlers.change();
assert.ok(steps.slice(1).every(step => step.disabled && !step.checked));
assert.equal(fields['[data-return-progress]'].textContent, '0 of 6 steps completed');
console.log('Return timeline: sequential unlocking, yellow/green states and cascading reset passed.');

assert.equal(fields['[data-review-count]'].textContent, '0/2 completed');
reviewRows[0].note.value = 'Helpful';
reviewRows[0].note.input();
assert.equal(fields['[data-review-count]'].textContent, '0/2 completed');
assert.equal(reviewRows[0].indicator.hidden, false);
for (let i=0; i<6; i++) reviewRows[0].selects[i].value = 'Selected';
reviewRows[0].selects[0].change();
assert.equal(fields['[data-review-count]'].textContent, '0/2 completed');
reviewRows[0].selects[6].value = 'Selected';
reviewRows[0].selects[6].change();
assert.equal(fields['[data-review-count]'].textContent, '1/2 completed');
assert.equal(reviewRows[0].status.textContent, 'Completed');
reviewRows[0].note.value = '';
reviewRows[0].note.input();
assert.equal(reviewRows[0].indicator.hidden, true);
assert.equal(fields['[data-review-count]'].textContent, '1/2 completed');
reviewRows[0].selects[3].value = '';
reviewRows[0].selects[3].change();
assert.equal(fields['[data-review-count]'].textContent, '0/2 completed');
assert.equal(reviewRows[0].status.textContent, 'Incomplete');
console.log('Staff review: seven-criterion completion, independent optional notes and cleared selections passed.');
