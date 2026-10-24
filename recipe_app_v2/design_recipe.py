"""Five Oxblood recipe compositions, with isolated server-rendered sample actions."""
import json
from datetime import date
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .design_home import CUISINES, HOME_RECIPES, LIBRARY_PALETTES
from .design_routes import COOKIE as HOME_COOKIE, sample_state

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / 'templates')
COOKIE = 'recipe_detail_study_v1'
VERSIONS = [
    ('split', 'Split', 'A generous photo and recipe introduction, with ingredients beside the method.'),
    ('panorama', 'Panorama', 'A wide photograph leads into a clean, open recipe layout.'),
    ('sidebar', 'Sidebar', 'Keep the recipe summary beside you while ingredients and instructions take the main column.'),
    ('workbench', 'Workbench', 'A compact introduction puts ingredients and cooking steps within easy reach.'),
    ('sheet', 'Recipe Sheet', 'A centered recipe sheet with ingredient tiles and a spacious, linear method.'),
]
INGREDIENTS = [
    ('Chicken', 'chicken_thigh.jpg', Fraction(3, 2), 'lb', 'Boneless chicken thighs', 'Pat dry before marinating.'),
    ('Marinade', 'greek_yogurt.jpg', Fraction(1, 2), 'cup', 'Greek yogurt', 'Plain, full-fat.'),
    ('Marinade', 'gochujang.jpg', Fraction(3), 'Tbsp', 'Gochujang', 'Adjust to your preferred heat.'),
    ('Marinade', 'garlic.jpg', Fraction(3), 'cloves', 'Garlic', 'Finely grated.'),
    ('Marinade', 'maple_syrup.jpg', Fraction(2), 'Tbsp', 'Maple syrup', ''),
    ('Marinade', 'soy_sauce.jpg', Fraction(2), 'Tbsp', 'Soy sauce', ''),
]
STEPS = [
    ('Mix the marinade', 'Whisk the yogurt, gochujang, garlic, maple syrup, and soy sauce in a large bowl until smooth. Set aside a little sauce in a separate bowl before adding the chicken.'),
    ('Give it a little time', 'Add the chicken and turn until well coated. Cover and refrigerate for 20 minutes. Meanwhile, prepare a lined broiler pan and lightly oil the rack.'),
    ('Cook until burnished', 'Arrange the chicken in a single layer. Broil, turning halfway through, until browned at the edges and the thickest part reaches 165°F / 74°C. Allow about 15–20 minutes; timing depends on your broiler and the size of the pieces.'),
    ('Rest, then serve', 'Rest the chicken for 5 minutes. Spoon over the sauce you reserved before adding the raw chicken, and serve with rice and something crisp.'),
]
DEFAULT_NOTE = 'Double the sauce for rice bowls tomorrow. Cucumber salad is a good side.'


def detail_state(request):
    default = dict(title='Sticky gochujang chicken', cuisine='Korean',
                   collections=['Weeknight dinners'], note=DEFAULT_NOTE,
                   cooked_on='', deleted=False)
    try:
        saved = json.loads(request.cookies.get(COOKIE, '{}'))
        if not isinstance(saved, dict):
            return default
        for key, limit in [('title', 120), ('note', 1500)]:
            if isinstance(saved.get(key), str) and (key != 'title' or saved[key].strip()):
                default[key] = saved[key][:limit]
        if saved.get('cuisine') in CUISINES:
            default['cuisine'] = saved['cuisine']
        if isinstance(saved.get('collections'), list):
            default['collections'] = [v for v in saved['collections'] if v in ('Weeknight dinners', 'Comfort food')]
        if isinstance(saved.get('cooked_on'), str) and saved['cooked_on']:
            default['cooked_on'] = date.fromisoformat(saved['cooked_on']).isoformat()
        default['deleted'] = saved.get('deleted') is True
    except (ValueError, TypeError):
        pass
    return default


def quantity(value):
    whole, remainder = divmod(value.numerator, value.denominator)
    fractions = {(1, 2): '½', (1, 4): '¼', (3, 4): '¾'}
    part = fractions.get((remainder, value.denominator), f'{remainder}/{value.denominator}') if remainder else ''
    return (str(whole) if whole else '') + (' ' if whole and part else '') + part


def detail_context(request, state=None, home=None, notice=''):
    state = state if state is not None else detail_state(request)
    home = home if home is not None else sample_state(request)
    try:
        sample_id = int(request.query_params.get('sample_id', ''))
    except ValueError:
        sample_id = 0
    sample = next((r for r in HOME_RECIPES if r['id'] == sample_id), None)
    if sample:
        state = dict(state, title=sample['title'], cuisine=sample['cuisine'],
                     collections=[sample['collection']],
                     note=state.get('note', '') if sample['id'] == 1 else '',
                     deleted=False if sample['id'] != 1 else state['deleted'])
    version = request.query_params.get('version', 'split')
    if version not in {v[0] for v in VERSIONS}:
        version = 'split'
    try:
        servings = int(request.query_params.get('servings', '4'))
    except ValueError:
        servings = 4
    if servings not in (2, 4, 6, 8):
        servings = 4
    ingredients = [dict(group=group, file=file, amount=quantity(amount * Fraction(servings, 4)),
                        unit=unit, name=name, note=note) for group, file, amount, unit, name, note in INGREDIENTS]
    steps = STEPS
    if sample and sample['id'] != 1:
        ingredients = [dict(group='Ingredient highlights', file=file, amount='', unit='',
                            name=file[:-4].replace('_', ' ').title(), note='')
                       for file in sample['ingredient_images']]
        steps = {
            2: [('Build the layers', 'Layer pasta, tomato sauce, and ricotta in a baking dish.'), ('Bake until bubbling', 'Bake until the center is hot and the top is browned.'), ('Rest and serve', 'Let the lasagna settle briefly, then slice and serve.')],
            3: [('Prepare the cucumbers', 'Smash and cut the cucumbers into bite-size pieces.'), ('Season and toss', 'Toss with garlic and chile, then adjust the seasoning.'), ('Serve chilled', 'Let the flavors mingle briefly before serving.')],
            4: [('Roast the carrots', 'Roast the carrots until tender and lightly browned.'), ('Mix the dressing', 'Stir together the yogurt, herbs, and seasonings.'), ('Finish the plate', 'Spoon the dressing over the warm carrots and serve.')],
            5: [('Whip the cream', 'Whip the cream with sugar until soft peaks form.'), ('Layer the cake', 'Alternate chocolate cookies and whipped cream in a dish.'), ('Chill and slice', 'Refrigerate until set, then slice to serve.')],
            6: [('Prepare the vegetables', 'Arrange tomatoes and spinach in a baking dish.'), ('Bake the fish', 'Nestle the fish into the vegetables and bake until opaque.'), ('Serve from the pan', 'Spoon the tomato and spinach juices over the fish.')],
        }.get(sample['id'], STEPS)
    params = dict(version=version, servings=servings)
    if sample:
        params['sample_id'] = sample['id']

    def url(**changes):
        return '/design/recipe?' + urlencode(dict(params, **changes))

    recipe_id = sample['id'] if sample else 1
    planned = home['plan'].get(str(recipe_id), '')
    return dict(version=version, versions=VERSIONS, version_info=next(v for v in VERSIONS if v[0] == version),
                palette=LIBRARY_PALETTES['oxblood'], palette_id='oxblood', state=state,
                favorite=recipe_id in home['favorites'], planned=planned, sample=sample,
                recipe_id=recipe_id,
                plan_label=date.fromisoformat(planned).strftime('%a, %b %d') if planned else '',
                cook_count=(sample['cooked'] if sample else 3) + bool(state['cooked_on']), today=date.today().isoformat(),
                servings=(sample['servings'] if sample else servings), ingredients=ingredients,
                ingredient_count=(len(ingredients) if sample and sample['id'] != 1 else len(ingredients)),
                recipe_minutes=(sample['minutes'] if sample else 60),
                recipe_image=(sample['image'] if sample else '100.jpg'),
                recipe_views=(sample['viewed'] if sample else 12),
                steps=steps, cuisines=CUISINES,
                url=url, action_url='/design/recipe/action?' + urlencode(params), notice=notice)


def render(request, data):
    template = 'design_recipe_preview.html' if request.headers.get('HX-Request') else 'design_recipe.html'
    response = templates.TemplateResponse(request=request, name=template, context=data)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Vary'] = 'HX-Request, Cookie'
    return response


@router.get('/design/recipe')
def recipe_studies(request: Request):
    return render(request, detail_context(request))


@router.post('/design/recipe/action')
def recipe_action(request: Request, action: str = Form(...), day: str = Form(''),
                  title: str = Form('', max_length=120), cuisine: str = Form('Korean'),
                  collections: list[str] = Form(default=[]), note: str = Form('', max_length=1500)):
    state, home = detail_state(request), sample_state(request)
    try:
        recipe_id = int(request.query_params.get('sample_id', '1'))
    except ValueError:
        recipe_id = 1
    notice = 'Sample recipe updated.'
    if action == 'favorite':
        favorites = set(home['favorites'])
        favorites.symmetric_difference_update({recipe_id})
        home['favorites'] = sorted(favorites)
        notice = 'Sample favorites updated.'
    elif action == 'plan':
        try:
            home['plan'][str(recipe_id)] = date.fromisoformat(day).isoformat()
        except ValueError:
            raise HTTPException(422, 'Choose a valid date.')
        notice = 'Sample meal plan updated.'
    elif action == 'unplan':
        home['plan'].pop(str(recipe_id), None)
        notice = 'Removed from the sample meal plan.'
    elif action == 'cooked':
        state['cooked_on'] = date.today().isoformat()
        notice = 'Cooking recorded in this preview.'
    elif action == 'undo-cooked':
        state['cooked_on'] = ''
        notice = 'Sample cooking record removed.'
    elif action == 'note':
        state['note'] = note.strip()
        notice = 'Your sample note is saved.'
    elif action == 'edit':
        if not title.strip() or cuisine not in CUISINES:
            raise HTTPException(422, 'Enter a title and select a cuisine.')
        state.update(title=title.strip(), cuisine=cuisine,
                     collections=[v for v in collections if v in ('Weeknight dinners', 'Comfort food')],
                     note=note.strip())
    elif action == 'delete':
        state['deleted'] = True
        notice = 'Sample hidden. You can restore it below.'
    elif action == 'restore':
        state['deleted'] = False
        notice = 'Sample restored.'
    else:
        raise HTTPException(400)
    if len(json.dumps(state)) > 3000:
        raise HTTPException(422, 'Please shorten the sample note.')
    data = detail_context(request, state, home, notice)
    response = render(request, data) if request.headers.get('HX-Request') else RedirectResponse(data['url'](), status_code=303)
    for name, value in [(COOKIE, state), (HOME_COOKIE, home)]:
        response.set_cookie(name, json.dumps(value, separators=(',', ':')), path='/design',
                            max_age=86400, httponly=True, samesite='strict', secure=request.url.scheme == 'https')
    return response
