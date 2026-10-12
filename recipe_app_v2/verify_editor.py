"""Verify local edit forms; --save tests only newly created dev fixtures."""
import argparse
import hashlib
import json
import secrets
from html.parser import HTMLParser
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .database import get_engine, get_write_engine
from .models import Recipe, Recipe_Ingredient, Recipe_Instruction, recipe_collection


class FormParser(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.fields = []
        self.textarea = None
        self.select = None
        self.option = None
        self.feed(body)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        name = attrs.get('name')
        if tag == 'input' and name and attrs.get('type') != 'file':
            if attrs.get('type') not in ('checkbox', 'radio') or 'checked' in attrs:
                self.fields.append((name, attrs.get('value', '')))
        if tag == 'textarea' and name:
            self.textarea = [name, '']
        if tag == 'select' and name:
            self.select = {'name': name, 'options': [], 'multiple': 'multiple' in attrs}
        if tag == 'option' and self.select:
            self.option = [attrs.get('value', ''), 'selected' in attrs]

    def handle_data(self, data):
        if self.textarea:
            self.textarea[1] += data

    def handle_endtag(self, tag):
        if tag == 'textarea' and self.textarea:
            self.fields.append(tuple(self.textarea))
            self.textarea = None
        if tag == 'option' and self.select and self.option:
            self.select['options'].append(self.option)
            self.option = None
        if tag == 'select' and self.select:
            selected = [option[0] for option in self.select['options'] if option[1]]
            if not selected and not self.select['multiple'] and self.select['options']:
                selected = [self.select['options'][0][0]]
            self.fields.extend((self.select['name'], value) for value in selected)
            self.select = None


def inventory():
    with get_engine().connect() as connection:
        tables = [row[0] for row in connection.execute(text('SHOW TABLES'))]
        result = {}
        for table in tables:
            safe = table.replace('`', '``')
            rows = connection.execute(text(f'SELECT * FROM `{safe}`')).all()
            serialized = sorted(json.dumps(list(row), default=str, ensure_ascii=False) for row in rows)
            result[table] = {'rows': len(rows), 'sha256': hashlib.sha256('\n'.join(serialized).encode()).hexdigest()}
        return result


def verify(save=False):
    owned_id = None
    prefix = 'V2 form verification ' + secrets.token_hex(6)
    before = inventory()
    summary = {}
    try:
        with httpx.Client(base_url='http://127.0.0.1:8001', timeout=30) as client:
            health = client.get('/health').json()
            assert health['database'] == 'MyRecipes_DEV' and health['read_connections_read_only']
            with Session(get_engine()) as session:
                ids = session.scalars(select(Recipe.recipe_id).order_by(Recipe.recipe_id)).all()
            # Compare every persisted legacy edit field with the new form.
            fields = {'name': 'name', 'url': 'source_url', 'whisk_url': 'whisk_url',
                      'prep_time': 'prep_time', 'cook_time': 'cook_time',
                      'additional_time': 'additional_time', 'servings': 'servings',
                      'note_from_user': 'note_from_user', 'ingredient_bulk': 'ingredient_bulk',
                      'instructions': 'instructions', 'source_notes': 'source_notes'}
            checked = 0
            for recipe_id in ids:
                legacy = httpx.get(f'http://127.0.0.1:8080/recipes/{recipe_id}/edit', timeout=30)
                response = client.get(f'/recipes/{recipe_id}/edit')
                assert legacy.status_code == response.status_code == 200, f'Edit GET failed: {recipe_id}'
                old, new = dict(FormParser(legacy.text).fields), dict(FormParser(response.text).fields)
                for old_key, new_key in fields.items():
                    # WTForms emits a newline immediately after the textarea tag.
                    expected = old.get(old_key, '')
                    if old_key in ('note_from_user', 'ingredient_bulk', 'instructions', 'source_notes'):
                        expected = expected.removeprefix('\r\n').removeprefix('\n')
                    assert expected.replace('\r\n', '\n') == new.get(new_key, '').replace('\r\n', '\n'), f'Field mismatch: {recipe_id}/{old_key}'
                checked += 1
            summary['legacy_edit_forms_compared'] = checked
            if save:
                assert health['dev_saves_enabled']
                fields = FormParser(client.get('/recipes/new').text).fields
                values = dict(fields)
                values.update(name=prefix, ingredient_mode='bulk',
                    ingredient_bulk='>Sauce\nsoy sauce, low sodium\nOnion',
                    instructions='>Prepare\nMix\nSimmer', source_notes='Source advice',
                    prep_time='10 mins', cook_time='20 mins', servings='2', intent='save')
                # Bulk mode ignores the three blank individual rows.
                values = {key: value for key, value in values.items() if not key.startswith('ingredient_')}
                values.update(ingredient_mode='bulk', ingredient_bulk='>Sauce\nsoy sauce, low sodium\nOnion')
                response = client.post('/recipes/new', data=values)
                assert response.status_code == 303, 'Dev create failed'
                owned_id = int(response.headers['location'].rsplit('/', 1)[1])
                fields = FormParser(client.get(f'/recipes/{owned_id}/edit').text).fields
                fields = [(key, prefix + ' edited' if key == 'name' else value) for key, value in fields]
                encoded = urlencode(fields + [('intent', 'save')])
                response = client.post(f'/recipes/{owned_id}/edit', content=encoded,
                                      headers={'Content-Type': 'application/x-www-form-urlencoded', 'HX-Request': 'true'})
                assert response.status_code == 200 and response.headers.get('HX-Redirect') == f'/recipes/{owned_id}', 'Dev edit failed'
                with Session(get_engine()) as session:
                    recipe = session.get(Recipe, owned_id)
                    assert (recipe.name, recipe.total_time, recipe.ingredient_count, recipe.servings) == (prefix + ' edited', '30 mins', 2, 2)
                    ingredients = session.scalars(select(Recipe_Ingredient).where(Recipe_Ingredient.recipe_id == owned_id).order_by(Recipe_Ingredient.sequence)).all()
                    assert [(i.name_written, i.note, bool(i.is_group_header)) for i in ingredients] == [('Sauce', None, True), ('soy sauce', 'low sodium', False), ('Onion', None, False)]
                # An earlier edit version must now fail without modifying data.
                response = client.post(f'/recipes/{owned_id}/edit', content=encoded,
                                      headers={'Content-Type': 'application/x-www-form-urlencoded'})
                assert response.status_code == 409, 'Stale edit was not rejected'
                summary['dev_create_edit_stale_rejection'] = 'passed'
    finally:
        if owned_id is not None:
            with Session(get_write_engine()) as session:
                recipe = session.scalar(select(Recipe).where(Recipe.recipe_id == owned_id).with_for_update())
                if recipe is None or not recipe.name.startswith(prefix):
                    raise RuntimeError('Refusing fixture cleanup: ownership check failed.')
                for model in (Recipe_Ingredient, Recipe_Instruction):
                    session.execute(delete(model).where(model.recipe_id == owned_id))
                session.execute(delete(recipe_collection).where(recipe_collection.c.recipe_id == owned_id))
                session.delete(recipe)
                session.commit()
        after = inventory()
        assert before == after, 'Dev database rows changed after fixture cleanup'
    summary.update(tables_unchanged_after_cleanup=len(before), fixture_removed=owned_id is not None,
                   production_contacted=False)
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--save', action='store_true', help='Create/edit and remove a new dev-only test recipe.')
    verify(parser.parse_args().save)
