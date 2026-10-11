// Results update independently of the input, so responses cannot erase typing.
// History restoration must also restore the controls from the restored URL.
document.addEventListener('htmx:historyRestore', () => {
  const params = new URLSearchParams(window.location.search);
  const input = document.getElementById('search-query');
  const sort = document.getElementById('sort');
  if (input) input.value = params.get('q') || '';
  if (sort) sort.value = params.get('sort') || 'recent';
});
