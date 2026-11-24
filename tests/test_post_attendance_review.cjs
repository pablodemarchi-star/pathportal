const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync('app/static/js/post_attendance.js', 'utf8');
const current = {
  can_edit: true, documentation_enabled: false, documentation_accessible: true, review_allowed: false,
  candidates: [], currencies: ['ARS'], reschedule_options: [], documentation_url: '',
  steps: {documentation: {status: 'in_progress'}}, window: {state: 'open', expires_at: '2000-01-01T00:00:00Z'}
};
const context = {current, esc: x => String(x ?? ''), option: () => '', moduleLabel: x => x,
  stepHeading: () => '', candidateRows: () => '', finalReviewControl: () => '',
  body: {querySelector: () => ({classList: {toggle() {}}})}, editor: {open: false}, syncWorkflow() {}, syncCandidates() {}};
vm.runInNewContext(source.slice(source.indexOf(' const isReviewed='), source.indexOf(' function candidateRows()'))
  + source.slice(source.indexOf(' function documentation()'), source.indexOf(' function render()'))
  + source.slice(source.indexOf(' function tick()'), source.indexOf('\n window.setInterval(tick'))
  + '\nglobalThis.api = {reviewActions, candidateModules, documentation, tick};', context);
const reported = {id: 1, review_status: 'Pending', edit_allowed: true, review_allowed: true,
  can_confirm: false, can_decline: true, component_reason: 'Supervisor evidence', exam: 'B2 Competency',
  allowed_modules: ['Listening'], modules: ['Listening'], fields_complete: true, confirmation_complete: false};
const institutional = {...reported, id: 2, edit_allowed: false, review_allowed: false,
  can_decline: false, component_reason: '', fields_complete: true, confirmation_complete: true};
assert.match(context.api.reviewActions(reported), /data-review-confirm="1" disabled/);
assert.doesNotMatch(context.api.reviewActions(reported), /data-review-decline="1" disabled/);
assert.match(context.api.reviewActions(institutional), /data-review-decline="2" disabled/);
assert.match(context.api.candidateModules(reported), /aria-disabled="false"/);
assert.match(context.api.candidateModules(institutional), /aria-disabled="true"/);
assert.match(context.api.documentation(), /^<fieldset data-documentation-fields>/);
assert.match(context.api.documentation(), /data-add-candidate disabled/);
assert.match(context.api.documentation(), /data-group-message disabled/);
current.documentation_accessible = false;
assert.match(context.api.documentation(), /^<fieldset data-documentation-fields disabled>/);
current.format = 'Online'; current.candidates = [reported, institutional];
context.api.tick();
assert.equal(current.review_allowed, false, 'Deadline alone must not bypass institution workflow gates');
assert.equal(institutional.review_allowed, false);
assert.equal(institutional.can_decline, false);
assert.equal(reported.review_allowed, true);
assert.equal(reported.can_decline, true);
assert.equal(reported.can_confirm, false, 'Confirmation requires rescheduling and credit where applicable');
const confirmButton = {}, declineButton = {};
const field = {dataset: {field: 'name'}, value: 'Saved candidate'};
const row = {querySelectorAll: () => [field], querySelector: selector => selector.includes('confirm') ? confirmButton : declineButton};
const draftContext = {current: {candidates: [{id: 1, name: 'Saved candidate', can_confirm: true, can_decline: true}]},
  pending: 0, body: {querySelector: () => row}};
vm.runInNewContext(source.slice(source.indexOf(' const candidateDraftPending='), source.indexOf(' function syncCandidates()'))
  + '\nglobalThis.sync = syncReviewActions;', draftContext);
draftContext.sync(); assert.equal(confirmButton.disabled, false);
field.value = ''; draftContext.sync();
assert.equal(confirmButton.disabled, true); assert.equal(declineButton.disabled, true, 'An empty unsaved field cannot use an older complete snapshot');
field.value = 'Saved candidate'; draftContext.pending = 1; draftContext.sync();
assert.equal(confirmButton.disabled, true, 'Wait until the candidate autosave completes');
draftContext.pending = 0; draftContext.sync(); assert.equal(confirmButton.disabled, false);
console.log('Attendance review: per-candidate editing/decisions, required-field controls, locked institutional actions and deadline isolation passed.');
