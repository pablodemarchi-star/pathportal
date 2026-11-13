(() => {
  document.querySelectorAll('[data-centre-feedback]').forEach(root => {
    const copy = JSON.parse(root.dataset.copy);
    const opener = root.querySelector('[data-centre-feedback-open]');
    const badge = root.querySelector('[data-feedback-status]');
    const thanks = root.querySelector('[data-feedback-thanks]');
    const dialog = root.querySelector('dialog');
    const form = dialog?.querySelector('form');
    const opensAt = Date.parse(root.dataset.opensAt);
    const closesAt = opensAt + 86400000;
    let saving = false;
    const available = () => Date.now() >= opensAt && Date.now() < closesAt;
    const refresh = () => {
      const submitted = root.dataset.submitted === 'true';
      badge.textContent = submitted ? copy.submitted : available() ? copy.available : copy.unavailable;
      badge.classList.toggle('is-available', submitted || available());
      opener.disabled = submitted || !available() || root.dataset.preview === 'true';
      opener.textContent = submitted ? copy.submitted : copy.open;
      if (!available() && dialog?.open && !saving) dialog.close();
    };
    const schedule = () => {
      refresh();
      const next = [opensAt, closesAt].find(at => at > Date.now());
      if (next) setTimeout(schedule, Math.min(next - Date.now() + 1, 2147483647));
    };
    schedule();
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    if (!form) return;
    const message = form.querySelector('[data-feedback-message]');
    const submit = form.querySelector('[type="submit"]');
    const fields = Array.from(form.querySelectorAll('input[type="radio"], textarea'));
    const conditionals = () => {
      form.querySelectorAll('[data-feedback-question]').forEach(question => {
        const score = Number(question.querySelector('input:checked')?.value || 0);
        const needed = score >= 1 && score <= 7;
        const box = question.querySelector('[data-feedback-conditional]');
        const input = box.querySelector('textarea');
        box.hidden = !needed;
        input.disabled = !needed;
        input.required = needed;
        if (!needed) {
          input.setAttribute('aria-invalid', 'false');
          const error = question.querySelector(`[data-error-for="${input.name}"]`);
          if (error) { error.hidden = true; error.textContent = ''; }
        }
      });
    };
    const saveDraft = () => {
      const data = {};
      fields.forEach(input => { if (input.type !== 'radio' || input.checked) data[input.name] = input.value; });
      try { sessionStorage.setItem(root.dataset.draftKey, JSON.stringify(data)); } catch {}
    };
    try {
      const data = JSON.parse(sessionStorage.getItem(root.dataset.draftKey) || '{}');
      fields.forEach(input => {
        if (typeof data[input.name] !== 'string') return;
        if (input.type === 'radio') input.checked = input.value === data[input.name];
        else input.value = data[input.name];
      });
    } catch {}
    conditionals();
    fields.forEach(input => {
      input.addEventListener(input.type === 'radio' ? 'change' : 'input', () => { conditionals(); saveDraft(); });
    });
    opener.addEventListener('click', () => { refresh(); if (!opener.disabled) dialog.showModal(); });
    dialog.querySelectorAll('[data-centre-feedback-close]').forEach(button => button.addEventListener('click', () => { if (!saving) dialog.close(); }));
    dialog.addEventListener('cancel', event => { if (saving) event.preventDefault(); });
    const showErrors = errors => {
      form.querySelectorAll('[data-error-for]').forEach(node => {
        const error = errors[node.dataset.errorFor];
        node.textContent = error || '';
        node.hidden = !error;
      });
      fields.forEach(input => input.setAttribute('aria-invalid', String(Boolean(errors[input.name]))));
      const first = fields.find(input => errors[input.name] && !input.disabled);
      if (first) { first.focus(); first.closest('.centre-feedback-question').scrollIntoView({block: 'nearest'}); }
    };
    const submitted = text => {
      root.dataset.submitted = 'true';
      try { sessionStorage.removeItem(root.dataset.draftKey); } catch {}
      thanks.textContent = text;
      thanks.hidden = false;
      dialog.close();
      refresh();
    };
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (saving) return;
      if (!available()) { message.textContent = copy.expired; refresh(); return; }
      conditionals();
      const errors = {};
      copy.questions.forEach(question => {
        const score = form.querySelector(`input[name="${question.key}_score"]:checked`);
        const comment = form.querySelector(`textarea[name="${question.key}_comment"]`);
        if (!score) errors[question.key + '_score'] = copy.invalid_score;
        if (score && Number(score.value) <= 7 && !comment.value.trim()) errors[comment.name] = copy.missing_comment;
      });
      form.querySelectorAll('textarea').forEach(input => {
        if (!input.disabled && input.value.length > 10000) errors[input.name] = copy.too_long;
      });
      showErrors(errors);
      if (Object.keys(errors).length) { message.textContent = copy.missing; return; }
      saving = true;
      submit.disabled = true;
      submit.textContent = copy.submitting;
      message.textContent = '';
      try {
        const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {Accept: 'application/json'}});
        const result = await response.json();
        if (response.status === 409) { submitted(copy.locked); return; }
        if (!response.ok || !result.ok) { showErrors(result.fields || {}); throw new Error(result.error || copy.error); }
        submitted(result.message || copy.thanks);
      } catch (error) { message.textContent = error.message || copy.error; }
      finally { saving = false; submit.disabled = false; submit.textContent = copy.submit; refresh(); }
    });
  });
})();
