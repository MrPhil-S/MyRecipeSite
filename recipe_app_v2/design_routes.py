"""Database-independent studies: Python state, Jinja HTML, HTMX updates."""
import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .design_home import COLLECTIONS, CUISINES, HOME_LAYOUTS, HOME_RECIPES, LIBRARY_PALETTES
from .sorting import SORT_CHOICES

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / 'templates')
IDS = {r['id'] for r in HOME_RECIPES}
COOKIE = 'homepage_study_v1'
HISTORY_COOKIE = 'homepage_searches_v1'


def sample_history(request):
    try:
        values = json.loads(request.cookies.get(HISTORY_COOKIE, '[]'))
        return [v[:200] for v in values if isinstance(v, str)][:8] if isinstance(values, list) else []
    except (ValueError, TypeError):
        return []


def sample_state(request):
    today = date.today()
    default = {'favorites': [1, 2, 5], 'plan': {
        '1': today.isoformat(), '3': (today + timedelta(days=1)).isoformat()}}
    try:
        data = json.loads(request.cookies.get(COOKIE, 'null'))
        if not isinstance(data, dict):
            return default
        favorites = [i for i in data['favorites'] if type(i) is int and i in IDS]
        plan = {str(int(i)): date.fromisoformat(day).isoformat()
                for i, day in data['plan'].items() if int(i) in IDS}
        return {'favorites': sorted(set(favorites)), 'plan': plan}
    except (ValueError, TypeError, KeyError, AttributeError):
        return default


def context(request, state=None):
    state = state if state is not None else sample_state(request)
    query = request.query_params
    palette_id = query.get('palette', 'oxblood')
    if palette_id not in LIBRARY_PALETTES:
        palette_id = 'oxblood'
    layout = query.get('layout', 'library')
    if layout not in {row[0] for row in HOME_LAYOUTS}:
        layout = 'library'
    collection = query.get('collection', 'All recipes')
    if collection not in COLLECTIONS:
        collection = 'All recipes'
    cuisine = query.get('cuisine', '')
    if cuisine not in CUISINES:
        cuisine = ''
    sort = query.get('sort', 'recent')
    if sort not in dict(SORT_CHOICES):
        sort = 'recent'
    q = query.get('q', '')[:200].strip()
    history = sample_history(request)
    try:
        per_page = int(query.get('per_page', '12'))
        page = max(1, int(query.get('page', '1')))
    except ValueError:
        per_page, page = 12, 1
    if per_page not in (3, 12, 24, 48, 96):
        per_page = 12
    recipes = [dict(r, favorite=r['id'] in state['favorites'],
                    planned=state['plan'].get(str(r['id']), '')) for r in HOME_RECIPES]

    def in_collection(r, value):
        return (value == 'All recipes' or
                value == 'Favorites' and r['favorite'] or
                value == 'Never cooked' and not r['cooked'] or
                value == 'Meal plan' and bool(r['planned']) or r['collection'] == value)

    results = [r for r in recipes if in_collection(r, collection) and
               (not cuisine or r['cuisine'] == cuisine) and
               all(word in (' '.join([r['title'], r['cuisine'], r['collection'],
                                      r['description'], *r['ingredient_images']])
                            .replace('_', ' ').casefold()) for word in q.casefold().split())]
    sort_key = {'recent': 'added', 'recent_asc': 'added', 'name': 'title',
                'name_desc': 'title', 'cooked': 'last_cooked',
                'cooked_asc': 'last_cooked', 'visited': 'last_viewed',
                'visited_asc': 'last_viewed'}[sort]
    results.sort(key=lambda r: r[sort_key].casefold() if sort_key == 'title' else r[sort_key],
                 reverse=sort in ('recent', 'name_desc', 'cooked', 'visited'))
    total = len(results)
    if query.get('remember') == '1' and q and total > 1:
        history = [q] + [value for value in history if value.casefold() != q.casefold()]
        history = history[:8]
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, pages)
    params = dict(layout=layout, palette=palette_id, collection=collection, cuisine=cuisine, q=q,
                  sort=sort, per_page=per_page, page=page)

    def url(**changes):
        values = dict(params, **changes)
        if 'page' not in changes:
            values['page'] = 1
        return '/design?' + urlencode({k: v for k, v in values.items() if v != ''})

    planned = sorted((r for r in recipes if r['planned']), key=lambda r: r['planned'])
    for r in planned:
        r['day_label'] = date.fromisoformat(r['planned']).strftime('%a, %b %d')
    ingredients = list(dict.fromkeys(img for r in planned for img in r['ingredient_images']))
    return dict(layout=layout, layouts=HOME_LAYOUTS, palette_id=palette_id,
                palette=LIBRARY_PALETTES[palette_id], palettes=LIBRARY_PALETTES,
                collection=collection, cuisine=cuisine,
                cuisines=CUISINES, collections=COLLECTIONS, sort=sort, sort_choices=SORT_CHOICES,
                q=q, per_page=per_page, page=page, pages=pages, total=total,
                recipes=results[(page-1)*per_page:page*per_page], all_recipes=recipes,
                planned=planned, ingredients=ingredients, today=date.today().isoformat(),
                counts={name: sum(bool(in_collection(r, name)) for r in recipes) for name in COLLECTIONS},
                url=url, action_url='/design/action?' + urlencode(params),
                layout_info=next(row for row in HOME_LAYOUTS if row[0] == layout),
                history=history, notice='')


def render(request, data):
    template = ('design_home_preview.html' if request.headers.get('HX-Request') else
                'design_home.html')
    response = templates.TemplateResponse(request=request, name=template, context=data)
    response.headers['Vary'] = 'HX-Request, HX-Target, Cookie'
    response.headers['Cache-Control'] = 'no-store'
    return response


@router.get('/design')
def homepage_preview(request: Request):
    data = context(request)
    response = render(request, data)
    if request.query_params.get('remember') == '1':
        response.set_cookie(HISTORY_COOKIE, json.dumps(data['history']), max_age=86400,
                            path='/design', httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https')
    if request.headers.get('HX-Request'):
        response.headers['HX-Push-Url'] = data['url'](page=data['page'])
    return response


@router.post('/design/action')
def sample_action(request: Request, recipe_id: int = Form(...),
                  action: str = Form(...), day: str = Form('')):
    if recipe_id not in IDS:
        raise HTTPException(404)
    state = sample_state(request)
    if action == 'favorite':
        favorites = set(state['favorites'])
        favorites.symmetric_difference_update({recipe_id})
        state['favorites'] = sorted(favorites)
        notice = 'Favorites updated in this preview.'
    elif action == 'plan':
        try:
            state['plan'][str(recipe_id)] = date.fromisoformat(day).isoformat()
        except ValueError:
            raise HTTPException(422, 'Choose a valid planning date.')
        notice = 'Recipe added to your sample meal plan.'
    elif action == 'unplan':
        state['plan'].pop(str(recipe_id), None)
        notice = 'Recipe removed from your sample meal plan.'
    else:
        raise HTTPException(400)
    data = context(request, state)
    data['notice'] = notice
    response = (render(request, data) if request.headers.get('HX-Request') else
                RedirectResponse(data['url'](page=data['page']), status_code=303))
    response.set_cookie(COOKIE, json.dumps(state, separators=(',', ':')),
                        max_age=86400, path='/design', httponly=True, samesite='strict',
                        secure=request.url.scheme == 'https')
    return response


@router.get('/design/sample/{recipe_id}')
def sample_detail(request: Request, recipe_id: int):
    recipe = next((r for r in HOME_RECIPES if r['id'] == recipe_id), None)
    if recipe is None:
        raise HTTPException(404)
    palette_id = request.query_params.get('palette', 'oxblood')
    if palette_id not in LIBRARY_PALETTES:
        palette_id = 'forest'
    return templates.TemplateResponse(request=request, name='design_home_detail.html',
                                      context={'r': recipe, 'palette_id': palette_id,
                                               'palette': LIBRARY_PALETTES[palette_id],
                                               'standalone': not request.headers.get('HX-Request')})
