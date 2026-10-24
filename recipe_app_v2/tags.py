"""Management of the existing collection, cuisine and synonym tables."""
import hashlib
import json
import logging
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .database import get_session, get_write_engine, writes_enabled
from .editor_routes import COOKIE, check_token, new_token, token_valid
from .models import Collection, Cuisine, Ingredient_Synonym, Recipe, recipe_collection
from .search import synonym_groups
from .sorting import table_headers

Kind = Literal['collections', 'cuisines', 'synonyms']
Action = Literal['edit', 'delete']
SPECS = {
    'collections': (Collection, 'collection_id', [('collection_name', 'Name', 30)], 'collection'),
    'cuisines': (Cuisine, 'cuisine_id', [('cuisine_name', 'Name', 30)], 'cuisine'),
    'synonyms': (Ingredient_Synonym, 'ingredient_synonym_id',
                 [('primary_term', 'Ingredient', 100), ('secondary_term', 'Synonym', 100)], 'synonym'),
}
router = APIRouter()


def linked_recipes(session, kind, tag_id):
    if kind == 'collections':
        return sorted(set(session.scalars(select(recipe_collection.c.recipe_id).where(
            recipe_collection.c.collection_id == tag_id)).all()))
    if kind == 'cuisines':
        return session.scalars(select(Recipe.recipe_id).where(
            Recipe.cuisine_id == tag_id).order_by(Recipe.recipe_id)).all()
    return []


def revision(session, kind, tag):
    values = {column.name: getattr(tag, column.name) for column in tag.__table__.columns}
    values['recipes'] = linked_recipes(session, kind, getattr(tag, SPECS[kind][1]))
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


class TagError(Exception):
    def __init__(self, message, status=422):
        self.message, self.status = message, status


def save_tag(kind, tag_id, action, values, version):
    if not writes_enabled():
        raise TagError('Tag changes are currently disabled.', 403)
    model, id_field, fields, singular = SPECS[kind]
    with Session(get_write_engine(), autoflush=False) as session:
        tag = None
        if tag_id is not None:
            tag = session.scalar(select(model).where(getattr(model, id_field) == tag_id).with_for_update())
            if tag is None:
                raise TagError('Tag not found.', 404)
            if revision(session, kind, tag) != version:
                raise TagError('This tag or its assignments changed. Reload before continuing.', 409)
        if action == 'delete':
            if tag is None:
                raise TagError('Tag not found.', 404)
            if kind == 'collections':
                session.execute(delete(recipe_collection).where(recipe_collection.c.collection_id == tag_id))
            elif kind == 'cuisines':
                session.execute(update(Recipe).where(Recipe.cuisine_id == tag_id).values(cuisine_id=None))
            session.delete(tag)
        else:
            aliases = []
            if kind == 'synonyms':
                aliases = [name.strip() for name in values['secondary_term'].splitlines() if name.strip()]
                if not aliases or len(aliases) > 50 or any(len(name) > 100 for name in aliases):
                    raise TagError('Enter 1–50 other names, one per line, with up to 100 characters each.')
                if len({name.lower() for name in aliases}) != len(aliases):
                    raise TagError('Each other name must be different.')
            for name, label, limit in fields:
                if kind == 'synonyms' and name == 'secondary_term':
                    continue
                if not values[name] or len(values[name]) > limit:
                    raise TagError(f'{label} must contain 1–{limit} characters.')
            if kind == 'synonyms':
                for alias in aliases:
                    if values['primary_term'].lower() == alias.lower():
                        raise TagError('Ingredient and other names must be different.')
                    forward = (func.lower(func.trim(model.primary_term)) == values['primary_term'].lower()) & (
                        func.lower(func.trim(model.secondary_term)) == alias.lower())
                    reverse = (func.lower(func.trim(model.primary_term)) == alias.lower()) & (
                        func.lower(func.trim(model.secondary_term)) == values['primary_term'].lower())
                    if session.scalar(select(getattr(model, id_field)).where(
                            or_(forward, reverse), getattr(model, id_field) != (tag_id or 0)).limit(1)) is not None:
                        raise TagError(f'The link to {alias} already exists.')
                if tag is None:
                    tag = model()
                    session.add(tag)
                tag.primary_term, tag.secondary_term = values['primary_term'], aliases[0]
                session.add_all(model(primary_term=values['primary_term'], secondary_term=alias) for alias in aliases[1:])
                session.commit()
                return
            conditions = [func.lower(func.trim(getattr(model, name))) == values[name].lower()
                          for name, _, _ in fields]
            duplicate = conditions[0]
            existing = session.scalar(select(getattr(model, id_field)).where(
                duplicate, getattr(model, id_field) != (tag_id or 0)).limit(1))
            if existing is not None:
                raise TagError(f'That {singular} already exists.')
            if tag is None:
                tag = model()
                session.add(tag)
            for name, _, _ in fields:
                setattr(tag, name, values[name])
        session.commit()


def render_form(request, session, kind, tag=None, action='edit', values=None, error=None,
                version=None, status=200):
    from .main import templates
    model, id_field, fields, singular = SPECS[kind]
    cookie = request.cookies.get(COOKIE, '')
    token = cookie if token_valid(cookie) else new_token()
    context = {'kind': kind, 'singular': singular, 'fields': fields, 'tag': tag,
        'tag_id': getattr(tag, id_field) if tag else None, 'action': action,
        'values': values if values is not None else {name: getattr(tag, name) if tag else '' for name, _, _ in fields},
        'version': version if version is not None else revision(session, kind, tag) if tag else '',
        'assigned': len(linked_recipes(session, kind, getattr(tag, id_field))) if tag else 0,
        'error': error, 'csrf_token': token, 'writes_enabled': writes_enabled()}
    response = templates.TemplateResponse(request=request,
        name=('_tag_delete.html' if action == 'delete' and request.headers.get('HX-Target') == 'tag-delete-content'
              else '_tag_form.html') if request.headers.get('HX-Request') == 'true' else 'tag_form.html',
        context=context, status_code=status)
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=7200,
                        secure=request.url.scheme == 'https')
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/tags')
def tags_home():
    return RedirectResponse('/tags/collections', status_code=303)


@router.get('/tags/{kind}')
def tag_list(request: Request, kind: Kind, q: str = Query('', max_length=200),
             page: int = Query(1, ge=1), session: Session = Depends(get_session),
             sort: Literal['name', 'recipes', 'secondary_term'] = 'name',
             direction: Literal['asc', 'desc'] = 'asc'):
    from .main import templates
    model, id_field, fields, singular = SPECS[kind]
    columns = [('name', fields[0][1])]
    columns.append(('secondary_term', 'Synonym') if kind == 'synonyms' else ('recipes', 'Recipes'))
    if sort not in dict(columns):
        raise HTTPException(422, 'Invalid sort column for this table.')
    if sort == 'recipes' and kind == 'collections':
        ordering = select(func.count(func.distinct(recipe_collection.c.recipe_id))).where(
            recipe_collection.c.collection_id == Collection.collection_id).scalar_subquery()
    elif sort == 'recipes':
        ordering = select(func.count()).select_from(Recipe).where(
            Recipe.cuisine_id == Cuisine.cuisine_id).scalar_subquery()
    else:
        ordering = getattr(model, fields[0][0] if sort == 'name' else sort)
    order = lambda expression: expression.asc() if direction == 'asc' else expression.desc()
    filters = [or_(*(func.lower(getattr(model, field)).contains(q.strip().lower(), autoescape=True)
                    for field, _, _ in fields))] if q.strip() else []
    total = session.scalar(select(func.count()).select_from(model).where(*filters))
    pages = max(1, (total + 49) // 50)
    page = min(page, pages)
    tags = session.scalars(select(model).where(*filters).order_by(
        order(ordering), *(order(getattr(model, field)) for field, _, _ in fields), order(getattr(model, id_field))
    ).offset((page - 1) * 50).limit(50)).all()
    ids = [getattr(tag, id_field) for tag in tags]
    counts = {}
    if ids and kind == 'collections':
        counts = dict(session.execute(select(recipe_collection.c.collection_id,
            func.count(func.distinct(recipe_collection.c.recipe_id))).where(
                recipe_collection.c.collection_id.in_(ids)).group_by(recipe_collection.c.collection_id)).all())
    elif ids and kind == 'cuisines':
        counts = dict(session.execute(select(Recipe.cuisine_id, func.count()).where(
            Recipe.cuisine_id.in_(ids)).group_by(Recipe.cuisine_id)).all())
    rows = [{'id': getattr(tag, id_field), 'values': [getattr(tag, field) for field, _, _ in fields],
             'assigned': counts.get(getattr(tag, id_field), 0)} for tag in tags]
    cookie = request.cookies.get(COOKIE, '')
    token = cookie if token_valid(cookie) else new_token()
    response = templates.TemplateResponse(request=request, name='tags.html', context={
        'csrf_token': token,
        'kind': kind, 'singular': singular, 'fields': fields, 'rows': rows, 'q': q,
        'page': page, 'pages': pages, 'total': total,
        'query_string': urlencode({'q': q, 'sort': sort, 'direction': direction}),
        'sort': sort, 'direction': direction,
        'headers': table_headers('/tags/' + kind, columns, sort, direction, {'q': q}),
        'writes_enabled': writes_enabled(),
        'synonym_groups': [group for group in synonym_groups(session)
                           if not q.strip() or any(q.strip().lower() in name for name in group)] if kind == 'synonyms' else []})
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=7200,
                        secure=request.url.scheme == 'https')
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/tags/{kind}/new')
def new_tag(request: Request, kind: Kind, session: Session = Depends(get_session)):
    return render_form(request, session, kind)


@router.get('/tags/{kind}/{tag_id}/{action}')
def tag_form(request: Request, kind: Kind, action: Action, tag_id: int = Path(ge=1),
             session: Session = Depends(get_session)):
    tag = session.get(SPECS[kind][0], tag_id)
    if tag is None:
        raise HTTPException(404, 'Tag not found.')
    return render_form(request, session, kind, tag, action)


async def submit_tag(request, session, kind, tag_id=None, action='edit'):
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 65536:
            raise HTTPException(413, 'Tag form is too large.')
        chunks.append(chunk)
    request._body = b''.join(chunks)
    if request._body.count(b'&') > 10:
        raise HTTPException(413, 'Too many form fields.')
    async with request.form(max_files=0, max_fields=10) as form:
        check_token(request, str(form.get('csrf_token', '')))
        tag = await run_in_threadpool(session.get, SPECS[kind][0], tag_id) if tag_id else None
        if tag_id and tag is None:
            raise HTTPException(404, 'Tag not found.')
        values = {name: getattr(tag, name) if action == 'delete' and tag else str(form.get(name, '')).strip()
                  for name, _, _ in SPECS[kind][2]}
        version = str(form.get('version', ''))
        try:
            await run_in_threadpool(save_tag, kind, tag_id, action, values, version)
        except TagError as exc:
            return render_form(request, session, kind, tag, action, values, exc.message, version, exc.status)
        except SQLAlchemyError as exc:
            logging.getLogger(__name__).error('Dev tag save failed (%s)', type(exc).__name__)
            return render_form(request, session, kind, tag, action, values,
                               'The tag could not be saved. Try again.', version, 503)
        target = '/tags/' + kind
        if request.headers.get('HX-Request') == 'true':
            return Response(headers={'HX-Redirect': target})
        return RedirectResponse(target, status_code=303)


@router.post('/tags/{kind}/new')
async def create_tag(request: Request, kind: Kind, session: Session = Depends(get_session)):
    return await submit_tag(request, session, kind)


@router.post('/tags/{kind}/{tag_id}/{action}')
async def change_tag(request: Request, kind: Kind, action: Action, tag_id: int = Path(ge=1),
                     session: Session = Depends(get_session)):
    return await submit_tag(request, session, kind, tag_id, action)
