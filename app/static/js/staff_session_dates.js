(() => {
  'use strict';
  const dates = new Intl.DateTimeFormat('en-CA', {timeZone:'America/Argentina/Buenos_Aires', year:'numeric', month:'2-digit', day:'2-digit'});
  let timer;
  const refresh = () => {
    clearTimeout(timer);
    const now = new Date();
    const parts = Object.fromEntries(dates.formatToParts(now).map(part => [part.type, part.value]));
    const today = `${parts.year}-${parts.month}-${parts.day}`;
    const groups = new Map();
    document.querySelectorAll('[data-staff-session-date]').forEach(row => {
      const date = row.dataset.staffSessionDate;
      const past = Boolean(date && date < today);
      row.classList.toggle('is-past-session', past);
      const parent = row.parentElement;
      if (!groups.has(parent)) groups.set(parent, []);
      groups.get(parent).push({row, past, date:date || '9999-12-31'});
    });
    groups.forEach((rows, parent) => {
      rows.sort((a, b) => Number(a.past) - Number(b.past) || a.date.localeCompare(b.date));
      rows.forEach(({row}) => parent.appendChild(row));
    });
    // Argentina midnight: keep an already-open portal up to date as well.
    const midnight = Date.parse(`${today}T00:00:00-03:00`) + 24 * 60 * 60 * 1000;
    timer = setTimeout(refresh, Math.max(1, midnight - now.getTime()));
  };
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.addEventListener('focus', refresh);
  refresh();
})();
