(() => {
  document.querySelectorAll('[data-report-components]').forEach(section => {
    const form = section.closest('form');
    const panel = section.querySelector('[data-component-absence-panel]');
    const rows = section.querySelector('[data-component-absence-rows]');
    const json = section.querySelector('[data-component-absence-json]');
    const template = section.querySelector('template');
    const choices = Array.from(section.querySelectorAll('[name="component_completion"]'));
    const error = section.querySelector('[data-component-absence-error]');
    const fields = row => Array.from(row.querySelectorAll('[data-component-field]'));
    const selected = () => choices.some(input => input.checked && input.value === 'component_absences');
    function sync(notify = false) {
      const active = selected();
      panel.hidden = !active;
      const values = Array.from(rows.children).map(row => {
        row.disabled = !active;
        return Object.fromEntries(fields(row).map(input => [input.dataset.componentField, input.value]));
      });
      json.value = JSON.stringify(values);
      const missing = active && !values.length;
      choices.forEach(input => input.setCustomValidity(missing ? 'Add at least one candidate component absence.' : ''));
      error.textContent = missing ? 'Add at least one candidate to continue.' : '';
      if (notify) json.dispatchEvent(new Event('input', {bubbles:true}));
    }
    function add(values = {}, focus = true) {
      const row = template.content.firstElementChild.cloneNode(true);
      fields(row).forEach(input => { input.value = typeof values[input.dataset.componentField] === 'string' ? values[input.dataset.componentField] : ''; });
      rows.appendChild(row);
      sync();
      if (focus) fields(row)[0].focus();
    }
    section.querySelector('[data-add-component-absence]').addEventListener('click', () => { add(); sync(true); });
    rows.addEventListener('input', () => sync(true));
    rows.addEventListener('change', () => sync(true));
    rows.addEventListener('click', event => {
      const button = event.target.closest('[data-remove-component-absence]');
      if (!button) return;
      button.closest('fieldset').remove();
      sync(true);
    });
    choices.forEach(input => input.addEventListener('change', () => sync(true)));
    form.addEventListener('report:draft-restored', () => {
      rows.replaceChildren();
      try { const values = JSON.parse(json.value || '[]'); if (Array.isArray(values)) values.forEach(value => add(value, false)); } catch {}
      sync();
    });
    sync();
  });
})();
