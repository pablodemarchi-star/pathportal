(() => {
  document.querySelectorAll('[data-staff-exam-day-report]').forEach((section) => {
    const opener = section.querySelector('[data-exam-day-report-link]');
    const dialog = section.querySelector('[data-session-report-dialog]');
    const form = dialog.querySelector('form');
    const outcome = form.querySelector('[data-report-outcome]');
    const reasons = form.querySelector('[data-report-reasons]');
    const facilities = form.querySelector('[data-report-facilities]');
    const comments = form.querySelector('[data-report-comments]');
    const emergencyPack = form.querySelector('[data-report-emergency-pack]');
    const emergencyReasons = form.querySelector('[data-report-emergency-reasons]');
    const feedback = form.querySelector('[data-report-feedback]');
    const submit = form.querySelector('[type="submit"]');
    const institutionalFeedback = form.querySelector('[data-report-feedback-checkbox]');
    let institutionSubmitted = institutionalFeedback?.dataset.submitted === 'true';
    let saving = false;
    let mediaPending = false;
    const draftFields = Array.from(form.querySelectorAll('input[name]:not([type="file"]):not([type="hidden"]), select[name], textarea[name]'));
    const clearDraft = () => { try { sessionStorage.removeItem(section.dataset.reportDraftKey); } catch {} };
    const saveDraft = () => {
      if (!section.dataset.reportDraftKey || !opener.dataset.folderUrl) return;
      const values = {};
      draftFields.forEach(input => {
        if (input.type === 'checkbox') {
          values[input.name] ||= [];
          if (input.checked) values[input.name].push(input.value);
        } else values[input.name] = input.value;
      });
      const status = form.querySelector('[data-report-draft-status]');
      try {
        sessionStorage.setItem(section.dataset.reportDraftKey, JSON.stringify(values));
        if (status) status.textContent = 'Draft saved in this browser tab.';
      } catch { if (status) status.textContent = 'Your browser could not save the draft. Keep this page open to retain your answers.'; }
    };
    form.addEventListener('input', saveDraft);
    form.addEventListener('change', saveDraft);
    const lockReport = (author) => {
      opener.dataset.folderUrl = '';
      opener.textContent = 'Report submitted';
      opener.disabled = true;
      opener.classList.add('is-disabled');
      opener.setAttribute('aria-disabled', 'true');
      opener.setAttribute('tabindex', '-1');
      draftFields.forEach(input => { input.disabled = true; });
      submit.disabled = true;
      feedback.textContent = author ? `This session report has already been submitted by ${author}.` : 'This session report has already been submitted.';
      clearDraft();
    };
    let checkingFeedback = false;
    const refreshFeedbackStatus = async () => {
      if (!section.dataset.feedbackStatusUrl || !opener.dataset.folderUrl || checkingFeedback || saving) return;
      if (!dialog.open && !section.closest('dialog')?.open) return;
      checkingFeedback = true;
      try {
        const response = await fetch(section.dataset.feedbackStatusUrl, {headers: {Accept: 'application/json'}, cache: 'no-store'});
        if (!response.ok) return;
        const result = await response.json();
        if (!result.ok) return;
        if (result.report_submitted) { lockReport(result.author_name); return; }
        if (Array.isArray(result.files) && mediaBox && !mediaPending) {
          const list = mediaBox.querySelector('[data-report-media-files]');
          list.replaceChildren();
          result.files.forEach(file => { const item = document.createElement('li'); item.textContent = file.filename; list.appendChild(item); });
          uploadedCount = result.files.length;
          marketingCheckbox.disabled = !uploadedCount || mediaBox.dataset.folderConfigured !== 'true';
          if (!uploadedCount) marketingCheckbox.checked = false;
        }
        institutionSubmitted = Boolean(result.submitted);
        institutionalFeedback.dataset.submitted = String(institutionSubmitted);
        institutionalFeedback.disabled = !institutionSubmitted;
        if (!institutionSubmitted) institutionalFeedback.checked = false;
        const badge = form.querySelector('[data-report-feedback-status]');
        badge.textContent = institutionSubmitted ? 'Feedback form submitted' : 'Feedback form not submitted';
        badge.classList.toggle('is-available', institutionSubmitted);
        form.querySelector('[data-report-feedback-help]').hidden = institutionSubmitted;
        submit.disabled = !institutionSubmitted || mediaPending;
      } catch {} finally { checkingFeedback = false; }
    };
    opener.addEventListener('click', refreshFeedbackStatus);
    window.addEventListener('focus', refreshFeedbackStatus);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshFeedbackStatus(); });
    window.setInterval(() => {
      if (!document.hidden && (dialog.open || section.closest('dialog')?.open)) refreshFeedbackStatus();
    }, 5000);

    const updateReasons = () => {
      const needed = ['The session finished ahead of schedule', 'There were minor delays', 'There were significant delays'].includes(outcome.value);
      form.querySelector('[data-report-reasons-field]').hidden = !needed;
      reasons.disabled = !needed;
      reasons.required = needed;
    };
    const available = () => {
      const opensAt = Date.parse(section.dataset.opensAt);
      return Boolean(opener.dataset.folderUrl) && Date.now() >= opensAt && Date.now() < opensAt + 86400000;
    };
    opener.addEventListener('click', (event) => {
      event.preventDefault();
      if (available()) { updateReasons(); dialog.showModal(); }
    });
    dialog.querySelectorAll('[data-session-report-close]').forEach((button) => {
      button.addEventListener('click', () => { if (!saving) dialog.close(); });
    });
    dialog.addEventListener('cancel', (event) => { if (saving) event.preventDefault(); });
    outcome.addEventListener('change', updateReasons);
    const updateComments = () => {
      const needed = ['Satisfactory, with comments', 'Unsatisfactory'].includes(facilities.value);
      form.querySelector('[data-report-comments-field]').hidden = !needed;
      comments.disabled = !needed;
      comments.required = needed;
    };
    facilities.addEventListener('change', updateComments);
    const updateEmergencyReasons = () => {
      const needed = ['Yes, it was opened and used', 'It was opened but not used'].includes(emergencyPack.value);
      form.querySelector('[data-report-emergency-reasons-field]').hidden = !needed;
      emergencyReasons.disabled = !needed;
      emergencyReasons.required = needed;
    };
    emergencyPack.addEventListener('change', updateEmergencyReasons);
    const timeline = form.querySelector('[data-report-return-timeline]');
    const returnSteps = Array.from(timeline.querySelectorAll('[data-return-step]'));
    const updateReturnSteps = () => {
      let previousChecked = true;
      returnSteps.forEach((step) => {
        step.disabled = !previousChecked;
        if (step.disabled) step.checked = false;
        step.closest('label').classList.toggle('is-checked', step.checked);
        step.closest('label').classList.toggle('is-locked', step.disabled);
        previousChecked = step.checked;
      });
      const count = returnSteps.filter((step) => step.checked).length;
      timeline.classList.toggle('is-complete', count === returnSteps.length);
      timeline.classList.toggle('is-in-progress', count > 0 && count < returnSteps.length);
      form.querySelector('[data-return-progress]').textContent = `${count} of ${returnSteps.length} steps completed`;
    };
    returnSteps.forEach((step) => step.addEventListener('change', updateReturnSteps));
    const reviewRows = Array.from(form.querySelectorAll('[data-review-row]'));
    const updateReview = () => {
      let completed = 0;
      reviewRows.forEach((row) => {
        const complete = Array.from(row.querySelectorAll('[data-review-select]')).every((select) => Boolean(select.value));
        row.classList.toggle('is-complete', complete);
        row.querySelector('[data-review-row-status]').textContent = complete ? 'Completed' : 'Incomplete';
        if (complete) completed += 1;
        const hasNote = Boolean(row.querySelector('[data-review-note]').value.trim());
        const notes = row.querySelector('[data-review-notes]');
        notes.classList.toggle('has-note', hasNote);
        notes.querySelector('[data-review-note-indicator]').hidden = !hasNote;
      });
      const counter = form.querySelector('[data-review-count]');
      counter.textContent = `${completed}/${reviewRows.length} completed`;
      counter.classList.toggle('is-complete', completed === reviewRows.length);
    };
    reviewRows.forEach((row) => {
      row.querySelectorAll('[data-review-select]').forEach((select) => select.addEventListener('change', updateReview));
      row.querySelector('[data-review-note]').addEventListener('input', updateReview);
    });
    const mediaBox = form.querySelector('[data-report-media]');
    let uploadedCount = 0;
    let marketingCheckbox;
    if (mediaBox) {
      const input = mediaBox.querySelector('[data-report-media-input]');
      const zone = mediaBox.querySelector('[data-report-media-dropzone]');
      const list = mediaBox.querySelector('[data-report-media-files]');
      const status = mediaBox.querySelector('[data-report-media-status]');
      marketingCheckbox = mediaBox.querySelector('[data-report-marketing-confirmed]');
      uploadedCount = list.querySelectorAll('li').length;
      const uploadFiles = async (files) => {
        if (mediaPending || saving || mediaBox.dataset.folderConfigured !== 'true' || !available()) return;
        mediaPending = true;
        input.disabled = true;
        submit.disabled = true;
        marketingCheckbox.checked = false;
        marketingCheckbox.disabled = true;
        const errors = [];
        try {
          for (const file of files) {
            status.textContent = `Uploading ${file.name}…`;
            const body = new FormData();
            body.append('csrf_token', form.querySelector('[name="csrf_token"]').value);
            body.append('file', file);
            try {
              const response = await fetch(mediaBox.dataset.uploadUrl, {method: 'POST', body, headers: {Accept: 'application/json'}});
              const result = await response.json();
              if (!response.ok || !result.ok) throw new Error(result.error || 'Upload failed. Please retry.');
              list.replaceChildren();
              result.files.forEach((item) => {
                const row = document.createElement('li');
                row.textContent = item.filename;
                list.appendChild(row);
              });
              uploadedCount = result.files.length;
            } catch (error) {
              errors.push(`${file.name}: ${error.message || 'Upload failed. Please retry.'}`);
            }
          }
          status.textContent = errors.length ? errors.join(' ') : `${uploadedCount} file(s) uploaded successfully.`;
        } finally {
          mediaPending = false;
          input.disabled = false;
          submit.disabled = !institutionSubmitted;
          marketingCheckbox.disabled = uploadedCount === 0;
          input.value = '';
          saveDraft();
        }
      };
      input.addEventListener('change', () => uploadFiles(Array.from(input.files)));
      zone.addEventListener('dragover', (event) => { event.preventDefault(); zone.classList.add('is-drag-over'); });
      zone.addEventListener('dragleave', () => zone.classList.remove('is-drag-over'));
      zone.addEventListener('drop', (event) => {
        event.preventDefault();
        zone.classList.remove('is-drag-over');
        uploadFiles(Array.from(event.dataTransfer?.files || []));
      });
    }
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!institutionSubmitted) {
        feedback.textContent = 'The exam centre must submit its Exam session feedback form before this report can be submitted.';
        return;
      }
      if (saving || mediaPending || !form.reportValidity()) return;
      if (!mediaBox || mediaBox.dataset.folderConfigured !== 'true' || !uploadedCount || !marketingCheckbox.checked) {
        feedback.textContent = 'Upload at least one file and confirm Marketing material before submitting.';
        return;
      }
      updateReturnSteps();
      if (!returnSteps.every((step) => step.checked)) {
        feedback.textContent = 'Please complete all six Exam return package verification steps in order.';
        return;
      }
      if (!available()) { feedback.textContent = 'This report is only available on the exam day.'; return; }
      saving = true;
      submit.disabled = true;
      feedback.textContent = 'Submitting…';
      try {
        const response = await fetch(form.action, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' } });
        const result = await response.json();
        if (response.status === 409) { lockReport(); return; }
        if (!response.ok || !result.ok) throw new Error(result.error || 'The report could not be submitted. Please try again.');
        opener.dataset.folderUrl = '';
        opener.textContent = 'Report submitted';
        opener.disabled = true;
        opener.classList.add('is-disabled');
        opener.setAttribute('aria-disabled', 'true');
        opener.setAttribute('tabindex', '-1');
        form.reset();
        clearDraft();
        feedback.textContent = '';
        dialog.close();
      } catch (error) {
        feedback.textContent = error.message || 'The report could not be submitted. Please try again.';
      } finally {
        saving = false;
        submit.disabled = !institutionSubmitted || !opener.dataset.folderUrl;
      }
    });
    if (opener.dataset?.folderUrl && section.dataset.reportDraftKey) {
      try {
        const values = JSON.parse(sessionStorage.getItem(section.dataset.reportDraftKey) || '{}');
        draftFields.forEach(input => {
          if (input.type === 'checkbox' && Array.isArray(values[input.name])) input.checked = values[input.name].includes(input.value);
          else if (input.type !== 'checkbox' && typeof values[input.name] === 'string') input.value = values[input.name];
        });
        if (institutionalFeedback && !institutionSubmitted) institutionalFeedback.checked = false;
        if (marketingCheckbox && !uploadedCount) marketingCheckbox.checked = false;
      } catch {}
    }
    updateReasons();
    updateComments();
    updateEmergencyReasons();
    updateReturnSteps();
    updateReview();
  });
})();
