(() => {
  const widgets = () => [...document.querySelectorAll('[data-return-label-upload]')];
  const render = (widget, documentData) => {
    widget.dataset.fileId = documentData?.file_id || '';
    widget.dataset.filePresent = documentData ? 'true' : 'false';
    widget.querySelector('[data-return-label-dropzone]').hidden = Boolean(documentData);
    widget.querySelector('[data-return-label-document]').hidden = !documentData;
    const link = widget.querySelector('[data-return-label-view]');
    link.textContent = documentData?.filename || '';
    link.href = documentData?.url || '#';
    syncReturnMaterialsOptions(widget.closest('[data-return-materials-form]'));
  };
  window.refreshReturnLabels = async () => {
    await Promise.allSettled(widgets().map(async widget => {
      if (widget.dataset.busy === 'true') return;
      const response = await fetch(widget.dataset.url, {headers: {Accept: 'application/json'}});
      if (!response.ok) return;
      const result = await response.json();
      if (result.ok) render(widget, result.document);
    }));
  };
  widgets().forEach(widget => {
    const form = widget.closest('[data-return-materials-form]');
    const input = widget.querySelector('[data-return-label-file]');
    const dropzone = widget.querySelector('[data-return-label-dropzone]');
    const remove = widget.querySelector('[data-return-label-delete]');
    const feedback = widget.querySelector('[data-return-label-feedback]');
    const locked = () => form.dataset.returnEnabled === 'false' || input.matches(':disabled')
      || Boolean(document.querySelector('main[data-current-menu-can-edit="false"]'));
    const error = message => {
      feedback.hidden = false; feedback.textContent = message; feedback.classList.add('is-error');
    };
    const save = async (files, deleting = false) => {
      if (locked() || widget.dataset.busy === 'true') return;
      if (!deleting && files.length !== 1) {
        error('Please select exactly one shipping label file.'); input.value = ''; return;
      }
      widget.dataset.busy = 'true';
      input.disabled = true; remove.disabled = true;
      feedback.hidden = false; feedback.classList.remove('is-error');
      feedback.textContent = deleting ? 'Deleting shipping label...' : 'Uploading shipping label...';
      try {
        while (returnMaterialsSaveQueues.get(form)?.length) await new Promise(resolve => setTimeout(resolve, 50));
        const body = new FormData();
        body.set('csrf_token', form.querySelector('[name="csrf_token"]').value);
        body.set('previous_file_id', widget.dataset.fileId || '');
        if (deleting) body.set('action', 'delete');
        else body.append('document', files[0]);
        const response = await fetch(widget.dataset.url, {method: 'POST', body, headers: {Accept: 'application/json'}});
        const result = await response.json();
        if (!response.ok || !result.ok) throw new Error(result.error || 'The shipping label could not be saved.');
        render(widget, result.document);
        feedback.hidden = true;
      } catch (exception) { error(exception.message || 'The shipping label could not be updated. Please retry.'); }
      finally {
        input.value = ''; input.disabled = false; remove.disabled = false;
        delete widget.dataset.busy;
      }
      await window.refreshReturnLabels();
    };
    input.addEventListener('change', () => { if (input.files.length) save([...input.files]); });
    remove.addEventListener('click', () => save([], true));
    dropzone.addEventListener('dragover', event => {
      event.preventDefault(); if (!locked()) dropzone.classList.add('is-dragging');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('is-dragging'));
    dropzone.addEventListener('drop', event => {
      event.preventDefault(); dropzone.classList.remove('is-dragging');
      if (!locked()) save([...event.dataTransfer.files]);
    });
  });
})();
