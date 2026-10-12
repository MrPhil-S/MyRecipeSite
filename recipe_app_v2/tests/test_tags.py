import os
import re
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from recipe_app_v2.database import ReadOnlySession, get_session
from recipe_app_v2.main import app
from recipe_app_v2.models import Base, Collection, Cuisine, Ingredient_Synonym, Recipe, Recipe_Ingredient


class TagTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)

        def sessions():
            with ReadOnlySession(self.engine, autoflush=False) as session:
                yield session
        app.dependency_overrides[get_session] = sessions
        self.environment = patch.dict(os.environ, {'RECIPE_DEV_WRITES': '1'})
        self.environment.start()
        self.writer = patch('recipe_app_v2.tags.get_write_engine', return_value=self.engine)
        self.writer.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.writer.stop()
        self.environment.stop()
        self.engine.dispose()

    def form(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return {key: re.search(f'name="{key}" value="([^"]*)"', response.text)[1]
                for key in ('csrf_token', 'version')}

    def test_table_sorting_counts_secondary_names_and_pagination(self):
        with Session(self.engine) as session:
            collections = [Collection(collection_name=f'Collection {i:02d}') for i in range(60)]
            cuisines = [Cuisine(cuisine_id=1, cuisine_name='Zulu'), Cuisine(cuisine_id=2, cuisine_name='Alpha')]
            session.add_all(collections + cuisines)
            session.flush()
            session.add_all([Recipe(name='One', cuisine_id=1, collections=[collections[-1]]),
                             Recipe(name='Two', cuisine_id=1, collections=[collections[-1]])])
            session.add_all([Ingredient_Synonym(primary_term='Zulu', secondary_term='Alpha'),
                             Ingredient_Synonym(primary_term='Alpha', secondary_term='Zulu')])
            session.commit()
            last_id = collections[-1].collection_id
        response = self.client.get('/tags/collections?sort=recipes&direction=desc&q=Collection')
        self.assertEqual(response.context['rows'][0]['id'], last_id)
        self.assertEqual(response.context['rows'][0]['assigned'], 2)
        self.assertIn('aria-sort="descending"', response.text)
        self.assertIn('page=2', response.text)
        self.assertIn('direction=desc', response.text)
        self.assertEqual(len(self.client.get('/tags/collections?sort=name&direction=desc&page=2').context['rows']), 10)
        self.assertEqual(self.client.get('/tags/cuisines?sort=recipes&direction=desc').context['rows'][0]['values'], ['Zulu'])
        self.assertEqual(self.client.get('/tags/synonyms?sort=secondary_term&direction=desc').context['rows'][0]['values'], ['Alpha', 'Zulu'])
        self.assertEqual(self.client.get('/tags/synonyms?sort=recipes').status_code, 422)

    def create(self, kind, values):
        response = self.client.post(f'/tags/{kind}/new', data=dict(self.form(f'/tags/{kind}/new'), **values),
                                    follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        model = {'collections': Collection, 'cuisines': Cuisine, 'synonyms': Ingredient_Synonym}[kind]
        with Session(self.engine) as session:
            return session.scalar(select(model)).__dict__[list(model.__table__.primary_key)[0].name]

    def test_create_edit_delete_all_three_types(self):
        for kind, values, changes in (
            ('collections', {'collection_name': 'Dinner'}, {'collection_name': 'Lunch'}),
            ('cuisines', {'cuisine_name': 'Italian'}, {'cuisine_name': 'French'}),
            ('synonyms', {'primary_term': 'coriander', 'secondary_term': 'cilantro'},
                         {'primary_term': 'aubergine', 'secondary_term': 'eggplant'})):
            tag_id = self.create(kind, values)
            path = f'/tags/{kind}/{tag_id}/edit'
            response = self.client.post(path, data=dict(self.form(path), **changes), headers={'HX-Request': 'true'})
            self.assertEqual(response.headers.get('HX-Redirect'), f'/tags/{kind}')
            self.assertIn(list(changes.values())[0], self.client.get(f'/tags/{kind}').text)
            path = f'/tags/{kind}/{tag_id}/delete'
            self.assertEqual(self.client.post(path, data=self.form(path), follow_redirects=False).status_code, 303)
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_deletion_clears_only_tag_assignments_and_keeps_recipes(self):
        collection_id = self.create('collections', {'collection_name': 'Favorites'})
        cuisine_id = self.create('cuisines', {'cuisine_name': 'Italian'})
        with Session(self.engine) as session:
            recipe = Recipe(name='Keep recipe', cuisine_id=cuisine_id)
            recipe.collections.append(session.get(Collection, collection_id))
            session.add(recipe)
            session.commit()
            recipe_id = recipe.recipe_id
        for kind, tag_id in (('collections', collection_id), ('cuisines', cuisine_id)):
            path = f'/tags/{kind}/{tag_id}/delete'
            self.assertIn('1 recipe assignment', self.client.get(path).text)
            response = self.client.post(path, data=self.form(path), follow_redirects=False)
            self.assertEqual(response.status_code, 303)
        with Session(self.engine) as session:
            recipe = session.get(Recipe, recipe_id)
            self.assertEqual(recipe.name, 'Keep recipe')
            self.assertIsNone(recipe.cuisine_id)
            self.assertEqual(recipe.collections, [])

    def test_validation_duplicates_reverse_pairs_escaping_and_literal_filter(self):
        self.create('collections', {'collection_name': 'Favorites'})
        for value in ('favorites', ' ', 'x' * 31):
            path = '/tags/collections/new'
            response = self.client.post(path, data=dict(self.form(path), collection_name=value))
            self.assertEqual(response.status_code, 422)
        self.create('synonyms', {'primary_term': 'coriander', 'secondary_term': 'cilantro'})
        path = '/tags/synonyms/new'
        for primary, secondary in (('cilantro', 'coriander'), ('same', 'SAME'), ('x' * 101, 'other')):
            response = self.client.post(path, data=dict(self.form(path), primary_term=primary, secondary_term=secondary))
            self.assertEqual(response.status_code, 422)
        self.create('cuisines', {'cuisine_name': '<script>100%_</script>'})
        body = self.client.get('/tags/cuisines?q=%25_').text
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('<script>100', body)

    def test_stale_edit_and_changed_assignments_block_deletion(self):
        tag_id = self.create('collections', {'collection_name': 'Before'})
        path = f'/tags/collections/{tag_id}/edit'
        data = dict(self.form(path), collection_name='My change')
        with Session(self.engine) as session:
            session.get(Collection, tag_id).collection_name = 'Changed elsewhere'
            session.commit()
        self.assertEqual(self.client.post(path, data=data).status_code, 409)
        path = f'/tags/collections/{tag_id}/delete'
        data = self.form(path)
        with Session(self.engine) as session:
            recipe = Recipe(name='New assignment')
            recipe.collections.append(session.get(Collection, tag_id))
            session.add(recipe)
            session.commit()
        self.assertEqual(self.client.post(path, data=data).status_code, 409)
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(Collection, tag_id))

    def test_synonym_changes_immediately_affect_recipe_search(self):
        with Session(self.engine) as session:
            session.add(Recipe(recipe_id=1, name='Herb recipe'))
            session.add(Recipe_Ingredient(recipe_id=1, name_written='coriander'))
            session.commit()
        self.assertNotIn('data-recipe-id="1"', self.client.get('/?q=cilantro').text)
        tag_id = self.create('synonyms', {'primary_term': 'coriander', 'secondary_term': 'cilantro'})
        self.assertIn('data-recipe-id="1"', self.client.get('/?q=cilantro').text)
        path = f'/tags/synonyms/{tag_id}/delete'
        self.client.post(path, data=self.form(path))
        self.assertNotIn('data-recipe-id="1"', self.client.get('/?q=cilantro').text)

    def test_readonly_csrf_missing_tag_pagination_and_failed_commit(self):
        path = '/tags/collections/new'
        data = dict(self.form(path), collection_name='Must not save')
        self.assertEqual(self.client.post(path, data=dict(data, csrf_token='forged')).status_code, 403)
        with patch.dict(os.environ, {'RECIPE_DEV_WRITES': '0'}):
            self.assertEqual(self.client.post(path, data=data).status_code, 403)
        from sqlalchemy.exc import OperationalError
        with patch('recipe_app_v2.tags.Session.commit', side_effect=OperationalError('test', {}, Exception())):
            self.assertEqual(self.client.post(path, data=data).status_code, 503)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Collection)), 0)
            session.add_all(Collection(collection_name=f'Collection {i:02}') for i in range(55))
            session.commit()
        self.assertEqual(self.client.get('/tags/collections').text.count('data-tag-id='), 50)
        self.assertEqual(self.client.get('/tags/collections?page=2').text.count('data-tag-id='), 5)
        self.assertEqual(self.client.get('/tags/collections/999/delete').status_code, 404)
        self.assertEqual(self.client.get('/tags/invalid').status_code, 422)

    def test_multiple_aliases_create_group_and_invalid_batch_rolls_back(self):
        path = '/tags/synonyms/new'
        response = self.client.post(path, data=dict(self.form(path), primary_term='green onion',
            secondary_term='spring onion\nscallion'), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Ingredient_Synonym)), 2)
        self.assertIn('green onion ↔ scallion ↔ spring onion', self.client.get('/tags/synonyms').text)
        for aliases in ('fresh onion\nscallion', 'green onion\nother', 'other\nOTHER', 'valid\n' + 'x' * 101):
            response = self.client.post(path, data=dict(self.form(path), primary_term='green onion', secondary_term=aliases))
            self.assertEqual(response.status_code, 422)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Ingredient_Synonym)), 2)
