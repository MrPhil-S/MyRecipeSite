// Saved ingredient order uses the existing editor form.
function listPositionKey() {
  const p = new URLSearchParams(location.search);
  const filters = new URLSearchParams({page:p.get('page')||'1', sort:p.get('sort')||'recent', q:p.get('q')||'', collection_id:p.get('collection_id')||'0', per_page:p.get('per_page')||'24'});
  return 'recipe-list-position:' + location.pathname + '?' + filters;
}
function rememberListPosition() {
  if (!['/', '/plan'].includes(location.pathname)) return;
  try {
    sessionStorage.setItem(listPositionKey(), String(window.scrollY));
    sessionStorage.setItem('recipe-last-list', location.pathname + location.search);
  } catch (_) {}
}
function refreshEditorControls() {
  const favorite = !!document.querySelector('[data-favorite-collection]:checked');
  document.querySelectorAll('[data-editor-favorite]').forEach(badge => { badge.hidden = !favorite; });
  if (location.pathname === '/recipes/new') {
    try {
      const target = sessionStorage.getItem('recipe-last-list');
      const url = target && new URL(target, location.origin);
      if (url && url.origin === location.origin && ['/', '/plan'].includes(url.pathname)) {
        document.querySelectorAll('#editor .back-link, #editor .form-actions a').forEach(link => { link.href = target; });
      }
    } catch (_) {}
  }
}
document.addEventListener('DOMContentLoaded', refreshEditorControls);
document.addEventListener('htmx:afterSwap', refreshEditorControls);
document.addEventListener('change', event => {
  if (event.target.matches('[data-favorite-collection]')) refreshEditorControls();
});
document.addEventListener('click', event => {
  if (event.target.closest('.recipe-link, a[href^="/recipes/new"]')) rememberListPosition();
  if (event.target.closest('a[href="#page-top"]')) {
    event.preventDefault();
    window.scrollTo({top:0, behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  }
  const dialog = document.getElementById('delete-recipe-modal');
  if (event.target.closest('[data-open-delete]') && dialog) dialog.showModal();
  if (event.target.closest('[data-close-delete]') && dialog) dialog.close();
});
// Pointer events support mouse, pen and touch. Reading-view rows stay in their
// section; the editor permits moving any row and keeps its hidden ID attached.
function ingredientGroup(row) {
  while (row.previousElementSibling) {
    row = row.previousElementSibling;
    if (row.classList.contains('group-heading')) return row;
  }
  return null;
}
function canMoveIngredient(row, target) {
  return target && row !== target && row.parentElement === target.parentElement &&
    (!row.parentElement.classList.contains('ingredients') ||
      !target.classList.contains('group-heading') && ingredientGroup(row) === ingredientGroup(target));
}
let ingredientDrag = null;
let dragFrame = null;
function moveDraggedIngredient() {
  if (!ingredientDrag) return;
  const {row,x,y} = ingredientDrag;
  const under = document.elementFromPoint(x,y);
  const target = under && under.closest('[data-sortable-ingredients] > *');
  if (canMoveIngredient(row,target)) {
    const bounds = target.getBoundingClientRect();
    row.parentElement.insertBefore(row, y < bounds.top + bounds.height/2 ? target : target.nextElementSibling);
  }
}
function scrollIngredientDrag() {
  if (!ingredientDrag) return;
  const y = ingredientDrag.y;
  const delta = y < 64 ? -12 : y > innerHeight-64 ? 12 : 0;
  if (delta) { window.scrollBy(0,delta); moveDraggedIngredient(); }
  dragFrame = requestAnimationFrame(scrollIngredientDrag);
}
document.addEventListener('pointerdown', event => {
  const handle = event.target.closest('.drag-handle');
  if (!handle || event.button !== 0 || ingredientDrag) return;
  event.preventDefault();
  handle.focus({preventScroll:true});
  const row = handle.parentElement;
  ingredientDrag = {row,next:row.nextElementSibling,handle,pointer:event.pointerId,x:event.clientX,y:event.clientY};
  row.classList.add('is-reordering');
  document.body.classList.add('ingredient-dragging');
  if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId);
  dragFrame = requestAnimationFrame(scrollIngredientDrag);
});
document.addEventListener('pointermove', event => {
  if (!ingredientDrag || ingredientDrag.pointer !== event.pointerId) return;
  event.preventDefault();
  ingredientDrag.x = event.clientX;
  ingredientDrag.y = event.clientY;
  moveDraggedIngredient();
}, {passive:false});
function finishIngredientDrag(cancel) {
  if (!ingredientDrag) return;
  const {row,next,handle} = ingredientDrag;
  if (cancel) row.parentElement.insertBefore(row,next);
  row.classList.remove('is-reordering');
  document.body.classList.remove('ingredient-dragging');
  handle.focus({preventScroll:true});
  ingredientDrag = null;
  cancelAnimationFrame(dragFrame);
}
document.addEventListener('pointerup', event => {
  if (ingredientDrag && ingredientDrag.pointer === event.pointerId) finishIngredientDrag(false);
});
document.addEventListener('pointercancel', () => finishIngredientDrag(true));
window.addEventListener('blur', () => finishIngredientDrag(true));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') finishIngredientDrag(true);
  const handle = event.target.closest('.drag-handle');
  if (!handle || !['ArrowUp','ArrowDown'].includes(event.key)) return;
  event.preventDefault();
  const row = handle.parentElement;
  const up = event.key === 'ArrowUp';
  const target = up ? row.previousElementSibling : row.nextElementSibling;
  if (canMoveIngredient(row,target)) row.parentElement.insertBefore(row,up ? target : target.nextElementSibling);
  handle.focus({preventScroll:true});
});
window.addEventListener('pageshow', () => {
  refreshEditorControls();
  if (!['/', '/plan'].includes(location.pathname)) return;
  try {
    const position = sessionStorage.getItem(listPositionKey());
    if (position !== null) requestAnimationFrame(() => window.scrollTo(0,Number(position)));
  } catch (_) {}
});
