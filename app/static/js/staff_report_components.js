(() => {
  document.querySelectorAll('[data-report-components]').forEach(section => {
    const form = section.closest('form');
    const panel = section.querySelector('[data-component-absence-panel]');
    const chips = section.querySelector('[data-component-absence-rows]');
    const json = section.querySelector('[data-component-absence-json]');
    const template = section.querySelector('template');
    const isIT = section.dataset?.absenceKind === 'it';
    const moduleOptions = JSON.parse(section.dataset?.moduleOptions || '{}');
    const choices = Array.from(section.querySelectorAll(isIT ? '[name="it_issues"]' : '[name="component_completion"]'));
    const error = section.querySelector('[data-component-absence-error]');
    const add = section.querySelector('[data-add-component-absence]');
    let values = [], editing = null;
    const locked = () => Boolean(json.disabled);
    const selected = () => choices.some(input => input.checked && (isIT ? input.value === '1' : input.value === 'component_absences'));
    const make = (tag, text, className) => {
      const node = document.createElement(tag);
      if (text !== undefined) node.textContent = text;
      if (className) node.className = className;
      return node;
    };
    const dialog = make('dialog', undefined, 'staff-report-candidate-dialog');
    dialog.setAttribute('aria-label', isIT ? 'Candidate IT issues' : 'Candidate component absence');
    const editor = make('form'); editor.noValidate = true;
    const heading = make('h3');
    const row = template.content.firstElementChild.cloneNode(true);
    const fields = Array.from(row.querySelectorAll('[data-component-field]'));
    const moduleInputs = Array.from(row.querySelectorAll('[data-it-module]'));
    const actions = make('div', undefined, 'staff-session-report-actions');
    const cancel = make('button', 'Cancel', 'secondary-button'); cancel.type = 'button';
    const save = make('button', 'Save candidate', 'primary-button'); save.type = 'submit';
    actions.append(cancel, save); editor.append(heading, row, actions); dialog.append(editor);
    form.closest('[data-staff-exam-day-report]').append(dialog);
    function syncModules() {
      if (!isIT) return [];
      const exam = fields.find(input => input.dataset.componentField === 'exam').value;
      const allowed = moduleOptions[exam] || [];
      moduleInputs.forEach(input => { if (!allowed.includes(input.value)) input.checked = false; });
      const speaking = moduleInputs.some(input => input.value === 'Speaking' && input.checked);
      const combined = moduleInputs.some(input => input.value !== 'Speaking' && input.checked);
      moduleInputs.forEach(input => {
        const available = allowed.includes(input.value);
        input.closest('label').hidden = !available;
        input.disabled = !available || (input.value === 'Speaking' ? combined : speaking);
        input.setCustomValidity('');
      });
      const modules = moduleInputs.filter(input => input.checked).map(input => input.value);
      const first = moduleInputs.find(input => !input.disabled);
      if (first) first.setCustomValidity(!modules.length ? 'Select at least one absent exam module.' : '');
      row.querySelector('[data-it-module-hint]').textContent = exam ? 'Speaking is exclusive. Listening and Speaking may be combined with Reading and Writing.' : 'Select Exam first.';
      return modules;
    }
    function complete(entry) {
      return entry && fields.every(input => typeof entry[input.dataset.componentField] === 'string' && entry[input.dataset.componentField].trim())
        && /^[0-9]{1,80}$/.test(entry.number)
        && (!isIT || Array.isArray(entry.modules) && entry.modules.length > 0);
    }
    function persist() {
      json.value = JSON.stringify(values);
      json.dispatchEvent(new Event('input', {bubbles:true}));
    }
    function open(index) {
      if (locked()) return;
      editing = index;
      const entry = index === null ? {} : values[index];
      fields.forEach(input => { input.value = entry[input.dataset.componentField] || ''; input.setCustomValidity(''); });
      moduleInputs.forEach(input => { input.checked = Array.isArray(entry.modules) && entry.modules.includes(input.value); });
      syncModules();
      heading.textContent = index === null ? 'Add candidate component absence' : 'Edit candidate component absence';
      dialog.showModal(); fields[0].focus();
    }
    function render() {
      const active = selected();
      panel.hidden = !active;
      chips.replaceChildren();
      values.forEach((entry, index) => {
        const label = [entry.number || 'Candidate number missing', entry.name || 'Candidate name missing'].join(' - ');
        const chip = make('span', undefined, 'staff-report-consideration-chip');
        const edit = make('button', label); edit.type = 'button'; edit.disabled = locked();
        edit.setAttribute('aria-label', 'Edit candidate: ' + label);
        edit.addEventListener('click', () => open(index));
        const remove = make('button', '×'); remove.type = 'button'; remove.disabled = locked();
        remove.setAttribute('aria-label', 'Remove candidate: ' + label);
        remove.addEventListener('click', () => {
          if (locked()) return;
          values.splice(index, 1); render(); persist();
        });
        chip.append(edit, remove); chips.append(chip);
      });
      add.disabled = locked();
      const message = active && !values.length ? 'Add at least one candidate component absence.'
        : active && values.some(entry => !complete(entry)) ? 'Complete every candidate component absence. Click its chip to edit.' : '';
      choices.forEach(input => input.setCustomValidity(message));
      error.textContent = message;
    }
    add.addEventListener('click', () => open(null));
    cancel.addEventListener('click', () => dialog.close());
    editor.addEventListener('input', event => { event.target.setCustomValidity(''); });
    editor.addEventListener('change', event => {
      if (isIT && event.target.matches('[data-it-module]') && event.target.checked) {
        moduleInputs.forEach(input => { if (input !== event.target && (event.target.value === 'Speaking' || input.value === 'Speaking')) input.checked = false; });
      }
      syncModules();
    });
    editor.addEventListener('submit', event => {
      event.preventDefault();
      if (locked()) { dialog.close(); return; }
      const entry = Object.fromEntries(fields.map(input => [input.dataset.componentField, input.value.trim()]));
      fields.forEach(input => input.setCustomValidity(!input.value.trim() ? 'Complete this field.' : ''));
      const number = fields.find(input => input.dataset.componentField === 'number');
      if (values.some((value, index) => index !== editing && value.number === entry.number)) number.setCustomValidity('This candidate number is already listed. Edit the existing candidate.');
      if (isIT) entry.modules = syncModules();
      if (!editor.reportValidity()) return;
      if (editing === null) values.push(entry); else values[editing] = entry;
      render(); persist(); dialog.close();
    });
    choices.forEach(input => input.addEventListener('change', render));
    form.addEventListener('report:draft-restored', () => {
      dialog.close();
      try { const parsed = JSON.parse(json.value || '[]'); values = Array.isArray(parsed) ? parsed.filter(entry => entry && typeof entry === 'object') : []; } catch { values = []; }
      render();
    });
    form.addEventListener('report:locked', () => { dialog.close(); render(); });
    render();
  });
})();
