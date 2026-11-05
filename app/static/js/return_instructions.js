window.syncReturnInstructions = payload => {
  const ids = new Set(payload.session_ids.map(String));
  document.querySelectorAll('[data-return-instructions-row]').forEach(row => {
    if (!ids.has(row.dataset.sessionId)) return;
    const content = row.querySelector('[data-logistics-instructions-value]');
    const title = row.querySelector('[data-logistics-instructions-title-value]');
    content.value = content.defaultValue = payload.html;
    title.value = title.defaultValue = payload.title;
    const status = document.createElement('em');
    status.textContent = payload.html ? 'added' : 'empty';
    row.querySelector('[data-return-instructions-open]').replaceChildren('Instructions (', status, ')');
  });
};
document.addEventListener('instructions:saved', event => {
  const source = event.target.closest('[data-return-instructions-row]');
  if (!source) return;
  window.syncReturnInstructions({title: event.detail.title, html: event.detail.html,
    session_ids: event.detail.sessionIds?.length ? event.detail.sessionIds : [source.dataset.sessionId]});
});
