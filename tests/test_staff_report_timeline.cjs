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
const criterionKeys=['arrival','attitude','responsibilities','staff_id','dress_code','language','overall'];
const commentRules={arrival:['Too risky'],attitude:['Too doubtful','Not helpful'],responsibilities:['Needed guidance','Made mistakes'],dress_code:['Could improve','Inappropriate'],overall:['Unsatisfactory']};
const reviewRows = Array.from({length: 2}, () => {
  const selects = criterionKeys.map(key => ({key,value: '', addEventListener(name, callback) {this[name] = callback;}}));
  const note = {value: '', addEventListener(name, callback) {this[name] = callback;}};
  const indicator = {}, requiredIndicator = {};
  const summary = {dataset:{},getAttribute:()=> 'Notes for Staff',setAttribute(name,value){this[name]=value;}};
  const comments = Object.entries(commentRules).map(([key,values])=>{
    const input={value:'',required:false,disabled:true,addEventListener(name,fn){this[name]=fn;},setCustomValidity(value){this.validation=value;}};
    return {dataset:{commentKey:key,commentTitle:'Comment on '+key,requiredValues:JSON.stringify(values)},input,querySelector:()=>input};
  });
  const notes = {classList: classes(), querySelector: key => key==='summary'?summary:key==='[data-review-note-required]'?requiredIndicator:indicator};
  const status = {};
  return {classList: classes(), selects, note, indicator, requiredIndicator, notes, status, comments,
    querySelectorAll: key => key==='[data-review-select]'?selects:key==='[data-review-comment-field]'?comments:key==='[data-review-comment]'?comments.map(field=>field.input):[],
    querySelector: key => key.startsWith('[data-review-select][data-criterion=')?selects.find(select=>select.key===key.match(/data-criterion="([^"]+)"/)[1]):({'[data-review-note]':note, '[data-review-notes]':notes, '[data-review-row-status]':status}[key])};
});
fields['[data-report-feedback-checkbox]']={dataset:{submitted:'true'}};
const form = {handlers:{},querySelector: (key) => fields[key], querySelectorAll: key=>key==='[data-review-row]'?reviewRows:[],
 addEventListener(name,fn){this.handlers[name]=fn;},reportValidity(){return false;}};
const dialog = {querySelector: () => form, querySelectorAll: () => [], addEventListener() {}};
const opener = {addEventListener() {}};
const section = {dataset: {}, querySelector: (key) => key === '[data-exam-day-report-link]' ? opener : dialog};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_session_report.js','utf8'), {document: {querySelectorAll: () => [section], addEventListener() {}}, window: {addEventListener() {}, setInterval() {}}});
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

const first=reviewRows[0];
first.selects[0].value='Too risky';first.selects[6].value='Unsatisfactory';first.selects[0].change();
assert.equal(first.requiredIndicator.hidden,false);
assert.equal(first.comments[0].hidden,false);
assert.equal(first.comments[0].input.required,true);
assert.equal(first.comments[4].input.required,true);
assert.equal(reviewRows[1].requiredIndicator.hidden,true);
assert.ok(first.notes.classList.values.has('has-required-missing'));
(async()=>{
 await form.handlers.submit({preventDefault(){}});
 assert.equal(first.notes.open,true);
 first.comments[0].input.value='Late arrival';first.comments[0].input.input();
 assert.equal(first.requiredIndicator.hidden,false);
 first.comments[4].input.value='Overall concern';first.comments[4].input.input();
 assert.equal(first.requiredIndicator.hidden,true);
 first.selects[0].value='Early enough';first.selects[0].change();
 assert.equal(first.comments[0].hidden,true);
 assert.equal(first.comments[0].input.required,false);
 assert.equal(first.comments[0].input.disabled,true);
 assert.equal(first.comments[0].input.value,'Late arrival');
 first.selects[0].value='Too risky';first.selects[0].change();
 assert.equal(first.comments[0].input.value,'Late arrival');
 assert.equal(first.comments[0].input.required,true);
 console.log('Required review comments: multiple criteria, per-person pending indicator, preserved text and opening Notes before validation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
