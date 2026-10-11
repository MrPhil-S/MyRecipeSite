import logging
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, Path as PathParameter, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .config import ROOT, dev_database_url
from .database import get_session, writes_enabled
from .uploads import upload_root
from .models import Recipe, Recipe_Ingredient, recipe_cooked_date
from .recipes import detail_context
from .search import search_filters
from .editor_routes import router as editor_router, COOKIE, check_token, new_token, token_valid
from .search_history import recent_searches, remember_search

PACKAGE = Path(__file__).resolve().parent
# Validate the target at import time, without opening a database connection.
dev_database_url()
app = FastAPI(title="My Recipes preview", docs_url=None, redoc_url=None, openapi_url=None)
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


def list_url(page, sort, q=""):
    values = {"page": page, "sort": sort}
    if q:
        values["q"] = q
    return "/?" + urlencode(values)


templates.env.globals["list_url"] = list_url
app.include_router(editor_router)


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request: Request, exc: SQLAlchemyError):
    # DB exception strings can contain credentials and SQL parameters.
    logging.getLogger(__name__).error("Dev database request failed (%s)", type(exc).__name__)
    return HTMLResponse("<h1>Recipe database unavailable</h1><p>Check the dev database connection.</p>", status_code=503)


@app.get("/health")
def health(session: Session = Depends(get_session)):
    session.execute(select(1)).scalar_one()
    return {"status": "ok", "database": "MyRecipes_DEV", "read_only": not writes_enabled(),
            "browse_read_only": True, "dev_saves_enabled": writes_enabled()}


@app.get("/", response_class=HTMLResponse)
def recipe_list(
    request: Request,
    page: int = Query(1, ge=1),
    sort: Literal["recent", "name"] = "recent",
    q: str = Query("", max_length=200),
    session: Session = Depends(get_session),
):
    page_size = 24
    filters = search_filters(session, q)
    total = session.scalar(select(func.count()).select_from(Recipe).where(*filters))
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    ingredients = (
        select(Recipe_Ingredient.recipe_id, func.count().label("ingredient_count"))
        .where(func.coalesce(Recipe_Ingredient.is_group_header, False) != True)
        .group_by(Recipe_Ingredient.recipe_id).subquery()
    )
    cooked = (
        select(recipe_cooked_date.recipe_id, func.count().label("cook_count"))
        .group_by(recipe_cooked_date.recipe_id).subquery()
    )
    ordering = (Recipe.name.asc(), Recipe.recipe_id.asc()) if sort == "name" else (
        Recipe.create_dt.desc(), Recipe.recipe_id.desc()
    )
    query = (
        select(Recipe, func.coalesce(ingredients.c.ingredient_count, 0).label("ingredient_count"),
               func.coalesce(cooked.c.cook_count, 0).label("cook_count"))
        .outerjoin(ingredients, Recipe.recipe_id == ingredients.c.recipe_id)
        .outerjoin(cooked, Recipe.recipe_id == cooked.c.recipe_id)
        .where(*filters).order_by(*ordering).offset((page - 1) * page_size).limit(page_size)
    )
    rows = session.execute(query).all()
    # Do not link to legacy detail routes: they record visits in the database.
    context = {"recipes": rows, "total": total, "page": page, "pages": pages, "sort": sort, "q": q,
               "history_notice": getattr(request.state, 'history_notice', None)}
    partial = (request.headers.get("HX-Request") == "true"
               and request.headers.get("HX-History-Restore-Request") != "true")
    template = "_recipes.html" if partial else "index.html"
    if not partial:
        cookie = request.cookies.get(COOKIE, '')
        context['csrf_token'] = cookie if token_valid(cookie) else new_token()
        context.update(search_history=recent_searches(session, q), history_query=q)
    response = templates.TemplateResponse(request=request, name=template, context=context)
    if not partial:
        response.set_cookie(COOKIE, context['csrf_token'], httponly=True, samesite='strict',
                            max_age=7200, secure=request.url.scheme == 'https')
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
        if len(q) > 200 or sort not in ('recent', 'name') or intent not in ('search', 'sort'):
            raise HTTPException(422, 'Invalid search form.')
        notice = None
        if intent == 'search':
            try:
                notice = await run_in_threadpool(remember_search, q)
            except SQLAlchemyError as exc:
                logging.getLogger(__name__).error('Search history save failed (%s)', type(exc).__name__)
                notice = 'Search history could not be saved.'
        if request.headers.get('HX-Request') != 'true':
            return RedirectResponse(list_url(1, sort, q), status_code=303)
        request.state.history_notice = notice
        response = await run_in_threadpool(recipe_list, request, 1, sort, q, session)
        response.headers['HX-Push-Url'] = list_url(1, sort, q)
        return response


@app.get("/recipes/{recipe_id}", response_class=HTMLResponse)
def recipe_detail(
    request: Request,
    recipe_id: int = PathParameter(ge=1),
    page: int = Query(1, ge=1),
    sort: Literal["recent", "name"] = "recent",
    q: str = Query("", max_length=200),
    session: Session = Depends(get_session),
):
    context = detail_context(session, recipe_id)
    if context is None:
        return templates.TemplateResponse(request=request, name="not_found.html",
                                          context={"page": page, "sort": sort, "q": q}, status_code=404)
    context.update(page=page, sort=sort, q=q)
    return templates.TemplateResponse(request=request, name="detail.html", context=context)
