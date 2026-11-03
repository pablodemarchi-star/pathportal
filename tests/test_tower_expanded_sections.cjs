const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('app/static/js/app.js', 'utf8');
const template = fs.readFileSync('app/templates/pre_session_control_tower/_session_modals.html', 'utf8');
const sections = ['schedule-overview', 'schedule-actions', 'staffing', 'logistics', 'packages', 'shipments', 'finance', 'sinapsis'].map(key => {
  const sectionTag = template.split('\n').find(line => line.includes(`id="${key}-{{ session.id }}"`) && line.includes('<section'));
  assert.ok(sectionTag.includes('data-always-expanded="true"'), key);
  assert.ok(!sectionTag.includes('data-default-collapsed="true"'), key);
  const classes = new Set(['is-collapsed']);
  return {id: `${key}-1`, dataset: {alwaysExpanded: 'true'}, classes,
    classList: {remove: value => classes.delete(value), toggle: (value, state) => state ? classes.add(value) : classes.delete(value)},
    querySelector: () => null};
});
const context = {document: {querySelectorAll: () => sections}, modalTargetKey: value => value.replace(/-\d+$/, ''), relatedFocusedTargets: {}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('const setControlSectionCollapsed ='), source.indexOf('const syncScheduleNoteContextInputs =')) +
  source.slice(source.indexOf('const initializeControlSections ='), source.indexOf('initializeControlSections();')) +
  '\nthis.initialize = initializeControlSections; this.reset = resetControlSectionsToDefault; this.focus = collapseUnrelatedControlSections; this.collapse = setControlSectionCollapsed;', context);
context.initialize();
const modal = {querySelectorAll: () => sections};
context.reset(modal);
context.focus(modal, 'packages-1');
for (const section of sections) {
  context.collapse(section, true);
  assert.equal(section.classes.has('is-collapsed'), false, section.id);
}
console.log('Tower sections remain expanded on initialization, modal reset, focus and attempted collapse.');
