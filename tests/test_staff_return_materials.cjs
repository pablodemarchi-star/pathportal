const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const portal = fs.readFileSync('app/static/js/staff_exam_sessions.js', 'utf8');
const shared = fs.readFileSync('app/static/js/app.js', 'utf8');
for (const [role, confirmed] of ['Supervisor', 'Examiner', 'Intern'].flatMap(role => [[role, false], [role, true]])) {
  for (const marked of [true, false]) {
    const returnSection = {kind: 'return'};
    const materials = {children: marked && confirmed ? [returnSection] : [],
      querySelector: selector => selector === '[data-staff-return-materials]' && marked && confirmed ? returnSection : null,
      insertBefore(node) {this.children.push(node);}};
    const makeNode = tag => ({tag, children: [], style: {}, append(...nodes) {this.children.push(...nodes);}, setAttribute() {},
      after(node) {materials.children.splice(materials.children.indexOf(node), 1); materials.children.splice(materials.children.indexOf(this) + 1, 0, node);}});
    const context = {URL, document: {createElement: makeNode}, root: {querySelector: () => materials},
      data: {role, format: 'Onsite', participation_confirmed: confirmed, receives_shipment: marked, return_materials: marked && confirmed ? {status: 'Pending'} : null, material_for_examiners_url: 'https://example.com/material'},
      cleanEmailValue: value => String(value || '').trim(), SINAPSIS_LOGIN_URL: 'https://example.com/login', OFFICIAL_CONFIRMATION_MATERIAL_URL: ''};
    vm.runInNewContext(portal.slice(portal.indexOf('  const make ='), portal.indexOf('  const hydrate ='))
      + shared.slice(shared.indexOf('const officialMaterialRows ='), shared.indexOf('const officialMaterialDescriptionHtml ='))
      + portal.slice(portal.indexOf('      const role = data.role;'), portal.indexOf('      if (!rows.length')), context);
    if (marked) {
      const shipment = materials.children.findIndex(node => node.children?.[0]?.textContent === '📬🚚 Exam box shipment');
      assert.ok(shipment >= 0, role);
      assert.equal(materials.children[shipment].children[1].textContent, confirmed
        ? 'Our Logistics team will contact you to arrange delivery of the examination materials for this session.'
        : 'Once you confirm your participation, our Logistics team will contact you in due course to arrange the delivery of the materials for your assigned exam session(s).');
      if (confirmed) assert.equal(materials.children.indexOf(returnSection), shipment + 1, role + ': Return must appear directly below shipment');
      else assert.equal(materials.children.includes(returnSection), false, 'Return stays hidden until participation is confirmed');
    } else {
      assert.equal(materials.children.includes(returnSection), false);
      assert.equal(materials.children.some(node => node.children?.[0]?.textContent === '📬🚚 Exam box shipment'), false, role + ': No shipment section without Receives shipment');
    }
  }
}
class Node {
  constructor() {this.handlers = {}; this.open = false;}
  addEventListener(name, fn) {this.handlers[name] = fn;}
  showModal() {this.open = true;}
  close() {this.open = false; this.handlers.close({target: this, stopPropagation() {}});}
  focus() {this.focused = true;}
  getBoundingClientRect() {return {left: 10, right: 100, top: 10, bottom: 100};}
}
const button = new Node(), dialog = new Node(), close = new Node();
dialog.querySelectorAll = () => [close];
const section = {querySelector: selector => selector.includes('open') ? button : dialog};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_return_materials.js', 'utf8'), {document: {querySelectorAll: () => [section], querySelector: () => null}});
button.handlers.click(); assert.equal(dialog.open, true);
close.handlers.click(); assert.equal(dialog.open, false); assert.equal(button.focused, true);
button.handlers.click(); dialog.handlers.click({target: dialog, clientX: 50, clientY: 50}); assert.equal(dialog.open, true);
dialog.handlers.click({target: dialog, clientX: 0, clientY: 0}); assert.equal(dialog.open, false);
console.log('Staff return: shipment/return ordering for every role, recipient-only content and instructions modal close/backdrop/focus passed.');

// The table shortcut opens only the return section and keeps nested IDs unique.
const popup = new Node(), content = new Node(), popupClose = new Node(), popupTitle = {}, popupDate = {};
const main = new Node(); main.initialized = false;
const sourceSection = {status: 'Pending', cloneNode() {
  const copy = new Node(); copy.status = this.status;
  copy.button = new Node(); copy.instructions = new Node(); copy.closeButton = new Node(); copy.title = {};
  copy.instructions.querySelectorAll = () => [copy.closeButton];
  copy.instructions.querySelector = () => copy.title;
  copy.instructions.setAttribute = (name, value) => {copy.instructions[name] = value;};
  copy.button.setAttribute = (name, value) => {copy.button[name] = value;};
  copy.querySelector = selector => selector.includes('instructions-open') ? copy.button : copy.instructions;
  return copy;
}};
main.querySelectorAll = () => [{dataset: {staffLogisticsRole: 'examiner'}, querySelector: () => sourceSection}];
popup.querySelector = selector => ({'[data-staff-return-content]': content, '[data-staff-return-close]': popupClose,
  '[data-staff-return-title]': popupTitle, '[data-staff-return-date-label]': popupDate}[selector]);
content.replaceChildren = (...nodes) => {content.children = nodes;};
content.querySelectorAll = () => content.children.flatMap(copy => copy.instructions.open ? [copy.instructions] : []);
const documentEvents = {}, bodyClasses = new Set();
const quickDocument = {querySelectorAll: () => [], querySelector: () => popup,
  getElementById: id => id === 'staff-session-detail-9' ? main : null,
  addEventListener: (name, fn) => {documentEvents[name] = fn;},
  body: {classList: {add: value => bodyClasses.add(value), remove: value => bodyClasses.delete(value)}}};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_return_materials.js', 'utf8'), {document: quickDocument});
const icon = new Node(); icon.dataset = {staffReturnSession: '9', staffReturnRole: 'examiner', staffReturnName: 'Return session', staffReturnDate: '24/11/2026'};
icon.closest = () => icon;
const openReturn = () => documentEvents.click({target: icon, preventDefault() {}});
openReturn();
assert.equal(popup.open, true); assert.equal(content.children[0].status, 'Pending');
assert.equal(main.open, false); assert.equal(main.initialized, false);
assert.equal(popupTitle.textContent, 'Return session');
const quickCopy = content.children[0];
assert.equal(quickCopy.instructions.id, 'staff-return-quick-instructions');
assert.equal(quickCopy.title.id, 'staff-return-quick-instructions-title');
assert.equal(quickCopy.button['aria-controls'], quickCopy.instructions.id);
quickCopy.button.handlers.click(); assert.equal(quickCopy.instructions.open, true);
quickCopy.closeButton.handlers.click(); assert.equal(quickCopy.instructions.open, false); assert.equal(popup.open, true);
popupClose.handlers.click(); assert.equal(popup.open, false); assert.equal(icon.focused, true);
assert.equal(bodyClasses.has('staff-return-dialog-open'), false);
sourceSection.status = 'Completed'; openReturn(); assert.equal(content.children[0].status, 'Completed');
popup.handlers.click({target: popup, clientX: 50, clientY: 50}); assert.equal(popup.open, true);
popup.handlers.click({target: popup, clientX: 0, clientY: 0}); assert.equal(popup.open, false);
icon.dataset.staffReturnSession = 'missing'; openReturn(); assert.equal(popup.open, false);
console.log('Return shortcut: Pending/Completed, isolated modal, important instructions, unique IDs, backdrop/X and focus passed.');
