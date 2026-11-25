(() => {
  'use strict';
  const sections = new Map();
  const dirty = item => item.saving || item.removing || item.timer || item.file || item.title.value !== item.savedTitle || !item.saved;
  const pending = state => state.busy > 0 || Boolean(state.failedControl) || [...state.cards.values()].some(dirty);
  window.announcementsHasUnsavedChanges = root => [...sections].some(([section, state]) => (!root || root.contains(section)) && pending(state));
  window.addEventListener('beforeunload', event => {
    if (window.announcementsHasUnsavedChanges()) { event.preventDefault(); event.returnValue = ''; }
  });
  const fetchJSON = async (url, options = {}) => {
    const response = await fetch(url, {cache:'no-store', ...options, headers:{Accept:'application/json', ...options.headers}});
    const result = await response.json().catch(() => ({}));
    if (!response.ok || response.redirected || !result.ok) {
      const error = new Error(result.error || 'Announcements could not be saved. Check your connection and retry.');
      error.status = response.status; throw error;
    }
    return result;
  };
  document.querySelectorAll('[data-announcements-section]').forEach(section => {
    const toggle = document.querySelector(`[data-announcement-toggle="${section.dataset.announcementsSection}"]`);
    const template = document.querySelector(`[data-announcement-template="${section.dataset.announcementsSection}"]`);
    const cards = section.querySelector('[data-announcements-cards]');
    const ready = section.querySelector('[data-announcements-ready]');
    const add = section.querySelector('[data-announcement-add]');
    const feedback = section.querySelector('[data-announcements-feedback]');
    const retry = section.querySelector('[data-announcements-retry]');
    const state = {cards:new Map(), queue:Promise.resolve(), busy:0, loaded:false, enabled:false, ready:false, revision:0, can_edit:false, stale:false};
    sections.set(section, state);
    const say = (message, error = false) => { feedback.textContent = message; feedback.classList.toggle('is-error', error); };
    const render = () => {
      section.hidden = state.loaded && !state.enabled;
      toggle.disabled = !state.loaded || !state.can_edit || state.stale || pending(state);
      toggle.setAttribute('aria-pressed', String(state.enabled));
      toggle.setAttribute('aria-label', state.enabled ? 'Disable Announcements' : 'Enable Announcements');
      add.disabled = !state.loaded || !state.can_edit || state.stale || state.busy > 0;
      ready.checked = Boolean(state.ready && !pending(state));
      ready.disabled = !state.can_edit || state.stale || !state.cards.size || pending(state);
      const badge = section.querySelector('[data-announcements-badge]');
      badge.textContent = ready.checked ? 'Completed' : 'Pending'; badge.classList.toggle('is-ready', ready.checked);
      section.querySelector('[data-announcements-empty]').hidden = state.cards.size > 0;
      section.querySelector('[data-announcements-help]').textContent = ready.checked ? 'Ready for confirmed supervisors in their session portals.' : 'Add at least one announcement and finish all changes before confirming.';
    };
    const apply = result => { state.revision = result.revision; state.enabled = result.enabled; state.ready = result.ready; };
    const post = async fields => {
      if (state.stale) throw new Error('Reopen this session to load the latest announcements.');
      const body = new FormData(); body.set('csrf_token', section.dataset.csrf); body.set('revision', state.revision);
      for (const [key, value] of Object.entries(fields)) body.set(key, value);
      const result = await fetchJSON(section.dataset.url, {method:'POST', body});
      apply(result);
      if (state.failedControl?.action === 'pending' && !result.ready) { state.failedControl = null; retry.hidden = true; }
      return result;
    };
    const enqueue = task => {
      state.busy++; render();
      const job = state.queue.then(task).catch(error => {
        if (error.status === 409) { state.stale = true; retry.hidden = true; }
        say(error.message, true); throw error;
      }).finally(() => { state.busy--; render(); });
      state.queue = job.catch(() => {});
      return job;
    };
    const controlPost = async fields => {
      state.failedControl = fields;
      try { const result = await post(fields); state.failedControl = null; retry.hidden = true; return result; }
      catch (error) { retry.hidden = state.stale || error.status === 409; throw error; }
    };
    const markPending = () => enqueue(async () => {
      if (state.ready) await controlPost({action:'pending'});
    });
    const cardFeedback = (item, message, kind) => {
      item.form.dataset.state = kind; item.feedback.textContent = message; item.retry.hidden = kind !== 'error';
    };
    const makeCard = row => {
      const fragment = template.content.cloneNode(true);
      const form = fragment.querySelector('form');
      const item = {form, id:row?.id || crypto.randomUUID(), saved:Boolean(row), savedTitle:row?.title || '', file:null, saving:false, removing:false, timer:null, blob:null};
      item.title = form.querySelector('[name=title]'); item.title.value = item.savedTitle;
      item.input = form.querySelector('[name=audio]'); item.player = form.querySelector('audio');
      item.filename = form.querySelector('[data-announcement-filename]');
      item.feedback = form.querySelector('[data-announcement-feedback]'); item.retry = form.querySelector('[data-announcement-retry]');
      const remove = form.querySelector('[data-announcement-delete]');
      item.title.disabled = item.input.disabled = remove.disabled = !state.can_edit;
      if (row) { item.input.required = false; item.filename.textContent = row.filename; item.player.src = row.audio_url; item.player.hidden = false; cardFeedback(item, 'Saved automatically', 'saved'); }
      const save = () => {
        clearTimeout(item.timer); item.timer = null;
        if (!item.title.value.trim() || !item.saved && !item.file) {
          cardFeedback(item, 'Enter a title and choose one MP3 or WAV audio. This card has not been saved.', 'pending'); render(); return;
        }
        if (item.saving || !dirty(item) || state.stale) return;
        item.saving = true; cardFeedback(item, 'Saving…', 'saving');
        enqueue(async () => {
          const title = item.title.value, file = item.file;
          const fields = {action:'save', id:item.id, title}; if (file) fields.audio = file;
          const result = await post(fields);
          const saved = result.announcements.find(value => value.id === item.id);
          item.saved = true; item.savedTitle = title;
          if (item.file === file) {
            item.file = null; item.input.value = ''; item.input.required = false;
            if (item.blob) URL.revokeObjectURL(item.blob); item.blob = null;
            item.player.src = saved.audio_url; item.filename.textContent = saved.filename;
          }
          cardFeedback(item, 'Saved automatically', 'saved');
        }).then(() => { item.saving = false; if (dirty(item)) schedule(); render(); })
          .catch(error => { item.saving = false; cardFeedback(item, error.message, 'error'); render(); });
      };
      const schedule = () => {
        clearTimeout(item.timer); item.timer = setTimeout(save, 500); render();
      };
      const changed = () => {
        if (state.failedControl?.action === 'ready') { state.failedControl = null; retry.hidden = true; }
        ready.checked = false; cardFeedback(item, 'Unsaved changes…', 'pending');
        markPending().catch(() => {}); schedule();
      };
      item.title.addEventListener('input', changed);
      item.player.addEventListener('play', () => { document.querySelectorAll('audio').forEach(other => { if (other !== item.player) other.pause(); }); });
      const selectFile = files => {
        if (!state.can_edit || state.stale) return;
        if (files.length !== 1 || !/\.(mp3|wav)$/i.test(files[0].name)) {
          item.input.value = ''; cardFeedback(item, 'Choose a single MP3 or WAV audio file.', 'error'); return;
        }
        item.file = files[0];
        if (item.blob) URL.revokeObjectURL(item.blob);
        item.blob = URL.createObjectURL(item.file); item.player.src = item.blob; item.player.hidden = false; item.filename.textContent = item.file.name;
        changed();
      };
      item.input.addEventListener('change', () => selectFile(item.input.files));
      const drop = form.querySelector('[data-announcement-drop]');
      drop.addEventListener('dragover', event => { event.preventDefault(); if (state.can_edit) drop.classList.add('is-over'); });
      drop.addEventListener('dragleave', () => drop.classList.remove('is-over'));
      drop.addEventListener('drop', event => { event.preventDefault(); drop.classList.remove('is-over'); selectFile(event.dataTransfer.files); });
      remove.addEventListener('click', () => {
        if (item.saving || item.removing || !state.can_edit || state.stale || !confirm('Delete this announcement? Its audio will be moved to the Drive trash.')) return;
        clearTimeout(item.timer); item.timer = null; item.removing = true; remove.disabled = true;
        enqueue(async () => {
          if (item.saved) await post({action:'delete', id:item.id});
          else if (state.ready) await controlPost({action:'pending'});
          item.player.pause(); if (item.blob) URL.revokeObjectURL(item.blob);
          form.remove(); state.cards.delete(item.id);
        }).catch(error => { item.removing = false; remove.disabled = false; cardFeedback(item, error.message, 'error'); });
      });
      item.retry.addEventListener('click', save);
      form.addEventListener('submit', event => { event.preventDefault(); save(); });
      state.cards.set(item.id, item); cards.append(fragment); render(); return item;
    };
    toggle.addEventListener('click', () => {
      if (toggle.disabled) return;
      enqueue(async () => { await controlPost({action:'toggle', enabled:state.enabled ? '0' : '1'}); say('Saved automatically'); })
        .catch(() => { retry.hidden = state.stale; });
    });
    add.addEventListener('click', () => {
      if (add.disabled) return;
      enqueue(async () => { if (state.ready) await controlPost({action:'pending'}); makeCard().title.focus(); }).catch(() => {});
    });
    ready.addEventListener('change', () => {
      const desired = ready.checked;
      if (ready.disabled) { render(); return; }
      enqueue(async () => { await controlPost({action:desired ? 'ready' : 'pending'}); say('Saved automatically'); }).catch(() => {});
    });
    const load = async () => {
      say('Loading announcements…'); toggle.disabled = true; retry.hidden = true;
      try {
        const result = await fetchJSON(section.dataset.url);
        apply(result); state.can_edit = result.can_edit; state.loaded = true;
        result.announcements.forEach(makeCard); say(state.can_edit ? 'Changes save automatically.' : 'View only.'); render();
      } catch (error) { section.hidden = false; say(error.message, true); retry.hidden = false; }
    };
    retry.addEventListener('click', () => { if (!state.loaded) load(); else if (state.failedControl) enqueue(async () => { await controlPost(state.failedControl); say('Saved automatically'); }).catch(() => {}); });
    load();
  });
})();
