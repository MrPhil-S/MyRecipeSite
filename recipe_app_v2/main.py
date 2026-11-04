import logging
from pathlib import Path
from urllib.parse import urlencode
from types import SimpleNamespace

from fastapi import Depends, FastAPI, HTTPException, Path as PathParameter, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .config import ROOT, app_environment, database_url
from .database import get_session, writes_enabled
from .uploads import upload_root
from .models import Collection, Cuisine, Recipe, Recipe_Ingredient, Recipe_Plan_Date, recipe_collection, recipe_cooked_date, recipe_view_date
from .recipes import detail_context
from .search import search_filters
from .editor_routes import router as editor_router, COOKIE, check_token, new_token, token_valid
from .search_history import recent_searches, remember_search
from .tags import router as tag_router
from .activity import router as activity_router, record_visit, deletion_version
from .collections import collection_filter, favorite_membership
from .sorting import SortOrder, SORT_CHOICES
from .image_alias_routes import router as image_alias_router
from .recipe_book import router as recipe_book_router

PACKAGE = Path(__file__).resolve().parent
# Validate the target at import time, without opening a database connection.
database_url()
app = FastAPI(title="My Recipes", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
# Serve explicit legacy asset directories, never templates or write routes.
images = ROOT / "myrecipes" / "static" / "recipe_images"
@app.get('/recipe-images/{filename}')
def recipe_image(filename: str):
    if any(c in filename for c in ('/', '\\', ':')) or filename in ('.', '..'):
        raise HTTPException(404)
    for directory in (upload_root() / 'images', images):
        target = directory / filename
        if target.is_file():
            return FileResponse(target)
    raise HTTPException(404)


@app.get('/source-pdfs/{recipe_id}.pdf')
def source_pdf(recipe_id: int):
    for directory in (upload_root() / 'pdfs', ROOT / 'myrecipes/static/custom_prints'):
        target = directory / f'{recipe_id}.pdf'
        if target.is_file():
            return FileResponse(target, media_type='application/pdf',
                                headers={'Content-Disposition': f'attachment; filename="{recipe_id}.pdf"'})
    raise HTTPException(404)


for route, folder in (("ingredient-images", "ingredient_images"),):
    directory = ROOT / "myrecipes" / "static" / folder
    if directory.is_dir():
        app.mount("/" + route, StaticFiles(directory=directory), name=folder)
templates = Jinja2Templates(directory=PACKAGE / "templates")


def list_url(page, sort, q="", collection_id=0, per_page=24, cuisine_id=0):
    values = {"page": page, "sort": sort}
    if q:
        values["q"] = q
    if collection_id:
        values['collection_id'] = collection_id
    if per_page != 24:
        values['per_page'] = per_page
    if cuisine_id:
        values['cuisine_id'] = cuisine_id
    return "/?" + urlencode(values)


templates.env.globals["list_url"] = list_url
app.include_router(editor_router)
app.include_router(tag_router)
app.include_router(activity_router)
app.include_router(image_alias_router)
app.include_router(recipe_book_router)


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request: Request, exc: SQLAlchemyError):
    # DB exception strings can contain credentials and SQL parameters.
    logging.getLogger(__name__).error("Recipe database request failed (%s)", type(exc).__name__)
    return HTMLResponse("<h1>Recipe database unavailable</h1><p>Check the database connection.</p>", status_code=503)


@app.get("/health")
def health(session: Session = Depends(get_session)):
    session.execute(select(1)).scalar_one()
    return {"status": "ok", "environment": app_environment(), "database": database_url().database,
            "read_only": not writes_enabled(), "browse_read_only": True,
            "saves_enabled": writes_enabled(),
            "read_connections_read_only": True,
            "visit_tracking_enabled": writes_enabled()}


@app.get("/", response_class=HTMLResponse)
def recipe_list(
    request: Request,
    page: int = Query(1, ge=1),
    sort: SortOrder = "recent",
    q: str = Query("", max_length=200),
    session: Session = Depends(get_session),
    collection_id: int = Query(0, ge=-3, le=2147483647),
    per_page: int = 24,
    cuisine_id: int = Query(0, ge=0, le=2147483647),
):
    if per_page not in (12, 24, 48, 96):
        raise HTTPException(422, 'Choose 12, 24, 48 or 96 recipes per page.')
    page_size = per_page
    filters = search_filters(session, q)
    if collection_id:
        if collection_id not in (-1, -2, -3) and session.get(Collection, collection_id) is None:
            raise HTTPException(404, 'Collection not found.')
        filters.append(collection_filter(collection_id))
    if cuisine_id:
        if session.get(Cuisine, cuisine_id) is None:
            raise HTTPException(404, 'Cuisine not found.')
        filters.append(Recipe.cuisine_id == cuisine_id)
    total = session.scalar(select(func.count()).select_from(Recipe).where(*filters))
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    ingredients = (
        select(Recipe_Ingredient.recipe_id, func.count().label("ingredient_count"))
        .where(func.coalesce(Recipe_Ingredient.is_group_header, False) != True)
        .group_by(Recipe_Ingredient.recipe_id).subquery()
    )
    cooked = (
        select(recipe_cooked_date.recipe_id, func.count().label("cook_count"), func.max(recipe_cooked_date.recipe_cooked_dt).label('last_cooked'))
        .group_by(recipe_cooked_date.recipe_id).subquery()
    )
    visited = select(recipe_view_date.recipe_id, func.max(recipe_view_date.recipe_view_dt).label('last_visited')).group_by(recipe_view_date.recipe_id).subquery()
    ordering = {
        'name': (Recipe.name.asc(), Recipe.recipe_id.asc()),
        'recent': (Recipe.create_dt.desc(), Recipe.recipe_id.desc()),
        'cooked': (func.date(func.coalesce(cooked.c.last_cooked, Recipe.create_dt)).desc(), Recipe.recipe_id.desc()),
        'visited': (func.coalesce(visited.c.last_visited, Recipe.create_dt).desc(), Recipe.recipe_id.desc()),
        'name_desc': (Recipe.name.desc(), Recipe.recipe_id.desc()),
        'recent_asc': (Recipe.create_dt.asc(), Recipe.recipe_id.asc()),
        'cooked_asc': (func.date(func.coalesce(cooked.c.last_cooked, Recipe.create_dt)).asc(), Recipe.recipe_id.asc()),
        'visited_asc': (func.coalesce(visited.c.last_visited, Recipe.create_dt).asc(), Recipe.recipe_id.asc()),
    }[sort]
    query = (
        select(Recipe, Cuisine.cuisine_name.label('cuisine_name'), func.coalesce(ingredients.c.ingredient_count, 0).label("ingredient_count"),
               func.coalesce(cooked.c.cook_count, 0).label("cook_count"), favorite_membership().label('favorite'),
               select(Recipe_Plan_Date.recipe_plan_date_id).where(Recipe_Plan_Date.recipe_id == Recipe.recipe_id,
                   Recipe_Plan_Date.removed_dt.is_(None)).exists().label('planned'))
        .outerjoin(Cuisine, Cuisine.cuisine_id == Recipe.cuisine_id)
        .outerjoin(ingredients, Recipe.recipe_id == ingredients.c.recipe_id)
        .outerjoin(cooked, Recipe.recipe_id == cooked.c.recipe_id)
        .outerjoin(visited, Recipe.recipe_id == visited.c.recipe_id)
        .where(*filters).order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
    )
    rows = session.execute(query).all()
    cookie = request.cookies.get(COOKIE, '')
    token = cookie if token_valid(cookie) else new_token()
    context = {"recipes": rows, "total": total, "page": page, "pages": pages, "sort": sort, "q": q,
               "history_notice": getattr(request.state, 'history_notice', None), 'collection_id': collection_id,
               'csrf_token': token, 'writes_enabled': writes_enabled(), 'per_page': per_page,
               'cuisine_id': cuisine_id}
    partial = (request.headers.get("HX-Request") == "true"
               and request.headers.get("HX-History-Restore-Request") != "true")
    template = "_library_results.html" if partial else "index.html"
    context["partial"] = partial
    collection_names = {0: 'All recipes', -1: 'Never cooked', -2: 'Favorites', -3: 'Meal plan'}
    collection_label = collection_names.get(collection_id)
    if collection_id > 0:
        collection_label = session.get(Collection, collection_id).collection_name
    collection_counts = {
        0: session.scalar(select(func.count()).select_from(Recipe)) or 0,
        -1: session.scalar(select(func.count()).select_from(Recipe).where(collection_filter(-1))) or 0,
        -2: session.scalar(select(func.count()).select_from(Recipe).where(collection_filter(-2))) or 0,
        -3: session.scalar(select(func.count()).select_from(Recipe).where(collection_filter(-3))) or 0,
    }
    actual_collection_counts = dict(session.execute(select(
        recipe_collection.c.collection_id, func.count(func.distinct(recipe_collection.c.recipe_id))
    ).group_by(recipe_collection.c.collection_id)).all())
    sidebar_collections = [
        SimpleNamespace(collection_id=key, collection_name=collection_names[key], count=collection_counts[key])
        for key in (0, -2, -1, -3)
    ]
    sidebar_collections.extend(
        SimpleNamespace(collection_id=row.collection_id, collection_name=row.collection_name,
                        count=actual_collection_counts.get(row.collection_id, 0))
        for row in session.scalars(select(Collection).order_by(Collection.collection_name, Collection.collection_id)).all()
        if row.collection_name.strip().lower() not in ('favorite', 'favorites')
    )
    context.update(search_history=recent_searches(session, q), history_query=q,
                   sort_choices=SORT_CHOICES, cuisines=session.scalars(select(Cuisine).order_by(Cuisine.cuisine_name, Cuisine.cuisine_id)).all(),
                   sidebar_collections=sidebar_collections, collection_label=collection_label,
                   planned_count=collection_counts[-3])
    response = templates.TemplateResponse(request=request, name=template, context=context)
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=7200, secure=request.url.scheme == 'https')
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/search/history', response_class=HTMLResponse)
def search_history_suggestions(request: Request, q: str = Query('', max_length=200),
                               session: Session = Depends(get_session)):
    response = templates.TemplateResponse(request=request, name='_search_history.html',
        context={'search_history': recent_searches(session, q), 'history_query': q})
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.post('/search', response_class=HTMLResponse)
async def explicit_search(request: Request, session: Session = Depends(get_session)):
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > 8192:
            raise HTTPException(413, 'Search form is too large.')
        chunks.append(chunk)
    request._body = b''.join(chunks)
    if request._body.count(b'&') > 10:
        raise HTTPException(413, 'Too many search fields.')
    async with request.form(max_files=0, max_fields=10) as form:
        check_token(request, str(form.get('csrf_token', '')))
        q, sort = str(form.get('q', '')).strip(), str(form.get('sort', 'recent'))
        intent = str(form.get('intent', 'search'))
        try:
            collection_id = int(str(form.get('collection_id', '0')))
            cuisine_id = int(str(form.get('cuisine_id', '0')))
            per_page = int(str(form.get('per_page', '24')))
        except ValueError:
            raise HTTPException(422, 'Invalid collection.')
        if len(q) > 200 or sort not in dict(SORT_CHOICES) or intent not in ('search', 'sort') or not -3 <= collection_id <= 2147483647 or not 0 <= cuisine_id <= 2147483647 or per_page not in (12, 24, 48, 96):
            raise HTTPException(422, 'Invalid search form.')
        if collection_id > 0 and session.get(Collection, collection_id) is None:
            raise HTTPException(404, 'Collection not found.')
        if cuisine_id and session.get(Cuisine, cuisine_id) is None:
            raise HTTPException(404, 'Cuisine not found.')
        notice = None
        if intent == 'search':
            try:
                filters = search_filters(session, q)
                if collection_id:
                    filters.append(collection_filter(collection_id))
                if cuisine_id:
                    filters.append(Recipe.cuisine_id == cuisine_id)
                result_count = session.scalar(select(func.count()).select_from(Recipe).where(*filters))
                notice = await run_in_threadpool(remember_search, q, result_count)
            except SQLAlchemyError as exc:
                logging.getLogger(__name__).error('Search history save failed (%s)', type(exc).__name__)
                notice = 'Search history could not be saved.'
        if request.headers.get('HX-Request') != 'true':
            return RedirectResponse(list_url(1, sort, q, collection_id, per_page, cuisine_id), status_code=303)
        request.state.history_notice = notice
        response = await run_in_threadpool(recipe_list, request, 1, sort, q, session, collection_id, per_page, cuisine_id)
        response.headers['HX-Push-Url'] = list_url(1, sort, q, collection_id, per_page, cuisine_id)
        return response


@app.get("/recipes/{recipe_id}", response_class=HTMLResponse)
def recipe_detail(
    request: Request,
    recipe_id: int = PathParameter(ge=1),
    page: int = Query(1, ge=1),
    sort: SortOrder = "recent",
    q: str = Query("", max_length=200),
    session: Session = Depends(get_session),
    collection_id: int = Query(0, ge=-3),
    per_page: int = 24,
    cuisine_id: int = Query(0, ge=0),
    from_plan: bool = False,
    log_visit: bool = True,
):
    if session.get(Recipe, recipe_id) is not None and log_visit and writes_enabled() and request.headers.get("HX-Request") != "true":
        record_visit(recipe_id)
        session.rollback()  # Start a new read snapshot so the new visit is counted.
    context = detail_context(session, recipe_id)
    if context is None:
        cookie = request.cookies.get(COOKIE, '')
        token = cookie if token_valid(cookie) else new_token()
        response = templates.TemplateResponse(request=request, name="not_found.html",
            context={"page": page, "sort": sort, "q": q, "collection_id": collection_id,
                     "per_page": per_page, "cuisine_id": cuisine_id, "csrf_token": token}, status_code=404)
        response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=7200,
                            secure=request.url.scheme == 'https')
        response.headers['Cache-Control'] = 'no-store'
        return response
    cookie = request.cookies.get(COOKIE, '')
    token = cookie if token_valid(cookie) else new_token()
    context.update(page=page, sort=sort, q=q, collection_id=collection_id, per_page=per_page, cuisine_id=cuisine_id, from_plan=from_plan,
                   deletion_version=deletion_version(session, context['recipe']) if writes_enabled() else '',
                   delete_return_to='/plan' if from_plan else list_url(page, sort, q, collection_id, per_page, cuisine_id),
                   search_history=recent_searches(session, q),
                   planned_count=session.scalar(select(func.count()).select_from(Recipe).where(collection_filter(-3))) or 0,
                   csrf_token=token, writes_enabled=writes_enabled(), return_to=request.url.path + ('?' + request.url.query if request.url.query else ''))
    partial = request.headers.get("HX-Request") == "true" and request.headers.get("HX-History-Restore-Request") != "true"
    response = templates.TemplateResponse(request=request, name="_detail_fragment.html" if partial else "detail.html", context=context)
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict', max_age=7200, secure=request.url.scheme == 'https')
    response.headers['Cache-Control'] = 'no-store'
    return response
