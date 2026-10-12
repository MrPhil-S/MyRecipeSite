import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from recipe_app_v2.database import ReadOnlySession, get_session
from recipe_app_v2.image_aliases import catalogue_path
from recipe_app_v2.ingredient_rematch import RematchError, affected_ingredients, apply_selected
from recipe_app_v2.main import app
from recipe_app_v2.models import Base, Recipe, Recipe_Ingredient, Recipe_Instruction


class CentralRematchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'RECIPE_UPLOADS': self.folder.name, 'RECIPE_DEV_WRITES': '1'})
        self.environment.start()
        catalogue_path().write_text(json.dumps({'alcohol': ['gin'], 'onion': []}), encoding='utf-8')
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as s:
            s.add_all([Recipe(recipe_id=1, name='One', note_from_user='Keep recipe notes'),
                       Recipe(recipe_id=2, name='Two')])
            s.add_all([Recipe_Ingredient(recipe_ingredient_id=1, recipe_id=1, name_written='2 ounces gin',
                         name_official='gin', note='Keep note', ingredient_id=777, is_group_header=None, sequence=1),
                       Recipe_Ingredient(recipe_ingredient_id=2, recipe_id=2, name_written='1 ounce gin', name_official='gin'),
                       Recipe_Ingredient(recipe_ingredient_id=3, recipe_id=1, name_written='Onion', name_official='onion'),
                       Recipe_Ingredient(recipe_ingredient_id=4, recipe_id=1, name_written='unknown ingredient', name_official='existing_custom'),
                       Recipe_Instruction(recipe_id=1, type=1, text_contents='Keep instructions')])
            s.commit()
        def sessions():
            with ReadOnlySession(self.engine, autoflush=False) as session:
                yield session
        app.dependency_overrides[get_session] = sessions
        self.writer = patch('recipe_app_v2.ingredient_rematch.get_write_engine', return_value=self.engine)
        self.writer.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.writer.stop()
        self.engine.dispose()
        self.environment.stop()
        self.folder.cleanup()

    def proposals(self):
        with Session(self.engine) as s:
            return affected_ingredients(s, 'alcohol')

    def test_discovers_all_recipes_and_updates_only_selected_column(self):
        changes = self.proposals()
        self.assertEqual([r['row_id'] for r in changes], [1, 2])
        with Session(self.engine) as s:
            before = {row.recipe_ingredient_id: {c.name: getattr(row, c.name) for c in row.__table__.columns}
                      for row in s.scalars(select(Recipe_Ingredient))}
        self.assertEqual(apply_selected([changes[0]['token']]), 1)
        with Session(self.engine) as s:
            after = {row.recipe_ingredient_id: {c.name: getattr(row, c.name) for c in row.__table__.columns}
                     for row in s.scalars(select(Recipe_Ingredient))}
            self.assertEqual(s.get(Recipe, 1).note_from_user, 'Keep recipe notes')
            self.assertEqual(s.scalar(select(Recipe_Instruction)).text_contents, 'Keep instructions')
        before[1]['name_official'] = 'alcohol'
        self.assertEqual(after, before)
        self.assertEqual([r['row_id'] for r in self.proposals()], [2])

    def test_stale_row_or_catalogue_rolls_back_entire_selection(self):
        changes = self.proposals()
        with Session(self.engine) as s:
            s.get(Recipe_Ingredient, 2).note = 'Changed after preview'
            s.commit()
        with self.assertRaises(RematchError) as raised:
            apply_selected([r['token'] for r in changes])
        self.assertEqual(raised.exception.status, 409)
        with Session(self.engine) as s:
            self.assertEqual(s.get(Recipe_Ingredient, 1).name_official, 'gin')
        changes = self.proposals()
        catalogue_path().write_text(json.dumps({'alcohol': ['gin', 'other'], 'onion': []}), encoding='utf-8')
        with self.assertRaises(RematchError):
            apply_selected([r['token'] for r in changes])
        with Session(self.engine) as s:
            self.assertEqual(s.get(Recipe_Ingredient, 2).name_official, 'gin')

    def test_central_page_requires_explicit_selection_and_csrf(self):
        response = self.client.get('/image-aliases/rematch?name=alcohol')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 2)
        self.assertFalse(any(' checked' in element for element in re.findall(r'<input[^>]+type="checkbox"[^>]*>', response.text)))
        token = response.context['csrf_token']
        selected = response.context['rows'][0]['token']
        self.assertEqual(self.client.post('/image-aliases/rematch', data={'csrf_token': 'bad', 'selected': selected}).status_code, 403)
        self.assertEqual(self.client.post('/image-aliases/rematch', data={'csrf_token': token}).status_code, 422)
        self.assertEqual(self.client.post('/image-aliases/rematch', data={'csrf_token': token, 'selected': selected + 'x'}).status_code, 422)
        self.assertEqual(self.client.post('/image-aliases/rematch', data={'csrf_token': token,
                         'selected': selected, 'name': 'alcohol'}, follow_redirects=False).status_code, 303)
        self.assertNotIn('Re-match image', self.client.get('/recipes/1/edit').text)
        with patch.dict(os.environ, {'RECIPE_DEV_WRITES': '0'}):
            self.assertEqual(self.client.post('/image-aliases/rematch', data={'csrf_token': token, 'selected': selected}).status_code, 403)
