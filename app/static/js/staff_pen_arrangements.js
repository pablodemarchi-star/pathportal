(() => {
  const outside = (event, dialog) => {
    if (event.target !== dialog) return false;
    const bounds = dialog.getBoundingClientRect();
    return event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom;
  };
  document.querySelectorAll('[data-staff-pen-candidate]').forEach(button => {
    const dialog = document.getElementById(button.dataset.staffPenCandidate);
    if (!dialog) return;
    button.addEventListener('click', () => { if (!dialog.open) dialog.showModal(); });
    dialog.querySelectorAll('[data-staff-pen-candidate-close]').forEach(close => close.addEventListener('click', () => dialog.close()));
    dialog.addEventListener('click', event => { if (outside(event, dialog)) dialog.close(); });
    dialog.addEventListener('close', event => { event.stopPropagation(); button.focus(); });
  });
  const popup = document.querySelector('[data-staff-pen-dialog]');
  if (!popup) return;
  const content = popup.querySelector('[data-staff-pen-content]');
  let section, placeholder, opener;
  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-staff-pen-open]');
    if (!trigger) return;
    event.preventDefault();
    if (popup.open) return;
    const session = document.getElementById('staff-session-detail-' + trigger.dataset.staffPenSession);
    const assignment = Array.from(session?.querySelectorAll('[data-staff-session-payload]') || []).find(item => item.dataset.staffLogisticsRole === trigger.dataset.staffPenRole);
    section = assignment?.querySelector('[data-staff-pen-section]');
    if (!section) return;
    opener = trigger;
    popup.querySelector('[data-staff-pen-title]').textContent = trigger.dataset.staffPenName;
    popup.querySelector('[data-staff-pen-date]').textContent = trigger.dataset.staffPenDate;
    // Move the existing section so nested candidate dialogs keep unique IDs and handlers.
    placeholder = document.createComment('PEN arrangements');
    section.parentNode.insertBefore(placeholder, section);
    content.replaceChildren(section);
    popup.showModal(); popup.scrollTop = 0;
    document.body.classList.add('staff-pen-dialog-open');
  });
  popup.querySelector('[data-staff-pen-close]').addEventListener('click', () => popup.close());
  popup.addEventListener('click', event => { if (outside(event, popup)) popup.close(); });
  popup.addEventListener('close', event => {
    if (event.target !== popup) return;
    section?.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    if (placeholder && section) placeholder.replaceWith(section);
    placeholder = null; section = null;
    document.body.classList.remove('staff-pen-dialog-open');
    opener?.focus();
  });
})();
