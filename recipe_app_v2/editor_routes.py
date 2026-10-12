"""Create/edit forms with optional dev-only saves."""
import hashlib
import hmac
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from .database import get_session, writes_enabled
from .editor import choices, empty_row, form_values, submitted_values, validate, recipe_rows, version_for
from .models import Recipe, Recipe_Ingredient
from .image_aliases import Matcher, image_url
from .ingredient_rematch import sign_preview, read_preview
from .recipe_saves import SaveError, save_recipe
from .uploads import MAX_UPLOAD, image_bytes, pdf_bytes

router = APIRouter()
SECRET = secrets.token_bytes(32)
COOKIE = 'recipe_editor_csrf'


def new_token():
    value = f'{int(time.time())}.{secrets.token_hex(16)}'
    return value + '.' + hmac.new(SECRET, value.encode(), hashlib.sha256).hexdigest()


def token_valid(token):
    try:
        value, signature = token.rsplit('.', 1)
        age = time.time() - int(value.split('.')[0])
        expected = hmac.new(SECRET, value.encode(), hashlib.sha256).hexdigest()
        return 0 <= age <= 7200 and hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


def check_token(request, token):
    cookie = request.cookies.get(COOKIE, '')
    if not hmac.compare_digest(token, cookie) or not token_valid(token):
        raise HTTPException(403, 'Reload the form before submitting.')
    origin = request.headers.get('origin')
    if origin and origin != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Submit the form from this application.')


def render(request, session, recipe, values=None, errors=None, token=None, status=200):
    from .main import templates
    cookie = request.cookies.get(COOKIE, '')
    token = token or (cookie if token_valid(cookie) else new_token())
    context = choices(session)
    context.update(recipe=recipe, values=values if values is not None else form_values(session, recipe),
                   errors=errors or [], csrf_token=token,
                   row=empty_row(), writes_enabled=writes_enabled())
    existing = {str(row.recipe_ingredient_id): row for row in recipe_rows(session, recipe.recipe_id)[0]} if recipe else {}
    for row in context['values']['rows']:
        old = existing.get(row['id'])
        row['image_name'] = (old.name_official or 'default_ingredient') if old else ''
        row['image_url'] = image_url(row['image_name'])
        row['selected_name'] = ''
        if row.get('image_token'):
            try:
                row['selected_name'] = read_preview(row['image_token'])['target']
            except ValueError:
                pass
        row['selected_url'] = image_url(row['selected_name'])
    partial = request.headers.get('HX-Request') == 'true'
    response = templates.TemplateResponse(request=request,
        name='_editor.html' if partial else 'editor.html', context=context, status_code=status)
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=7200,
                        secure=request.url.scheme == 'https')
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/recipes/new')
def new_recipe(request: Request, session: Session = Depends(get_session)):
    return render(request, session, None)


@router.get('/editor/ingredient-row')
def ingredient_row(request: Request):
    from .main import templates
    return templates.TemplateResponse(request=request, name='_ingredient_row.html', context={'row': empty_row()})


@router.post('/editor/ingredient-image-preview')
async def ingredient_image_preview(request: Request, session: Session = Depends(get_session)):
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 4096:
            raise HTTPException(413, 'Image preview request is too large.')
        chunks.append(chunk)
    import json
    try:
        values = json.loads(b''.join(chunks))
        if not isinstance(values, dict):
            raise ValueError()
        check_token(request, str(values.get('csrf_token', '')))
        recipe_id, row_id = int(values['recipe_id']), int(values['row_id'])
        name, version = str(values['name']).strip(), str(values['version'])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, 'Invalid ingredient preview.')
    if not writes_enabled():
        raise HTTPException(403, 'Dev saves are disabled.')
    if not name or len(name) > 100:
        raise HTTPException(422, 'Enter an ingredient name of up to 100 characters.')
    def preview():
        recipe = session.get(Recipe, recipe_id)
        ingredient = session.get(Recipe_Ingredient, row_id)
        if recipe is None or ingredient is None or ingredient.recipe_id != recipe_id:
            raise HTTPException(404, 'Ingredient not found in this recipe.')
        ingredients, instructions = recipe_rows(session, recipe_id)
        if version_for(recipe, ingredients, instructions) != version:
            raise HTTPException(409, 'The recipe changed. Reload the edit page before re-matching.')
        if ingredient.is_group_header:
            raise HTTPException(422, 'Group headings do not have ingredient images.')
        matcher = Matcher()
        target = matcher.match(name)
        token = sign_preview(recipe_id, row_id, name, version, matcher.version, target) if target != 'default_ingredient' else ''
        return {'name': target, 'image': image_url(target), 'token': token,
                'changed': target != (ingredient.name_official or 'default_ingredient')}
    return await run_in_threadpool(preview)


@router.get('/recipes/{recipe_id}/edit')
def edit_recipe(recipe_id: int, request: Request, session: Session = Depends(get_session)):
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(404, 'Recipe not found.')
    return render(request, session, recipe)


async def submit(request, session, recipe):
    # Bound the entire encoded body, including multipart overhead. Existing
    # Starlette's urlencoded parser does not enforce max_fields by itself.
    size = 0
    chunks = []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 18 * 1024 * 1024:
            raise HTTPException(413, 'The recipe form is too large.')
        chunks.append(chunk)
    request._body = b''.join(chunks)
    if (request.headers.get('content-type', '').split(';')[0] == 'application/x-www-form-urlencoded'
            and request._body.count(b'&') >= 2000):
        raise HTTPException(413, 'Too many recipe form fields.')
    async with request.form(max_files=2, max_fields=2000, max_part_size=60000) as form:
        token = str(form.get('csrf_token', ''))
        check_token(request, token)
        if not writes_enabled():
            raise HTTPException(403, 'Saving to the dev database is disabled.')
        if form.get('intent') not in (None, 'save'):
            raise HTTPException(400, 'This form has changed. Reload it before submitting.')
        try:
            values = submitted_values(form)
        except ValueError as exc:
            return render(request, session, recipe, errors=[str(exc)], token=token, status=422)
        options = await run_in_threadpool(choices, session)
        clean, errors = await run_in_threadpool(validate, values, options)
        image, pdf = None, None
        for key, validator in (('image', image_bytes), ('pdf', pdf_bytes)):
            upload = form.get(key)
            if isinstance(upload, UploadFile) and upload.filename:
                data = await upload.read(MAX_UPLOAD + 1)
                try:
                    validated = await run_in_threadpool(validator, data)
                    if key == 'image':
                        image = validated
                    else:
                        pdf = validated
                except ValueError as exc:
                    errors.append(str(exc))
        if not errors:
            try:
                recipe_id = await run_in_threadpool(save_recipe,
                    recipe.recipe_id if recipe else None, values, image, pdf)
            except SaveError as exc:
                return render(request, session, recipe, values=values, errors=exc.messages,
                              token=token, status=exc.status)
            except OSError:
                return render(request, session, recipe, values=values,
                    errors=['Uploads could not be stored. Nothing was saved; check the dev upload folder.'],
                    token=token, status=503)
            except SQLAlchemyError as exc:
                logging.getLogger(__name__).error('Dev recipe save failed (%s)', type(exc).__name__)
                return render(request, session, recipe, values=values,
                    errors=['The dev database could not save this recipe. Your entered values are shown below.'],
                    token=token, status=503)
            target = f'/recipes/{recipe_id}'
            if request.headers.get('HX-Request') == 'true':
                return Response(status_code=200, headers={'HX-Redirect': target})
            return RedirectResponse(target, status_code=303)
        return render(request, session, recipe, values=values, errors=errors,
                      token=token, status=422)


@router.post('/recipes/new')
async def submit_new(request: Request, session: Session = Depends(get_session)):
    return await submit(request, session, None)


@router.post('/recipes/{recipe_id}/edit')
async def submit_edit(recipe_id: int, request: Request, session: Session = Depends(get_session)):
    recipe = await run_in_threadpool(session.get, Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(404, 'Recipe not found.')
    return await submit(request, session, recipe)
