(() => {
  const root = document.querySelector('.qc-page');
  if (!root) return;
  const rows = [...root.querySelectorAll('[data-qc-row]')];
  const query = root.querySelector('#qc-query'), format = root.querySelector('#qc-format'), attention = root.querySelector('#qc-attention'), sort = root.querySelector('#qc-sort');
  const dialog = root.querySelector('#qc-dialog'), content = root.querySelector('#qc-dialog-content'), link = root.querySelector('#qc-open-block');
  const visibleRows = () => rows.filter(row => !row.hidden);
  const set = (id, value) => { root.querySelector(id).textContent = value; };
  function filter() {
    const term = query.value.trim().toLocaleLowerCase();
    rows.forEach(row => { row.hidden = !((!term || row.dataset.name.includes(term)) && (!format.value || row.dataset.format === format.value) && (!attention.checked || row.dataset.attention === '1')); });
    const ordered = [...rows].sort((a,b) => sort.value === 'priority' ? Number(b.dataset.attention)-Number(a.dataset.attention) || Number(a.dataset.days)-Number(b.dataset.days) : Number(a.dataset.days)-Number(b.dataset.days));
    ordered.forEach(row => row.parentElement.append(row));
    const shown = visibleRows();
    set('#qc-total', shown.length); set('#qc-ready', shown.filter(r => r.dataset.ready === '1').length);
    set('#qc-overdue', shown.filter(r => r.dataset.overdue === '1').length); set('#qc-issues', shown.filter(r => r.dataset.issues === '1').length);
    set('#qc-near', shown.filter(r => Number(r.dataset.days) >= 0 && Number(r.dataset.days) <= 29 && r.dataset.ready !== '1').length);
    root.querySelector('#qc-empty').hidden = shown.length > 0;
    const url = new URL(location.href);
    [['q',query.value],['format',format.value],['attention',attention.checked ? '1' : ''],['sort',sort.value === 'date' ? '' : sort.value]].forEach(([key,value]) => value ? url.searchParams.set(key,value) : url.searchParams.delete(key));
    history.replaceState(null,'',url);
    root.querySelector('.qc-header-actions a').href = url.toString();
  }
  [query,format,attention,sort].forEach(input => input.addEventListener('input',filter));
  root.querySelector('#qc-year').addEventListener('change', () => root.querySelector('#qc-filters').submit());
  root.querySelector('#qc-filters').addEventListener('submit', event => { event.preventDefault(); filter(); });
  filter();
  const node = (tag, text) => { const item=document.createElement(tag); if(text !== undefined) item.textContent=text; return item; };
  const stamp = value => value ? new Intl.DateTimeFormat('en-GB',{timeZone:'America/Argentina/Buenos_Aires',dateStyle:'short',timeStyle:'short'}).format(new Date(value))+' (GMT-3)' : 'Not enough historical data';
  const days = value => value === null || value === undefined ? 'Not enough historical data' : `${value} calendar days`;
  function open(title, subtitle) {
    set('#qc-dialog-title',title);set('#qc-dialog-subtitle',subtitle); content.replaceChildren(); link.hidden=true; dialog.showModal();
  }
  root.querySelectorAll('[data-qc-detail]').forEach(button => button.addEventListener('click', () => {
    const d=button.dataset, timing=JSON.parse(d.timing);
    open(d.label,d.session);
    content.append(node('p', d.status), node('p', d.detail));
    if(d.deadline) content.append(node('p',`Deadline: ${d.deadline}`));
    const definitions=node('dl');
    const entries=[['Enabled',stamp(timing.enabled_at)],['First recorded action',stamp(timing.first_action_at)],['Completed',stamp(timing.completed_at)],['Wait before first action',days(timing.wait)],['Total elapsed since enablement',days(timing.elapsed)],['First recorded action to completion',days(timing.duration)],['Reopenings since tracking started',String(timing.reopenings)]];
    entries.forEach(([label,value]) => definitions.append(node('dt',label),node('dd',value)));
    content.append(definitions,node('p','Recorded times are calendar time, not working hours. Historical gaps are shown explicitly. Reopened processes retain their original known start; elapsed time includes the reopening period.'));
    if (timing.history.length) {content.append(node('h3','Recorded milestones'));const list=node('ul');timing.history.forEach(event=>list.append(node('li',`${stamp(event.at)} · ${event.event}`))); content.append(list);}
    if(d.url && d.applicable==='1'){link.href=d.url;link.hidden=false;}
  }));
  root.querySelector('#qc-times').addEventListener('click', () => {
    open('Process times','CURRENT FILTERED SESSIONS');
    content.append(node('p','Only complete processes with a known enablement date are included in averages. Unknown historical periods are excluded. Shared processes are counted once per session.'));
    const groups=new Map();
    visibleRows().forEach(row=>row.querySelectorAll('[data-qc-detail]').forEach(button=>{
      if(button.dataset.applicable!=='1')return;
      const timing=JSON.parse(button.dataset.timing), key=button.dataset.label;
      if(!groups.has(key))groups.set(key,[]);
      timing.deadline = button.dataset.deadlineIso;
      groups.get(key).push(timing);
    }));
    const table=node('table'), head=node('tr');['Process','Measured completions','Average days','Longest days','On time (known)','Reopenings'].forEach(label=>head.append(node('th',label)));table.append(head);
    groups.forEach((timings,key)=>{
      const measured=timings.filter(t=>t.completed_at && t.elapsed!==null), values=measured.map(t=>t.elapsed), tr=node('tr');
      const knownDeadlines = timings.filter(t => t.completed_at && t.deadline);
      const localDate = value => {const parts = new Intl.DateTimeFormat('en-GB',{timeZone:'America/Argentina/Buenos_Aires',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(value));const part = type => parts.find(p => p.type === type).value;return `${part('year')}-${part('month')}-${part('day')}`;};
      const onTime = knownDeadlines.filter(t => localDate(t.completed_at) <= t.deadline).length;
      const cells=[key,`${measured.length} / ${timings.length}`,values.length?(values.reduce((a,b)=>a+b,0)/values.length).toFixed(1):'No data',values.length?Math.max(...values).toFixed(1):'No data',knownDeadlines.length ? `${Math.round(onTime/knownDeadlines.length*100)}% (${onTime}/${knownDeadlines.length})` : 'No data',timings.reduce((sum,t)=>sum+t.reopenings,0)];
      cells.forEach(value=>tr.append(node('td',String(value))));table.append(tr);
    });content.append(table);
  });
  dialog.querySelector('.qc-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}});
})();
