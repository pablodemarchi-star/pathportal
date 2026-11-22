(() => {
  const start = () => {
    document.querySelectorAll('.exam-records-modal').forEach(modal => {
      const message = document.createElement('p');
      message.setAttribute('role', 'status');
      modal.querySelector('.modal-panel').append(message);
      let busy = false;
      async function save(data) {
        if (busy) return;
        busy = true;
        modal.setAttribute('aria-busy', 'true');
        message.textContent = 'Saving…';
        data.set('csrf_token', modal.dataset.csrf);
        try {
          const response = await fetch(modal.dataset.endpoint, { method: 'POST', body: data });
          const result = await response.json();
          if (!response.ok || !result.ok) throw new Error(result.error || 'Could not save. Please try again.');
          sessionStorage.setItem('exam-records-scroll', String(modal.scrollTop));
          sessionStorage.setItem('exam-records-reopen', modal.id);
          window.location.reload();
        } catch (error) {
          message.textContent = error.message;
          busy = false;
          modal.removeAttribute('aria-busy');
          modal.querySelectorAll('[data-beyond-step], [data-speaking-step]').forEach(input => {
            input.checked = Number((input.dataset.speakingStep || input.dataset.beyondStep)) <= Number(input.closest('[data-speaking-setup], [data-beyond-setup]').dataset.completedSteps);
          });
        }
      }
      function upload(input, files) {
        if (input.disabled || busy) return;
        if (files.length !== 1) {
          message.textContent = 'Choose exactly one file.';
          return;
        }
        const data = new FormData();
        data.set('action', input.dataset.uploadAction || 'upload');
        if (['rw_upload', 'listening_upload'].includes(input.dataset.uploadAction)) {
          if (!/\.(xlsx|xls)$/i.test(files[0].name)) {
            message.textContent = 'Choose an Excel file (.xlsx or .xls).';
            input.value = '';
            return;
          }
          data.set('revision', input.closest('[data-beyond-setup]').dataset.revision);
        }
        if (!['rw_upload', 'listening_upload'].includes(input.dataset.uploadAction)) {
          data.set('revision', input.closest('[data-speaking-setup]').dataset.revision);
        }
        data.set('person_ref', input.dataset.personRef);
        data.set('previous_file_id', input.dataset.previousFileId);
        data.set('record', files[0]);
        save(data);
        input.value = '';
      }
      modal.querySelectorAll('[data-copy-beyond]').forEach(button => button.addEventListener('click', async () => {
        if (button.disabled) return;
        try {
          await navigator.clipboard.writeText(button.dataset.copyBeyond);
          message.textContent = 'Session name copied.';
          button.classList.add('is-copied');
          window.setTimeout(() => button.classList.remove('is-copied'), 1800);
        } catch (_) {
          message.textContent = 'Could not copy the name. Select the session name and copy it manually.';
        }
      }));
      modal.querySelectorAll('[data-record-file]').forEach(input => {
        input.addEventListener('change', () => upload(input, input.files));
        const drop = input.closest('[data-record-drop]');
        ['dragover', 'dragleave', 'drop'].forEach(type => drop.addEventListener(type, event => {
          event.preventDefault();
          if (type === 'drop') upload(input, event.dataTransfer.files);
          drop.classList.toggle('is-dragging', type === 'dragover' && !input.disabled);
        }));
      });
      modal.querySelectorAll('[data-beyond-step], [data-speaking-step]').forEach(input => input.addEventListener('change', () => {
        const speaking = input.hasAttribute('data-speaking-step');
        const section = input.closest('[data-speaking-setup], [data-beyond-setup]');
        if (input.disabled || busy) {
          input.checked = Number(input.dataset.speakingStep || input.dataset.beyondStep) <= Number(section.dataset.completedSteps);
          return;
        }
        const data = new FormData();
        data.set('action', speaking ? 'speaking' : (section.dataset.setupAction || 'beyond'));
        data.set('step', input.dataset.speakingStep || input.dataset.beyondStep);
        data.set('checked', input.checked ? '1' : '0');
        data.set('previous_steps', section.dataset.completedSteps);
        data.set('revision', section.dataset.revision);
        save(data);
      }));
    });
    const reopen = sessionStorage.getItem('exam-records-reopen');
    if (reopen) {
      sessionStorage.removeItem('exam-records-reopen');
      document.querySelector(`[data-open-modal="${CSS.escape(reopen)}"]`)?.click();
      const scrollTop = Number(sessionStorage.getItem('exam-records-scroll') || 0);
      sessionStorage.removeItem('exam-records-scroll');
      window.requestAnimationFrame(() => {
        const modal = document.getElementById(reopen);
        if (modal) modal.scrollTop = scrollTop;
      });
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
