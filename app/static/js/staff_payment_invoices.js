(() => {
  const dialog = document.querySelector('[data-staff-invoice-preview]');
  if (!dialog) return;
  const frame = dialog.querySelector('[data-staff-invoice-preview-frame]');
  const title = dialog.querySelector('#staff-invoice-preview-title');
  const fallback = dialog.querySelector('[data-staff-invoice-preview-fallback]');
  const download = dialog.querySelector('[data-staff-invoice-preview-download]');
  let opener;
  document.querySelectorAll('[data-staff-invoice-view]').forEach(link => {
    link.addEventListener('click', event => {
      event.preventDefault(); opener = link;
      title.textContent = link.dataset.invoiceName || 'Invoice';
      const previewable = link.dataset.invoicePreviewable === 'true';
      frame.hidden = !previewable; fallback.hidden = previewable;
      if (previewable) frame.src = link.href;
      else { frame.removeAttribute('src'); download.href = link.href; }
      dialog.showModal();
    });
  });
  dialog.querySelector('[data-staff-invoice-preview-close]').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => { frame.removeAttribute('src'); opener?.focus(); });
  document.querySelectorAll('.staff-payment-invoice-remove-form').forEach(form => {
    form.addEventListener('submit', () => { form.querySelector('button').disabled = true; });
  });
})();
