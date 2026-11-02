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
      const feedback = button.parentElement.querySelector('.marketing-copy-feedback');
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
