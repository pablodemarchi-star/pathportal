(() => {
  const states = [];
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  document.querySelectorAll('[data-shared-report-url]').forEach(section => {
    if (!section.dataset.sharedReportUrl) return;
    const form = section.querySelector('[data-session-report-form]');
    const dialog = section.querySelector('[data-session-report-dialog]');
    const fields = [...form.querySelectorAll('input[name]:not([type="file"]):not([type="hidden"]), select[name], textarea[name]'),
      ...form.querySelectorAll('[data-component-absence-json], [data-report-considerations-json]')];
    const actorRole = section.dataset.sharedReportRole;
    const fieldOwners = Object.fromEntries(fields.map(input => [input.name, input.closest?.('[data-report-owner]')?.dataset.reportOwner]));
    fieldOwners._return_instructions_version = 'examiner';
    const writable = key => !actorRole || fieldOwners[key] === actorRole;
    const collect = () => {
      const values = {};
      fields.forEach(input => {
        if (['checkbox', 'radio'].includes(input.type)) {
          values[input.name] ||= [];
          if (input.checked) values[input.name].push(input.value);
        } else values[input.name] = input.value;
      });
      const version = form.querySelector('[data-report-return-version]');
      if (version) values._return_instructions_version = version.value;
      return values;
    };
    const defaults = collect();
    delete defaults._return_instructions_version;
    const state = {remote:{}, latest:{...defaults}, loading:true, busy:null, failure:false, locked:false};
    states.push(state);
    const status = form.querySelector('[data-report-draft-status]');
    const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'secondary-button compact-action'; retry.textContent = 'Retry'; retry.hidden = true;
    status.after(retry);
    const revision = document.createElement('input'); revision.type = 'hidden'; revision.name = 'shared_report_revision'; revision.value = '0'; form.append(revision);
    const diff = () => Object.fromEntries(Object.entries(state.latest).filter(([key, value]) => writable(key) && !equal(value, ({...defaults, ...state.remote})[key])));
    const pending = () => state.loading || Boolean(state.busy || state.failure || Object.keys(diff()).length);
    state.pending = pending; form.sharedDraftPending = pending;
    const progress = () => {
      form.dispatchEvent(new CustomEvent('report:shared-progress'));
      if (!form.sharedReportCompletion) return;
      for (const role of ['examiner', 'supervisor']) {
        const chip = section.querySelector('[data-report-progress-' + role + ']');
        if (chip) { const complete = form.sharedReportCompletion[role]; chip.textContent = `${role === 'examiner' ? 'Examiner' : 'Remote supervisor'} · ${complete ? 'Completed' : 'Pending'}`; chip.classList.toggle('is-complete', complete); }
      }
      form.querySelectorAll('[data-report-block]').forEach(block => {
        const chip = block.querySelector('[data-report-block-status]');
        const complete = form.sharedReportCompletion.blocks[block.dataset.reportBlock];
        if (chip) { chip.textContent = complete ? 'Completed' : 'Pending'; chip.classList.toggle('is-complete', complete); }
      });
    };
    const restore = values => form.dispatchEvent(new CustomEvent('report:shared-restore', {detail:values}));
    const accept = (data, remaining = diff()) => {
      if (data.submitted) {
        state.locked = true; state.failure = false; state.latest = {...defaults}; state.remote = {};
        retry.hidden = true; status.textContent = 'Report submitted.';
        form.dispatchEvent(new CustomEvent('report:shared-locked', {detail:data})); return;
      }
      if (Number(data.revision) < Number(revision.value)) return;
      form.sharedReportCompletion = data.completion;
      state.remote = data.values; state.latest = {...defaults, ...data.values, ...remaining}; revision.value = String(data.revision);
      restore(state.latest); progress();
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
      try { accept(await request()); state.loading = false; state.failure = false; retry.hidden = true; status.textContent = 'Shared draft is up to date.'; progress(); }
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
      try { return await state.busy; } finally { state.busy = null; progress(); }
    };
    form.sharedDraftFlush = flush;
    form.addEventListener('report:shared-change', event => {
      if (state.locked) return;
      state.latest = {...event.detail};
      progress();
      status.textContent = state.failure ? status.textContent : 'Saving shared draft…';
      clearTimeout(timer); timer = setTimeout(flush, 250);
    });
    retry.addEventListener('click', async () => {
      if (state.conflict) {
        if (!confirm('Reload the shared draft? Your unsaved answers will be replaced with the latest shared answers.')) return;
        state.latest = {...defaults, ...state.remote}; state.conflict = false; await load();
      } else { state.failure = false; retry.hidden = true; await load(); if (!state.failure) await flush(); }
    });
    let reading = false;
    setInterval(async () => {
      if (document.hidden || reading || state.loading || state.busy || state.failure || state.locked || !(dialog.open || section.closest('dialog')?.open)) return;
      reading = true;
      try { const result = await request(); if (!state.busy) accept(result); } catch (error) { fail(error); } finally { reading = false; }
    }, 1000);
  });
  window.addEventListener('beforeunload', event => {
    if (states.some(state => !state.locked && state.pending())) { event.preventDefault(); event.returnValue = ''; }
  });
})();
