(() => {
  'use strict';
  document.querySelectorAll('[data-drive-settings]').forEach(root => {
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
        const authorizeOnly = card.dataset.driveAuthorizeOnly === 'true';
        const folderLink = authorizeOnly ? card.querySelector('[data-drive-folder-link]').value.trim() : '';
        let expectedFolderId = '';
        if (authorizeOnly) {
          let parsed;
          try { parsed = new URL(folderLink); } catch { throw new Error('Enter a valid Google Drive folder link.'); }
          const match = parsed.pathname.match(/^\/(?:drive\/(?:u\/\d+\/)?)?folders\/([A-Za-z0-9_-]{10,160})\/?$/);
          if (parsed.protocol !== 'https:' || parsed.hostname !== 'drive.google.com' || parsed.username || parsed.password || !match) throw new Error('Enter a valid Google Drive folder link.');
          expectedFolderId = match[1];
        }
        await loadPicker();
        let config = await request(root.dataset.tokenUrl);
        const pickerApi = window.google.picker;
        const folders = () => new pickerApi.DocsView(pickerApi.ViewId.FOLDERS).setIncludeFolders(true).setSelectFolderEnabled(true);
        const builder = new pickerApi.PickerBuilder().setAppId(config.app_id).setDeveloperKey(config.api_key)
          .setOAuthToken(config.access_token).setOrigin(window.location.origin)
          .setTitle('Choose the destination folder').setSelectableMimeTypes('application/vnd.google-apps.folder');
        const suggestedId = expectedFolderId || card.dataset.suggestedId;
        if (suggestedId) builder.addView(folders().setFileIds(suggestedId));
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
            if (expectedFolderId && folder.id !== expectedFolderId) throw new Error('Choose the same folder as the Session pictures folder link.');
            const saved = await request(card.dataset.saveUrl, {folder_id:folder.id, ...(authorizeOnly ? {folder_url:folderLink} : {})});
            const link = document.createElement('a'); link.href = saved.url; link.textContent = saved.name;
            link.target = '_blank'; link.rel = 'noopener noreferrer';
            card.querySelector('[data-drive-current]').replaceChildren(link);
            card.dataset.suggestedId = folder.id;
            button.textContent = authorizeOnly ? (card.dataset.driveButtonLabel || 'Choose and authorize folder') : 'Change folder'; message.className = 'is-success';
            message.textContent = authorizeOnly ? 'Drive access authorized for this Session pictures folder.' : 'Folder saved. New uploads will be stored here.';
          } catch (error) {message.className = 'is-error';message.textContent = error.message;}
          finally {button.disabled = false;picker.dispose();}
        });
        picker = builder.build(); picker.setVisible(true); message.textContent = 'Choose a folder in Google Drive.';
      } catch (error) {button.disabled = false;message.className = 'is-error';message.textContent = error.message;}
    });
  });
  });
})();
