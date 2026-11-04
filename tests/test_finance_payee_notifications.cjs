const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync('app/static/js/finance_payee_notifications.js', 'utf8');
const yes = {value: 'yes', checked: false}, no = {value: 'no', checked: true};
const email = {value: '', hidden: true, disabled: true, required: false};
const group = {
 querySelector: selector => selector.includes(':checked') ? (yes.checked ? yes : no) : email,
 querySelectorAll: () => [yes, no]
};
const handlers = {};
const form = {querySelector: () => group};
const context = {window: {}, document: {querySelectorAll: () => [group], addEventListener: (type, fn) => { handlers[type] = fn; }}};
vm.runInNewContext(source, context);
assert.equal(no.checked, true);
assert.equal(email.hidden, true);
context.window.applyPayeeNotificationDefaults(form, {paymentNotification: 'yes', paymentNotificationEmail: 'payee@example.com'});
assert.equal(yes.checked, true);
assert.equal(email.value, 'payee@example.com');
assert.equal(email.hidden, false);
assert.equal(email.disabled, false);
assert.equal(email.required, true);
yes.checked = false; no.checked = true;
handlers.change({target: {name: 'automatic_payment_notification', closest: () => group}});
assert.equal(email.disabled, true);
assert.equal(email.required, false);
context.window.applyPayeeNotificationDefaults(form, undefined);
assert.equal(no.checked, true);
assert.equal(email.value, '');
console.log('Payee notification fields: legacy No, saved preference, required email and switching Payees verified.');
