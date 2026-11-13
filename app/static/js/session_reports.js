(() => {
  const form = document.querySelector('[data-reports-filters]');
  if (!form) return;
  const body = document.querySelector('[data-reports-body]');
  const rows = Array.from(body.querySelectorAll('[data-report-row]'));
  const query = form.querySelector('[data-reports-query]');
  const format = form.querySelector('[data-reports-format]');
  const sort = form.querySelector('[data-reports-sort]');
  const status = form.querySelector('[data-reports-status]');
  const attention = form.querySelector('[data-reports-attention]');
  const apply = () => {
    const term = query.value.trim().toLocaleLowerCase();
    const visible = rows.filter(row => {
      const data = row.dataset;
      const statusMatch = !status.value || status.value === 'both' && data.complete === '1' || status.value === 'supervisor_pending' && data.report === '0' && data.reportApplicable === '1' || status.value === 'feedback_pending' && data.feedback === '0';
      row.hidden = !(data.name.toLocaleLowerCase().includes(term) && (!format.value || data.format === format.value) && statusMatch && (!attention.checked || Number(data.attention) > 0));
      return !row.hidden;
    });
    const compare = (a,b) => {
      const x=a.dataset,y=b.dataset;
      if (sort.value === 'priority' && Number(x.attention)!==Number(y.attention)) return Number(y.attention)-Number(x.attention);
      if (sort.value === 'score') {
        if (x.score === '' || y.score === '') { if (x.score !== y.score) return x.score === '' ? 1 : -1; }
        else if (Number(x.score)!==Number(y.score)) return Number(x.score)-Number(y.score);
      }
      if (sort.value.startsWith('name')) return x.name.localeCompare(y.name) * (sort.value.endsWith('_desc')?-1:1);
      return x.date.localeCompare(y.date)*(sort.value==='date_desc'?-1:1) || x.name.localeCompare(y.name);
    };
    rows.sort(compare).forEach(row=>body.appendChild(row));
    const set=(key,value)=>document.querySelector(`[data-reports-${key}]`).textContent=value;
    set('total',visible.length);
    set('supervisor',visible.filter(row=>row.dataset.report==='1').length);
    set('feedback',visible.filter(row=>row.dataset.feedback==='1').length);
    set('complete',visible.filter(row=>row.dataset.complete==='1').length);
    set('alerts',visible.filter(row=>Number(row.dataset.attention)>0).length);
    document.querySelector('[data-reports-empty]').hidden=visible.length>0;
    const url=new URL(window.location.href);
    for (const [key,value] of [['q',query.value],['format',format.value],['sort',sort.value],['report_status',status.value],['attention',attention.checked?'1':'']]) {
      if(value)url.searchParams.set(key,value);else url.searchParams.delete(key);
    }
    url.searchParams.set('tab','reports');
    window.history.replaceState(null,'',url);
  };
  form.addEventListener('submit',event=>event.preventDefault());
  query.addEventListener('input',apply);
  [format,sort,status,attention].forEach(input=>input.addEventListener('change',apply));
  form.querySelector('[data-reports-year]').addEventListener('change',()=>form.submit());
  apply();
  const dialog=document.querySelector('[data-reports-dialog]');
  const content=dialog.querySelector('[data-reports-content]');
  let requestId=0;
  document.querySelectorAll('[data-reports-open]').forEach(button=>button.addEventListener('click',async()=>{
    const current=++requestId;
    dialog.querySelector('h2').textContent=button.dataset.name;
    content.textContent='Loading reports…';
    if(!dialog.open)dialog.showModal();
    try {
      const response=await fetch(button.dataset.url,{headers:{Accept:'text/html'},cache:'no-store'});
      if(response.redirected)throw new Error('Your sign-in session expired. Please sign in again.');
      if(!response.ok)throw new Error('Reports could not be loaded. Close this window and try again.');
      const html=await response.text();
      if(current===requestId)content.innerHTML=html;
    } catch(error){if(current===requestId)content.textContent=error.message;}
  }));
  dialog.querySelector('[data-reports-close]').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{
    if(event.target!==dialog)return;
    const rect=dialog.getBoundingClientRect();
    if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();
  });
})();
