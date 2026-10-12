"""Dev-only management of ingredient image aliases, independent of search synonyms."""
from urllib.parse import quote, urlencode
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from .activity import csrf_context, set_cookie
from .database import writes_enabled
from .editor_routes import check_token
from .image_aliases import Matcher, image_url, load_catalogue, normalize, revision, save_entry
from .sorting import table_headers

router = APIRouter()


@router.get('/image-aliases')
def alias_list(request: Request, q: str = Query('', max_length=200),
               page: int = Query(1, ge=1), sample: str = Query('', max_length=1000),
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
    matched = Matcher(values).match(sample) if sample.strip() else None
    token = csrf_context(request)
    response = templates.TemplateResponse(request=request, name='image_aliases.html', context={
        'rows': [{'name': name, 'aliases': values[name], 'image': image_url(name),
                  'edit_url': '/image-aliases/edit?name=' + quote(name, safe='')}
                 for name in names[(page - 1) * 50:page * 50]],
        'q': q, 'page': page, 'pages': pages, 'total': len(names),
        'query_string': urlencode({'q': q, 'sample': sample, 'sort': sort, 'direction': direction}),
        'sort': sort, 'direction': direction,
        'headers': table_headers('/image-aliases', [('image', 'Image'), ('name', 'Official image name'),
            ('aliases', 'Aliases')], sort, direction, {'q': q, 'sample': sample}),
        'sample': sample, 'matched': matched, 'matched_image': image_url(matched) if matched else None,
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
    return RedirectResponse('/image-aliases', status_code=303)
