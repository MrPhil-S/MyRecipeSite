import io
import os
import re
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from recipe_app_v2.database import ReadOnlySession, get_session
from recipe_app_v2.editor import form_values
from recipe_app_v2.main import app
from recipe_app_v2.models import (Base, Collection, Cuisine, Recipe, Recipe_Ingredient,
                                 Recipe_Instruction, recipe_cooked_date)


def form_data(values):
    data = {key: value for key, value in values.items() if key not in ('rows', 'collection_ids')}
    data['collection_ids'] = values['collection_ids']
    for field in ('id', 'name', 'note', 'group', 'keep'):
        data['ingredient_' + field] = [row[field] for row in values['rows']]
    return data


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([Cuisine(cuisine_id=1, cuisine_name='Test cuisine'),
                             Collection(collection_id=1, collection_name='Favorites')])
            session.commit()
        self.folder = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'RECIPE_DEV_WRITES': '1', 'RECIPE_UPLOADS': self.folder.name})
        self.environment.start()
        self.writer = patch('recipe_app_v2.recipe_saves.get_write_engine', return_value=self.engine)
        self.writer.start()
        self.activity_writer = patch('recipe_app_v2.activity.get_write_engine', return_value=self.engine)
        self.activity_writer.start()

        def sessions():
            with ReadOnlySession(self.engine, autoflush=False) as session:
                yield session
        app.dependency_overrides[get_session] = sessions
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.writer.stop()
        self.activity_writer.stop()
        self.environment.stop()
        self.folder.cleanup()
        self.engine.dispose()

    def values(self, recipe_id=None):
        path = f'/recipes/{recipe_id}/edit' if recipe_id else '/recipes/new'
        body = self.client.get(path).text
        token = re.search(r'name="csrf_token" value="([^"]+)"', body)[1]
        with ReadOnlySession(self.engine) as session:
            values = form_values(session, session.get(Recipe, recipe_id) if recipe_id else None)
        data = form_data(values)
        data['csrf_token'] = token
        return data

    def create(self):
        data = self.values()
        data.update(name='Test <recipe>', source_url='https://www.example.com/recipe',
                    prep_time='1 hr', cook_time='30 mins', servings='4', cuisine_id='1',
                    collection_ids=['1'], ingredient_mode='bulk',
                    ingredient_bulk='>Sauce\nsoy sauce, low sodium\n\nOnion',
                    instructions='>Prepare\nMix\nSimmer', source_notes='A note\nAnother note',
                    note_from_user='My notes')
        response = self.client.post('/recipes/new', data=data, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        return int(response.headers['location'].rsplit('/', 1)[1])

    def test_create_edit_and_preserve_hidden_metadata_history(self):
        recipe_id = self.create()
        with Session(self.engine) as session:
            recipe = session.get(Recipe, recipe_id)
            self.assertEqual((recipe.total_time, recipe.source_url_short, recipe.ingredient_count),
                             ('1 hr 30 mins', 'Example', 2))
            self.assertEqual([c.collection_id for c in recipe.collections], [1])
            ingredient = session.scalar(select(Recipe_Ingredient).where(Recipe_Ingredient.name_written == 'soy sauce'))
            ingredient.ingredient_id = 999
            ingredient.name_official = 'soy_sauce'
            ingredient_id = ingredient.recipe_ingredient_id
            session.add(recipe_cooked_date(recipe_id=recipe_id))
            session.add(Recipe_Instruction(recipe_id=recipe_id, type=3, text_contents='Preserve other type'))
            session.commit()
        data = self.values(recipe_id)
        data.update(name='Edited', note_from_user='Changed notes')
        response = self.client.post(f'/recipes/{recipe_id}/edit', data=data, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Recipe, recipe_id).name, 'Edited')
            ingredient = session.get(Recipe_Ingredient, ingredient_id)
            self.assertEqual((ingredient.ingredient_id, ingredient.name_official, ingredient.note),
                             (999, 'soy_sauce', 'low sodium'))
            self.assertEqual(session.scalar(text('SELECT count(*) FROM recipe_cooked_date')), 1)
            self.assertEqual(session.scalar(text('SELECT count(*) FROM recipe__instruction WHERE type=3')), 1)
            self.assertEqual(session.scalar(text('SELECT count(*) FROM recipe_view_date')), 0)
        self.assertIn('Edited', self.client.get(f'/recipes/{recipe_id}').text)

    def test_invalid_submission_retained_and_does_not_write(self):
        data = self.values()
        data.update(name='<script>keep this</script>', source_url='javascript:alert(1)',
                    servings='-2', prep_time='tomorrow', cuisine_id='999', collection_ids=['999'],
                    ingredient_mode='bulk', ingredient_bulk='x' * 101, instructions='>' )
        response = self.client.post('/recipes/new', data=data, headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('&lt;script&gt;keep this&lt;/script&gt;', response.text)
        self.assertIn('Choose existing collections', response.text)
        self.assertNotIn('<!doctype', response.text)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(text('SELECT count(*) FROM recipe')), 0)

    def test_stale_edit_rejected(self):
        recipe_id = self.create()
        data = self.values(recipe_id)
        with Session(self.engine) as session:
            session.get(Recipe, recipe_id).name = 'Changed elsewhere'
            session.commit()
        data['name'] = 'Stale changes'
        response = self.client.post(f'/recipes/{recipe_id}/edit', data=data)
        self.assertEqual(response.status_code, 409)
        self.assertIn('Stale changes', response.text)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Recipe, recipe_id).name, 'Changed elsewhere')

    def test_csrf_and_disabled_saves(self):
        data = self.values()
        data['name'] = 'Safe preview'
        original = data['csrf_token']
        self.assertEqual(self.values()['csrf_token'], original, 'Opening another form must not invalidate this tab')
        data['csrf_token'] = 'forged'
        self.assertEqual(self.client.post('/recipes/new', data=data).status_code, 403)
        data['csrf_token'] = original
        self.assertEqual(self.client.post('/recipes/new', data=data,
            headers={'Origin': 'https://other.example'}).status_code, 403)
        with patch.dict(os.environ, {'RECIPE_DEV_WRITES': '0'}):
            self.assertEqual(self.client.post('/recipes/new', data=data).status_code, 403)
            response = self.client.get('/recipes/new')
            self.assertEqual(response.status_code, 200)
            self.assertIn('disabled>Create recipe', response.text)
            self.assertNotIn('Review changes', response.text)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(text('SELECT count(*) FROM recipe')), 0)

    def test_child_identifiers_unique_url_and_removal(self):
        first, second = self.create(), self.create()
        data = self.values(first)
        data['whisk_url'] = 'https://whisk.example/unique'
        self.assertEqual(self.client.post(f'/recipes/{first}/edit', data=data).status_code, 200)
        data = self.values(second)
        data['whisk_url'] = 'https://whisk.example/unique'
        self.assertEqual(self.client.post(f'/recipes/{second}/edit', data=data).status_code, 422)
        with Session(self.engine) as session:
            other_id = session.scalar(select(Recipe_Ingredient.recipe_ingredient_id).where(Recipe_Ingredient.recipe_id == first))
        data = self.values(second)
        data['ingredient_id'][0] = str(other_id)
        self.assertEqual(self.client.post(f'/recipes/{second}/edit', data=data).status_code, 422)
        data = self.values(second)
        data['ingredient_keep'][1] = '0'
        self.assertEqual(self.client.post(f'/recipes/{second}/edit', data=data).status_code, 200)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Recipe, second).ingredient_count, 1)

    def test_uploads_and_commit_failure_restore_database_and_files(self):
        recipe_id = self.create()
        png = io.BytesIO()
        Image.new('RGB', (1200, 800), 'red').save(png, 'PNG')
        pdf = b'%PDF-1.4\nA minimal fixture\n%%EOF\n'
        data = self.values(recipe_id)
        response = self.client.post(f'/recipes/{recipe_id}/edit', data=data,
            files={'image': ('test.png', png.getvalue(), 'image/png'), 'pdf': ('test.pdf', pdf, 'application/pdf')})
        self.assertEqual(response.status_code, 200, response.text)
        with Session(self.engine) as session:
            image_file = session.get(Recipe, recipe_id).image_file
        self.assertEqual(len(image_file), 20)
        self.assertEqual(self.client.get(f'/recipe-images/{image_file}').status_code, 200)
        self.assertEqual(self.client.get(f'/source-pdfs/{recipe_id}.pdf').content, pdf)
        data = self.values(recipe_id)
        data['name'] = 'Must roll back'
        with patch('recipe_app_v2.recipe_saves.Session.commit', side_effect=OSError('simulated failure')):
            response = self.client.post(f'/recipes/{recipe_id}/edit', data=data,
                files={'image': ('test.png', png.getvalue(), 'image/png'),
                       'pdf': ('test.pdf', pdf + b'replacement', 'application/pdf')})
        self.assertEqual(response.status_code, 503)
        with Session(self.engine) as session:
            recipe = session.get(Recipe, recipe_id)
            self.assertEqual((recipe.name, recipe.image_file), ('Test <recipe>', image_file))
        self.assertEqual(self.client.get(f'/source-pdfs/{recipe_id}.pdf').content, pdf)
        self.assertEqual(len(list((Path(self.folder.name) / 'images').iterdir())), 1)

    def test_invalid_files_and_oversized_body_rejected(self):
        data = self.values()
        data['name'] = 'Do not save'
        response = self.client.post('/recipes/new', data=data,
            files={'image': ('test.jpg', b'not an image', 'image/jpeg'), 'pdf': ('test.pdf', b'not a PDF', 'application/pdf')})
        self.assertEqual(response.status_code, 422)
        response = self.client.post('/recipes/new', content=b'x' * (18 * 1024 * 1024 + 1),
                                    headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(response.status_code, 413)
        response = self.client.post('/recipes/new', content=b'x=1&' * 2000,
                                    headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(response.status_code, 413)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(text('SELECT count(*) FROM recipe')), 0)
