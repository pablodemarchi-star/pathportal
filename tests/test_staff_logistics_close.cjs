const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync('app/static/js/app.js', 'utf8');
const start = source.indexOf('const closeModal = (modal) => {');
const end = source.indexOf('\nconst openRequestedSessionModal', start);
let dirty = true, confirms = 0, resets = 0, closed = false;
const form = logistics => ({matches: () => logistics, reset: () => resets++});
const modal = {
  matches: () => false, dataset: {},
  querySelectorAll: selector => selector === 'form' ? [form(true), form(false)] : [],
  classList: {remove: () => {closed = true;}}, setAttribute() {}
};
const window = {logisticsHasUnsavedChanges: () => dirty, confirm: () => {confirms++; return false;}};
const context = {window, document: {}, modalOpeners: new Map(), clearFocusedMode() {}, resetControlSectionsToDefault() {},
  syncReturnMaterialsOptions() {}, syncInterviewInvitationConfirmation() {}, syncInductionStatusPanels() {}, syncOnboardingFollowUpControls() {}, syncPotentialInterviewNoShow() {}};
vm.runInNewContext(source.slice(start, end) + '\nglobalThis.close = closeModal;', context);
context.close(modal);
assert.equal(confirms, 1); assert.equal(closed, false); assert.equal(resets, 0);
dirty = false; context.close(modal);
assert.equal(closed, true); assert.equal(resets, 1, 'Closing a clean modal must not reset saved Logistics cards');
console.log('Logistics close: pending-save warning keeps the modal open; saved card fields survive closing.');
