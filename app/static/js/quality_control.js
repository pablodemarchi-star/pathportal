(() => {
  const root = document.querySelector('.qc-page');
  if (!root) return;
  const rows = [...root.querySelectorAll('[data-qc-row]')];
  const query = root.querySelector('#qc-query'), format = root.querySelector('#qc-format'), attention = root.querySelector('#qc-attention'), sort = root.querySelector('#qc-sort');
  const dialog = root.querySelector('#qc-dialog'), content = root.querySelector('#qc-dialog-content'), link = root.querySelector('#qc-open-block');
  const visibleRows = () => rows.filter(row => !row.hidden);
  const set = (id, value) => { const element=root.querySelector(id); if(element) element.textContent = value; };
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
    root.querySelectorAll('.qc-tabs a').forEach(anchor => {const next=new URL(anchor.href);url.searchParams.forEach((value,key)=>{if(key!=='tab')next.searchParams.set(key,value);});['q','format','attention','sort'].forEach(key=>{if(!url.searchParams.has(key))next.searchParams.delete(key);});anchor.href=next.toString();});
    root.dispatchEvent(new CustomEvent('quality:filtered'));
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
    const d=button.dataset;
    open(d.label,d.session);
    content.append(node('p', d.status), node('p', d.detail));
    if(d.deadline) content.append(node('p',`Deadline: ${d.deadline}`));
    if(d.url && d.applicable==='1'){link.href=d.url;link.hidden=false;}
  }));
  dialog.querySelector('.qc-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();}});
})();
