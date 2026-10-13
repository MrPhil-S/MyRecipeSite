// Results update independently of the input, so responses cannot erase typing.
// History restoration must also restore the controls from the restored URL.
function syncCollections(collectionId) {
  const collection = document.getElementById('collection-filter');
  if (collection) collection.value = collectionId;
  document.querySelectorAll('[data-collection-id].collection-tile').forEach((tile) => {
    if (tile.dataset.collectionId === String(collectionId)) tile.setAttribute('aria-current', 'true');
    else tile.removeAttribute('aria-current');
    const params = new URLSearchParams({page: '1', sort: document.getElementById('sort').value, per_page: document.getElementById('per-page').value});
    const query = document.getElementById('search-query').value;
    if (query) params.set('q', query);
    if (tile.dataset.collectionId !== '0') params.set('collection_id', tile.dataset.collectionId);
    tile.href = '/?' + params;
  });
}

document.addEventListener('htmx:afterSwap', () => {
  const recipes = document.getElementById('recipes');
  if (recipes) syncCollections(recipes.dataset.collectionId);
});
document.addEventListener('input', (event) => {
  if (event.target.id === 'search-query') syncCollections(document.getElementById('collection-filter').value);
});
document.addEventListener('change', (event) => {
  if (event.target.id === 'sort') syncCollections(document.getElementById('collection-filter').value);
});
document.addEventListener('htmx:historyRestore', () => {
  const params = new URLSearchParams(window.location.search);
  const input = document.getElementById('search-query');
  const sort = document.getElementById('sort');
  const collection = document.getElementById('collection-filter');
  if (input) input.value = params.get('q') || '';
  if (sort) sort.value = params.get('sort') || 'recent';
  if (collection) collection.value = params.get('collection_id') || '0';
  if (collection) syncCollections(collection.value);
});

document.addEventListener('click', (event) => {
  const suggestion = event.target.closest('[data-history-query]');
  if (!suggestion) return;
  const form = suggestion.closest('form');
  const input = form.querySelector('input[name=q]');
  input.value = suggestion.dataset.historyQuery;
  form.requestSubmit(form.querySelector('button[type=submit]'));
});
