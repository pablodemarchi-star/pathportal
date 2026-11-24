(() => {
  const bindInstructions = (section, quick = false) => {
    const button = section.querySelector('[data-staff-return-instructions-open]');
    const dialog = section.querySelector('[data-staff-return-instructions-dialog]');
    if (!button || !dialog) return;
    if (quick) {
      dialog.id = 'staff-return-quick-instructions';
      const title = dialog.querySelector('h3');
      title.id = 'staff-return-quick-instructions-title';
      dialog.setAttribute('aria-labelledby', title.id);
      button.setAttribute('aria-controls', dialog.id);
    }
    button.addEventListener('click', () => dialog.showModal());
    dialog.querySelectorAll('[data-staff-return-instructions-close]').forEach(close => close.addEventListener('click', () => dialog.close()));
    dialog.addEventListener('close', event => { event.stopPropagation(); button.focus(); });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
    });
  };
  document.querySelectorAll('[data-staff-return-materials], [data-report-return-materials]').forEach(section => bindInstructions(section));
  const popup = document.querySelector('[data-staff-return-dialog]');
  if (!popup) return;
  const content = popup.querySelector('[data-staff-return-content]');
  let opener;
  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-staff-return-open]');
    if (!trigger) return;
    const session = document.getElementById('staff-session-detail-' + trigger.dataset.staffReturnSession);
    const assignment = Array.from(session?.querySelectorAll('[data-staff-session-payload]') || []).find(item => item.dataset.staffLogisticsRole === trigger.dataset.staffReturnRole);
    const section = assignment?.querySelector('[data-staff-return-materials]');
    if (!section) return;
    event.preventDefault();
    opener = trigger;
    popup.querySelector('[data-staff-return-title]').textContent = trigger.dataset.staffReturnName;
    popup.querySelector('[data-staff-return-date-label]').textContent = trigger.dataset.staffReturnDate;
    const copy = section.cloneNode(true);
    bindInstructions(copy, true);
    content.replaceChildren(copy);
    popup.showModal(); popup.scrollTop = 0;
    document.body.classList.add('staff-return-dialog-open');
  });
  popup.querySelector('[data-staff-return-close]').addEventListener('click', () => popup.close());
  popup.addEventListener('click', event => {
    if (event.target !== popup) return;
    const bounds = popup.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) popup.close();
  });
  popup.addEventListener('close', event => {
    if (event.target !== popup) return;
    content.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    content.replaceChildren();
    document.body.classList.remove('staff-return-dialog-open');
    opener?.focus();
  });
})();
