const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
class Node {
  constructor() {this.events = new Map(); this.dataset = {}; this.children = []; this.open = false; this.hidden = false;}
  addEventListener(name, fn) {this.events.set(name, [...(this.events.get(name) || []), fn]);}
  emit(name, extra = {}) {const event = {target: this, stopPropagation() {this.stopped = true;}, ...extra}; for (const fn of this.events.get(name) || []) fn(event); return event;}
  showModal() {this.open = true;}
  close() {this.open = false; this.emit('close');}
  focus() {this.focused = true;}
  replaceChildren(...nodes) {this.children = nodes;}
  getBoundingClientRect() {return {left: 10, right: 100, top: 10, bottom: 100};}
}
const dialog = new Node(), content = new Node(), close = new Node(), title = {}, date = {}, doc = new Node();
const titleSelectors = {'[data-staff-logistics-content]': content, '[data-staff-logistics-close]': close,
  '[data-staff-logistics-title]': title, '[data-staff-logistics-date-label]': date};
dialog.querySelector = selector => titleSelectors[selector];
content.querySelectorAll = () => content.children.flatMap(copy => copy.nested.open ? [copy.nested] : []);
function travel(label) {
  const original = {label, clones: 0};
  original.cloneNode = deep => {
    assert.equal(deep, true); original.clones++;
    const copy = new Node(), button = new Node(), nested = new Node(), nestedClose = new Node();
    copy.label = label; copy.nested = nested; copy.button = button; copy.nestedClose = nestedClose;
    copy.links = [{name: 'Booking', target: '_blank', href: 'https://example.com/booking'}];
    const item = {querySelector: selector => selector.includes('instructions-dialog') ? nested : button};
    copy.querySelectorAll = () => [item]; nested.querySelectorAll = () => [nestedClose];
    return copy;
  };
  return original;
}
const selected = travel('Examiner logistics'), otherRole = travel('Supervisor logistics'), otherSession = travel('Another session logistics');
const assignment = (role, kind, section) => ({dataset: {staffLogisticsRole: role, staffLogisticsKind: kind}, querySelector: () => section});
const session = {open: false, initialized: false, querySelectorAll: () => [
  assignment('supervisor', 'Complex logistics', otherRole), assignment('examiner', 'Complex logistics', selected)]};
const classes = new Set();
const document = {querySelector: () => dialog, getElementById: id => id === 'staff-session-detail-7' ? session : null,
  addEventListener: (name, fn) => doc.addEventListener(name, fn), body: {classList: {add: x => classes.add(x), remove: x => classes.delete(x)}}};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_logistics_portal.js', 'utf8'), {document});
const trigger = new Node(); trigger.dataset = {staffLogisticsSession: '7', staffLogisticsRole: 'examiner', staffLogisticsKind: 'Complex logistics', staffLogisticsName: 'Test session', staffLogisticsDate: '24/11/2026'};
trigger.closest = selector => selector === '[data-staff-logistics-open]' ? trigger : null;
const open = () => {let prevented = false; doc.emit('click', {target: trigger, preventDefault() {prevented = true;}}); assert.equal(prevented, true);};
open();
assert.equal(dialog.open, true); assert.equal(content.children[0].label, 'Examiner logistics');
assert.equal(session.open, false); assert.equal(session.initialized, false, 'Opening Logistics must not open or initialize the full session');
assert.equal(otherRole.clones, 0); assert.equal(otherSession.clones, 0);
assert.equal(title.textContent, 'Test session'); assert.equal(date.textContent, '24/11/2026');
assert.equal(content.children[0].links[0].target, '_blank');
const copy = content.children[0]; copy.button.emit('click'); assert.equal(copy.nested.open, true);
copy.nestedClose.emit('click'); assert.equal(copy.nested.open, false); assert.equal(dialog.open, true); assert.equal(copy.button.focused, true);
copy.button.emit('click'); copy.nested.emit('click', {clientX: 0, clientY: 0});
assert.equal(copy.nested.open, false); assert.equal(dialog.open, true);
dialog.emit('click', {clientX: 50, clientY: 50}); assert.equal(dialog.open, true, 'Padding inside the modal is not backdrop');
dialog.emit('click', {target: copy, clientX: 0, clientY: 0}); assert.equal(dialog.open, true);
close.emit('click'); assert.equal(dialog.open, false); assert.equal(content.children.length, 0); assert.equal(trigger.focused, true);
assert.equal(classes.has('staff-logistics-dialog-open'), false);
open(); dialog.emit('click', {clientX: 0, clientY: 0}); assert.equal(dialog.open, false);
open(); const nested = content.children[0]; nested.button.emit('click'); close.emit('click'); assert.equal(nested.nested.open, false);
trigger.dataset.staffLogisticsSession = '999'; open(); assert.equal(dialog.open, false, 'Never show another session as fallback');
console.log('Portal Logistics: correct role/session content, no full-session opening, nested instructions, X/backdrop closing and focus restoration passed.');
