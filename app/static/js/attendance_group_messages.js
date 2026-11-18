/* Read-only message previews; candidate decisions remain in Attendance. */
window.createAttendanceGroupMessages=({dialog,getState,getEndpoint,csrf,copyText,hasPending,report})=>{
 const institution=dialog.querySelector('[data-group-institution]'),status=dialog.querySelector('[data-group-status]');
 const list=dialog.querySelector('[data-group-candidates]'),all=dialog.querySelector('[data-group-all]'),count=dialog.querySelector('[data-group-count]');
 const preview=dialog.querySelector('[data-group-preview]'),feedback=dialog.querySelector('[data-group-feedback]'),copy=dialog.querySelector('[data-group-copy]');
 let candidates=[],generation=0,timer,copying=false;
 const eligible=()=>candidates.filter(candidate=>candidate.institution_key===institution.value&&candidate.review_status===status.value);
 const selected=()=>Array.from(list.querySelectorAll('input:checked')).map(input=>input.value);
 const inform=(message,error=false)=>{feedback.textContent=message;feedback.classList.toggle('is-error',error);};
 const invalidate=()=>{generation++;clearTimeout(timer);copy.disabled=true;preview.value='';};
 async function requestMessage(ids){const data=new FormData();data.set('csrf_token',csrf);ids.forEach(id=>data.append('candidate_ids',id));
  const response=await fetch(getEndpoint(),{method:'POST',body:data,cache:'no-store',headers:{Accept:'application/json'}});
  if(response.redirected||!response.headers.get('Content-Type')?.includes('application/json'))throw new Error('Please sign in again before copying.');
  const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.error||'The message could not be prepared.');return result.message;
 }
 async function refreshPreview(){const ids=selected(),version=generation;if(!ids.length){inform('Select at least one candidate.');return;}
  inform('Preparing message…');try{const message=await requestMessage(ids);if(version!==generation||!dialog.open)return;preview.value=message;copy.disabled=false;inform('Review the message before copying.');}
  catch(error){if(version===generation&&dialog.open)inform(error.message,true);}
 }
 function selectionChanged(){invalidate();const total=eligible().length,n=selected().length;all.checked=Boolean(total&&n===total);all.indeterminate=n>0&&n<total;count.textContent=`${n}/${total} candidates selected`;timer=setTimeout(refreshPreview,180);}
 function renderCandidates(){invalidate();list.replaceChildren();const rows=eligible();rows.forEach(candidate=>{const label=document.createElement('label');label.className='pa-check';const input=document.createElement('input');input.type='checkbox';input.value=String(candidate.id);input.checked=true;input.setAttribute('aria-label','Include '+candidate.number+' - '+candidate.name);const text=document.createElement('span');text.textContent=candidate.number+' - '+candidate.name;label.append(input,text);list.append(label);});all.disabled=!rows.length;selectionChanged();}
 institution.addEventListener('change',renderCandidates);status.addEventListener('change',renderCandidates);list.addEventListener('change',selectionChanged);
 all.addEventListener('change',()=>{list.querySelectorAll('input').forEach(input=>input.checked=all.checked);selectionChanged();});
 dialog.querySelectorAll('[data-group-close]').forEach(button=>button.addEventListener('click',()=>{if(!copying){invalidate();dialog.close();}}));
 dialog.addEventListener('cancel',event=>{if(copying)event.preventDefault();else invalidate();});
 copy.addEventListener('click',async()=>{if(copy.disabled||copying)return;copying=true;copy.disabled=true;const version=generation;const visible=preview.value;
  try{const message=await requestMessage(selected());if(version!==generation||!dialog.open)return;
   if(message!==visible){preview.value=message;inform('Candidate details changed. Review the updated message, then copy again.');return;}
   await copyText(message);inform('WhatsApp message copied.');
  }catch(error){if(version===generation)inform(error.message||'The message could not be copied. Please retry.',true);}
  finally{copying=false;if(version===generation&&dialog.open&&preview.value)copy.disabled=false;}
 });
 return {isOpen:()=>dialog.open,open(){
  if(hasPending()){report('Wait for changes to finish saving before opening the grouped message.',true);return;}
  candidates=getState().candidates.filter(candidate=>candidate.institution_key&&['Confirmed','Declined'].includes(candidate.review_status)&&(candidate.review_status==='Declined'||candidate.whatsapp_message));
  if(!candidates.length){report('No Confirmed or Declined candidates with a completed Institution are available to group.',true);return;}
  institution.replaceChildren();const groups=new Map();candidates.forEach(candidate=>{if(!groups.has(candidate.institution_key))groups.set(candidate.institution_key,candidate.institution_name.trim().replace(/\s+/g,' '));});
  [...groups].sort((a,b)=>a[1].localeCompare(b[1])).forEach(([value,label])=>{const option=document.createElement('option');option.value=value;option.textContent=label;institution.append(option);});
  status.value=candidates.some(candidate=>candidate.institution_key===institution.value&&candidate.review_status==='Confirmed')?'Confirmed':'Declined';
  dialog.showModal();renderCandidates();
 }};
};
