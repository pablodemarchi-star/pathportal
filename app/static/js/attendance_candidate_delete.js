/* Candidate deletion is explicit; the password is verified exclusively by the server. */
(() => {
 window.createAttendanceCandidateDelete = ({body,dialog,getState,hasPending,save,getError}) => {
  const form=dialog.querySelector('form'),password=dialog.querySelector('[data-candidate-delete-password]');
  const passwordField=dialog.querySelector('[data-candidate-delete-password-field]'),feedback=dialog.querySelector('[data-candidate-delete-status]');
  const cancel=dialog.querySelector('[data-candidate-delete-cancel]'),submit=dialog.querySelector('[data-candidate-delete-submit]');
  let selected=null,opener=null,busy=false;
  const close=()=>{if(!busy)dialog.close();};
  body.addEventListener('click',event=>{
   const button=event.target.closest('[data-delete-candidate]');
   if(!button||button.disabled||hasPending()||!getState()?.can_edit||dialog.open)return;
   const candidate=getState().candidates.find(item=>item.id===Number(button.dataset.deleteCandidate));
   if(!candidate?.delete_allowed)return;
   selected={id:candidate.id,version:candidate.delete_version};opener=button;
   dialog.querySelector('[data-candidate-delete-name]').textContent=`${candidate.number} · ${candidate.name}`;
   const reviewed=['Confirmed','Declined'].includes(candidate.review_status);
   passwordField.hidden=!reviewed;password.disabled=!reviewed;password.required=reviewed;password.value='';feedback.textContent='';
   dialog.showModal();(reviewed?password:cancel).focus();
  });
  cancel.addEventListener('click',close);
  dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  dialog.addEventListener('click',event=>{
   if(event.target!==dialog||busy)return;
   const bounds=dialog.getBoundingClientRect();
   if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)close();
  });
  dialog.addEventListener('close',()=>{
   password.value='';selected=null;
   if(opener?.isConnected)opener.focus();else body.closest('dialog')?.querySelector('[data-attendance-close]')?.focus();
  });
  form.addEventListener('submit',async event=>{
   event.preventDefault();if(busy||!selected||!form.reportValidity())return;
   const candidate=getState()?.candidates.find(item=>item.id===selected.id);
   if(hasPending()||!getState()?.can_edit||!candidate?.delete_allowed||candidate.delete_version!==selected.version){feedback.textContent='The candidate or Attendance has changed. Close this message, refresh Attendance and review the current details before deleting.';return;}
   busy=true;cancel.disabled=true;submit.disabled=true;feedback.textContent='Deleting candidate…';
   try{
    const saved=await save({action:'delete_candidate',candidate_id:selected.id,confirmed:'1',delete_version:selected.version,password:password.disabled?'':password.value});
    if(saved){busy=false;dialog.close();}
    else{feedback.textContent=getError()||'The candidate could not be deleted. Please retry.';password.value='';if(!password.disabled)password.focus();}
   }finally{busy=false;cancel.disabled=false;submit.disabled=false;}
  });
 };
})();
