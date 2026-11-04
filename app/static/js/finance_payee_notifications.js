(() => {
  const groupFor = form => form?.querySelector('[data-payee-notification]');
  const sync = group => {
    if (!group) return;
    const enabled = group.querySelector('[name="automatic_payment_notification"]:checked')?.value === 'yes';
    const email = group.querySelector('[name="payment_notification_email"]');
    email.hidden = !enabled; email.disabled = !enabled || group.dataset?.readOnly === 'true'; email.required = enabled;
  };
  window.applyPayeeNotificationDefaults = (form, option) => {
    const group = groupFor(form);
    if (!group) return;
    const contact = form.querySelector('[name="payee_contact_id"]');
    if (contact) contact.value = option?.contactId || '';
    const choice = option?.paymentNotification === 'yes' ? 'yes' : 'no';
    group.querySelectorAll('[name="automatic_payment_notification"]').forEach(radio => { radio.checked = radio.value === choice; });
    group.querySelector('[name="payment_notification_email"]').value = option?.paymentNotificationEmail || '';
    sync(group);
  };
  document.querySelectorAll('[data-payee-notification]').forEach(sync);
  document.addEventListener('change', event => {
    if (event.target.name === 'automatic_payment_notification') sync(event.target.closest('[data-payee-notification]'));
  });
  document.addEventListener('input', event => {
    if (!event.target.matches('[data-finance-payee-input]')) return;
    const form = event.target.closest('form');
    const name = event.target.value.trim().toLowerCase();
    const picker = event.target.closest('[data-finance-payee-picker]');
    const option = [...picker.querySelectorAll('[data-finance-payee-option]')].find(item => item.dataset.contactName?.trim().toLowerCase() === name);
    window.applyPayeeNotificationDefaults(form, option?.dataset);
  });
})();
