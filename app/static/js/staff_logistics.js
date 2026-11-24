(() => {
  const textRanges = new WeakMap();
  const syncInstructions = editor => {
    const hidden = editor.closest('form').querySelector('[name="instructions_html"]');
    hidden.value = editor.innerHTML;
    hidden.dispatchEvent(new Event('input', {bubbles:true}));
  };
  document.addEventListener('selectionchange', () => {
    const selection = window.getSelection();
    if (!selection?.rangeCount) return;
    const range = selection.getRangeAt(0);
    const node = range.commonAncestorContainer;
    const editor = (node.nodeType === 1 ? node : node.parentElement)?.closest('[data-logistics-instructions-editor]');
    if (editor) textRanges.set(editor, range.cloneRange());
  });
  document.addEventListener('input', event => {
    const editor = event.target.closest('[data-logistics-instructions-editor]');
    if (editor) syncInstructions(editor);
  });
  document.addEventListener('mousedown', event => {
    if (event.target.closest('[data-logistics-text-command], [data-logistics-text-link]')) event.preventDefault();
  });
  document.addEventListener('click', async event => {
    const textAction = event.target.closest('[data-logistics-text-command], [data-logistics-text-link], [data-logistics-rich-link-apply], [data-logistics-rich-link-cancel]');
    if (textAction) {
      const wrapper = textAction.closest('[data-logistics-rich-text]');
      const editor = wrapper.querySelector('[data-logistics-instructions-editor]');
      if (editor.getAttribute('contenteditable') !== 'true') return;
      const panel = wrapper.querySelector('[data-logistics-rich-link-panel]');
      const error = wrapper.querySelector('[data-logistics-rich-link-error]');
      const input = wrapper.querySelector('[data-logistics-rich-link-url]');
      const restore = () => {
        editor.focus();
        const range = textRanges.get(editor);
        if (range) { const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); }
      };
      if (textAction.hasAttribute('data-logistics-text-link')) {
        panel.hidden = false; error.textContent = ''; input.value = ''; input.focus(); return;
      }
      if (textAction.hasAttribute('data-logistics-rich-link-cancel')) { panel.hidden = true; restore(); return; }
      if (textAction.hasAttribute('data-logistics-rich-link-apply')) {
        const range = textRanges.get(editor);
        if (!range || range.collapsed) { error.textContent = 'Select the text to link first.'; return; }
        let url;
        try { url = new URL(input.value.trim()); } catch { error.textContent = 'Enter a valid link.'; return; }
        if (!['http:', 'https:', 'mailto:'].includes(url.protocol)) { error.textContent = 'Use an http, https or email link.'; return; }
        restore(); document.execCommand('createLink', false, url.href); panel.hidden = true;
      } else {
        restore(); document.execCommand(textAction.dataset.logisticsTextCommand, false, null);
      }
      syncInstructions(editor); return;
    }
    const add=event.target.closest('[data-add-logistics-link]');
    if(add){
      const form = add.closest('form');
      if (!editable(form)) return;
      stateFor(form);
      const row = createLinkRow();
      form.querySelector('[data-logistics-links]').append(row);
      row.querySelector('[data-link-name]').focus(); changed(form); return;
    }
    const remove = event.target.closest('[data-remove-logistics-link]');
    if (remove) {
      const form = remove.closest('form');
      if (!editable(form)) return;
      stateFor(form); remove.closest('[data-logistics-link]').remove(); changed(form); return;
    }
    const close=event.target.closest('[data-close-logistics-payment]');if(close){close.closest('dialog').close();return;}
    const link=event.target.closest('[data-logistics-payment-url]');if(!link)return;
    event.preventDefault();
    const section=link.closest('.logistics-control-section');
    const dialog=section.querySelector('[data-logistics-payment-dialog]');
    const content=dialog.querySelector('[data-logistics-payment-content]');content.textContent='Loading payment request…';dialog.showModal();
    try{const response=await fetch(link.dataset.logisticsPaymentUrl,{cache:'no-store'});if(!response.ok||response.redirected)throw new Error('Payment request could not be loaded.');content.innerHTML=await response.text();}catch(error){content.textContent=error.message;}
  });
  document.addEventListener('change', event => {
    const picker = event.target.closest('[data-logistics-session-picker]');
    if (picker) picker.querySelector('[data-logistics-session-count]').textContent = `${picker.querySelectorAll('[name=session_ids]:checked').length} selected`;
  });
  function chooseCard(result) {
    return new Promise(resolve => {
      const make = (tag, text, className) => {
        const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;
      };
      const dialog=make('dialog',undefined,'staff-logistics-conflict-dialog');
      dialog.setAttribute('aria-label','Choose the Logistics card to keep');
      const title=make('h2','Choose the card to keep');
      const intro=make('p','These sessions already have separate Logistics cards. Keep one card to share its instructions, links and payment requests. The shared card will return to Pending.');
      const warning=make('p','Pending payment requests on discarded cards will be cancelled. Completed payments will be retained with an alert.','staffing-schedule-notice');
      const sessions=make('p','Applies to: '+result.sessions.join(' · '),'staff-logistics-conflict-sessions');
      const options=make('div',undefined,'staff-logistics-conflict-options');
      const footer=make('div',undefined,'staff-session-report-actions');
      const cancel=make('button','Cancel','secondary-button');cancel.type='button';
      const confirm=make('button','Keep selected card','primary-button');confirm.type='button';confirm.disabled=true;
      let chosen=null;
      result.cards.forEach(card=>{
        const label=make('label');const radio=make('input');radio.type='radio';radio.name='logistics_keep_card';radio.value=String(card.id);
        const detail=make('div');detail.append(make('strong',card.name+' · Card #'+card.id+(card.current?' · Current card':'')),make('p',card.sessions.join(' · ')),make('small',card.status+' · '+card.link_count+' link(s)'));
        detail.append(make('p',card.description||'No instructions added.','staff-logistics-conflict-preview'));
        radio.addEventListener('change',()=>{chosen=card.id;confirm.disabled=false;});
        label.append(radio,detail);options.append(label);
      });
      footer.append(cancel,confirm);dialog.append(title,intro,warning,sessions,options,footer);document.body.append(dialog);
      const dismiss=()=>{dialog.close();};
      cancel.addEventListener('click',dismiss);
      confirm.addEventListener('click',()=>{if(chosen!==null){dialog.returnValue=String(chosen);dialog.close();}});
      dialog.addEventListener('close',()=>{const value=dialog.returnValue;dialog.remove();resolve(value&&chosen!==null?chosen:null);},{once:true});
      dialog.showModal();
    });
  }
  const states = new Map();
  let saveQueue = Promise.resolve();
  const linkValues = form => Array.from(form.querySelectorAll('[data-logistics-link]')).map(row => ({
    name: row.querySelector('[data-link-name]').value,
    url: row.querySelector('[data-link-url]').value
  }));
  const snapshot = form => ({
    instructions: form.querySelector('[data-logistics-instructions-editor]')?.innerHTML || '',
    links: linkValues(form),
    sessions: Array.from(form.querySelectorAll('[name=session_ids]:checked'), input => input.value),
    status: form.querySelector('[name=status]').value
  });
  const key = form => JSON.stringify(snapshot(form));
  const stateFor = form => {
    if (!states.has(form)) states.set(form, {saved: key(form), queued: false, saving: false, timer: null});
    return states.get(form);
  };
  const editable = form => !form.querySelector('.staff-logistics-editor')?.disabled;
  const feedback = (form, text, type = 'pending') => {
    form.querySelector('[data-logistics-save-status]').textContent = text;
    form.dataset.autosaveState = type;
    form.querySelector('[data-logistics-retry]').hidden = type !== 'error';
  };
  const hasPending = form => {
    const state = stateFor(form);
    return state.queued || state.saving || state.saved !== key(form);
  };
  window.logisticsHasUnsavedChanges = (root = document) =>
    Array.from(root.querySelectorAll('[data-logistics-card-form]')).some(form => editable(form) && hasPending(form));
  document.querySelectorAll('[data-logistics-card-form]').forEach(stateFor);
  document.addEventListener('focusin', event => {
    const form = event.target.closest('[data-logistics-card-form]');
    if (form) stateFor(form);
  });
  const queueSave = form => {
    const state = stateFor(form);
    window.clearTimeout(state.timer); state.timer = null;
    if (state.queued || state.saving || !editable(form)) return;
    state.queued = true;
    saveQueue = saveQueue.then(async () => {
      state.queued = false;
      if (!form.isConnected || !hasPending(form)) return;
      await saveCard(form);
    }).catch(error => feedback(form, error.message || 'Changes could not be saved. Retry.', 'error'));
  };
  const changed = (form, delay = 650) => {
    if (!form || !editable(form)) return;
    const state = stateFor(form);
    window.clearTimeout(state.timer);
    if (state.saved === key(form) && !state.saving && !state.queued) {
      feedback(form, 'Saved', 'saved'); return;
    }
    feedback(form, 'Unsaved changes…');
    state.timer = window.setTimeout(() => queueSave(form), delay);
  };
  function createLinkRow(link = {name: '', url: ''}) {
    const row = document.createElement('div'); row.dataset.logisticsLink = '';
    const handle = document.createElement('button'); handle.type = 'button';
    handle.className = 'staff-logistics-drag-handle'; handle.dataset.logisticsDragHandle = '';
    handle.textContent = '⠿'; handle.setAttribute('aria-label', 'Reorder link');
    handle.title = 'Drag to reorder; use arrow keys to move';
    const name = document.createElement('input'); name.dataset.linkName = ''; name.placeholder = 'Link name';
    name.required = true; name.maxLength = 200; name.value = link.name; name.setAttribute('aria-label', 'Link name');
    const url = document.createElement('input'); url.dataset.linkUrl = ''; url.type = 'url'; url.placeholder = 'https://…';
    url.required = true; url.maxLength = 2000; url.value = link.url; url.setAttribute('aria-label', 'Link URL');
    const open = document.createElement('a'); open.textContent = 'Open ↗'; open.target = '_blank'; open.rel = 'noopener noreferrer';
    if (/^https?:\/\//i.test(link.url)) open.href = link.url;
    else open.hidden = true;
    const remove = document.createElement('button'); remove.type = 'button'; remove.dataset.removeLogisticsLink = '';
    remove.textContent = '×'; remove.setAttribute('aria-label', 'Remove link');
    row.append(handle, name, url, open, remove);
    return row;
  }
  function updateCardStatus(form, status) {
    const article = form.closest('.staff-logistics-card');
    const tone = status.toLowerCase().replaceAll(' ', '-');
    article.dataset.logisticsState = tone;
    const chip = article.querySelector('.staff-logistics-state');
    chip.className = 'staff-logistics-chip staff-logistics-state is-' + tone;
    chip.textContent = (status === 'Completed' ? '✓ ' : status === 'In process' ? '◷ ' : '○ ') + status;
  }
  async function saveCard(form) {
    const state = stateFor(form);
    const draft = snapshot(form);
    const sent = JSON.stringify(draft);
    if (!draft.sessions.length) { feedback(form, 'Choose at least one applicable session. Changes not saved.', 'error'); return; }
    if (draft.links.some(link => {
      try { return !link.name.trim() || !['http:', 'https:'].includes(new URL(link.url).protocol); }
      catch (_) { return true; }
    }) || !form.checkValidity()) {
      feedback(form, 'Complete each link with a name and a valid http(s) URL. Changes not saved.', 'error'); return;
    }
    state.saving = true;
    feedback(form, 'Saving…');
    const data = new FormData(form);
    data.set('instructions_html', draft.instructions);
    data.set('links', JSON.stringify(draft.links));
    let saved = false;
    try {
      let response, result;
      while (true) {
        response = await fetch(form.action, {method: 'POST', body: data, headers: {Accept: 'application/json', 'X-Logistics-Autosave': '1'}});
        result = await response.json().catch(() => ({}));
        if (response.status !== 409 || result.code !== 'logistics_card_conflict') break;
        const otherDraft = Array.from(states).some(([other]) => other !== form && other.isConnected
          && result.cards.some(card => String(card.id) === other.dataset.cardId) && hasPending(other));
        if (otherDraft) throw new Error('Another linked card still has unsaved changes. Let it finish saving, then retry combining these sessions.');
        const keep = await chooseCard(result);
        if (keep === null) throw new Error('Changes not saved. Session sharing needs your confirmation.');
        data.set('keep_card_id', String(keep)); data.set('conflict_token', result.conflict_token);
      }
      if (!response.ok || response.redirected || !result.ok) throw new Error(result.error || 'Changes could not be saved. Check your connection and retry.');
      const unchanged = key(form) === sent;
      const retainedOther = result.card_id && String(result.card_id) !== form.dataset.cardId;
      if (retainedOther) {
        form.action = form.action.replace(/\/cards\/\d+$/, '/cards/' + result.card_id);
        form.dataset.cardId = String(result.card_id);
        form.closest('.staff-logistics-card').querySelectorAll('[data-payment-request-logistics-card-id]').forEach(button => {
          button.dataset.paymentRequestLogisticsCardId = String(result.card_id);
        });
        // Keep edits made during a request as an unsaved draft, never silently discard them.
        if (!unchanged) throw new Error('Cards combined. Your latest edits are still here; review them and retry to save them to the retained card.');
        const editor = form.querySelector('[data-logistics-instructions-editor]');
        editor.innerHTML = result.card.instructions_html || '';
        if (!result.card.instructions_html) editor.textContent = result.card.description || '';
        form.querySelector('[data-logistics-links]').replaceChildren(...result.card.links.map(createLinkRow));
      }
      if (unchanged && result.card) {
        form.querySelectorAll('[name=session_ids]').forEach(input => { input.checked = result.card.session_ids.includes(Number(input.value)); });
        form.querySelector('[name=status]').value = result.status;
      } else if (result.scope_changed && form.querySelector('[name=status]').value === draft.status) {
        // A sharing change requires confirmation again, even if instructions were edited in flight.
        form.querySelector('[name=status]').value = result.status;
      }
      updateCardStatus(form, result.status || draft.status);
      if (result.payment_html !== null && result.payment_html !== undefined) {
        const article = form.closest('.staff-logistics-card');
        article.querySelector('[data-logistics-payments-list]').innerHTML = result.payment_html;
        article.querySelector('[data-logistics-payment-count]').textContent = String(result.payment_count);
      }
      state.saved = unchanged ? key(form) : sent;
      saved = true;
      // Remove only obsolete, clean copies; never replace unrelated drafts or reload the modal.
      document.querySelectorAll('[data-logistics-card-form]').forEach(other => {
        if (other === form || hasPending(other)) return;
        if ((result.retired_card_ids || []).map(String).includes(other.dataset.cardId)
            || (retainedOther && other.dataset.cardId === form.dataset.cardId)) {
          other.closest('.staff-logistics-card').remove(); states.delete(other);
        }
      });
      feedback(form, state.saved === key(form) ? 'Saved' : 'Unsaved changes…', state.saved === key(form) ? 'saved' : 'pending');
      if (unchanged && result.card && !result.card.session_ids.includes(Number(form.dataset.sessionId))) {
        form.closest('.staff-logistics-card').remove(); states.delete(form);
      }
    } catch (error) {
      feedback(form, error.message || 'Changes could not be saved. Retry.', 'error');
    } finally {
      state.saving = false;
      if (saved && state.saved !== key(form)) queueSave(form);
    }
  }
  document.addEventListener('input', event => {
    const form = event.target.closest('[data-logistics-card-form]');
    if (!form || event.isComposing || event.target.closest('[data-logistics-rich-link-panel]')) return;
    const row = event.target.closest('[data-logistics-link]');
    if (row) {
      const open = row.querySelector('a');
      const url = row.querySelector('[data-link-url]').value;
      open.hidden = !/^https?:\/\//i.test(url);
      if (!open.hidden) open.href = url;
      else open.removeAttribute('href');
    }
    changed(form);
  });
  document.addEventListener('compositionend', event => changed(event.target.closest('[data-logistics-card-form]')));
  document.addEventListener('change', event => {
    if (!event.target.closest('[data-logistics-rich-link-panel]')) changed(event.target.closest('[data-logistics-card-form]'), 100);
  });
  document.addEventListener('click', event => {
    const retry = event.target.closest('[data-logistics-retry]');
    if (retry) queueSave(retry.closest('form'));
  });
  document.addEventListener('submit', event => {
    const form = event.target.closest('[data-logistics-card-form]');
    if (!form) return;
    event.preventDefault(); queueSave(form);
  });
  window.addEventListener('beforeunload', event => {
    if (!window.logisticsHasUnsavedChanges()) return;
    event.preventDefault(); event.returnValue = '';
  });
  let drag = null;
  document.addEventListener('pointerdown', event => {
    const handle = event.target.closest('[data-logistics-drag-handle]');
    if (!handle || handle.disabled || event.button !== 0 || !editable(handle.closest('form'))) return;
    const row = handle.closest('[data-logistics-link]');
    drag = {row, handle, form: handle.closest('form'), list: row.parentElement, startY: event.clientY, moved: false};
    handle.setPointerCapture(event.pointerId); event.preventDefault();
  });
  document.addEventListener('pointermove', event => {
    if (!drag || Math.abs(event.clientY - drag.startY) < 4 && !drag.moved) return;
    drag.moved = true; drag.row.classList.add('is-dragging');
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-logistics-link]');
    if (!target || target === drag.row || target.parentElement !== drag.list) return;
    const bounds = target.getBoundingClientRect();
    drag.list.insertBefore(drag.row, event.clientY < bounds.top + bounds.height / 2 ? target : target.nextSibling);
  });
  const endDrag = () => {
    if (!drag) return;
    const current = drag; drag = null; current.row.classList.remove('is-dragging');
    if (current.moved) { current.handle.focus(); changed(current.form, 100); }
  };
  document.addEventListener('pointerup', endDrag);
  document.addEventListener('pointercancel', endDrag);
  document.addEventListener('keydown', event => {
    const handle = event.target.closest('[data-logistics-drag-handle]');
    if (!handle || !['ArrowUp', 'ArrowDown'].includes(event.key) || !editable(handle.closest('form'))) return;
    const row = handle.closest('[data-logistics-link]');
    const sibling = event.key === 'ArrowUp' ? row.previousElementSibling : row.nextElementSibling;
    event.preventDefault();
    if (!sibling) return;
    row.parentElement.insertBefore(row, event.key === 'ArrowUp' ? sibling : sibling.nextSibling);
    handle.focus(); changed(handle.closest('form'), 100);
  });
})();
