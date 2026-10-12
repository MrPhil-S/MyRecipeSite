// Small UI interactions; persistence remains in the server form handlers.
function listPositionKey() {
  const params = new URLSearchParams(location.search);
  const filters = new URLSearchParams({page: params.get('page') || '1', sort: params.get('sort') || 'recent', q: params.get('q') || '', collection_id: params.get('collection_id') || '0'});
  return 'recipe-list-position:' + location.pathname + '?' + filters;
}
function rememberListPosition() {
  if (location.pathname !== '/' && location.pathname !== '/plan') return;
  try { sessionStorage.setItem(listPositionKey(), String(window.scrollY)); } catch (_) {}
}
document.addEventListener('click', (event) => {
  if (event.target.closest('.recipe-link, .floating-create')) rememberListPosition();
  const open = event.target.closest('[data-open-delete]');
  const close = event.target.closest('[data-close-delete]');
  const dialog = document.getElementById('delete-recipe-modal');
  if (open && dialog) dialog.showModal();
  if (close && dialog) dialog.close();
  const move = event.target.closest('[data-move-ingredient]');
  if (!move) return;
  const row = move.closest('.ingredient-row');
  const adjacent = move.dataset.moveIngredient === 'up' ? row.previousElementSibling : row.nextElementSibling;
  if (!adjacent) return;
  if (move.dataset.moveIngredient === 'up') row.parentNode.insertBefore(row, adjacent);
  else row.parentNode.insertBefore(adjacent, row);
  move.focus();
});
document.addEventListener('change', (event) => {
  if (!event.target.matches('[data-ingredient-sort]')) return;
  const list = document.querySelector('.ingredients');
  const rows = Array.from(list.children);
  rows.forEach((row, index) => { if (!row.dataset.originalOrder) row.dataset.originalOrder = String(index + 1); });
  // Keep headings and their ingredients together; only sort within each group.
  rows.sort((a, b) => Number(a.dataset.originalOrder) - Number(b.dataset.originalOrder));
  const groups = [[]];
  rows.forEach((row) => {
    if (row.classList.contains('group-heading')) groups.push([row]);
    else groups[groups.length - 1].push(row);
  });
  const order = event.target.value;
  groups.forEach((group) => {
    const heading = group[0] && group[0].classList.contains('group-heading') ? group.shift() : null;
    if (order !== 'original') group.sort((a, b) => {
      const comparison = a.dataset.ingredientName.localeCompare(b.dataset.ingredientName, undefined, {numeric: true, sensitivity: 'base'});
      return order === 'name_desc' ? -comparison : comparison;
    });
    if (heading) list.appendChild(heading);
    group.forEach((row) => list.appendChild(row));
  });
});
window.addEventListener('pageshow', () => {
  if (location.pathname !== '/' && location.pathname !== '/plan') return;
  try {
    const position = sessionStorage.getItem(listPositionKey());
    if (position !== null) requestAnimationFrame(() => window.scrollTo(0, Number(position)));
  } catch (_) {}
});
