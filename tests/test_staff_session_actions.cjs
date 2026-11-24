const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
class Node {
  constructor() {this.events = {}; this.dataset = {}; this.children = []; this.open = false; this.hidden = false;}
  addEventListener(name, fn) {this.events[name] = fn;}
  showModal() {this.open = true;}
  close() {this.open = false; this.events.close?.({target: this});}
  focus() {this.focused = true;}
  before(node) {this.placeholder = node; node.original = this;}
  replaceChildren(...nodes) {this.children = nodes;}
  getBoundingClientRect() {return {left: 10, right: 100, top: 10, bottom: 100};}
}
const popup = new Node(), content = new Node(), close = new Node(), title = {}, date = {};
popup.querySelector = selector => ({'[data-staff-report-popup-content]': content, '[data-staff-report-popup-close]': close,
  '[data-staff-report-popup-title]': title, '[data-staff-report-popup-date]': date}[selector]);
const opener = new Node(); opener.dataset.folderUrl = '/report';
const section = new Node(); section.querySelector = () => opener; section.querySelectorAll = () => [];
section.draft = 'Keep these answers';
const link = new Node(); link.dataset = {staffReportSession: '1', staffReportRole: 'supervisor', staffReportKind: 'native',
  staffReportOpensAt: '2026-11-24T00:00:00Z', staffReportName: 'Session', staffReportDate: '24/11/2026'};
link.closest = () => link;
const classes = new Set(), handlers = {}, observers = []; let now = Date.parse('2026-11-24T12:00:00Z'), restored;
const document = {querySelector: () => popup, querySelectorAll: () => [link],
  getElementById: () => ({querySelectorAll: () => [{dataset: {staffLogisticsRole: 'supervisor'}, querySelector: () => section}]}),
  createComment: () => ({replaceWith(node) {restored = node;}}), addEventListener: (name, fn) => {handlers[name] = fn;},
  body: {classList: {add: x => classes.add(x), remove: x => classes.delete(x)}}};
const window = {setInterval: fn => {window.refresh = fn;}, addEventListener() {}};
vm.runInNewContext(fs.readFileSync('app/static/js/staff_session_actions.js', 'utf8'), {document, window,
  Date: {parse: Date.parse, now: () => now}, MutationObserver: class {constructor(fn) {observers.push(fn);} observe() {}}});
assert.equal(link.hidden, false);
handlers.click({target: link, preventDefault() {}});
assert.equal(popup.open, true); assert.equal(content.children[0], section, 'Move the original section, preserving form listeners and drafts');
assert.equal(title.textContent, 'Session'); assert.equal(section.draft, 'Keep these answers');
close.events.click(); assert.equal(restored, section); assert.equal(popup.open, false); assert.equal(link.focused, true);
assert.equal(classes.has('staff-report-popup-open'), false);
handlers.click({target: link, preventDefault() {}}); popup.events.click({target: popup, clientX: 50, clientY: 50}); assert.equal(popup.open, true);
popup.events.click({target: popup, clientX: 0, clientY: 0}); assert.equal(popup.open, false);
now = Date.parse('2026-11-25T00:00:00Z'); opener.disabled = true; window.refresh(); assert.equal(link.hidden, false);
handlers.click({target: link, preventDefault() {}}); assert.equal(popup.open, true, 'The locked section can still be opened');
assert.equal(opener.disabled, true, 'Opening the section must not unlock the actual report'); close.events.click();
now = Date.parse('2026-11-24T12:00:00Z'); window.refresh(); assert.equal(link.hidden, false);
opener.dataset.folderUrl = ''; observers[0](); assert.equal(link.hidden, false, 'Submitted report keeps its section shortcut');
handlers.click({target: link, preventDefault() {}}); assert.equal(popup.open, true); assert.equal(opener.disabled, true); close.events.click();
console.log('Session actions: report availability, submitted lock, original form/draft preservation, isolated popup, X/backdrop and focus passed.');
