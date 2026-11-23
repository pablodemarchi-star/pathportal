(() => {
  document.querySelectorAll('[data-report-considerations]').forEach(section => {
    const form = section.closest('form');
    const json = section.querySelector('[data-report-considerations-json]');
    const chips = section.querySelector('[data-consideration-chips]');
    const add = section.querySelector('[data-add-consideration]');
    let values = [], editing = null;
    const make = (tag, text, className) => {
      const element = document.createElement(tag);
      if (text !== undefined) element.textContent = text;
      if (className) element.className = className;
      return element;
    };
    const dialog = make('dialog', undefined, 'staff-report-consideration-dialog');
    dialog.setAttribute('aria-label', 'Important consideration');
    const editor = make('form');
    editor.noValidate = true;
    const heading = make('h3', 'Important consideration');
    const titleLabel = make('label', 'Title'), textLabel = make('label', 'Text');
    const title = make('input'), text = make('textarea');
    title.type = 'text'; title.required = true; title.maxLength = 200;
    text.required = true; text.maxLength = 10000; text.rows = 7;
    titleLabel.append(title); textLabel.append(text);
    const actions = make('div', undefined, 'staff-session-report-actions');
    const cancel = make('button', 'Cancel', 'secondary-button'); cancel.type = 'button';
    const save = make('button', 'Save consideration', 'primary-button'); save.type = 'submit';
    actions.append(cancel, save); editor.append(heading, titleLabel, textLabel, actions);
    dialog.append(editor);
    form.closest('[data-staff-exam-day-report]').append(dialog);
    const locked = () => Boolean(json.disabled);
    function persist() {
      json.value = JSON.stringify(values);
      json.dispatchEvent(new Event('input', {bubbles:true}));
    }
    function open(index) {
      if (locked()) return;
      editing = index;
      title.value = index === null ? '' : values[index].title;
      text.value = index === null ? '' : values[index].text;
      title.setCustomValidity(''); text.setCustomValidity('');
      heading.textContent = index === null ? 'Add important consideration' : 'Edit important consideration';
      dialog.showModal(); title.focus();
    }
    function render() {
      chips.replaceChildren();
      values.forEach((entry, index) => {
        const chip = make('span', undefined, 'staff-report-consideration-chip');
        const edit = make('button', entry.title); edit.type = 'button'; edit.disabled = locked();
        edit.setAttribute('aria-label', 'Edit consideration: ' + entry.title);
        edit.addEventListener('click', () => open(index));
        const remove = make('button', '×'); remove.type = 'button'; remove.disabled = locked();
        remove.setAttribute('aria-label', 'Remove consideration: ' + entry.title);
        remove.addEventListener('click', () => { if (!locked()) { values.splice(index, 1); persist(); render(); } });
        chip.append(edit, remove); chips.append(chip);
      });
      add.disabled = locked();
    }
    add.addEventListener('click', () => open(null));
    cancel.addEventListener('click', () => dialog.close());
    title.addEventListener('input', () => title.setCustomValidity(''));
    text.addEventListener('input', () => text.setCustomValidity(''));
    editor.addEventListener('submit', event => {
      event.preventDefault(); if (locked()) { dialog.close(); return; }
      title.setCustomValidity(!title.value.trim() ? 'Enter a Title.' : title.value.trim().length > 200 ? 'Title must not exceed 200 characters.' : '');
      text.setCustomValidity(!text.value.trim() ? 'Enter Text.' : text.value.trim().length > 10000 ? 'Text must not exceed 10,000 characters.' : '');
      if (!title.reportValidity() || !text.reportValidity()) return;
      const entry = {title:title.value.trim(), text:text.value.trim()};
      if (editing === null) values.push(entry); else values[editing] = entry;
      persist(); render(); dialog.close();
    });
    form.addEventListener('report:draft-restored', () => {
      try { const parsed = JSON.parse(json.value || '[]'); values = Array.isArray(parsed) ? parsed.filter(entry => entry && typeof entry.title === 'string' && typeof entry.text === 'string') : []; } catch { values = []; }
      render();
    });
    form.addEventListener('report:locked', () => { dialog.close(); render(); });
    render();
  });
})();
