const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/staff_exam_sessions.js', 'utf8');
const script = source.slice(source.lastIndexOf('(() => {'));
const opening = Date.parse('2026-11-13T00:00:00-03:00');
let now = opening - 1;
const handlers = {};
const timers = [];
const attributes = {};
const link = {
  dataset: { folderUrl: 'https://example.com/report' },
  classList: { toggle(name, value) { attributes[name] = value; } },
  setAttribute(name, value) { attributes[name] = value; },
  removeAttribute(name) { delete attributes[name]; },
  getAttribute(name) { return attributes[name]; },
  addEventListener(name, callback) { handlers[name] = callback; },
};
const badge = {classList: {toggle() {}}};
const section = { classList: {toggle() {}}, dataset: { opensAt: '2026-11-13T00:00:00-03:00' }, querySelector: key => key === '[data-exam-day-report-link]' ? link : key === '[data-report-availability]' ? badge : null };
vm.runInNewContext(script, {
  Date: { parse: Date.parse, now: () => now },
  document: { querySelectorAll: () => [section], addEventListener(name, callback) { handlers[name] = callback; } },
  window: { setTimeout(callback) { timers.push(callback); }, addEventListener(name, callback) { handlers[name] = callback; } },
});
assert.equal(link.href, '#');
assert.equal(badge.textContent, 'Available on exam date');
assert.equal(attributes['aria-disabled'], 'true');
now = opening;
timers.shift()();
assert.equal(link.href, 'https://example.com/report');
assert.equal(badge.textContent, 'Available');
assert.equal(attributes['aria-disabled'], 'false');
now = opening + 24 * 3600000 - 1;
handlers.focus();
assert.equal(link.href, 'https://example.com/report');
now += 1;
let prevented = false;
handlers.click({ preventDefault() { prevented = true; } });
assert.equal(prevented, true);
assert.equal(link.href, '#');
now = opening;
link.dataset.folderUrl = '';
handlers.visibilitychange();
assert.equal(attributes['aria-disabled'], 'true');
console.log('Exam-day report: GMT-3 midnight boundaries, disabled clicks and missing URL passed.');
