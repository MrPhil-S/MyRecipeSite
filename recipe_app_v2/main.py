import logging
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Path as PathParameter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import ROOT, dev_database_url
from .database import get_session
from .models import Recipe, Recipe_Ingredient, recipe_cooked_date
from .recipes import detail_context
from .search import search_filters

PACKAGE = Path(__file__).resolve().parent
# Validate the target at import time, without opening a database connection.
dev_database_url()
app = FastAPI(title="My Recipes preview", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
# Serve explicit legacy asset directories, never templates or write routes.
images = ROOT / "myrecipes" / "static" / "recipe_images"
if images.is_dir():
    app.mount("/recipe-images", StaticFiles(directory=images), name="recipe_images")
for route, folder in (("ingredient-images", "ingredient_images"), ("source-pdfs", "custom_prints")):
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


@app.exception_handler(SQLAlchemyError)
async def database_unavailable(request: Request, exc: SQLAlchemyError):
    # DB exception strings can contain credentials and SQL parameters.
    logging.getLogger(__name__).error("Dev database request failed (%s)", type(exc).__name__)
    return HTMLResponse("<h1>Recipe database unavailable</h1><p>Check the dev database connection.</p>", status_code=503)


@app.get("/health")
def health(session: Session = Depends(get_session)):
    session.execute(select(1)).scalar_one()
    return {"status": "ok", "database": "MyRecipes_DEV", "read_only": True}


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
    context = {"recipes": rows, "total": total, "page": page, "pages": pages, "sort": sort, "q": q}
    partial = (request.headers.get("HX-Request") == "true"
               and request.headers.get("HX-History-Restore-Request") != "true")
    template = "_recipes.html" if partial else "index.html"
    return templates.TemplateResponse(request=request, name=template, context=context)


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
