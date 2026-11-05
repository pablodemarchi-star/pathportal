document.querySelectorAll('[data-payment-live-search]').forEach(input => {
  const panel = input.closest('[data-payment-search-panel]');
  const rows = [...panel.querySelectorAll('[data-payment-search-text]')];
  const empty = panel.querySelector('[data-payment-search-empty]');
  const apply = () => {
    const query = input.value.trim().toLowerCase();
    let count = 0;
    rows.forEach(row => {
      row.hidden = !row.dataset.paymentSearchText.toLowerCase().includes(query);
      if (!row.hidden) count++;
    });
    empty.hidden = !query || count > 0;
    const url = new URL(window.location.href);
    if (query) url.searchParams.set('payment_search', input.value);
    else url.searchParams.delete('payment_search');
    window.history.replaceState(null, '', url);
  };
  input.addEventListener('input', apply);
  apply();
});
