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
      const row=document.createElement('div');row.dataset.logisticsLink='';
      const name=document.createElement('input');name.dataset.linkName='';name.placeholder='Link name';name.required=true;name.maxLength=200;name.setAttribute('aria-label','Link name');
      const url=document.createElement('input');url.dataset.linkUrl='';url.type='url';url.placeholder='https://…';url.required=true;url.setAttribute('aria-label','Link URL');
      const remove=document.createElement('button');remove.type='button';remove.dataset.removeLogisticsLink='';remove.textContent='×';remove.setAttribute('aria-label','Remove link');
      row.append(name,url,remove);add.closest('form').querySelector('[data-logistics-links]').append(row);name.focus();return;
    }
    const remove=event.target.closest('[data-remove-logistics-link]');if(remove){remove.closest('[data-logistics-link]').remove();return;}
    const close=event.target.closest('[data-close-logistics-payment]');if(close){close.closest('dialog').close();return;}
    const link=event.target.closest('[data-logistics-payment-url]');if(!link)return;
    event.preventDefault();
    const section=link.closest('.logistics-control-section');
    const dialog=section.querySelector('[data-logistics-payment-dialog]');
    const content=dialog.querySelector('[data-logistics-payment-content]');content.textContent='Loading payment request…';dialog.showModal();
    try{const response=await fetch(link.dataset.logisticsPaymentUrl,{cache:'no-store'});if(!response.ok||response.redirected)throw new Error('Payment request could not be loaded.');content.innerHTML=await response.text();}catch(error){content.textContent=error.message;}
  });
  document.addEventListener('submit',async event=>{
    const form=event.target.closest('[data-logistics-card-form]');if(!form)return;event.preventDefault();
    const output=form.querySelector('[data-logistics-save-status]');
    if(!form.querySelector('[name=session_ids]:checked')){output.textContent='Choose at least one applicable session.';return;}
    const data=new FormData(form);
    const editor=form.querySelector('[data-logistics-instructions-editor]');
    if(editor) data.set('instructions_html',editor.innerHTML);
    data.set('links',JSON.stringify(Array.from(form.querySelectorAll('[data-logistics-link]')).map(row=>({name:row.querySelector('[data-link-name]').value,url:row.querySelector('[data-link-url]').value}))));
    const submit=form.querySelector('[type=submit]');submit.disabled=true;output.textContent='Saving…';
    try{const response=await fetch(form.action,{method:'POST',body:data,headers:{Accept:'application/json'}});if(!response.ok||response.redirected)throw new Error('Changes could not be saved. Check the fields and reload if the session team changed.');const result=await response.json();if(!result.ok)throw new Error('Changes could not be saved.');const next=new URL(window.location.href);next.searchParams.set('open_schedule_modal',form.dataset.sessionId);next.searchParams.set('open_modal_target','logistics');next.searchParams.set('logistics_only','1');window.location.assign(next);}catch(error){output.textContent=error.message;submit.disabled=false;}
  });
})();
