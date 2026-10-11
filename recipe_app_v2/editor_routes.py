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
from .editor import choices, empty_row, form_values, submitted_values, validate
from .models import Recipe
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


def render(request, session, recipe, values=None, errors=None, reviewed=False, token=None, status=200):
    from .main import templates
    cookie = request.cookies.get(COOKIE, '')
    token = token or (cookie if token_valid(cookie) else new_token())
    context = choices(session)
    context.update(recipe=recipe, values=values if values is not None else form_values(session, recipe),
                   errors=errors or [], reviewed=reviewed, csrf_token=token,
                   row=empty_row(), writes_enabled=writes_enabled())
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
        intent = str(form.get('intent', 'save' if writes_enabled() else 'review'))
        if intent == 'save' and not writes_enabled():
            raise HTTPException(403, 'Saving to the dev database is disabled.')
        if not errors and intent == 'save':
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
                      reviewed=not errors, token=token, status=422 if errors else 200)


@router.post('/recipes/new')
async def submit_new(request: Request, session: Session = Depends(get_session)):
    return await submit(request, session, None)


@router.post('/recipes/{recipe_id}/edit')
async def submit_edit(recipe_id: int, request: Request, session: Session = Depends(get_session)):
    recipe = await run_in_threadpool(session.get, Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(404, 'Recipe not found.')
    return await submit(request, session, recipe)
