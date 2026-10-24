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

    def test_filters_include_unresolved_default_images_and_blank_assignments(self):
        with Session(self.engine) as session:
            session.add_all([
                Recipe_Ingredient(recipe_ingredient_id=10, recipe_id=1, name_written='gin', name_official='default_ingredient'),
                Recipe_Ingredient(recipe_ingredient_id=11, recipe_id=1, name_written='mystery', name_official=None),
                Recipe_Ingredient(recipe_ingredient_id=12, recipe_id=2, name_written='unknown', name_official=''),
                Recipe_Ingredient(recipe_ingredient_id=13, recipe_id=1, name_written='Heading', name_official='default_ingredient', is_group_header=True),
            ])
            session.commit()
        response = self.client.get('/image-aliases/rematch', params={'current': 'default_ingredient', 'scope': 'all'})
        rows = response.context['rows']
        self.assertEqual({row['row_id'] for row in rows}, {10, 11, 12})
        self.assertEqual(sum(bool(row['token']) for row in rows), 1)
        self.assertIn('No confident match', response.text)
        for query in ('One', 'oNe', '1'):
            response = self.client.get('/image-aliases/rematch', params={'recipe_query': query, 'current': 'default_ingredient', 'scope': 'all'})
            self.assertEqual({row['row_id'] for row in response.context['rows']}, {10, 11})
        response = self.client.get('/image-aliases/rematch', params={'recipe_query': '%', 'scope': 'all'})
        self.assertEqual(response.context['total'], 0)
        response = self.client.get('/image-aliases/rematch', params={'current': 'default_ingredient'})
        self.assertEqual([row['row_id'] for row in response.context['rows']], [10])

    def test_review_filters_survive_sort_pagination_error_and_apply(self):
        from urllib.parse import parse_qs, urlsplit
        with Session(self.engine) as session:
            session.add_all(Recipe_Ingredient(recipe_id=1, name_written='gin', name_official='default_ingredient') for _ in range(51))
            session.commit()
        filters = {'recipe_query': 'One', 'current': 'default_ingredient', 'scope': 'all', 'sort': 'ingredient', 'direction': 'desc', 'page': 2}
        response = self.client.get('/image-aliases/rematch', params=filters)
        self.assertEqual(len(response.context['rows']), 1)
        self.assertEqual(response.context['total'], 51)
        self.assertIn('current=default_ingredient', response.context['headers'][0]['url'])
        data = dict(filters, csrf_token=response.context['csrf_token'])
        error = self.client.post('/image-aliases/rematch', data=data)
        self.assertEqual(error.status_code, 422)
        self.assertEqual(error.context['page'], 2)
        self.assertEqual(error.context['current'], 'default_ingredient')
        data['selected'] = response.context['rows'][0]['token']
        saved = self.client.post('/image-aliases/rematch', data=data, follow_redirects=False)
        self.assertEqual(saved.status_code, 303)
        query = parse_qs(urlsplit(saved.headers['location']).query)
        for key, value in filters.items():
            self.assertEqual(query[key], [str(value)])

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

    def test_preparation_note_affects_preview_and_apply_and_staleness(self):
        catalogue_path().write_text(json.dumps({'garlic': [], 'minced_garlic': []}), encoding='utf-8')
        with Session(self.engine) as s:
            row = s.get(Recipe_Ingredient, 1)
            row.name_written, row.note, row.name_official = 'garlic', 'minced', 'garlic'
            s.commit()
        with Session(self.engine) as s:
            changes = affected_ingredients(s, 'minced_garlic')
        self.assertEqual([(r['row_id'], r['note'], r['proposed']) for r in changes],
                         [(1, 'minced', 'minced_garlic')])
        self.assertEqual(apply_selected([changes[0]['token']]), 1)
        with Session(self.engine) as s:
            self.assertEqual(s.get(Recipe_Ingredient, 1).name_official, 'minced_garlic')
            s.get(Recipe_Ingredient, 1).name_official = 'garlic'
            s.commit()
        with Session(self.engine) as s:
            changes = affected_ingredients(s, 'minced_garlic')
            s.get(Recipe_Ingredient, 1).note = 'whole'
            s.commit()
        with self.assertRaises(RematchError):
            apply_selected([changes[0]['token']])
        with Session(self.engine) as s:
            self.assertEqual(s.get(Recipe_Ingredient, 1).name_official, 'garlic')

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
