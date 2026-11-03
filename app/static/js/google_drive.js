(() => {
  'use strict';
  const root = document.querySelector('[data-drive-settings]');
  if (!root) return;
  let loading;
  const loadPicker = () => {
    if (window.google?.picker) return Promise.resolve();
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      const timer = setTimeout(() => {loading = null; script.remove(); reject(new Error('Google Picker could not be loaded. Please try again.'));}, 20000);
      script.src = 'https://apis.google.com/js/api.js';
      script.onload = () => window.gapi.load('picker', {callback: () => {clearTimeout(timer); resolve();},
        onerror: () => {clearTimeout(timer); loading = null; reject(new Error('Google Picker could not be loaded. Please try again.'));}});
      script.onerror = () => {clearTimeout(timer); loading = null; reject(new Error('Google Picker could not be loaded. Please try again.'));};
      document.head.append(script);
    });
    return loading;
  };
  const request = async (url, fields = {}) => {
    const body = new FormData(); body.set('csrf_token', root.dataset.csrf);
    Object.entries(fields).forEach(([key,value]) => body.set(key,value));
    const response = await fetch(url, {method:'POST', body, cache:'no-store', headers:{Accept:'application/json'}});
    if (!response.ok && response.status === 403) throw new Error('Administrator access is required.');
    if (response.redirected || !response.headers.get('Content-Type')?.includes('application/json')) throw new Error('Please sign in to the portal again and retry.');
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || 'The folder could not be saved.');
    return result;
  };
  root.querySelectorAll('[data-drive-choose]').forEach(button => {
    button.addEventListener('click', async () => {
      const card = button.closest('[data-drive-destination]');
      const message = card.querySelector('[data-drive-message]');
      button.disabled = true; message.className = ''; message.textContent = 'Opening Google Drive…';
      try {
        await loadPicker();
        let config = await request(root.dataset.tokenUrl);
        const pickerApi = window.google.picker;
        const folders = () => new pickerApi.DocsView(pickerApi.ViewId.FOLDERS).setIncludeFolders(true).setSelectFolderEnabled(true);
        const builder = new pickerApi.PickerBuilder().setAppId(config.app_id).setDeveloperKey(config.api_key)
          .setOAuthToken(config.access_token).setOrigin(window.location.origin)
          .setTitle('Choose the destination folder').setSelectableMimeTypes('application/vnd.google-apps.folder');
        if (card.dataset.suggestedId) builder.addView(folders().setFileIds(card.dataset.suggestedId));
        builder.addView(folders());
        let picker;
        builder.setCallback(async data => {
          if (![pickerApi.Action.PICKED,pickerApi.Action.CANCEL].includes(data.action)) return;
          config = null;
          if (data.action === pickerApi.Action.CANCEL) {
            message.textContent = ''; button.disabled = false; picker.dispose(); return;
          }
          const folder = data.docs?.[0];
          if (!folder?.id) {button.disabled = false; return;}
          message.textContent = 'Checking folder access…';
          try {
            const saved = await request(card.dataset.saveUrl, {folder_id:folder.id});
            const link = document.createElement('a'); link.href = saved.url; link.textContent = saved.name;
            link.target = '_blank'; link.rel = 'noopener noreferrer';
            card.querySelector('[data-drive-current]').replaceChildren(link);
            card.dataset.suggestedId = folder.id;
            button.textContent = 'Change folder'; message.className = 'is-success';
            message.textContent = 'Folder saved. New uploads will be stored here.';
          } catch (error) {message.className = 'is-error';message.textContent = error.message;}
          finally {button.disabled = false;picker.dispose();}
        });
        picker = builder.build(); picker.setVisible(true); message.textContent = 'Choose a folder in Google Drive.';
      } catch (error) {button.disabled = false;message.className = 'is-error';message.textContent = error.message;}
    });
  });
})();
