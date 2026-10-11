"""Recipe form values and validation, independent of HTTP and database writes."""
import hashlib
import json
import re
from urllib.parse import urlsplit

from sqlalchemy import select

from .models import Collection, Cuisine, Recipe, Recipe_Ingredient, Recipe_Instruction

FIELDS = {
    'name': 200, 'source_url': 255, 'whisk_url': 255,
    'prep_time': 20, 'cook_time': 20, 'additional_time': 20,
    'servings': 10, 'note_from_user': 1000,
    'ingredient_bulk': 60000, 'instructions': 60000, 'source_notes': 60000,
    'cuisine_id': 10, 'version': 64, 'ingredient_mode': 10,
}


def empty_row():
    return {'id': '', 'name': '', 'note': '', 'group': '0', 'keep': '1'}


def recipe_rows(session, recipe_id):
    ingredients = session.scalars(select(Recipe_Ingredient).where(
        Recipe_Ingredient.recipe_id == recipe_id).order_by(
        Recipe_Ingredient.sequence, Recipe_Ingredient.recipe_ingredient_id)).all()
    instructions = session.scalars(select(Recipe_Instruction).where(
        Recipe_Instruction.recipe_id == recipe_id).order_by(
        Recipe_Instruction.sequence, Recipe_Instruction.recipe_instruction_id)).all()
    return ingredients, instructions


def version_for(recipe, ingredients, instructions):
    # Include hidden ingredient metadata and all instruction types so an edit
    # cannot silently overwrite a change made by another browser or Flask.
    def columns(obj):
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    value = [columns(recipe), [columns(i) for i in ingredients],
             [columns(i) for i in instructions], sorted(c.collection_id for c in recipe.collections)]
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def form_values(session, recipe=None):
    values = {key: '' for key in FIELDS}
    values.update(ingredient_mode='rows', collection_ids=[], rows=[empty_row() for _ in range(3)])
    if recipe is None:
        return values
    ingredients, instructions = recipe_rows(session, recipe.recipe_id)
    for key in ('name', 'source_url', 'whisk_url', 'prep_time', 'cook_time',
                'additional_time', 'servings', 'note_from_user', 'cuisine_id'):
        value = getattr(recipe, key)
        values[key] = '' if value is None else str(value)
    values['version'] = version_for(recipe, ingredients, instructions)
    values['collection_ids'] = [str(c.collection_id) for c in recipe.collections]
    values['rows'] = [{'id': str(i.recipe_ingredient_id), 'name': i.name_written,
                       'note': i.note or '', 'group': '1' if i.is_group_header else '0',
                       'keep': '1'} for i in ingredients] + [empty_row()]
    values['ingredient_bulk'] = '\n'.join(
        ('>' if i.is_group_header else '') + i.name_written + (', ' + i.note if i.note else '')
        for i in ingredients)
    values['instructions'] = '\n'.join(
        ('>' if i.is_group_header else '') + i.text_contents for i in instructions if i.type == 1)
    values['source_notes'] = '\n'.join(i.text_contents for i in instructions if i.type == 2)
    return values


def submitted_values(form):
    values = {key: str(form.get(key, '')) for key in FIELDS}
    values['collection_ids'] = [str(v) for v in form.getlist('collection_ids')]
    arrays = [form.getlist('ingredient_' + field) for field in ('id', 'name', 'note', 'group', 'keep')]
    if len({len(a) for a in arrays}) != 1 or len(arrays[0]) > 300:
        raise ValueError('Ingredient rows are incomplete or exceed the 300-row limit.')
    values['rows'] = [dict(zip(('id', 'name', 'note', 'group', 'keep'), map(str, row)))
                      for row in zip(*arrays)]
    return values


def duration_minutes(value):
    if not value:
        return 0
    # Accept legacy spellings such as "1h 30m", "2 hrs", "30 mins".
    pattern = r'\s*(?:(\d+)\s*(?:hours?|hrs?|h)\s*)?(?:(\d+)\s*(?:minutes?|mins?|m)\s*)?'
    match = re.fullmatch(pattern, value, re.IGNORECASE)
    if not match or not any(match.groups()):
        raise ValueError('Use hours and/or minutes, for example 1 hr 30 mins.')
    return int(match[1] or 0) * 60 + int(match[2] or 0)


def total_time(values):
    entries = [values[key] for key in ('prep_time', 'cook_time', 'additional_time')]
    if not any(entries):
        return None
    hours, minutes = divmod(sum(duration_minutes(v) for v in entries), 60)
    parts = []
    if hours:
        parts.append(f'{hours} hr' + ('s' if hours != 1 else ''))
    if minutes or not hours:
        parts.append(f'{minutes} min' + ('s' if minutes != 1 else ''))
    return ' '.join(parts)


def choices(session):
    return {
        'cuisines': session.scalars(select(Cuisine).order_by(Cuisine.cuisine_name, Cuisine.cuisine_id)).all(),
        'collection_choices': session.scalars(select(Collection).order_by(
            Collection.collection_name, Collection.collection_id)).all(),
    }


def validate(values, options):
    errors = []
    clean = {}
    for key, limit in FIELDS.items():
        clean[key] = values[key].strip()
        if len(clean[key]) > limit:
            errors.append(f'{key.replace("_", " ").capitalize()}: maximum {limit} characters.')
    if not clean['name']:
        errors.append('Recipe name is required.')
    for key in ('source_url', 'whisk_url'):
        if clean[key]:
            try:
                url = urlsplit(clean[key])
                valid = url.scheme.lower() in ('http', 'https') and url.hostname and not url.username
                valid = valid and not any(c.isspace() or ord(c) < 32 for c in clean[key])
                url.port
            except ValueError:
                valid = False
            if not valid:
                errors.append(f'{key.replace("_", " ").capitalize()}: enter an HTTP or HTTPS URL.')
    clean['servings'] = None
    if values['servings'].strip():
        try:
            clean['servings'] = int(values['servings'])
            if not 1 <= clean['servings'] <= 2147483647:
                raise ValueError()
        except ValueError:
            errors.append('Servings must be a positive whole number.')
    for key in ('prep_time', 'cook_time', 'additional_time'):
        try:
            duration_minutes(clean[key])
        except ValueError as exc:
            errors.append(f'{key.replace("_", " ").capitalize()}: {exc}')
    try:
        if len(total_time(clean) or '') > 20:
            errors.append('Combined cooking time is too large for the existing recipe field.')
    except ValueError:
        pass  # The individual duration errors above identify the bad fields.
    allowed_cuisines = {str(c.cuisine_id) for c in options['cuisines']}
    allowed_collections = {str(c.collection_id) for c in options['collection_choices']}
    if clean['cuisine_id'] and clean['cuisine_id'] not in allowed_cuisines:
        errors.append('Choose an existing cuisine.')
    if any(c not in allowed_collections for c in values['collection_ids']):
        errors.append('Choose existing collections.')
    clean['collection_ids'] = sorted(set(values['collection_ids']))
    clean['ingredients'] = []
    if clean['ingredient_mode'] == 'bulk':
        rows = []
        for line in clean['ingredient_bulk'].splitlines():
            if line.strip():
                name, sep, note = line.strip().partition(',')
                rows.append({'id': '', 'name': name.lstrip('>').strip() if name.startswith('>') else name.strip(),
                             'note': note.strip() if sep else '', 'group': '1' if name.startswith('>') else '0', 'keep': '1'})
    else:
        rows = values['rows']
        if clean['ingredient_mode'] != 'rows':
            errors.append('Choose individual rows or bulk ingredients.')
    for index, row in enumerate(rows, 1):
        if row['keep'] == '0':
            continue
        name, note = row['name'].strip(), row['note'].strip()
        if not name and not note:
            continue
        if not name or len(name) > 100 or len(note) > 100:
            errors.append(f'Ingredient {index}: name is required; name and note each allow 100 characters.')
        if row['group'] not in ('0', '1') or row['keep'] != '1':
            errors.append(f'Ingredient {index}: invalid row options.')
        clean['ingredients'].append(dict(row, name=name, note=note))
    if len(clean['ingredients']) > 300:
        errors.append('Use at most 300 ingredient rows.')
    clean['steps'] = []
    for key, kind in (('instructions', 1), ('source_notes', 2)):
        sequence = 0
        for line in clean[key].splitlines():
            line = line.strip()
            if not line:
                continue
            group = kind == 1 and line.startswith('>')
            text = line[1:].strip() if group else line
            sequence += 1
            if not text or len(text) > 1000:
                errors.append(f'{key.replace("_", " ").capitalize()}, line {sequence}: enter 1–1000 characters.')
            clean['steps'].append({'text': text, 'group': group, 'type': kind, 'sequence': sequence})
    return clean, errors
