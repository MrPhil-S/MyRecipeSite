"""Dev-only management of ingredient image aliases, independent of search synonyms."""
from urllib.parse import quote, urlencode
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from .activity import csrf_context, set_cookie
from .database import get_session, writes_enabled
from .editor_routes import check_token
from .image_aliases import Matcher, image_url, load_catalogue, normalize, revision, save_entry
from .sorting import table_headers
from .ingredient_rematch import RematchError, affected_ingredients, apply_selected
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .models import Recipe_Ingredient

router = APIRouter()


@router.get('/image-aliases')
def alias_list(request: Request, q: str = Query('', max_length=200),
               page: int = Query(1, ge=1), sample: str = Query('', max_length=1000),
               sample_note: str = Query('', max_length=1000),
               sort: Literal['name', 'aliases', 'image'] = 'name',
               direction: Literal['asc', 'desc'] = 'asc'):
    from .main import templates
    values = load_catalogue()
    needle = normalize(q)
    names = [name for name in sorted(values) if not needle or any(
        needle in normalize(term) for term in [name] + values[name])]
    def ordering(name):
        if sort == 'aliases':
            return (', '.join(values[name]).casefold(), name.casefold(), name)
        if sort == 'image':
            return (image_url(name) == '/ingredient-images/default_ingredient.jpg', name.casefold(), name)
        return (name.casefold(), name)
    names.sort(key=ordering, reverse=direction == 'desc')
    pages = max(1, (len(names) + 49) // 50)
    page = min(page, pages)
    matched = Matcher(values).match(sample, sample_note) if sample.strip() else None
    token = csrf_context(request)
    response = templates.TemplateResponse(request=request, name='image_aliases.html', context={
        'csrf_token': token,
        'rows': [{'name': name, 'aliases': values[name], 'image': image_url(name),
                  'edit_url': '/image-aliases/edit?name=' + quote(name, safe=''),
                  'review_url': '/image-aliases/rematch?name=' + quote(name, safe='')}
                 for name in names[(page - 1) * 50:page * 50]],
        'q': q, 'page': page, 'pages': pages, 'total': len(names),
        'query_string': urlencode({'q': q, 'sample': sample, 'sample_note': sample_note, 'sort': sort, 'direction': direction}),
        'sort': sort, 'direction': direction,
        'headers': table_headers('/image-aliases', [('image', 'Image'), ('name', 'Official image name'),
            ('aliases', 'Aliases')], sort, direction, {'q': q, 'sample': sample, 'sample_note': sample_note}),
        'sample': sample, 'sample_note': sample_note, 'matched': matched, 'matched_image': image_url(matched) if matched else None,
        'writes_enabled': writes_enabled()})
    return set_cookie(request, response, token)


def render_form(request, original='', name=None, aliases=None, version=None, error=None, status=200):
    from .main import templates
    values = load_catalogue()
    if original and original not in values:
        raise HTTPException(404, 'Image alias entry not found.')
    token = csrf_context(request)
    response = templates.TemplateResponse(request=request, name='image_alias_form.html', status_code=status, context={
        'original': original, 'name': name if name is not None else original,
        'aliases': aliases if aliases is not None else '\n'.join(values.get(original, [])),
        'version': version if version is not None else revision(values), 'csrf_token': token,
        'error': error, 'writes_enabled': writes_enabled(), 'image': image_url(name or original)})
    return set_cookie(request, response, token)


@router.get('/image-aliases/edit')
def alias_form(request: Request, name: str = Query('', max_length=100)):
    return render_form(request, original=name)


@router.post('/image-aliases/edit')
async def alias_save(request: Request):
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 65536:
            raise HTTPException(413, 'Alias form is too large.')
        chunks.append(chunk)
    request._body = b''.join(chunks)
    if request._body.count(b'&') > 10:
        raise HTTPException(413, 'Too many form fields.')
    async with request.form(max_files=0, max_fields=10) as form:
        check_token(request, str(form.get('csrf_token', '')))
        original, name = str(form.get('original', '')), str(form.get('name', '')).strip()
        aliases, version = str(form.get('aliases', '')), str(form.get('version', ''))
        action = str(form.get('action', 'save'))
        if action not in ('save', 'delete'):
            raise HTTPException(422, 'Invalid action.')
        if action == 'delete' and str(form.get('confirm_delete', '')) != 'yes':
            return render_form(request, original, name, aliases, version,
                               'Confirm deletion before removing this entry.', 422)
        try:
            await run_in_threadpool(save_entry, name,
                [line.strip() for line in aliases.splitlines() if line.strip()], version, original, action)
        except PermissionError as exc:
            raise HTTPException(403, str(exc))
        except RuntimeError as exc:
            return render_form(request, original, name, aliases, version, str(exc), 409)
        except ValueError as exc:
            return render_form(request, original, name, aliases, version, str(exc), 422)
    target = '/image-aliases/rematch?name=' + quote(name, safe='') if action == 'save' else '/image-aliases'
    return RedirectResponse(target, status_code=303)


def render_rematches(request, session, name='', page=1, sort='recipe', direction='asc', error=None, status=200, applied=0, recipe_query='', current='', scope='changes'):
    from .main import templates
    changes = affected_ingredients(session, name, recipe_query, current, scope)
    current_options = session.scalars(select(func.coalesce(func.nullif(Recipe_Ingredient.name_official, ''), 'default_ingredient')).where(Recipe_Ingredient.is_group_header.is_not(True)).distinct()).all()
    field = {'recipe': 'recipe_name', 'ingredient': 'ingredient', 'current': 'current', 'proposed': 'proposed'}[sort]
    changes.sort(key=lambda row: (row[field].casefold(), row['recipe_id'], row['row_id']), reverse=direction == 'desc')
    pages = max(1, (len(changes) + 49) // 50)
    page = min(page, pages)
    filters = {'name': name, 'recipe_query': recipe_query, 'current': current, 'scope': scope}
    parameters = dict(filters, sort=sort, direction=direction)
    token = csrf_context(request)
    response = templates.TemplateResponse(request=request, name='image_rematches.html', status_code=status, context={
        'rows': changes[(page - 1) * 50:page * 50], 'total': len(changes), 'page': page, 'pages': pages,
        **filters, 'sort': sort, 'direction': direction, 'query_string': urlencode(parameters),
        'current_options': sorted(set(current_options) | {'default_ingredient'}),
        'selectable': any(row['token'] for row in changes[(page - 1) * 50:page * 50]),
        'default_url': '/image-aliases/rematch?' + urlencode(dict(parameters, name='', current='default_ingredient', scope='all')),
        'headers': table_headers('/image-aliases/rematch', [('recipe', 'Recipe'), ('ingredient', 'Ingredient'),
            ('current', 'Current image'), ('proposed', 'Proposed image')], sort, direction, filters),
        'error': error, 'applied': applied, 'csrf_token': token, 'writes_enabled': writes_enabled()})
    return set_cookie(request, response, token)


@router.get('/image-aliases/rematch')
def rematch_list(request: Request, name: str = Query('', max_length=100), page: int = Query(1, ge=1),
                 sort: Literal['recipe', 'ingredient', 'current', 'proposed'] = 'recipe',
                 direction: Literal['asc', 'desc'] = 'asc', applied: int = Query(0, ge=0, le=50),
                 recipe_query: str = Query('', max_length=200), current: str = Query('', max_length=100),
                 scope: Literal['changes', 'all'] = 'changes',
                 session: Session = Depends(get_session)):
    return render_rematches(request, session, name, page, sort, direction, applied=applied,
                            recipe_query=recipe_query, current=current, scope=scope)


@router.post('/image-aliases/rematch')
async def rematch_apply(request: Request, session: Session = Depends(get_session)):
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 131072:
            raise HTTPException(413, 'Image selection is too large.')
        chunks.append(chunk)
    request._body = b''.join(chunks)
    if request._body.count(b'&') > 60:
        raise HTTPException(413, 'Too many image selections.')
    async with request.form(max_files=0, max_fields=60) as form:
        check_token(request, str(form.get('csrf_token', '')))
        name = str(form.get('name', ''))
        recipe_query, current = str(form.get('recipe_query', '')), str(form.get('current', ''))
        scope = str(form.get('scope', 'changes'))
        try:
            page = int(str(form.get('page', '1')))
        except ValueError:
            raise HTTPException(422, 'Invalid page.')
        if page < 1 or len(recipe_query) > 200 or len(current) > 100 or scope not in ('changes', 'all'):
            raise HTTPException(422, 'Invalid image review filters.')
        sort, direction = str(form.get('sort', 'recipe')), str(form.get('direction', 'asc'))
        if len(name) > 100 or sort not in ('recipe', 'ingredient', 'current', 'proposed') or direction not in ('asc', 'desc'):
            raise HTTPException(422, 'Invalid image review parameters.')
        try:
            count = await run_in_threadpool(apply_selected, [str(v) for v in form.getlist('selected')])
        except RematchError as exc:
            return await run_in_threadpool(render_rematches, request, session, name, page, sort, direction, str(exc), exc.status,
                                             recipe_query=recipe_query, current=current, scope=scope)
    return RedirectResponse('/image-aliases/rematch?' + urlencode(
        {'name': name, 'sort': sort, 'direction': direction, 'applied': count,
         'recipe_query': recipe_query, 'current': current, 'scope': scope, 'page': page}), status_code=303)
