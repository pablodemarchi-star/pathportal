(() => {
  'use strict';
  const MODES = ['schedule', 'staffing', 'packages', 'shipments', 'logistics', 'finance', 'sinapsis', 'communications'];
  const child = document.body.matches('[data-tower-modal-document]');
  const nativeFetch = window.fetch.bind(window);
  const controllerURL = document.currentScript.src;
  const notifyParent = type => window.parent.postMessage({type, revision: document.body.dataset.revision}, window.location.origin);

  if (!child) {
    let summaryBusy = false;
    const refreshSummary = async () => {
      if (summaryBusy) return;
      summaryBusy = true;
      try {
        const response = await nativeFetch(window.location.href, {cache: 'no-store'});
        if (!response.ok || response.redirected) return;
        const page = new DOMParser().parseFromString(await response.text(), 'text/html');
        const current = document.querySelector('[data-tower-table-region]');
        const fresh = page.querySelector('[data-tower-table-region]');
        if (!current || !fresh) return;
        const positions = [...current.querySelectorAll('.table-wrap')].map(item => [item.scrollLeft, item.scrollTop]);
        current.replaceWith(fresh);
        [...fresh.querySelectorAll('.table-wrap')].forEach((item, index) => {
          [item.scrollLeft, item.scrollTop] = positions[index] || [0, 0];
        });
        page.querySelectorAll('[data-tower-session]').forEach(modal => {
          if (!document.getElementById(modal.id)) document.body.append(modal);
        });
        window.initTowerSummaryControls?.(fresh);
      } catch (_) { /* Keep the current table until the next successful refresh. */ }
      finally { summaryBusy = false; }
    };
    const displayLoadedFrame = (modal, frame) => {
      const loading = modal.querySelector('[data-tower-loading]');
      const header = modal.querySelector('[data-tower-loading-header]');
      const retry = modal.querySelector('[data-tower-retry]');
          try {
            if (!frame.contentDocument?.body.matches('[data-tower-modal-document]') || !frame.contentDocument.querySelector('.modal.is-open')) throw new Error('Load failed');
            loading.hidden = true; retry.hidden = true; header.hidden = true; frame.hidden = false;
            frame.contentWindow.focus();
          } catch (_) {
            // A failed refresh must restore the error panel too, not leave the
            // failed iframe visible with only an unexplained retry button.
            frame.hidden = true;
            header.hidden = false;
            loading.hidden = false;
            let loginPage = false;
            try { loginPage = Boolean(frame.contentDocument?.querySelector('form[action="/login"], input[name="password"]')); } catch (_) {}
            loading.textContent = loginPage
              ? 'Your sign-in session has expired. Reload the page and sign in again.'
              : `${modal.dataset.towerLoadingKind === 'bundle' ? 'Bundle' : 'Session'} details could not be loaded. Please try again. If the problem persists, reload the page.`;
            retry.hidden = false;
          }
    };
    window.loadTowerModal = (modal, opener) => {
      const frame = modal.querySelector('[data-tower-frame]');
      const loading = modal.querySelector('[data-tower-loading]');
      const header = modal.querySelector('[data-tower-loading-header]');
      const retry = modal.querySelector('[data-tower-retry]');
      const load = () => {
        const url = new URL(window.location.href);
        url.searchParams.set('session_modal', modal.dataset.towerSession);
        url.searchParams.set('open_schedule_modal', modal.dataset.towerSession);
        url.searchParams.delete('close_view');
        for (const mode of MODES) {
          url.searchParams.delete(`${mode}_only`);
          if (modal.classList.contains(`is-${mode}-only`)) url.searchParams.set(`${mode}_only`, '1');
        }
        if (opener) {
          url.searchParams.delete('open_schedule_action');
          for (const mode of MODES) url.searchParams.delete(`open_${mode}_control`);
          const target = opener.dataset.modalScrollTarget;
          url.searchParams.set('open_modal_target', target ? target.replace(/-\d+$/, '') : 'overview');
        }
        frame.hidden = true; header.hidden = false; loading.hidden = false; retry.hidden = true;
        const bundleNumber = opener?.dataset.modalBundleNumber || modal.dataset.towerBundleNumber;
        const bundleShipment = modal.classList.contains('is-shipments-only') && Boolean(bundleNumber);
        modal.dataset.towerLoadingKind = bundleShipment ? 'bundle' : 'session';
        const titleNode = modal.querySelector('[data-tower-loading-title]');
        if (titleNode) {
          modal.dataset.towerSessionName ||= titleNode.textContent;
          titleNode.textContent = bundleShipment ? `Bundle ${bundleNumber}` : modal.dataset.towerSessionName;
        }
        loading.textContent = bundleShipment ? 'Loading bundle details…' : 'Loading session details…';
        if (bundleShipment) frame.title = `Bundle ${bundleNumber} — bundle details`;
        else if (modal.dataset.towerSessionName) frame.title = `${modal.dataset.towerSessionName} — session details`;
        frame.onload = () => displayLoadedFrame(modal, frame);
        frame.src = url.href;
      };
      retry.onclick = load;
      load();
    };
    const refreshModalSafely = modal => {
      if (modal.dataset.refreshPending) return;
      const previous = modal.querySelector('[data-tower-frame]');
      if (!previous || previous.hidden) return;
      modal.dataset.refreshPending = '1';
      const candidate = document.createElement('iframe');
      candidate.hidden = true;
      candidate.title = previous.title;
      let finished = false;
      const finish = () => { finished = true; delete modal.dataset.refreshPending; };
      const keepCurrent = () => {
        if (finished) return;
        finish(); candidate.remove();
        previous.contentWindow.postMessage({type: 'tower-refresh-failed'}, window.location.origin);
      };
      candidate.onload = () => {
        if (finished) return;
        try {
          if (!candidate.contentDocument?.body.matches('[data-tower-modal-document]') || !candidate.contentDocument.querySelector('.modal.is-open')) {
            keepCurrent(); return;
          }
          const editing = previous.contentWindow.towerHasUnsavedChanges?.()
            || previous.contentDocument.activeElement?.matches('input, textarea, select, [contenteditable="true"]');
          if (editing || !modal.classList.contains('is-open')) {
            finish(); candidate.remove();
            if (editing) previous.contentWindow.postMessage({type: 'tower-refresh-deferred'}, window.location.origin);
            return;
          }
          const scroll = previous.contentWindow.scrollY;
          candidate.setAttribute('data-tower-frame', '');
          previous.replaceWith(candidate);
          candidate.hidden = false;
          candidate.onload = () => displayLoadedFrame(modal, candidate);
          modal.querySelector('[data-tower-retry]').onclick = () => window.loadTowerModal(modal);
          finish();
          candidate.contentWindow.scrollTo(0, scroll);
          refreshSummary();
        } catch (_) { keepCurrent(); }
      };
      candidate.onerror = keepCurrent;
      previous.parentElement.append(candidate);
      candidate.src = previous.contentWindow.location.href;
      window.setTimeout(() => { if (!finished) keepCurrent(); }, 20000);
    };
    window.addEventListener('message', event => {
      if (event.origin !== window.location.origin) return;
      const modal = [...document.querySelectorAll('[data-tower-session]')].find(item => item.querySelector('iframe')?.contentWindow === event.source);
      if (modal && event.data?.type === 'tower-session-refresh-request') { refreshModalSafely(modal); return; }
      if (!modal || !['tower-session-close', 'tower-session-saved', 'tower-session-refreshed'].includes(event.data?.type)) return;
      if (event.data.type === 'tower-session-close') modal.querySelector('[data-close-modal]')?.click();
      else refreshSummary();
    });
    return;
  }

  const body = document.body;
  let revision = body.dataset.revision;
  let stale = false;
  let checking = false;
  let writes = 0;
  let lastForm = null;
  let writeQueue = Promise.resolve();
  let needsRefresh = false;
  const dirtyForms = new Set();
  const userEdits = new WeakMap();
  let editSequence = 0;
  const notice = document.querySelector('[data-tower-update-notice]');
  const message = notice.querySelector('[data-tower-update-message]');
  const reloadButton = notice.querySelector('[data-tower-reload]');
  const active = () => !document.hidden && window.frameElement?.closest('.modal')?.classList.contains('is-open');
  const dirty = () => [...dirtyForms].some(form => form.isConnected) || Boolean(document.querySelector('.nested-modal.is-open, dialog[open]'));
  window.towerHasUnsavedChanges = dirty;
  const reload = (explicit = false) => {
    try { sessionStorage.setItem(`tower-modal-scroll:${body.dataset.sessionId}`, String(window.scrollY)); } catch (_) {}
    needsRefresh = false;
    if (explicit || body.hasAttribute('data-tower-staff-card')) window.location.reload();
    else notifyParent('tower-session-refresh-request');
  };
  window.addEventListener('load', () => {
    try {
      const key = `tower-modal-scroll:${body.dataset.sessionId}`;
      const position = sessionStorage.getItem(key); sessionStorage.removeItem(key);
      if (position !== null) setTimeout(() => window.scrollTo(0, Number(position)), 150);
    } catch (_) {}
  });
  const refreshIfClean = () => {
    if (needsRefresh && active() && !writes && !dirty() && !document.activeElement?.matches('input, textarea, select, [contenteditable="true"]')) reload();
  };
  document.addEventListener('focusout', () => setTimeout(refreshIfClean, 250));

  window.addEventListener('message', event => {
    if (event.origin !== window.location.origin || event.source !== window.parent) return;
    if (event.data?.type === 'tower-refresh-failed') {
      notice.hidden = false; reloadButton.hidden = false;
      message.textContent = 'The session could not be refreshed. Your current view and changes have been kept. You can retry or reload when ready.';
    } else if (event.data?.type === 'tower-refresh-deferred') {
      conflict();
    }
  });

  const conflict = () => {
    stale = true; notice.hidden = false; reloadButton.hidden = false;
    message.textContent = 'This session was updated by another user.';
  };
  const stamp = form => {
    if (form.method.toLowerCase() !== 'post' || new URL(form.action, window.location.href).origin !== window.location.origin) return;
    for (const [name, value] of [['tower_revision', revision], ['tower_revision_session_id', body.dataset.sessionId]]) {
      let input = form.querySelector(`[name="${name}"]`);
      if (!input) { input = document.createElement('input'); input.type = 'hidden'; input.name = name; form.append(input); }
      input.value = value;
    }
  };
  const stampAll = () => document.querySelectorAll('form').forEach(stamp);
  stampAll();
  new MutationObserver(records => {
    for (const record of records) for (const node of record.addedNodes) {
      if (!(node instanceof Element)) continue;
      if (node.matches('form')) stamp(node);
      node.querySelectorAll('form').forEach(stamp);
    }
  }).observe(document.body, {childList: true, subtree: true});
  for (const type of ['input', 'change']) document.addEventListener(type, event => {
    const form = event.target.closest('form');
    if (event.isTrusted) userEdits.set(event.target, ++editSequence);
    if (form) { dirtyForms.add(form); lastForm = form; }
  }, true);

  const check = async () => {
    if (checking || writes || !active() || document.querySelector('[data-staffing-card-frame]')?.closest('.modal')?.classList.contains('is-open')) return;
    checking = true;
    try {
      const response = await nativeFetch(body.dataset.revisionUrl, {cache: 'no-store', headers: {Accept: 'application/json'}});
      if (!response.ok || response.redirected) throw new Error('Refresh failed');
      const result = await response.json();
      if (result.revision !== revision) {
        if (dirty() || document.activeElement?.matches('input, textarea, select, [contenteditable="true"]')) conflict();
        else reload();
      } else if (!stale) notice.hidden = true;
    } catch (_) {
      if (!stale) {
        notice.hidden = false; reloadButton.hidden = true;
        message.textContent = 'Unable to check for updates. Your changes have been kept. Retrying shortly.';
      }
    } finally { checking = false; }
  };
  window.setInterval(check, 25000);
  window.addEventListener('focus', check);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) check(); });
  reloadButton.addEventListener('click', () => {
    if (dirty() && !window.confirm('Reload this session? Unsaved changes will be lost.')) return;
    reload(true);
  });
  document.addEventListener('click', event => {
    const closer = event.target.closest('[data-close-modal]');
    if (closer?.closest('.modal')?.id !== `schedule-workflow-${body.dataset.sessionId}`) return;
    event.preventDefault(); event.stopImmediatePropagation(); notifyParent('tower-session-close');
  }, true);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !body.hasAttribute('data-tower-staff-card') && !document.querySelector('.nested-modal.is-open, dialog[open]')) {
      event.preventDefault(); event.stopImmediatePropagation(); notifyParent('tower-session-close');
    }
  }, true);

  const staffFrame = document.querySelector('[data-staffing-card-frame]');
  staffFrame?.addEventListener('load', () => {
    const doc = staffFrame.contentDocument;
    if (!doc?.querySelector('[data-embedded-staff-card]') || doc.body.hasAttribute('data-tower-modal-document')) return;
    doc.body.dataset.towerModalDocument = '';
    doc.body.dataset.towerStaffCard = '';
    doc.body.dataset.sessionId = body.dataset.sessionId;
    doc.body.dataset.revision = revision;
    doc.body.dataset.revisionUrl = body.dataset.revisionUrl;
    doc.body.prepend(notice.cloneNode(true));
    const style = doc.createElement('link'); style.rel = 'stylesheet';
    style.href = new URL('../css/tower_live.css', controllerURL).href; doc.head.append(style);
    const script = doc.createElement('script'); script.src = controllerURL; doc.body.append(script);
  });
  window.addEventListener('message', event => {
    if (event.origin !== window.location.origin || event.source !== staffFrame?.contentWindow) return;
    if (event.data?.type === 'tower-session-saved') {
      revision = event.data.revision; body.dataset.revision = revision; stampAll();
      needsRefresh = true; notifyParent('tower-session-saved');
    } else if (event.data?.type === 'tower-session-close') {
      staffFrame.closest('.modal').querySelector('[data-close-modal]')?.click();
    }
  });

  // Both AJAX and regular forms carry the exact snapshot that the user edited.
  // The server rejects stale writes before the existing action handler runs.
  const approved = new WeakSet();
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (form.method.toLowerCase() !== 'post' || new URL(form.action, window.location.href).origin !== window.location.origin) return;
    lastForm = form;
    if (approved.has(form)) { approved.delete(form); stamp(form); return; }
    event.preventDefault(); event.stopImmediatePropagation();
    if (stale) { conflict(); return; }
    try {
      await writeQueue;
      if (stale) { conflict(); return; }
      const response = await nativeFetch(body.dataset.revisionUrl, {cache: 'no-store'});
      if (!response.ok || response.redirected) throw new Error('Check failed');
      if ((await response.json()).revision !== revision) { conflict(); return; }
      approved.add(form); form.requestSubmit(event.submitter || undefined);
    } catch (_) {
      notice.hidden = false; reloadButton.hidden = true;
      message.textContent = 'Unable to verify the latest session information. Please try saving again.';
    }
  }, true);
  const preserveRejectedDraft = (form, response) => {
    const fields = Array.from(form?.elements || []).filter(field => field.type !== 'hidden').map(field => ({
      field, value: field.value, checked: field.checked,
      selected: field.options ? Array.from(field.options, option => option.selected) : null,
      edit: userEdits.get(field)
    }));
    const restore = () => fields.forEach(saved => {
      // Existing handlers sometimes roll back a failed autosave. Keep the draft,
      // but never replace a newer keystroke entered while the save was pending.
      if (!saved.field.isConnected || userEdits.get(saved.field) !== saved.edit) return;
      if (saved.selected) Array.from(saved.field.options).forEach((option, index) => { option.selected = saved.selected[index]; });
      else if (saved.field.type !== 'file') saved.field.value = saved.value;
      if (saved.checked !== undefined) saved.field.checked = saved.checked;
    });
    for (const method of ['json', 'text']) {
      const read = response[method].bind(response);
      response[method] = async () => {
        const result = await read();
        setTimeout(restore, 0);
        return result;
      };
    }
    return response;
  };

  window.fetch = (input, options = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, window.location.href);
    const method = String(options.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (method !== 'POST' || url.origin !== window.location.origin) return nativeFetch(input, options);
    const form = lastForm?.action === url.href ? lastForm : [...document.forms].find(item => item.action === url.href);
    const save = async () => {
      if (stale) {
        conflict();
        return preserveRejectedDraft(form, new Response(JSON.stringify({ok: false, saved: false, code: 'stale_session', error: 'This session was updated by another user.'}), {status: 409, headers: {'Content-Type': 'application/json'}}));
      }
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : {}));
      headers.set('X-Tower-Revision', revision); headers.set('X-Tower-Session', body.dataset.sessionId);
      const response = await nativeFetch(input, {...options, headers});
      if (response.status === 409) {
        const result = await response.clone().json().catch(() => ({}));
        if (result.code === 'stale_session') { conflict(); preserveRejectedDraft(form, response); }
      }
      const next = response.headers.get('X-Tower-Revision');
      if (response.ok && next) {
        const result = response.headers.get('Content-Type')?.includes('application/json') ? await response.clone().json() : {};
        if (result.ok !== false && result.saved !== false && !result.confirmation_required) {
          revision = next; body.dataset.revision = next; stampAll();
          if (form) dirtyForms.delete(form);
          notifyParent('tower-session-saved');
          if (headers.get('X-Finance-Autosave') !== '1') {
            needsRefresh = true;
            setTimeout(refreshIfClean, 1200);
          }
        }
      }
      return response;
    };
    // Serializing this document's writes avoids mistaking our own autosaves for
    // another user's update, while each write still checks the server snapshot.
    writes++;
    const pending = writeQueue.then(save);
    writeQueue = pending.catch(() => {});
    return pending.finally(() => { writes--; });
  };
})();
