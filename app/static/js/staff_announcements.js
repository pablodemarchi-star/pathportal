(() => {
  document.querySelectorAll('[data-announcements-open]').forEach(link => {
    const dialog = document.getElementById(link.dataset.announcementsOpen);
    if (!dialog) return;
    link.addEventListener('click', event => { event.preventDefault(); if (!dialog.open) dialog.showModal(); });
    dialog.querySelector('[data-announcements-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
    });
    dialog.addEventListener('close', () => { dialog.querySelectorAll('audio').forEach(audio => audio.pause()); link.focus(); });
    dialog.querySelectorAll('audio').forEach(audio => audio.addEventListener('play', () => {
      document.querySelectorAll('audio').forEach(other => { if (other !== audio) other.pause(); });
    }));
  });
})();
