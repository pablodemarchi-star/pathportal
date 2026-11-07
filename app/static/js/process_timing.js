function processDuration(seconds) {
  if (seconds === null || seconds === undefined) return 'Insufficient timing data';
  const hours = Math.floor(Math.max(0, seconds) / 3600);
  if (!hours) return seconds > 0 ? '<1h' : '0h';
  const days = Math.floor(hours / 24), remaining = hours % 24;
  return days ? `${days}d${remaining ? ` ${remaining}h` : ''}` : `${hours}h`;
}
function processMedian(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a,b)=>a-b), middle = Math.floor(sorted.length/2);
  return sorted.length%2 ? sorted[middle] : (sorted[middle-1]+sorted[middle])/2;
}
function processTotals(clock, now=Date.now()) {
  const totals={...clock.totals};
  const key={'Path time':'path','Waiting external':'external','Incident time':'incident'}[clock.category];
  if (key) {const elapsed=Math.max(0,(now-new Date(clock.as_of).getTime())/1000);totals[key]+=elapsed;totals.total+=elapsed;}
  return totals;
}
(() => {
  const root=document.querySelector('.qc-page[data-tab="timing"]');
  if (!root) return;
  const buttons=[...root.querySelectorAll('[data-qc-timing]')];
  const dialog=root.querySelector('#qc-dialog'), content=root.querySelector('#qc-dialog-content'), link=root.querySelector('#qc-open-block');
  const bySession=root.querySelector('#qc-by-session'), byProcess=root.querySelector('#qc-by-process');
  const node=(tag,text)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;};
  const stamp=value=>value?new Intl.DateTimeFormat('en-GB',{timeZone:'America/Argentina/Buenos_Aires',dateStyle:'short',timeStyle:'short'}).format(new Date(value))+' (GMT-3)':'Not recorded';
  const read=button=>JSON.parse(button.dataset.clock || 'null');
  function updateCells() {
    buttons.forEach(button=>{
      const clock=read(button);if(!clock)return;
      if(button.dataset.stale==='1'){button.querySelector('[data-time-total]').textContent='Refresh required';button.title='Process assignment changed. Refresh the page.';['[data-time-breakdown]','[data-time-partial]','[data-time-total-label]'].forEach(selector=>{const element=button.querySelector(selector);if(element)element.hidden=true;});return;}
      const totals=processTotals(clock);
      const applicable=button.dataset.applicable==='1'&&clock.category!=='N/A';
      button.querySelector('[data-time-total]').textContent=applicable?processDuration(totals.total):'N/A';
      const label=button.querySelector('[data-time-total-label]');
      if(label){label.hidden=!applicable;label.textContent=clock.coverage_complete?'Total time':'Recorded time';}
      const partial=button.querySelector('[data-time-partial]');
      if(partial){partial.hidden=!applicable||clock.coverage_complete;partial.title=`Partial measurement recorded since ${stamp(clock.tracked_from)}. Earlier periods are unknown.`;}
      const breakdown=button.querySelector('[data-time-breakdown]');
      if(breakdown){breakdown.hidden=!applicable;['path','external','incident'].forEach(key=>{button.querySelector(`[data-time-${key}]`).textContent=processDuration(totals[key]);});}
      button.title=`Total time: ${processDuration(totals.total)}\nPath time: ${processDuration(totals.path)}\nExternal waiting: ${processDuration(totals.external)}\nIncident time: ${processDuration(totals.incident)}\nStarted: ${stamp(clock.started_at)}\nCompleted: ${stamp(clock.completed_at)}${clock.coverage_complete?'':'\nPartial measurement only; earlier intervals are unknown.'}`;
    });
    renderSummary();
  }
  function renderSummary() {
    const groups=new Map();
    root.querySelectorAll('[data-qc-row]').forEach(row=>{
      if(row.hidden)return;
      row.querySelectorAll('[data-qc-timing]').forEach(button=>{
        const label=button.dataset.label;
        if(!groups.has(label))groups.set(label,{clocks:new Map(),applicable:0});
        if(button.dataset.applicable!=='1')return;
        groups.get(label).applicable++;
        const clock=read(button);
        if(clock&&button.dataset.stale!=='1')groups.get(label).clocks.set(clock.id,clock);
      });
    });
    const body=byProcess.querySelector('tbody');body.replaceChildren();
    groups.forEach(({clocks,applicable},label)=>{
      const cohort=[...clocks.values()].filter(clock=>clock.category==='Completed'&&clock.coverage_complete);
      const tr=node('tr');tr.append(node('th',label));
      ['total','path','external','incident'].forEach(key=>tr.append(node('td',!applicable?'N/A':cohort.length?processDuration(processMedian(cohort.map(clock=>clock.totals[key]))):'Insufficient timing data')));
      tr.append(node('td',`${cohort.length} / ${clocks.size}`));body.append(tr);
    });
  }
  root.addEventListener('quality:filtered',renderSummary);
  root.querySelectorAll('[data-timing-view]').forEach(button=>button.addEventListener('click',()=>{
    const process=button.dataset.timingView==='process';bySession.hidden=process;byProcess.hidden=!process;
    root.querySelectorAll('[data-timing-view]').forEach(tab=>tab.setAttribute('aria-pressed',String(tab===button)));
    const url=new URL(location.href);process?url.searchParams.set('mode','process'):url.searchParams.delete('mode');history.replaceState(null,'',url);
    root.querySelector('.qc-header-actions a').href=url.toString();renderSummary();
  }));
  let generation=0;
  function publish(data) {
    buttons.forEach(button=>{
      const previous=read(button);
      if(previous&&previous.id===data.id){
        const current=data.operational?.[button.dataset.sessionId];
        if(current){delete button.dataset.stale;button.dataset.availability=current.availability;button.dataset.operationalStatus=current.status;button.dataset.applicable=current.applicable?'1':'0';}
        else if(data.operational){button.dataset.stale='1';button.dataset.availability='Refresh required';button.dataset.operationalStatus='Process assignment changed';}
        const summary={...data};delete summary.operational;delete summary.history;delete summary.incidents;delete summary.sessions;delete summary.next_before;delete summary.manual_note;delete summary.manual_reason;delete summary.waiting_reasons;button.dataset.clock=JSON.stringify(summary);button.querySelector('[data-time-state]').textContent=data.category;const progress=button.querySelector('[data-time-progress]');if(progress)progress.textContent=`${button.dataset.availability} · ${button.dataset.operationalStatus}`;
        ['progress','near','issue','blocked','complete','pending'].forEach(state=>button.classList.remove(`qc-${state}`));
        const colour={'Completed':'complete','Blocked':'blocked','Not started':'pending','Path time':'progress','Waiting external':'near','Incident time':'issue','N/A':'na'}[data.category];
        button.classList.add(`qc-${colour}`);
      }
    });updateCells();
  }
  function historyList(data) {
    const list=node('ul');list.className='qc-timing-history';
    data.history.forEach(entry=>{
      const text=`${stamp(entry.started_at)} — ${entry.category}${entry.reason?` · ${entry.reason}`:''}${entry.note?` · ${entry.note}`:''}${entry.ended_at?` → ${stamp(entry.ended_at)}`:' · current'} · ${entry.source} · ${entry.created_by}`;
      list.append(node('li',text));
    });return list;
  }
  function renderDetail(data,button) {
    content.replaceChildren();publish(data);
    content.append(node('p',`Timing category: ${data.category}`));
    content.append(node('p',`Availability: ${button.dataset.availability} · Operational status: ${button.dataset.operationalStatus}`));
    if(data.category==='Not started')content.append(node('p','Unblocked. Timing begins when the first process activity is registered.'));
    if(!data.coverage_complete){const warning=node('p','Partial data. Earlier periods are unknown. The figures below include only the intervals recorded since '+stamp(data.tracked_from)+'.');warning.className='qc-timing-warning';content.append(warning);}
    const definitions=node('dl');[['Started',stamp(data.started_at)],['Completed',stamp(data.completed_at)],['Reopenings',String(data.reopenings)]].forEach(([label,value])=>definitions.append(node('dt',label),node('dd',value)));
    content.append(definitions);
    const split=node('div');split.className='qc-timing-split';const values=processTotals(data);
    [['total','Total time'],['path','Path time'],['external','External waiting'],['incident','Incident time']].forEach(([key,label])=>{
      const item=node('div');item.append(node('span',label),node('strong',processDuration(values[key])));split.append(item);
    });content.append(split);
    if(data.sessions.length>1)content.append(node('p','Shared process: '+data.sessions.map(s=>s.name).join(' · ')+'. Timing actions apply to the shared process.'));
    if(data.incidents.length){content.append(node('h3','Linked incidents'));const list=node('ul');data.incidents.forEach(i=>list.append(node('li',`${i.title} · ${i.status} · Scope: ${i.affected_block==='general'?'General session':i.affected_block}`)));content.append(list);}
    const reasons=data.waiting_reasons || data.history.filter(entry=>entry.category==='Waiting external').map(entry=>entry.reason);
    if(reasons.length){content.append(node('h3','External waiting reasons'));const list=node('ul');[...new Set(reasons)].forEach(reason=>list.append(node('li',reason)));content.append(list);}
    content.append(node('h3','Category history'));const list=historyList(data);content.append(list);
    if(data.next_before){const older=node('button','Load earlier history');older.type='button';older.className='qc-button';let before=data.next_before;older.addEventListener('click',async()=>{
      older.disabled=true;
      try{const response=await fetch(button.dataset.detailUrl+'?before='+before,{credentials:'same-origin',headers:{Accept:'application/json'}});if(!response.ok)throw new Error();const previous=await response.json();const earlier=historyList(previous);list.prepend(...earlier.children);before=previous.next_before;older.hidden=!before;}
      catch(_){older.textContent='Could not load history. Try again.';}finally{older.disabled=false;}
    });content.append(older);}
    if(['Path time','Waiting external','Incident time'].includes(data.category)){
      const actions=node('section');actions.className='qc-manual-actions';actions.append(node('p','These controls classify time only. They do not change the operational block. Automatic external waits and active incidents retain their priority.'));
      const error=node('p');error.className='qc-error';error.setAttribute('role','alert');actions.append(error);
      const controls=node('div');controls.className='qc-timing-actions';const mark=node('button','Mark as waiting external');mark.type='button';mark.className='qc-button';controls.append(mark);
      const form=node('form');form.hidden=true;
      const reasonLabel=node('label','Reason');const select=node('select');select.required=true;select.append(new Option('Select a reason',''));
      ['Institution','Staff member','Provider','Courier','Recipient','Other'].forEach(reason=>select.append(new Option(reason,reason)));reasonLabel.append(select);form.append(reasonLabel);
      const noteLabel=node('label','Note');const note=node('textarea');note.maxLength=1000;note.rows=3;noteLabel.append(note);noteLabel.hidden=true;form.append(noteLabel);
      select.addEventListener('change',()=>{noteLabel.hidden=select.value!=='Other';note.required=select.value==='Other';});
      const save=node('button','Save waiting classification');save.type='submit';save.className='qc-button';form.append(save);
      mark.addEventListener('click',()=>{form.hidden=!form.hidden;});
      async function submit(action){
        error.textContent='';const body=new FormData();body.set('csrf_token',root.dataset.csrf);body.set('revision',String(data.revision));body.set('action',action);if(action==='wait'){body.set('reason',select.value);body.set('note',note.value);}
        actions.querySelectorAll('button').forEach(b=>b.disabled=true);
        try{const response=await fetch(button.dataset.detailUrl+'/waiting',{method:'POST',credentials:'same-origin',body,headers:{Accept:'application/json'}});const result=await response.json().catch(()=>({error:'Your session expired or the service is unavailable. Reload the page and try again.'}));if(!response.ok||result.error)throw new Error(result.error||'The timing change could not be saved.');renderDetail(result,button);}
        catch(err){error.textContent=err.message||'The timing change could not be saved. Try again.';actions.querySelectorAll('button').forEach(b=>b.disabled=false);}
      }
      form.addEventListener('submit',event=>{event.preventDefault();if(form.reportValidity())submit('wait');});
      if(data.manual_reason){const resume=node('button','Resume Path time');resume.type='button';resume.className='qc-button';resume.addEventListener('click',()=>submit('resume'));controls.append(resume);actions.append(node('p',`Manual waiting: ${data.manual_reason}${data.manual_note?' · '+data.manual_note:''}`));}
      actions.append(controls,form);content.append(actions);
    }
    link.hidden=!button.dataset.url;link.href=button.dataset.url||'#';
  }
  buttons.forEach(button=>button.addEventListener('click',async()=>{
    const current=++generation;
    root.querySelector('#qc-dialog-title').textContent=button.dataset.label;root.querySelector('#qc-dialog-subtitle').textContent=button.dataset.session;
    content.replaceChildren(node('p','Loading process detail…'));link.hidden=true;dialog.showModal();
    if(!button.dataset.detailUrl){content.replaceChildren(node('p',button.dataset.applicable==='1'?'Timing starts when the first process activity is registered.':'N/A · This block does not apply to this session format.'));return;}
    try{const response=await fetch(button.dataset.detailUrl,{credentials:'same-origin',headers:{Accept:'application/json'}});if(!response.ok)throw new Error();const data=await response.json();if(current===generation&&dialog.open)renderDetail(data,button);}
    catch(_){if(current===generation&&dialog.open)content.replaceChildren(node('p','The process detail could not be loaded. Close this window and try again.'));}
  }));
  updateCells();
  setInterval(updateCells,60000);
  if(new URL(location.href).searchParams.get('mode')==='process')root.querySelector('[data-timing-view="process"]').click();
})();
