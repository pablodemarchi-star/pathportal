(() => {
  const root=document.querySelector('[data-drive-bulk]');
  if(!root)return;
  const checkboxes=Array.from(document.querySelectorAll('[data-drive-bulk-session]'));
  const all=document.querySelector('[data-drive-bulk-all]');
  const start=root.querySelector('[data-drive-bulk-start]');
  const dialog=root.querySelector('[data-drive-bulk-dialog]');
  const status=root.querySelector('[data-drive-bulk-status]');
  const list=root.querySelector('[data-drive-bulk-results]');
  let busy=false,loading;
  const selected=()=>checkboxes.filter(input=>input.checked).map(input=>input.value);
  const sync=()=>{
    const count=selected().length;
    root.querySelector('[data-drive-bulk-count]').textContent=`${count} session${count===1?'':'s'} selected`;
    start.disabled=busy||count===0;
    if(all){all.checked=count>0&&count===checkboxes.length;all.indeterminate=count>0&&count<checkboxes.length;}
  };
  checkboxes.forEach(input=>input.addEventListener('change',sync));
  all?.addEventListener('change',()=>{checkboxes.forEach(input=>input.checked=all.checked);sync();});
  root.querySelector('[data-drive-bulk-clear]').addEventListener('click',()=>{checkboxes.forEach(input=>input.checked=false);sync();});
  root.querySelector('[data-drive-bulk-close]').addEventListener('click',()=>dialog.close());
  const post=async(url,fields)=>{
    const body=new FormData();body.set('csrf_token',root.dataset.csrf);
    Object.entries(fields||{}).forEach(([key,value])=>(Array.isArray(value)?value:[value]).forEach(item=>body.append(key,item)));
    const response=await fetch(url,{method:'POST',body,headers:{Accept:'application/json'},cache:'no-store'});
    if(response.redirected)throw new Error('Please sign in to the portal again.');
    if(!response.headers.get('Content-Type')?.includes('application/json'))throw new Error('The request could not be completed. Reload the planner and try again.');
    const data=await response.json();
    if(!response.ok||!data.ok)throw new Error(data.error||'The request could not be completed.');
    return data;
  };
  const loadPicker=()=>{
    if(window.google?.picker)return Promise.resolve();
    if(loading)return loading;
    loading=new Promise((resolve,reject)=>{
      const script=document.createElement('script');
      const timer=setTimeout(()=>{loading=null;script.remove();reject(new Error('Google Drive could not be loaded. Please retry.'));},20000);
      script.src='https://apis.google.com/js/api.js';
      const failed=()=>{clearTimeout(timer);loading=null;reject(new Error('Google Drive could not be loaded. Please retry.'));};
      script.onload=()=>window.gapi.load('picker',{callback:()=>{clearTimeout(timer);resolve();},onerror:failed});
      script.onerror=failed;document.head.append(script);
    });
    return loading;
  };
  const show=()=>{if(!dialog.open)dialog.showModal();};
  start.addEventListener('click',async()=>{
    const ids=selected();if(!ids.length||busy)return;
    busy=true;sync();list.replaceChildren();status.textContent='Checking configured Session pictures folders…';show();
    const menu=start.closest('details');if(menu)menu.open=false;
    let picker;
    try{
      const plan=await post(root.dataset.prepareUrl,{session_ids:ids});
      const entries=new Map();
      const add=(names,text,kind='pending')=>{
        const item=document.createElement('li');
        const title=document.createElement('strong');title.textContent=names.join(' · ');
        const badge=document.createElement('span');badge.className='drive-bulk-state is-'+kind;badge.textContent=text;
        item.append(title,badge);list.appendChild(item);return badge;
      };
      plan.issues.forEach(issue=>add([issue.session_name],issue.error,'failed'));
      plan.folders.forEach(folder=>entries.set(folder.folder_id,add(folder.session_names,'Awaiting selection')));
      if(!plan.folders.length){status.textContent='No valid Session pictures folders found. Configure their links in the planner first.';busy=false;sync();return;}
      await loadPicker();
      let config=await post(root.dataset.tokenUrl);
      const api=window.google.picker;
      const folders=()=>new api.DocsView(api.ViewId.FOLDERS).setIncludeFolders(true).setSelectFolderEnabled(true);
      const builder=new api.PickerBuilder().setAppId(config.app_id).setDeveloperKey(config.api_key).setOAuthToken(config.access_token)
        .setOrigin(window.location.origin).setTitle('Select the Session pictures folders to authorize')
        .setSelectableMimeTypes('application/vnd.google-apps.folder').enableFeature(api.Feature.MULTISELECT_ENABLED)
        .addView(folders().setFileIds(plan.folders.map(folder=>folder.folder_id).join(','))).addView(folders());
      let handled=false;
      builder.setCallback(async data=>{
        if(handled||![api.Action.PICKED,api.Action.CANCEL].includes(data.action))return;
        handled=true;config=null;picker.dispose();show();
        if(data.action===api.Action.CANCEL){status.textContent='Authorization cancelled. Session folder links were not changed.';busy=false;sync();return;}
        const picked=new Set((data.docs||[]).map(doc=>doc.id));
        const intended=plan.folders.filter(folder=>picked.has(folder.folder_id));
        plan.folders.filter(folder=>!picked.has(folder.folder_id)).forEach(folder=>{const badge=entries.get(folder.folder_id);badge.textContent='Not selected';badge.className='drive-bulk-state is-pending';});
        let authorized=0,failed=0;
        for(const [index,folder] of intended.entries()){
          status.textContent=`Checking Drive access ${index+1}/${intended.length}…`;
          const badge=entries.get(folder.folder_id);
          try{
            const result=await post(root.dataset.verifyUrl,{session_ids:ids,folder_ids:[folder.folder_id]});
            const item=result.results.find(item=>item.folder_id===folder.folder_id);
            if(item?.status==='authorized'){authorized++;badge.textContent='Authorized';badge.className='drive-bulk-state is-authorized';}
            else{failed++;badge.textContent=item?.error||'Could not verify this folder.';badge.className='drive-bulk-state is-failed';}
          }catch(error){failed++;badge.textContent=error.message;badge.className='drive-bulk-state is-failed';}
        }
        const unmatched=Array.from(picked).filter(id=>!entries.has(id)).length;
        status.textContent=`${authorized} folder(s) authorized · ${failed} failed · ${plan.folders.length-intended.length} not selected · ${plan.issues.length} session(s) need a valid folder link.${unmatched?` ${unmatched} unrelated folder(s) ignored.`:''} Session links were not changed.`;
        busy=false;sync();
      });
      picker=builder.build();dialog.close();picker.setVisible(true);
    }catch(error){picker?.dispose();show();status.textContent=error.message;busy=false;sync();}
  });
  sync();
})();
