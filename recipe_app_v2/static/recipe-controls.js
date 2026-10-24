// Saved ingredient order uses the existing editor form.
function listPositionKey() {
  const p = new URLSearchParams(location.search);
  const filters = new URLSearchParams({page:p.get('page')||'1', sort:p.get('sort')||'recent', q:p.get('q')||'', collection_id:p.get('collection_id')||'0', cuisine_id:p.get('cuisine_id')||'0', per_page:p.get('per_page')||'24'});
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
function editorAfterValidation(root = document) {
  const editor = root.querySelector?.('#editor') || (root.matches?.('#editor') ? root : null);
  if (!editor) return;
  editor.querySelectorAll('[data-row-error]').forEach(message => {
    const row = editor.querySelectorAll('#ingredient-rows .ingredient-row')[Number(message.dataset.rowError)];
    if (!row) return;
    row.classList.add('has-error');
    row.querySelectorAll('[name="ingredient_name"], [name="ingredient_note"]').forEach(input => {
      input.setAttribute('aria-invalid', 'true');
      input.insertAdjacentHTML('afterend', `<span class="field-error">${message.textContent}</span>`);
    });
  });
  const firstInvalid = editor.querySelector('[aria-invalid="true"]');
  if (firstInvalid) requestAnimationFrame(() => {
    firstInvalid.scrollIntoView({behavior:'smooth', block:'start'});
    firstInvalid.focus({preventScroll:true});
  });
  else if (editor.querySelector('.form-errors')) requestAnimationFrame(() => editor.querySelector('.form-errors')?.scrollIntoView({behavior:'smooth', block:'start'}));
}
document.addEventListener('DOMContentLoaded', () => editorAfterValidation());
document.addEventListener('htmx:afterSwap', () => editorAfterValidation(document));
let pendingEditorFiles = {};
let pendingImagePreviewRefresh = false;
document.addEventListener('htmx:beforeRequest', event => {
  const form = event.detail.elt?.closest?.('#editor form');
  if (!form) return;
  pendingEditorFiles = {};
  ['image', 'pdf'].forEach(name => {
    const input = form.querySelector(`[name="${name}"]`);
    if (input?.files?.length) pendingEditorFiles[name] = Array.from(input.files);
  });
});
document.addEventListener('htmx:afterSwap', event => {
  const editor = document.querySelector('#editor');
  if (!editor || !Object.keys(pendingEditorFiles).length) return;
  for (const [name, files] of Object.entries(pendingEditorFiles)) {
    const input = editor.querySelector(`[name="${name}"]`);
    if (!input) continue;
    const transfer = new DataTransfer();
    files.forEach(file => transfer.items.add(file));
    input.files = transfer.files;
    if (name === 'image') pendingImagePreviewRefresh = true;
  }
  pendingEditorFiles = {};
});
document.addEventListener('htmx:afterSettle', () => {
  if (!pendingImagePreviewRefresh) return;
  pendingImagePreviewRefresh = false;
  document.querySelector('#editor [name="image"]')?.dispatchEvent(new Event('change', {bubbles:true}));
});
document.addEventListener('click', event => {
  const remove = event.target.closest('[data-remove-ingredient]');
  if (remove) remove.closest('.ingredient-row')?.remove();
});
document.addEventListener('change', event => {
  if (event.target.matches('[data-group-toggle]')) {
    const row = event.target.closest('.ingredient-row');
    row.querySelector('[name="ingredient_group"]').value = event.target.checked ? '1' : '0';
    row.classList.toggle('is-group-heading', event.target.checked);
  }
});
document.addEventListener('change', event => {
  if (event.target.matches('[data-favorite-collection]')) refreshEditorControls();
});
document.addEventListener('click', event => {
  if (event.target.closest('[data-print-page]')) window.print();
  if (event.target.closest('.recipe-link, .photo-link, .card-body h3 a, a[href^="/recipes/new"]')) rememberListPosition();
  if (event.target.closest('a[href="#page-top"]')) {
    event.preventDefault();
    window.scrollTo({top:0, behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  }
  const dialog = document.getElementById('delete-recipe-modal');
  if (event.target.closest('[data-open-delete]') && dialog) dialog.showModal();
  if (event.target.closest('[data-close-delete]') && dialog) dialog.close();
  const cookedDateDialog = document.getElementById('cooked-date-modal');
  if (event.target.closest('[data-open-cooked-date]') && cookedDateDialog) {
    cookedDateDialog.showModal();
    cookedDateDialog.querySelector('[name="cooked_date"]')?.focus({preventScroll:true});
  }
  if (event.target.closest('[data-close-cooked-date]') && cookedDateDialog) cookedDateDialog.close();
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

let floatingActionFrame = null;
function updateFloatingActionOverlap() {
  const actions = document.querySelector('.library-floating-actions');
  if (actions && document.querySelector('.recipe-editor')) {
    actions.hidden = true;
    return;
  }
  if (actions) actions.hidden = false;
  let overlaps = false;
  if (actions && matchMedia('(max-width: 600px)').matches) {
    const actionBounds = actions.getBoundingClientRect();
    overlaps = Array.from(document.querySelectorAll('.pagination, .utility-footer, .app-footer')).some(target => {
      const bounds = target.getBoundingClientRect();
      return actionBounds.left < bounds.right && actionBounds.right > bounds.left &&
        actionBounds.top < bounds.bottom && actionBounds.bottom > bounds.top;
    });
  }
  if (actions) actions.classList.toggle('is-overlapping-page-content', overlaps);
}
function scheduleFloatingActionOverlapCheck() {
  if (floatingActionFrame !== null) return;
  floatingActionFrame = requestAnimationFrame(() => {
    floatingActionFrame = null;
    updateFloatingActionOverlap();
  });
}
document.addEventListener('DOMContentLoaded', scheduleFloatingActionOverlapCheck);
document.addEventListener('htmx:afterSwap', scheduleFloatingActionOverlapCheck);
window.addEventListener('scroll', scheduleFloatingActionOverlapCheck, {passive:true});
window.addEventListener('resize', scheduleFloatingActionOverlapCheck);
window.addEventListener('load', scheduleFloatingActionOverlapCheck);
