(() => {
  const controllers = new Map();
  const sectionStates = new WeakMap();
  const sections = new Set();
  window.penHasUnsavedChanges = root => [...sections].some(section => (!root || root.contains(section)) && sectionStates.get(section).completing) || [...controllers].some(([card, state]) => (!root || root.contains(card)) && (state.controller.dirty || state.deleting));
  window.addEventListener('beforeunload', event => {
    if (window.penHasUnsavedChanges()) { event.preventDefault(); event.returnValue = ''; }
  });
  const request = async (url, options = {}) => {
    const response = await fetch(url, {cache:'no-store', ...options, headers:{Accept:'application/json', 'X-PEN-Autosave':'1', ...options.headers}});
    const data = await response.json().catch(() => ({}));
    if (!response.ok || response.redirected || data.ok !== true) {
      const error = new Error(data.error || (response.redirected ? 'Your sign-in session expired. Please sign in again.' : 'The arrangements could not be saved. Please retry.'));
      error.status = response.status; throw error;
    }
    return data;
  };
  const text = (tag, value) => { const node = document.createElement(tag); node.textContent = value; return node; };
  const renderCompletion = section => {
    const settings = sectionStates.get(section);
    const checkbox = section.querySelector('[data-pen-confirm]');
    const chip = section.querySelector('[data-pen-completion-chip]');
    const message = section.querySelector('[data-pen-confirm-status]');
    const completion = settings.completion || {count:0, complete:false};
    const dirty = [...controllers].some(([card, state]) => section.contains(card) && (state.controller.dirty || state.deleting));
    checkbox.checked = Boolean(completion.complete && !dirty && !settings.completionStale);
    checkbox.disabled = !settings.loaded || !settings.can_edit || completion.count < 1 || dirty || Boolean(settings.completing) || Boolean(settings.completionStale);
    chip.textContent = checkbox.checked ? 'Completed' : 'Pending';
    chip.classList.toggle('is-complete', checkbox.checked);
    const panel = checkbox.closest('.pen-completion');
    panel.classList.toggle('is-complete', checkbox.checked);
    panel.classList.toggle('has-error', Boolean(settings.completionError));
    message.textContent = settings.completing ? 'Saving verification…' : settings.completionError ||
      (dirty ? 'Complete and save all candidate changes before verifying this section.' :
       !completion.count ? 'Add and save at least one candidate before verifying this section.' :
       checkbox.checked ? 'Verified. Any change to a candidate or report will require a new verification.' : 'Verify the arrangements to complete this section.');
  };
  const count = section => {
    const total = section.querySelectorAll('[data-pen-form]').length;
    section.querySelector('[data-pen-count]').textContent = `${total} candidate${total === 1 ? '' : 's'}`;
    section.querySelector('[data-pen-empty]').hidden = total > 0;
    renderCompletion(section);
  };
  const makeCard = (section, row = null) => {
    const settings = sectionStates.get(section);
    const card = section.querySelector('[data-pen-card-template]').content.firstElementChild.cloneNode(true);
    const id = row?.id || crypto.randomUUID();
    card.action = settings.url + '/' + id;
    const number = card.elements.namedItem('candidate_no'), name = card.elements.namedItem('candidate_name');
    const editor = card.querySelector('[data-pen-editor]');
    const picker = card.querySelector('.pen-examiner-picker');
    const options = card.querySelector('[data-pen-examiners]');
    const status = card.querySelector('[data-pen-status]');
    const retry = card.querySelector('[data-pen-retry]');
    const fileInput = card.querySelector('[data-pen-file]');
    number.value = row?.candidate_no || ''; name.value = row?.candidate_name || '';
    // Server sanitizes this HTML before storage and again before returning it.
    editor.innerHTML = row?.recommendations_html || '';
    const state = {document:row?.document || null, file:null, removeDocument:false, deleting:false, range:null};
    const selected = new Set(row?.examiner_refs || []);
    const removedExaminers = [...selected].some(value => !settings.examiners.some(item => item.value === value));
    for (const item of settings.examiners) {
      const label = document.createElement('label'), checkbox = document.createElement('input');
      checkbox.type = 'checkbox'; checkbox.name = 'examiner_refs'; checkbox.value = item.value;
      checkbox.checked = selected.has(item.value);
      checkbox.disabled = !settings.can_edit || settings.examiners_disabled;
      label.append(checkbox, text('span', item.label)); options.append(label);
    }
    const selections = () => [...options.querySelectorAll('input:checked')];
    const updateTitle = () => { card.querySelector('[data-pen-card-title]').textContent = name.value.trim() || 'New candidate'; };
    const updateExaminers = () => {
      const checked = selections();
      card.querySelector('[data-pen-examiners-label]').textContent = settings.examiners_disabled ? 'Not applicable' : checked.length ? checked.map(input => input.nextElementSibling.textContent).join(', ') : 'Select examiners';
    };
    const updateFile = () => {
      const link = card.querySelector('[data-pen-document]');
      link.hidden = !state.document || state.removeDocument;
      if (!link.hidden) { link.href = state.document.url; link.textContent = state.document.filename; }
      else link.removeAttribute('href');
      card.querySelector('[data-pen-filename]').textContent = state.file ? `Selected: ${state.file.name}` : state.removeDocument ? 'Report will be removed when this card is saved.' : '';
      card.querySelector('[data-pen-file-remove]').hidden = !settings.can_edit || (!state.file && (!state.document || state.removeDocument));
      card.querySelector('[data-pen-file-indicator]').hidden = !state.file && (!state.document || state.removeDocument);
      card.querySelector('[data-pen-text-indicator]').hidden = !editor.textContent.trim();
    };
    const validate = () => {
      const missing = [];
      if (!number.value.trim()) missing.push('Candidate no.');
      if (!name.value.trim()) missing.push('Candidate name');
      number.setAttribute('aria-invalid', String(!number.value.trim())); name.setAttribute('aria-invalid', String(!name.value.trim()));
      const validExaminers = settings.examiners_disabled || selections().length > 0;
      picker.setAttribute('aria-invalid', String(!validExaminers));
      if (!validExaminers) missing.push('Examiner(s) in charge');
      if (missing.length) return `Not saved. Complete ${missing.join(', ')}.`;
      if (editor.innerHTML.length > 50000) return 'Not saved. Shorten the recommendations to fewer than 50,000 characters.';
      return '';
    };
    const controller = new window.PenCardAutosave({
      validate,
      status(kind, message) { card.dataset.state = kind; status.textContent = message; retry.hidden = kind !== 'error'; renderCompletion(section); },
      settled: () => renderCompletion(section),
      snapshot: () => ({number:number.value.trim(), name:name.value.trim(), refs:selections().map(input => input.value), html:editor.innerHTML, file:state.file, removeDocument:state.removeDocument}),
      async save(snapshot, revision) {
        const body = new FormData(); body.set('csrf_token', section.dataset.penCsrf); body.set('revision', revision);
        body.set('candidate_no', snapshot.number); body.set('candidate_name', snapshot.name); body.set('recommendations_html', snapshot.html);
        snapshot.refs.forEach(ref => body.append('examiner_refs', ref));
        if (snapshot.file) body.set('document', snapshot.file);
        if (snapshot.removeDocument) body.set('remove_document', '1');
        const result = await request(card.action, {method:'POST', body});
        settings.completion = result.completion; settings.completionError = '';
        return result;
      },
      saved(candidate, snapshot) {
        state.document = candidate.document;
        // Do not clear a newer file selection or overwrite text typed during the request.
        if (state.file === snapshot.file && state.removeDocument === snapshot.removeDocument) {
          state.file = null; state.removeDocument = false; fileInput.value = '';
        }
        updateFile();
      }
    }, row?.revision || 0);
    state.controller = controller; controllers.set(card, state);
    const changed = event => {
      if (!settings.can_edit || state.deleting || event.isComposing) return;
      updateTitle(); updateExaminers(); updateFile(); controller.change();
    };
    card.addEventListener('input', changed); card.addEventListener('change', changed);
    card.addEventListener('compositionend', changed);
    card.addEventListener('submit', event => { event.preventDefault(); if (settings.can_edit) controller.flush(); });
    retry.addEventListener('click', () => controller.flush());
    const chooseFile = files => {
      if (!settings.can_edit || state.deleting || !files.length) return;
      if (files.length !== 1) { window.alert('Select a single Specialist assessment report per candidate.'); return; }
      state.file = files[0]; state.removeDocument = false; updateFile(); controller.change();
    };
    fileInput.addEventListener('change', () => chooseFile([...fileInput.files]));
    const dropzone = card.querySelector('[data-pen-dropzone]');
    dropzone.addEventListener('dragover', event => { event.preventDefault(); if (settings.can_edit && !state.deleting) dropzone.classList.add('is-dragging'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('is-dragging'));
    dropzone.addEventListener('drop', event => { event.preventDefault(); dropzone.classList.remove('is-dragging'); chooseFile([...event.dataTransfer.files]); });
    card.querySelector('[data-pen-file-remove]').addEventListener('click', () => {
      if (!settings.can_edit || state.deleting) return;
      state.file = null; state.removeDocument = true; fileInput.value = ''; updateFile(); controller.change();
    });
    card.querySelector('[data-pen-delete]').addEventListener('click', async event => {
      if (!settings.can_edit || state.deleting) return;
      if (!window.confirm('Delete this candidate card? Any saved assessment report will be moved to the Drive trash.')) return;
      const button = event.currentTarget;
      state.deleting = true; button.disabled = true;
      await controller.pause();
      try {
        if (controller.revision) {
          const body = new FormData(); body.set('csrf_token', section.dataset.penCsrf); body.set('revision', controller.revision); body.set('action', 'delete');
          const result = await request(card.action, {method:'POST', body});
          settings.completion = result.completion; settings.completionError = '';
        } else if (controller.attempted) {
          const latest = await request(settings.url);
          if (latest.candidates.some(candidate => candidate.id === id)) throw new Error('Reopen this session to load the saved candidate before deleting.');
        }
        controller.remove(); controllers.delete(card); card.remove(); count(section);
      } catch (error) {
        controller.notify('error', error.message); controller.resume();
      } finally { state.deleting = false; button.disabled = false; renderCompletion(section); }
    });
    const rememberSelection = () => {
      const selection = window.getSelection();
      if (!selection?.rangeCount) return;
      const range = selection.getRangeAt(0);
      if (editor.contains(range.commonAncestorContainer)) state.range = range.cloneRange();
    };
    editor.addEventListener('keyup', rememberSelection); editor.addEventListener('mouseup', rememberSelection); editor.addEventListener('input', rememberSelection);
    card.querySelectorAll('[data-pen-command]').forEach(button => {
      button.addEventListener('mousedown', event => event.preventDefault());
      button.addEventListener('click', () => {
        if (!settings.can_edit || state.deleting) return;
        editor.focus();
        if (state.range) { const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(state.range); }
        document.execCommand(button.dataset.penCommand, false, null); rememberSelection(); changed({});
      });
    });
    // Paste plain text; users can apply the compact toolbar's formatting afterwards.
    editor.addEventListener('paste', event => {
      if (!settings.can_edit) return;
      event.preventDefault(); document.execCommand('insertText', false, event.clipboardData.getData('text/plain')); changed({});
    });
    if (!settings.can_edit) {
      card.querySelectorAll('input, button').forEach(input => { input.disabled = true; });
      editor.contentEditable = 'false'; dropzone.hidden = true;
    }
    if (settings.examiners_disabled) {
      card.querySelector('.pen-examiners').classList.add('is-disabled');
      picker.querySelector('summary').setAttribute('aria-disabled', 'true'); picker.querySelector('summary').tabIndex = -1;
      picker.addEventListener('click', event => event.preventDefault());
      card.querySelector('[data-pen-examiners-required]').hidden = true;
    }
    if (settings.examiners_disabled || !settings.examiners.length || removedExaminers) {
      const help = card.querySelector('[data-pen-examiners-help]'); help.hidden = false;
      help.textContent = settings.examiners_disabled ? 'Not applicable to Online at exam centre sessions.' : !settings.examiners.length ? 'No Examiners assigned. Assign an Examiner in Staffing before saving this card.' : 'Some previously selected Examiners are no longer assigned. Review the current selection before saving.';
    }
    section.querySelector('[data-pen-cards]').append(card); updateTitle(); updateExaminers(); updateFile(); count(section);
    if (row) controller.notify('saved', 'Saved automatically');
    else { controller.change(); number.focus(); }
    return card;
  };
  document.querySelectorAll('[data-pen-section]').forEach(section => {
    const settings = {url:section.dataset.penUrl, loaded:false, loading:false}; sectionStates.set(section, settings); sections.add(section);
    const add = section.querySelector('[data-pen-add]'), retry = section.querySelector('[data-pen-load-retry]'), status = section.querySelector('[data-pen-section-status]');
    const load = async () => {
      if (settings.loaded || settings.loading) return;
      settings.loading = true; retry.hidden = true; status.textContent = 'Loading arrangements…';
      try {
        const data = await request(settings.url); Object.assign(settings, data);
        if (!data.enabled) { section.hidden = true; return; }
        data.candidates.forEach(candidate => makeCard(section, candidate));
        settings.loaded = true; add.hidden = !data.can_edit; add.disabled = !data.can_edit;
        status.textContent = data.can_edit ? 'Changes save automatically once required fields are complete.' : 'View only'; count(section);
      } catch (error) { status.textContent = error.message; retry.hidden = false; }
      finally { settings.loading = false; }
    };
    section.querySelector('[data-pen-confirm]').addEventListener('change', async event => {
      const desired = event.target.checked;
      const dirty = [...controllers].some(([card, state]) => section.contains(card) && (state.controller.dirty || state.deleting));
      if (!settings.can_edit || settings.completing || dirty || !settings.completion?.count) { renderCompletion(section); return; }
      settings.completing = true; settings.completionError = ''; renderCompletion(section);
      try {
        const body = new FormData(); body.set('csrf_token', section.dataset.penCsrf);
        body.set('snapshot', settings.completion.snapshot); body.set('confirmed', desired ? '1' : '0');
        const result = await request(settings.url + '/confirmation', {method:'POST', body});
        settings.completion = result.completion;
      } catch (error) { settings.completionError = error.message; settings.completionStale = error.status === 409; }
      finally { settings.completing = false; renderCompletion(section); }
    });
    retry.addEventListener('click', load); add.addEventListener('click', () => { if (settings.can_edit) makeCard(section); });
    // Fetch only when this section becomes visible in its session modal.
    if (typeof IntersectionObserver !== 'undefined') {
      const observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { load(); observer.disconnect(); } });
      observer.observe(section);
    } else load();
  });
})();
