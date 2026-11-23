(() => {
  document.querySelectorAll('[data-report-components]').forEach(section => {
    const form = section.closest('form');
    const panel = section.querySelector('[data-component-absence-panel]');
    const rows = section.querySelector('[data-component-absence-rows]');
    const json = section.querySelector('[data-component-absence-json]');
    const template = section.querySelector('template');
    const isIT = section.dataset?.absenceKind === 'it';
    const moduleOptions = JSON.parse(section.dataset?.moduleOptions || '{}');
    const choices = Array.from(section.querySelectorAll(isIT ? '[name="it_issues"]' : '[name="component_completion"]'));
    const error = section.querySelector('[data-component-absence-error]');
    const fields = row => Array.from(row.querySelectorAll('[data-component-field]'));
    const selected = () => choices.some(input => input.checked && (isIT ? input.value === '1' : input.value === 'component_absences'));
    function syncModules(row, active) {
      const exam = fields(row).find(input => input.dataset.componentField === 'exam').value;
      const allowed = moduleOptions[exam] || [];
      const inputs = Array.from(row.querySelectorAll('[data-it-module]'));
      inputs.forEach(input => { if (!allowed.includes(input.value)) input.checked = false; });
      const speaking = inputs.some(input => input.value === 'Speaking' && input.checked);
      const combined = inputs.some(input => input.value !== 'Speaking' && input.checked);
      inputs.forEach(input => {
        const available = allowed.includes(input.value);
        input.closest('label').hidden = !available;
        input.disabled = !available || (input.value === 'Speaking' ? combined : speaking);
        input.setCustomValidity('');
      });
      const values = inputs.filter(input => input.checked).map(input => input.value);
      const first = inputs.find(input => !input.disabled);
      if (first) first.setCustomValidity(active && !values.length ? 'Select at least one absent exam module.' : '');
      row.querySelector('[data-it-module-hint]').textContent = exam ? 'Speaking is exclusive. Listening and Speaking may be combined with Reading and Writing.' : 'Select Exam first.';
      return values;
    }
    function sync(notify = false) {
      const active = selected();
      panel.hidden = !active;
      const values = Array.from(rows.children).map(row => {
        row.disabled = !active;
        const value = Object.fromEntries(fields(row).map(input => [input.dataset.componentField, input.value]));
        if (isIT) value.modules = syncModules(row, active);
        return value;
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
      if (isIT) row.querySelectorAll('[data-it-module]').forEach(input => { input.checked = Array.isArray(values.modules) && values.modules.includes(input.value); });
      rows.appendChild(row);
      sync();
      if (focus) fields(row)[0].focus();
    }
    section.querySelector('[data-add-component-absence]').addEventListener('click', () => { add(); sync(true); });
    rows.addEventListener('input', () => sync(true));
    rows.addEventListener('change', event => {
      if (isIT && event.target.matches('[data-it-module]') && event.target.checked) {
        const inputs = event.target.closest('fieldset').querySelectorAll('[data-it-module]');
        inputs.forEach(input => { if (input !== event.target && (event.target.value === 'Speaking' || input.value === 'Speaking')) input.checked = false; });
      }
      sync(true);
    });
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
