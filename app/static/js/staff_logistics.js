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
  document.addEventListener('submit',async event=>{
    const form=event.target.closest('[data-logistics-card-form]');if(!form)return;event.preventDefault();
    const output=form.querySelector('[data-logistics-save-status]');
    if(!form.querySelector('[name=session_ids]:checked')){output.textContent='Choose at least one applicable session.';return;}
    const data=new FormData(form);
    const editor=form.querySelector('[data-logistics-instructions-editor]');
    if(editor) data.set('instructions_html',editor.innerHTML);
    data.set('links',JSON.stringify(Array.from(form.querySelectorAll('[data-logistics-link]')).map(row=>({name:row.querySelector('[data-link-name]').value,url:row.querySelector('[data-link-url]').value}))));
    const submit=form.querySelector('[type=submit]');submit.disabled=true;output.textContent='Saving…';
    try {
      let response,result;
      while(true) {
        response=await fetch(form.action,{method:'POST',body:data,headers:{Accept:'application/json'}});
        result=await response.json().catch(()=>({}));
        if(response.status!==409||result.code!=='logistics_card_conflict')break;
        const keep=await chooseCard(result);
        if(keep===null){output.textContent='Changes not saved.';submit.disabled=false;return;}
        data.set('keep_card_id',String(keep));data.set('conflict_token',result.conflict_token);
      }
      if(!response.ok||response.redirected||!result.ok)throw new Error(result.error||'Changes could not be saved. Check the fields and reload if the session team changed.');
      const next=new URL(window.location.href);next.searchParams.set('open_schedule_modal',form.dataset.sessionId);next.searchParams.set('open_modal_target','logistics');next.searchParams.set('logistics_only','1');window.location.assign(next);
    }catch(error){output.textContent=error.message;submit.disabled=false;}
  });
})();
