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
    const institutionSubmitted = institutionalFeedback?.dataset.submitted === 'true';
    let saving = false;
    let mediaPending = false;
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
        if (!response.ok || !result.ok) throw new Error(result.error || 'The report could not be submitted. Please try again.');
        opener.dataset.folderUrl = '';
        opener.textContent = 'Report submitted';
        opener.disabled = true;
        opener.classList.add('is-disabled');
        opener.setAttribute('aria-disabled', 'true');
        opener.setAttribute('tabindex', '-1');
        form.reset();
        feedback.textContent = '';
        dialog.close();
      } catch (error) {
        feedback.textContent = error.message || 'The report could not be submitted. Please try again.';
      } finally {
        saving = false;
        submit.disabled = !institutionSubmitted;
      }
    });
    updateReasons();
    updateComments();
    updateEmergencyReasons();
    updateReturnSteps();
    updateReview();
  });
})();
