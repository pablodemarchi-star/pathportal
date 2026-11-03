(() => {
  const dialog = document.querySelector('[data-staff-id-dialog]');
  if (!dialog) return;
  const find = key => dialog.querySelector(`[data-staff-id-${key}]`);
  const message = find('message'), form = find('form'), input = find('file'), expiryInput = find('expiry-input');
  const frame = find('frame'), image = find('image'), preview = find('preview');
  let opener, url, documentInfo = null, selectedFile = null, busy = false, readOnly = false, issued = false;
  let expiryTimer;
  const isExpired = () => !!documentInfo?.expires_at && Date.now() >= Date.parse(documentInfo.expires_at);
  const updateExpiry = () => {
    const expired = isExpired();
    opener?.classList.toggle('is-expired', expired);
    const label = find('expiry-label');
    label.hidden = !documentInfo?.expiry_date;
    label.textContent = documentInfo?.expiry_date ? `Expiry date: ${documentInfo.expiry_date}${expired ? ' · Expired' : ''}` : '';
    label.classList.toggle('is-expired', expired);
    if (find('unissue')) find('unissue').hidden = !(issued && expired && dialog.dataset.canEdit === 'true');
  };
  const refreshExpiry = () => {
    clearTimeout(expiryTimer);
    const now = Date.now();
    let next = Infinity;
    document.querySelectorAll('[data-staff-id-open]').forEach(button => {
      const expiry = Date.parse(button.dataset.staffIdExpiry || '');
      const expired = Number.isFinite(expiry) && now >= expiry;
      button.classList.toggle('is-expired', expired);
      button.title = expired ? 'Expired' : '';
      if (expiry > now) next = Math.min(next, expiry - now);
    });
    if (dialog.open) updateExpiry();
    if (Number.isFinite(next)) expiryTimer = setTimeout(refreshExpiry, Math.min(next + 20, 2147483647));
  };
  document.addEventListener('visibilitychange', refreshExpiry);
  refreshExpiry();
  const status = (text, error = false) => {
    message.textContent = text;
    message.classList.toggle('is-error', error);
  };
  const setBusy = value => {
    busy = value;
    dialog.querySelectorAll('button, input').forEach(control => { control.disabled = value; });
  };
  const render = () => {
    preview.hidden = !documentInfo;
    dialog.classList.toggle('has-document', !!documentInfo);
    opener?.classList.toggle('has-document', !!documentInfo);
    if (opener) opener.dataset.staffIdExpiry = documentInfo?.expires_at || '';
    updateExpiry();
    refreshExpiry();
    if (form) form.hidden = readOnly || !!documentInfo;
    if (find('actions')) find('actions').hidden = readOnly;
    if (find('cancel')) find('cancel').hidden = true;
    frame.removeAttribute('src');
    image.removeAttribute('src');
    if (!documentInfo) {
      if (!form || readOnly) status('No document has been uploaded yet.');
      return;
    }
    find('filename').textContent = 'Download';
    find('filename').download = documentInfo.filename;
    find('filename').href = url + '/preview?download=1';
    const isImage = documentInfo.previewable && documentInfo.mime_type?.startsWith('image/');
    image.hidden = !isImage;
    frame.hidden = !documentInfo.previewable || isImage;
    find('fallback').hidden = documentInfo.previewable;
    find('download').href = url + '/preview?download=1';
    const source = url + '/preview?t=' + Date.now();
    if (isImage) image.src = source;
    else if (documentInfo.previewable) frame.src = source + '#view=Fit&zoom=page-fit&toolbar=0&navpanes=0';
  };
  const select = files => {
    selectedFile = null;
    if (files.length !== 1) {
      status('Please select exactly one file.', true);
      find('selected').textContent = '';
      return;
    }
    selectedFile = files[0];
    find('selected').textContent = selectedFile.name;
    status('');
  };
  const mutate = async (method, file, unissue = false) => {
    if (busy || (readOnly && !unissue)) return;
    const body = new FormData();
    body.set('csrf_token', dialog.dataset.csrf);
    body.set('previous_file_id', documentInfo?.file_id || '');
    if (file) { body.set('document', file); body.set('expiry_date', expiryInput.value); }
    if (unissue) body.set('action', 'unissue');
    setBusy(true); status(method === 'DELETE' ? 'Deleting…' : 'Uploading…');
    try {
      const response = await fetch(url, {method, body, headers: {Accept: 'application/json'}});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || 'The document could not be saved. Please try again.');
      documentInfo = result.document;
      issued = !!result.read_only;
      if (opener) opener.textContent = issued ? 'ID issued ✓' : 'No ID issued';
      if (opener?.dataset.memberId) {
        document.querySelectorAll(`#edit-member-${opener.dataset.memberId} input[name="id_issued"]`)
          .forEach(checkbox => { checkbox.checked = issued; checkbox.defaultChecked = issued; });
      }
      readOnly = dialog.dataset.canEdit !== "true" || !!result.read_only;
      selectedFile = null;
      if (input) input.value = '';
      if (expiryInput) expiryInput.value = '';
      if (find('selected')) find('selected').textContent = '';
      render();
      status(unissue ? 'Status changed to No ID issued. The previous card was moved to the Drive trash.' : method === 'DELETE' ? 'Document deleted.' : 'Document saved.');
    } catch (error) { status(error.message || 'The document could not be saved. Please try again.', true); }
    finally { setBusy(false); }
  };
  document.querySelectorAll('[data-staff-id-open]').forEach(button => button.addEventListener('click', async () => {
    if (dialog.open) return;
    opener = button; url = button.dataset.documentUrl;
    documentInfo = null; selectedFile = null;
    dialog.classList.remove('has-document');
    if (input) input.value = '';
    if (expiryInput) expiryInput.value = '';
    find('expiry-label').hidden = true;
    if (find('unissue')) find('unissue').hidden = true;
    if (find('selected')) find('selected').textContent = '';
    dialog.querySelector('#staff-id-document-title').textContent = `Staff ID card for ${button.dataset.memberName}`;
    preview.hidden = true;
    if (form) form.hidden = true;
    frame.removeAttribute('src');
    dialog.showModal(); setBusy(true); status('Loading…');
    try {
      const response = await fetch(url, {headers: {Accept: 'application/json'}});
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || 'The document could not be loaded. Please try again.');
      documentInfo = result.document;
      issued = !!result.read_only;
      if (opener) opener.textContent = issued ? 'ID issued ✓' : 'No ID issued';
      if (opener?.dataset.memberId) {
        document.querySelectorAll(`#edit-member-${opener.dataset.memberId} input[name="id_issued"]`)
          .forEach(checkbox => { checkbox.checked = issued; checkbox.defaultChecked = issued; });
      }
      readOnly = dialog.dataset.canEdit !== "true" || !!result.read_only;
      status(''); render();
    } catch (error) { status(error.message || 'The document could not be loaded. Please try again.', true); }
    finally { setBusy(false); }
  }));
  find('close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog && !busy) dialog.close(); });
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => { frame.removeAttribute('src'); image.removeAttribute('src'); opener?.focus(); });
  find('replace')?.addEventListener('click', () => {
    if (readOnly) return;
    form.hidden = false;
    expiryInput.value = '';
    find('cancel').hidden = false;
    status('Select one file to replace the current document.');
  });
  find('cancel')?.addEventListener('click', () => { selectedFile = null; input.value = ''; find('selected').textContent = ''; form.hidden = true; status(''); });
  find('delete')?.addEventListener('click', () => {
    if (window.confirm('Delete this document and move it to the Drive trash?')) mutate('DELETE');
  });
  find('unissue')?.addEventListener('click', () => {
    if (issued && isExpired()) mutate('POST', null, true);
  });
  expiryInput?.addEventListener('input', () => {
    const digits = expiryInput.value.replace(/\D/g, '').slice(0, 8);
    expiryInput.value = [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4)].filter(Boolean).join('/');
  });
  input?.addEventListener('change', () => select(input.files));
  const zone = find('dropzone');
  ['dragenter', 'dragover'].forEach(type => zone?.addEventListener(type, event => { event.preventDefault(); zone.classList.add('is-drag-over'); }));
  ['dragleave', 'drop'].forEach(type => zone?.addEventListener(type, event => { event.preventDefault(); zone.classList.remove('is-drag-over'); }));
  zone?.addEventListener('drop', event => { if (!busy) select(event.dataTransfer.files); });
  form?.addEventListener('submit', event => {
    event.preventDefault();
    if (!selectedFile) { status('Please select exactly one file.', true); return; }
    if (!expiryInput.reportValidity()) return;
    mutate('POST', selectedFile);
  });
})();
