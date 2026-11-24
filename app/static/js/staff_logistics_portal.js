(() => {
  const dialog = document.querySelector('[data-staff-logistics-dialog]');
  if (!dialog) return;
  const content = dialog.querySelector('[data-staff-logistics-content]');
  let opener;
  const closeOnBackdrop = (surface, event) => {
    if (event.target !== surface) return;
    const bounds = surface.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) surface.close();
  };
  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-staff-logistics-open]');
    if (!trigger) return;
    event.preventDefault();
    const session = document.getElementById('staff-session-detail-' + trigger.dataset.staffLogisticsSession);
    const assignment = Array.from(session?.querySelectorAll('[data-staff-session-payload]') || []).find(item =>
      item.dataset.staffLogisticsRole === trigger.dataset.staffLogisticsRole
      && item.dataset.staffLogisticsKind === trigger.dataset.staffLogisticsKind);
    const section = assignment?.querySelector('[data-staff-travel-section]');
    if (!section) return;
    opener = trigger;
    dialog.querySelector('[data-staff-logistics-title]').textContent = trigger.dataset.staffLogisticsName;
    dialog.querySelector('[data-staff-logistics-date-label]').textContent = trigger.dataset.staffLogisticsDate;
    // Clone only Logistics: leave the session dialog and its lazy initialization untouched.
    const copy = section.cloneNode(true);
    copy.hidden = false;
    copy.querySelectorAll('[data-staff-logistics-instructions-item]').forEach(item => {
      const instructions = item.querySelector('[data-staff-logistics-instructions-dialog]');
      const button = item.querySelector('[data-staff-logistics-instructions-open]');
      button.addEventListener('click', () => instructions.showModal());
      instructions.querySelectorAll('[data-staff-logistics-instructions-close]').forEach(close => {
        close.addEventListener('click', () => instructions.close());
      });
      instructions.addEventListener('click', event => closeOnBackdrop(instructions, event));
      instructions.addEventListener('close', event => { event.stopPropagation(); button.focus(); });
    });
    content.replaceChildren(copy);
    dialog.showModal();
    dialog.scrollTop = 0;
    document.body.classList.add('staff-logistics-dialog-open');
  });
  dialog.querySelector('[data-staff-logistics-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => closeOnBackdrop(dialog, event));
  dialog.addEventListener('close', event => {
    if (event.target !== dialog) return;
    content.querySelectorAll('dialog[open]').forEach(nested => nested.close());
    content.replaceChildren();
    document.body.classList.remove('staff-logistics-dialog-open');
    opener?.focus();
  });
})();
