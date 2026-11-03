(() => {
  document.querySelectorAll('[data-staff-invoice-form]').forEach(form => {
    const input = form.querySelector('[data-staff-invoice-input]');
    const zone = form.querySelector('[data-staff-invoice-dropzone]');
    const selected = form.querySelector('[data-staff-invoice-selected]');
    const filename = form.querySelector('[data-staff-invoice-filename]');
    const error = form.querySelector('[data-staff-invoice-error]');
    const button = form.querySelector('[data-staff-invoice-submit]');
    const showSelected = () => {
      selected.hidden = !input.files.length;
      filename.textContent = input.files[0]?.name || '';
      error.hidden = true;
    };
    input.addEventListener('change', showSelected);
    zone.addEventListener('dragover', event => { event.preventDefault(); zone.classList.add('is-drag-over'); });
    zone.addEventListener('dragleave', event => { if (!zone.contains(event.relatedTarget)) zone.classList.remove('is-drag-over'); });
    zone.addEventListener('drop', event => {
      event.preventDefault(); zone.classList.remove('is-drag-over');
      const files = event.dataTransfer?.files;
      if (!files?.length) return;
      if (files.length !== 1) { error.textContent = 'Please select exactly one invoice file.'; error.hidden = false; return; }
      const transfer = new DataTransfer(); transfer.items.add(files[0]); input.files = transfer.files;
      showSelected();
    });
    form.querySelector('[data-staff-invoice-remove]').addEventListener('click', () => { input.value = ''; showSelected(); });
    form.addEventListener('submit', event => {
      if (input.files.length !== 1) { event.preventDefault(); error.textContent = 'Please select exactly one invoice file.'; error.hidden = false; return; }
      button.disabled = true; button.textContent = 'Uploading…';
    });
    window.addEventListener('pageshow', () => { button.disabled = false; button.textContent = button.dataset.originalLabel; });
    button.dataset.originalLabel = button.textContent;
  });
})();
