(() => {
  const root = document.querySelector('.qc-page');
  if (!root) return;
  const rows = [...root.querySelectorAll('[data-qc-row]')];
  const query = root.querySelector('#qc-query'), format = root.querySelector('#qc-format'), attention = root.querySelector('#qc-attention'), sort = root.querySelector('#qc-sort');
  const dialog = root.querySelector('#qc-dialog'), content = root.querySelector('#qc-dialog-content'), link = root.querySelector('#qc-open-block');
  const names = new Intl.Collator('en', {sensitivity:'base', numeric:true});
  const visibleRows = () => rows.filter(row => !row.hidden);
  const set = (id, value) => { const element=root.querySelector(id); if(element) element.textContent = value; };
  function filter() {
    const term = query.value.trim().toLocaleLowerCase();
    rows.forEach(row => { row.hidden = !((!term || row.dataset.name.includes(term)) && (!format.value || row.dataset.format === format.value) && (!attention.checked || row.dataset.attention === '1')); });
    const descending=sort.value.endsWith('_desc');
    const blockKey=sort.value.startsWith('block_')?sort.value.slice(6).replace(/_desc$/,''):null;
    const values=new Map(), now=Date.now();
    if(blockKey){
      const ranks={pending:0,blocked:1,issue:2,progress:3,near:4,complete:5};
      rows.forEach(row=>{
        const cell=row.querySelector(`[data-qc-sort-cell="${blockKey}"]`);
        let value={missing:true};
        if(cell&&cell.dataset.applicable==='1'){
          if(root.dataset?.tab==='timing'){
            const button=cell.querySelector('[data-qc-timing]');
            const clock=button?JSON.parse(button.dataset.clock||'null'):null;
            if(clock&&clock.category!=='N/A'&&button.dataset.stale!=='1')value={missing:false,number:processTotals(clock,now).total,label:''};
          }else value={missing:false,number:ranks[cell.dataset.state]??0,label:cell.dataset.sortLabel||''};
        }
        values.set(row,value);
      });
    }
    const ordered = [...rows].sort((a,b) => {
      const dateOrder=Number(a.dataset.days)-Number(b.dataset.days);
      const tie=names.compare(a.dataset.name,b.dataset.name)||Number(a.dataset.sessionId||0)-Number(b.dataset.sessionId||0);
      if(blockKey){
        const first=values.get(a),second=values.get(b);
        if(first.missing||second.missing)return Number(first.missing)-Number(second.missing)||dateOrder||tie;
        return (descending?-1:1)*((first.number-second.number)||names.compare(first.label,second.label))||dateOrder||tie;
      }
      if(sort.value==='name'||sort.value==='name_desc')return (descending?-1:1)*names.compare(a.dataset.name,b.dataset.name)||dateOrder||tie;
      if(sort.value==='priority')return Number(b.dataset.attention)-Number(a.dataset.attention)||dateOrder||tie;
      if(sort.value==='recipient'||sort.value==='recipient_desc'){
        const first=(a.dataset.recipient||'').trim(),second=(b.dataset.recipient||'').trim();
        if(!first||!second)return Number(!first)-Number(!second)||dateOrder||tie;
        return (sort.value==='recipient_desc'?-1:1)*names.compare(first,second)||dateOrder||tie;
      }
      return (sort.value==='date_desc'?-1:1)*dateOrder||tie;
    });
    ordered.forEach(row => row.parentElement.append(row));
    root.querySelectorAll('[data-qc-sort-header]').forEach(header=>{
      const key=header.dataset.qcSortHeader, active=sort.value===key||sort.value===key+'_desc';
      header.setAttribute('aria-sort',active?(descending?'descending':'ascending'):'none');
      header.querySelector('[data-sort-indicator]').textContent=active?(descending?'↓':'↑'):'↕';
    });
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
  root.addEventListener('quality:timing-updated',()=>{if(sort.value.startsWith('block_'))filter();});
  root.querySelectorAll('[data-qc-sort]').forEach(button=>button.addEventListener('click',()=>{const key=button.dataset.qcSort;sort.value=sort.value===key?key+'_desc':key;filter();}));
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
