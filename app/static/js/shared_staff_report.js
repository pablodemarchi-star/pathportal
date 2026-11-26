(() => {
  const states = [];
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  document.querySelectorAll('[data-shared-report-url]').forEach(section => {
    if (!section.dataset.sharedReportUrl) return;
    const form = section.querySelector('[data-session-report-form]');
    const dialog = section.querySelector('[data-session-report-dialog]');
    const fields = [...form.querySelectorAll('input[name]:not([type="file"]):not([type="hidden"]), select[name], textarea[name]'),
      ...form.querySelectorAll('[data-component-absence-json], [data-report-considerations-json]')];
    const personal = new Set(['return_instructions_confirmed', '_return_instructions_version']);
    const collect = () => {
      const values = {};
      fields.forEach(input => {
        if (personal.has(input.name)) return;
        if (['checkbox', 'radio'].includes(input.type)) {
          values[input.name] ||= [];
          if (input.checked) values[input.name].push(input.value);
        } else values[input.name] = input.value;
      });
      return values;
    };
    const defaults = collect();
    const state = {remote:{}, latest:{...defaults}, loading:true, busy:null, failure:false, locked:false};
    states.push(state);
    const status = form.querySelector('[data-report-draft-status]');
    const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'secondary-button compact-action'; retry.textContent = 'Retry'; retry.hidden = true;
    status.after(retry);
    const revision = document.createElement('input'); revision.type = 'hidden'; revision.name = 'shared_report_revision'; revision.value = '0'; form.append(revision);
    const diff = () => Object.fromEntries(Object.entries(state.latest).filter(([key, value]) => !equal(value, ({...defaults, ...state.remote})[key])));
    const pending = () => state.loading || Boolean(state.busy || state.failure || Object.keys(diff()).length);
    state.pending = pending; form.sharedDraftPending = pending;
    const restore = values => {
      // Return acknowledgements are personal: each submitting staff member reviews the instructions.
      const acknowledgement = fields.find(input => input.name === 'return_instructions_confirmed');
      const version = form.querySelector('[data-report-return-version]');
      form.dispatchEvent(new CustomEvent('report:shared-restore', {detail:{...values,
        return_instructions_confirmed:acknowledgement?.checked ? ['1'] : [], _return_instructions_version:version?.value}}));
    };
    const accept = (data, remaining = diff()) => {
      if (data.submitted) {
        state.locked = true; state.failure = false; state.latest = {...defaults}; state.remote = {};
        retry.hidden = true; status.textContent = 'Report submitted.';
        form.dispatchEvent(new CustomEvent('report:shared-locked', {detail:data})); return;
      }
      state.remote = data.values; state.latest = {...defaults, ...data.values, ...remaining}; revision.value = String(data.revision);
      restore(state.latest);
    };
    const request = async options => {
      const response = await fetch(section.dataset.sharedReportUrl, {cache:'no-store', headers:{Accept:'application/json'}, ...options});
      const data = await response.json();
      if (!response.ok || !data.ok) { const error = new Error(data.error || 'The shared draft could not be saved. Please retry.'); error.conflict = data.conflict; throw error; }
      return data;
    };
    const fail = error => { state.failure = true; state.conflict = error.conflict; status.textContent = error.message; retry.hidden = false; retry.textContent = error.conflict ? 'Reload shared draft' : 'Retry'; };
    let timer;
    const load = async () => {
      try { accept(await request()); state.loading = false; state.failure = false; retry.hidden = true; status.textContent = 'Shared draft is up to date.'; }
      catch (error) { state.loading = false; fail(error); }
    };
    const loaded = load();
    const flush = async () => {
      clearTimeout(timer);
      await loaded;
      if (state.busy) { await state.busy; return flush(); }
      if (state.failure || state.locked) return false;
      state.busy = (async () => {
        try {
          while (Object.keys(diff()).length) {
            const changes = diff();
            status.textContent = 'Saving shared draft…';
            const body = new FormData(); body.set('csrf_token', form.querySelector('[name="csrf_token"]').value);
            body.set('changes', JSON.stringify(changes)); body.set('base', JSON.stringify(state.remote));
            const data = await request({method:'POST', body});
            const remaining = diff();
            Object.keys(changes).forEach(key => { if (equal(remaining[key], changes[key])) delete remaining[key]; });
            accept(data, remaining);
            if (state.locked) return false;
          }
          status.textContent = 'Shared draft saved. Changes are available to the session team.';
          return true;
        } catch (error) { fail(error); return false; }
      })();
      try { return await state.busy; } finally { state.busy = null; }
    };
    form.sharedDraftFlush = flush;
    form.addEventListener('report:shared-change', event => {
      if (state.locked) return;
      const values = {...event.detail}; personal.forEach(key => delete values[key]); state.latest = values;
      status.textContent = state.failure ? status.textContent : 'Saving shared draft…';
      clearTimeout(timer); timer = setTimeout(flush, 500);
    });
    retry.addEventListener('click', async () => {
      if (state.conflict) {
        if (!confirm('Reload the shared draft? Your unsaved answers will be replaced with the latest shared answers.')) return;
        state.latest = {...defaults, ...state.remote}; state.conflict = false; await load();
      } else { state.failure = false; retry.hidden = true; await load(); if (!state.failure) await flush(); }
    });
    setInterval(async () => {
      if (document.hidden || state.loading || state.busy || state.failure || state.locked || !(dialog.open || section.closest('dialog')?.open)) return;
      try { accept(await request()); } catch (error) { fail(error); }
    }, 5000);
  });
  window.addEventListener('beforeunload', event => {
    if (states.some(state => !state.locked && state.pending())) { event.preventDefault(); event.returnValue = ''; }
  });
})();
