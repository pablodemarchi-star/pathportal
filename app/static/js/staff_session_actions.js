(() => {
  const popup = document.querySelector('[data-staff-report-popup]');
  if (!popup) return;
  const content = popup.querySelector('[data-staff-report-popup-content]');
  const sources = new Map();
  document.querySelectorAll('[data-staff-report-quick]').forEach(link => {
    const session = document.getElementById('staff-session-detail-' + link.dataset.staffReportSession);
    const assignment = Array.from(session?.querySelectorAll('[data-staff-session-payload]') || []).find(item => item.dataset.staffLogisticsRole === link.dataset.staffReportRole);
    const native = link.dataset.staffReportKind === 'native';
    const section = assignment?.querySelector(native ? '[data-staff-exam-day-report]' : '[data-staff-external-report-section]');
    const opener = section?.querySelector(native ? '[data-exam-day-report-link]' : '[data-staff-external-report-link]');
    if (section && opener) sources.set(link, {section, opener, native});
  });
  const available = (link, source) => {
    const opens = Date.parse(link.dataset.staffReportOpensAt);
    return Boolean(source?.opener.dataset.folderUrl) && Number.isFinite(opens)
      && Date.now() >= opens && (!source.native || Date.now() < opens + 86400000);
  };
  const refresh = () => sources.forEach((source, link) => {
    link.hidden = false;
    if (!source.native) {
      const enabled = available(link, source);
      source.opener.classList.toggle('is-disabled', !enabled);
      source.opener.setAttribute('aria-disabled', String(!enabled));
      source.opener.setAttribute('tabindex', enabled ? '0' : '-1');
      source.opener.href = enabled ? source.opener.dataset.folderUrl : '#';
    }
  });
  sources.forEach((source, link) => {
    if (!source.native) source.opener.addEventListener('click', event => {
      if (!available(link, source)) event.preventDefault();
    });
    new MutationObserver(refresh).observe(source.opener, {attributes: true, attributeFilter: ['data-folder-url']});
  });
  let active;
  document.addEventListener('click', event => {
    const link = event.target.closest('[data-staff-report-quick]');
    if (!link) return;
    event.preventDefault();
    const source = sources.get(link);
    if (!source || popup.open) { refresh(); return; }
    refresh();
    const placeholder = document.createComment('End-of-session report position');
    source.section.before(placeholder);
    active = {link, source, placeholder, hidden: source.section.hidden};
    source.section.hidden = false;
    content.replaceChildren(source.section);
    popup.querySelector('[data-staff-report-popup-title]').textContent = link.dataset.staffReportName;
    popup.querySelector('[data-staff-report-popup-date]').textContent = link.dataset.staffReportDate;
    popup.showModal(); popup.scrollTop = 0;
    document.body.classList.add('staff-report-popup-open');
  });
  popup.querySelector('[data-staff-report-popup-close]').addEventListener('click', () => popup.close());
  popup.addEventListener('click', event => {
    if (event.target !== popup) return;
    const bounds = popup.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) popup.close();
  });
  popup.addEventListener('close', event => {
    if (event.target !== popup || !active) return;
    const {source, placeholder, hidden, link} = active;
    source.section.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    placeholder.replaceWith(source.section);
    source.section.hidden = hidden;
    active = null;
    content.replaceChildren();
    document.body.classList.remove('staff-report-popup-open');
    link.focus(); refresh();
  });
  refresh();
  window.setInterval(refresh, 30000);
  window.addEventListener('focus', refresh);
})();
