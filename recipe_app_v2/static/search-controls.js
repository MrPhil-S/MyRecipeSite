// The server renders collection/cuisine navigation with each results response.
// Restore unswapped form controls when HTMX restores a previous results URL.
document.addEventListener('htmx:historyRestore', () => {
  const params = new URLSearchParams(location.search);
  for (const [id, name, fallback] of [
    ['search-query', 'q', ''], ['sort', 'sort', 'recent'],
    ['collection-filter', 'collection_id', '0'], ['cuisine-filter', 'cuisine_id', '0'],
    ['per-page', 'per_page', '24']
  ]) {
    const control = document.getElementById(id);
    if (control) control.value = params.get(name) || fallback;
  }
});

// Recent searches submit the existing form, including its CSRF token and filters.
document.addEventListener('click', event => {
  const suggestion = event.target.closest('[data-history-query]');
  const form = suggestion && suggestion.closest('form');
  const input = form && form.querySelector('input[name=q]');
  if (!input) return;
  input.value = suggestion.dataset.historyQuery;
  form.requestSubmit(form.querySelector('button[type=submit]'));
});
