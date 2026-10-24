"""Cooking, visit, plan and recipe deletion operations."""
import hashlib
import json
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .database import get_session, get_write_engine, writes_enabled
from .editor import recipe_rows, version_for
from .editor_routes import COOKIE, check_token, new_token, token_valid
from .sorting import SortOrder
from .collections import favorite_membership
from .cooked_history import can_undo_cooked
from .models import (Collection, Recipe, Recipe_Ingredient, Recipe_Instruction, Recipe_Plan_Date,
                     recipe_collection, recipe_cooked_date, recipe_view_date)

router = APIRouter()
CHILDREN = (Recipe_Ingredient, Recipe_Instruction, Recipe_Plan_Date, recipe_cooked_date, recipe_view_date)


def csrf_context(request):
    cookie = request.cookies.get(COOKIE, '')
    return cookie if token_valid(cookie) else new_token()


def set_cookie(request, response, token):
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=7200,
                        secure=request.url.scheme == 'https')
    response.headers['Cache-Control'] = 'no-store'
    return response


def record_visit(recipe_id):
    if not writes_enabled():
        return
    with Session(get_write_engine()) as session:
        recipe = session.scalar(select(Recipe).where(Recipe.recipe_id == recipe_id).with_for_update())
        if recipe is not None:
            session.add(recipe_view_date(recipe_id=recipe_id))
            session.commit()


def mutate(recipe_id, action):
    if not writes_enabled():
        raise HTTPException(403, 'Recipe changes are currently disabled.')
    with Session(get_write_engine()) as session:
        recipe = session.scalar(select(Recipe).where(Recipe.recipe_id == recipe_id).with_for_update())
        if recipe is None:
            raise HTTPException(404, 'Recipe not found.')
        active = select(Recipe_Plan_Date.recipe_plan_date_id).where(
            Recipe_Plan_Date.recipe_id == recipe_id, Recipe_Plan_Date.removed_dt.is_(None))
        if action == 'cooked':
            session.add(recipe_cooked_date(recipe_id=recipe_id))
        elif action == 'undo-cooked':
            latest = session.scalar(select(recipe_cooked_date).where(
                recipe_cooked_date.recipe_id == recipe_id).order_by(
                recipe_cooked_date.recipe_cooked_dt.desc(),
                recipe_cooked_date.recipe_cooked_date_id.desc()).limit(1).with_for_update())
            if not can_undo_cooked(latest.recipe_cooked_dt if latest else None,
                                   session.scalar(select(func.current_timestamp()))):
                raise HTTPException(409, 'Only cooking records from the last 24 hours can be undone.')
            session.delete(latest)
        elif action == 'plan-add':
            if session.scalar(active.limit(1)) is None:
                session.add(Recipe_Plan_Date(recipe_id=recipe_id))
        elif action == 'plan-remove':
            session.execute(update(Recipe_Plan_Date).where(
                Recipe_Plan_Date.recipe_id == recipe_id, Recipe_Plan_Date.removed_dt.is_(None)
            ).values(removed_dt=func.current_timestamp()))
        elif action in ('favorite-add', 'favorite-remove'):
            favorites = session.scalars(select(Collection).where(
                func.lower(func.trim(Collection.collection_name)).in_(('favorites', 'favorite')))
                .order_by(Collection.collection_id).with_for_update()).all()
            if action == 'favorite-add':
                if not favorites:
                    favorites = [Collection(collection_name='Favorites')]
                    session.add(favorites[0])
                if not any(c in recipe.collections for c in favorites):
                    recipe.collections.append(favorites[0])
            else:
                recipe.collections[:] = [c for c in recipe.collections if c not in favorites]
        session.commit()


def deletion_version(session, recipe):
    ingredients, instructions = recipe_rows(session, recipe.recipe_id)
    history = []
    for model in (recipe_cooked_date, recipe_view_date, Recipe_Plan_Date):
        rows = session.scalars(select(model).where(model.recipe_id == recipe.recipe_id)
                               .order_by(*model.__table__.primary_key.columns)).all()
        history.append([{column.name: getattr(row, column.name) for column in model.__table__.columns}
                        for row in rows])
    return hashlib.sha256((version_for(recipe, ingredients, instructions) +
        json.dumps(history, sort_keys=True, default=str)).encode()).hexdigest()


def delete_recipe_data(recipe_id, version):
    if not writes_enabled():
        raise HTTPException(403, 'Recipe changes are currently disabled.')
    with Session(get_write_engine(), autoflush=False) as session:
        recipe = session.scalar(select(Recipe).where(Recipe.recipe_id == recipe_id).with_for_update())
        if recipe is None:
            raise HTTPException(404, 'Recipe not found.')
        if deletion_version(session, recipe) != version:
            raise HTTPException(409, 'This recipe or its history changed. Reload the confirmation before deleting.')
        for model in CHILDREN:
            session.execute(delete(model).where(model.recipe_id == recipe_id))
        session.execute(delete(recipe_collection).where(recipe_collection.c.recipe_id == recipe_id))
        # The fingerprint loaded collections; refresh that relationship after
        # removing links so ORM deletion does not attempt to delete them twice.
        session.expire(recipe, ['collections'])
        session.delete(recipe)
        session.commit()


def safe_return(value):
    if any(c in value for c in ('\r', '\n', '\\')):
        raise HTTPException(422, 'Invalid return location.')
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or not (parts.path in ('/', '/plan') or
            parts.path.startswith('/recipes/') and parts.path[9:].isdigit()):
        raise HTTPException(422, 'Invalid return location.')
    return value


async def read_form(request):
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 8192:
            raise HTTPException(413, 'Recipe action is too large.')
        chunks.append(chunk)
    request._body = b''.join(chunks)
    if request._body.count(b'&') > 12:
        raise HTTPException(413, 'Too many form fields.')
    form = await request.form(max_files=0, max_fields=12)
    check_token(request, str(form.get('csrf_token', '')))
    return form


@router.post('/recipes/{recipe_id}/actions/{action}')
async def recipe_action(request: Request, recipe_id: int,
                        action: Literal['cooked', 'undo-cooked', 'plan-add', 'plan-remove', 'favorite-add', 'favorite-remove']):
    form = await read_form(request)
    target = safe_return(str(form.get('return_to', f'/recipes/{recipe_id}')))
    await run_in_threadpool(mutate, recipe_id, action)
    if request.headers.get('HX-Request') == 'true':
        path = urlsplit(target).path
        selector = '#recipes' if path == '/' else '#meal-plan' if path == '/plan' else '#recipe-detail-page'
        location = {'path': target, 'target': selector, 'swap': 'outerHTML'}
        return Response(status_code=204, headers={'HX-Location': json.dumps(location)})
    return RedirectResponse(target, status_code=303)


@router.get('/plan')
def meal_plan(request: Request, session: Session = Depends(get_session)):
    from .main import templates
    active = select(Recipe_Plan_Date.recipe_id, func.max(Recipe_Plan_Date.added_dt).label('added')).where(
        Recipe_Plan_Date.removed_dt.is_(None)).group_by(Recipe_Plan_Date.recipe_id).subquery()
    cooked = select(recipe_cooked_date.recipe_id, func.count().label('cook_count'),
        func.max(recipe_cooked_date.recipe_cooked_dt).label('last_cooked')).group_by(
        recipe_cooked_date.recipe_id).subquery()
    last_marked_cook = select(recipe_cooked_date.recipe_cooked_dt).where(
        recipe_cooked_date.recipe_id == Recipe.recipe_id).order_by(
        recipe_cooked_date.recipe_cooked_dt.desc(), recipe_cooked_date.recipe_cooked_date_id.desc()
    ).limit(1).scalar_subquery()
    rows = session.execute(select(Recipe, active.c.added,
        func.coalesce(cooked.c.cook_count, 0).label('cook_count'), cooked.c.last_cooked,
        last_marked_cook.label('last_marked_cook_dt'),
        favorite_membership().label('favorite'), (active.c.recipe_id.is_not(None)).label('planned'))
        .join(active, Recipe.recipe_id == active.c.recipe_id)
        .outerjoin(cooked, cooked.c.recipe_id == Recipe.recipe_id)
                           .order_by(active.c.added.desc(), Recipe.recipe_id.desc())).all()
    grouped = {}
    server_now = session.scalar(select(func.current_timestamp()))
    undo_cooked_ids = {row.Recipe.recipe_id for row in rows
                       if can_undo_cooked(row.last_marked_cook_dt, server_now)}
    for row in rows:
        added = row.added
        group = grouped.setdefault(added.date(), {'age': max(0, (server_now - added).days), 'recipes': []})
        group['recipes'].append(row)
    token = csrf_context(request)
    partial = request.headers.get('HX-Request') == 'true' and request.headers.get('HX-History-Restore-Request') != 'true'
    response = templates.TemplateResponse(request=request, name='_plan_fragment.html' if partial else 'plan.html', context={
        'groups': grouped, 'csrf_token': token, 'writes_enabled': writes_enabled(), 'total': len(rows),
        'undo_cooked_ids': undo_cooked_ids,
        'planned_count': len(rows)})
    return set_cookie(request, response, token)


@router.get('/recipes/{recipe_id}/delete')
def delete_confirmation(request: Request, recipe_id: int, page: int = Query(1, ge=1),
                        sort: SortOrder = 'recent',
                        q: str = Query('', max_length=200), collection_id: int = Query(0, ge=-3), per_page: int = 24,
                        cuisine_id: int = Query(0, ge=0),
                        session: Session = Depends(get_session)):
    from .main import templates, list_url
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(404, 'Recipe not found.')
    token = csrf_context(request)
    response = templates.TemplateResponse(request=request, name='delete_recipe.html', context={
        'recipe': recipe, 'version': deletion_version(session, recipe), 'csrf_token': token,
        'return_to': '/plan' if request.query_params.get('from_plan') == 'true' else list_url(page, sort, q, collection_id, per_page, cuisine_id),
        'cancel_to': f'/recipes/{recipe_id}' + ('?' + request.url.query if request.url.query else ''),
        'writes_enabled': writes_enabled(), 'error': None})
    return set_cookie(request, response, token)


@router.post('/recipes/{recipe_id}/delete')
async def delete_recipe(request: Request, recipe_id: int, session: Session = Depends(get_session)):
    form = await read_form(request)
    target = safe_return(str(form.get('return_to', '/')))
    try:
        await run_in_threadpool(delete_recipe_data, recipe_id, str(form.get('version', '')))
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        from .main import templates
        recipe = await run_in_threadpool(session.get, Recipe, recipe_id)
        return templates.TemplateResponse(request=request, name='delete_recipe.html', status_code=409,
            context={'recipe': recipe, 'version': str(form.get('version', '')), 'csrf_token': str(form.get('csrf_token', '')),
                'return_to': target, 'cancel_to': target, 'writes_enabled': writes_enabled(), 'error': exc.detail,
                'reload_to': f'/recipes/{recipe_id}/delete' + ('?from_plan=true' if target == '/plan' else
                    ('?' + urlsplit(target).query if urlsplit(target).query else ''))})
    return RedirectResponse(target, status_code=303)
