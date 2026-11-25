(() => {
  'use strict';
  const filters = document.querySelector('.marketing-filters');
  if (filters) {
    const search = filters.querySelector('[name="q"]');
    const format = filters.querySelector('[name="format"]');
    const focusKey = `marketing-search-focus:${window.location.pathname}`;
    let timer;
    let composing = false;
    const apply = () => {
      clearTimeout(timer);
      if (document.activeElement === search) {
        try {
          sessionStorage.setItem(focusKey, JSON.stringify({
            start: search.selectionStart, end: search.selectionEnd
          }));
        } catch (error) { /* Filtering also works without session storage. */ }
      }
      filters.requestSubmit();
    };
    const schedule = () => {
      clearTimeout(timer);
      if (!composing) timer = setTimeout(apply, 450);
    };
    search.addEventListener('input', schedule);
    search.addEventListener('search', apply);
    search.addEventListener('compositionstart', () => { composing = true; clearTimeout(timer); });
    search.addEventListener('compositionend', () => { composing = false; schedule(); });
    format.addEventListener('change', apply);
    filters.querySelector('[data-marketing-sort]').addEventListener('change', event => {
      filters.querySelector('[name="sort"]').value = event.target.value;
      apply();
    });
    filters.querySelector('[data-marketing-sort-direction]').addEventListener('click', () => {
      const direction = filters.querySelector('[name="dir"]');
      direction.value = direction.value === 'asc' ? 'desc' : 'asc';
      apply();
    });
    filters.addEventListener('submit', () => clearTimeout(timer));
    try {
      const saved = sessionStorage.getItem(focusKey);
      sessionStorage.removeItem(focusKey);
      if (saved) {
        const position = JSON.parse(saved);
        search.focus({preventScroll: true});
        search.setSelectionRange(position.start, position.end);
      }
    } catch (error) { /* Restoring the cursor is optional. */ }
  }
  document.querySelectorAll('[data-marketing-open]').forEach(button => {
    button.addEventListener('click', () => {
      const dialog = document.getElementById(button.dataset.marketingOpen);
      dialog.showModal();
      dialog.addEventListener('close', () => button.focus(), {once: true});
    });
  });
  document.querySelectorAll('[data-marketing-close]').forEach(button => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });
  document.querySelectorAll('[data-marketing-copy]').forEach(button => {
    button.addEventListener('click', async () => {
      const source = document.getElementById(button.dataset.marketingCopy).querySelector('[data-marketing-rich-content]');
      const feedback = (button.closest('td, .marketing-dialog-actions') || button.parentElement).querySelector('.marketing-copy-feedback');
      const clone = source.cloneNode(true);
      clone.style.cssText = 'position:fixed;left:-10000px;top:0;white-space:normal';
      document.body.append(clone);
      const plain = clone.innerText;
      clone.remove();
      try {
        let formatted = false;
        if (navigator.clipboard?.write && window.ClipboardItem) {
          try {
            await navigator.clipboard.write([new ClipboardItem({
              'text/html': new Blob([source.innerHTML], {type: 'text/html'}),
              'text/plain': new Blob([plain], {type: 'text/plain'})
            })]);
            formatted = true;
          } catch (error) {
            if (!navigator.clipboard?.writeText) throw error;
          }
        }
        if (!formatted) {
          if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
          await navigator.clipboard.writeText(plain);
        }
        feedback.textContent = formatted ? 'Copied with formatting' : 'Text copied';
      } catch (error) {
        feedback.textContent = 'Unable to copy. Please select and copy the text manually.';
      }
    });
  });
  document.querySelectorAll('[data-marketing-visibility]').forEach(button => {
    if (button.disabled || !button.dataset.visibilityUrl) return;
    button.addEventListener('click', async () => {
      if (button.disabled) return;
      const hidden = button.dataset.hidden === '1';
      const feedback = button.closest('td').querySelector('[data-marketing-visibility-feedback]');
      button.disabled = true; button.setAttribute('aria-busy', 'true');
      feedback.classList.remove('is-error'); feedback.textContent = 'Saving visibility…';
      let conflict = false;
      try {
        const body = new FormData(); body.set('csrf_token', button.dataset.visibilityCsrf);
        body.set('hidden', hidden ? '0' : '1'); body.set('previous_hidden', hidden ? '1' : '0');
        const response = await fetch(button.dataset.visibilityUrl, {method:'POST', body, headers:{Accept:'application/json'}});
        const result = await response.json().catch(() => ({}));
        if (!response.ok || response.redirected || !result.ok || typeof result.hidden !== 'boolean') {
          conflict = response.status === 409;
          throw new Error(result.error || 'Visibility could not be saved. Please retry.');
        }
        button.dataset.hidden = result.hidden ? '1' : '0';
        button.classList.toggle('is-hidden', result.hidden);
        button.setAttribute('aria-pressed', String(result.hidden));
        button.setAttribute('aria-label', result.hidden ? 'Show session on external marketing link' : 'Hide session from external marketing link');
        button.title = result.hidden ? 'Hidden from external marketing link' : 'Visible on external marketing link. Click to hide.';
        feedback.textContent = result.hidden ? 'Hidden from external marketing link.' : 'Visible on external marketing link.';
      } catch (error) {
        feedback.textContent = error.message || 'Visibility could not be saved. Please retry.';
        feedback.classList.add('is-error');
      } finally { button.disabled = conflict; button.removeAttribute('aria-busy'); }
    });
  });
  document.addEventListener('instructions:saved', event => {
    const row = event.target.closest('[data-marketing-row]');
    if (!row) return;
    const dialog = document.getElementById(`marketing-info-${row.dataset.marketingRow}`);
    dialog.querySelector('h2').textContent = event.detail.title || 'Session information';
    dialog.querySelector('[data-marketing-body]').innerHTML = event.detail.html;
    document.querySelectorAll(`[data-marketing-copy="${dialog.id}"]`).forEach(button => {
      button.disabled = !event.detail.html;
    });
    row.querySelector('.marketing-copy-feedback').textContent = '';
  });
})();
