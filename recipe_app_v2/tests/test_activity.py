import os
import re
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from recipe_app_v2.database import ReadOnlySession, get_session
from recipe_app_v2.cooked_history import can_undo_cooked
from recipe_app_v2.main import app
from recipe_app_v2.models import (Base, Collection, Cuisine, Recipe, Recipe_Ingredient, Recipe_Instruction,
    Recipe_Plan_Date, recipe_collection, recipe_cooked_date, recipe_view_date)


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            collection = Collection(collection_id=1, collection_name='Favorites')
            recipe = Recipe(recipe_id=1, name='Chicken soup', create_dt=datetime(2025, 1, 1))
            recipe.collections.append(collection)
            session.add_all([recipe, Recipe(recipe_id=2, name='Bread', create_dt=datetime(2025, 1, 2)),
                Recipe_Ingredient(recipe_id=1, name_written='Chicken'),
                Recipe_Instruction(recipe_id=1, type=1, text_contents='Simmer')])
            session.commit()
        def sessions():
            with ReadOnlySession(self.engine, autoflush=False) as session:
                yield session
        app.dependency_overrides[get_session] = sessions
        self.environment = patch.dict(os.environ, {'RECIPE_DEV_WRITES': '1'})
        self.environment.start()
        self.writer = patch('recipe_app_v2.activity.get_write_engine', return_value=self.engine)
        self.writer.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.writer.stop()
        self.environment.stop()
        self.engine.dispose()

    def form(self, path='/'):
        body = self.client.get(path).text
        return {key: re.search(f'name="{key}" value="([^"]*)"', body)[1]
                for key in ('csrf_token', 'version') if f'name="{key}"' in body}

    def count(self, model):
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(model))

    def test_visits_cooking_readonly_mode_and_verification_optout(self):
        self.assertIn('1 recorded views', self.client.get('/recipes/1').text)
        self.assertEqual(self.count(recipe_view_date), 1)
        self.client.get('/recipes/1?log_visit=false')
        self.assertEqual(self.count(recipe_view_date), 1)
        data = self.form()
        target = '/recipes/1?sort=visited&q=chicken&collection_id=1'
        response = self.client.post('/recipes/1/actions/cooked', data=dict(data, return_to=target), follow_redirects=False)
        self.assertEqual(response.headers['location'], target)
        self.assertEqual(self.count(recipe_cooked_date), 1)
        with patch.dict(os.environ, {'RECIPE_DEV_WRITES': '0'}):
            self.client.get('/recipes/1')
            self.assertEqual(self.count(recipe_view_date), 1)
            self.assertEqual(self.client.post('/recipes/1/actions/cooked', data=data).status_code, 403)

    def test_undo_cooked_removes_only_the_latest_event(self):
        with Session(self.engine) as session:
            now = session.scalar(select(func.current_timestamp()))
            older = now - timedelta(hours=2)
            session.add_all([recipe_cooked_date(recipe_id=1, recipe_cooked_dt=older,
                                                recorded_dt=older),
                             recipe_cooked_date(recipe_id=1, recipe_cooked_dt=now - timedelta(hours=1),
                                                recorded_dt=now - timedelta(hours=1))])
            session.commit()
        response = self.client.get('/recipes/1?log_visit=false')
        self.assertIn('actions/undo-cooked', response.text)
        result = self.client.post('/recipes/1/actions/undo-cooked', data=self.form(), follow_redirects=False)
        self.assertEqual(result.status_code, 303)
        self.assertEqual(self.count(recipe_cooked_date), 1)
        with Session(self.engine) as session:
            remaining = session.scalar(select(recipe_cooked_date))
            self.assertEqual(remaining.recipe_cooked_dt, older)

    def test_undo_cooked_expires_after_24_hours(self):
        with Session(self.engine) as session:
            now = session.scalar(select(func.current_timestamp()))
            session.add_all([recipe_cooked_date(recipe_id=1, recipe_cooked_dt=now - timedelta(hours=25),
                                                recorded_dt=now - timedelta(hours=25)),
                             Recipe_Plan_Date(recipe_id=1)])
            session.commit()
        self.assertNotIn('actions/undo-cooked', self.client.get('/recipes/1?log_visit=false').text)
        self.assertNotIn('actions/undo-cooked', self.client.get('/plan').text)
        result = self.client.post('/recipes/1/actions/undo-cooked', data=self.form(), follow_redirects=False)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.count(recipe_cooked_date), 1)

    def test_undo_cooked_boundary(self):
        now = datetime(2026, 1, 1)
        self.assertTrue(can_undo_cooked(now - timedelta(hours=24) + timedelta(microseconds=1), now))
        self.assertFalse(can_undo_cooked(now - timedelta(hours=24), now))
        self.assertFalse(can_undo_cooked(now + timedelta(seconds=1), now))

    def test_cooked_can_be_recorded_again_after_an_existing_event(self):
        with Session(self.engine) as session:
            session.add(recipe_cooked_date(recipe_id=1, recipe_cooked_dt=datetime(2025, 1, 1),
                                           recorded_dt=datetime(2025, 1, 1)))
            session.commit()
        page = self.client.get('/recipes/1?log_visit=false').text
        self.assertIn('>Mark cooked</button>', page)
        self.assertNotIn('actions/undo-cooked', page)
        response = self.client.post('/recipes/1/actions/cooked', data=self.form(), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.count(recipe_cooked_date), 2)
        self.assertIn('actions/undo-cooked', self.client.get('/recipes/1?log_visit=false').text)

    def test_backdated_cooking_can_be_undone_within_24_hours_of_recording(self):
        data = dict(self.form(), cooked_date='2025-01-02')
        response = self.client.post('/recipes/1/actions/cooked', data=data, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with Session(self.engine) as session:
            cooked = session.scalar(select(recipe_cooked_date))
            self.assertEqual(cooked.recipe_cooked_dt.date(), datetime(2025, 1, 2).date())
            self.assertGreater(cooked.recorded_dt, cooked.recipe_cooked_dt)
        self.assertIn('actions/undo-cooked', self.client.get('/recipes/1?log_visit=false').text)
        response = self.client.post('/recipes/1/actions/undo-cooked', data=self.form(), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.count(recipe_cooked_date), 0)

    def test_favorites_are_idempotent_existing_collection_links_and_shared_badges(self):
        data = self.form()
        with Session(self.engine) as session:
            session.add(Collection(collection_id=2, collection_name='Dinner'))
            recipe = session.get(Recipe, 2)
            recipe.collections.append(session.get(Collection, 2))
            session.commit()
        for _ in range(2):
            response = self.client.post('/recipes/2/actions/favorite-add', data=data, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
        with Session(self.engine) as session:
            self.assertEqual(sorted(c.collection_id for c in session.get(Recipe, 2).collections), [1, 2])
            self.assertEqual(session.scalar(select(func.count()).select_from(recipe_collection).where(
                recipe_collection.c.recipe_id == 2)), 2)
        self.assertIn('aria-pressed="true"', self.client.get('/recipes/2?log_visit=false').text)
        self.assertEqual(self.client.get('/').text.count('class="favorite is-favorite"'), 2)
        self.client.post('/recipes/2/actions/plan-add', data=data, follow_redirects=False)
        self.assertIn('class="favorite is-favorite"', self.client.get('/plan').text)
        self.assertIn('data-favorite-collection', self.client.get('/recipes/2/edit').text)
        for _ in range(2):
            self.client.post('/recipes/2/actions/favorite-remove', data=data, follow_redirects=False)
        with Session(self.engine) as session:
            self.assertEqual([c.collection_id for c in session.get(Recipe, 2).collections], [2])
        self.assertIn('aria-pressed="false"', self.client.get('/recipes/2?log_visit=false').text)
        self.assertEqual(self.client.post('/recipes/2/actions/favorite-add', data={'csrf_token': 'bad'}).status_code, 403)
        with patch.dict(os.environ, {'RECIPE_DEV_WRITES': '0'}):
            self.assertEqual(self.client.post('/recipes/2/actions/favorite-add', data=data).status_code, 403)

    def test_plan_photo_controls_use_history_and_fragment_updates_nav_count(self):
        data = self.form()
        self.client.post('/recipes/1/actions/plan-add', data=data, follow_redirects=False)
        self.client.post('/recipes/1/actions/cooked', data=data, follow_redirects=False)
        body = self.client.get('/plan').text
        self.assertIn('aria-label="Cooked 1 times"', body)
        self.assertIn('class="favorite is-favorite"', body)
        self.assertIn('class="plan-trigger is-planned"', body)
        self.assertIn('name="return_to" value="/plan"', body)
        self.assertIn('actions/undo-cooked', body)
        fragment = self.client.get('/plan', headers={'HX-Request': 'true'}).text
        self.assertNotIn('<html', fragment)
        self.assertIn('id="app-plan-count" hx-swap-oob="outerHTML">1</span>', fragment)
        with patch.dict(os.environ, {'RECIPE_DEV_WRITES': '0'}):
            readonly = self.client.get('/plan').text
            self.assertIn('class="favorite-badge"', readonly)
            self.assertIn('class="plan-control plan-trigger is-planned"', readonly)
            self.assertNotIn('class="favorite-form"', readonly)

    def test_never_cooked_uses_history_and_pagination_preserves_filters(self):
        with Session(self.engine) as session:
            session.get(Recipe, 1).cooked_count = 99  # Stale legacy counters must not decide membership.
            session.add(recipe_cooked_date(recipe_id=2))
            session.add_all([Recipe(name=f'Uncooked {n}') for n in range(30)])
            session.commit()
        body = self.client.get('/?collection_id=-1&per_page=12&sort=name').text
        self.assertIn('data-recipe-id="1"', body)
        self.assertNotIn('data-recipe-id="2"', body)
        self.assertEqual(len(re.findall(r'data-recipe-id="\d+"', body)), 12)
        self.assertIn('collection_id=-1&amp;per_page=12', body)
        detail = self.client.get('/recipes/1?collection_id=-1&per_page=12&page=2&log_visit=false').text
        self.assertIn('page=2&amp;sort=recent&amp;collection_id=-1&amp;per_page=12', detail)
        response = self.client.post('/search', data=dict(self.form(), q='Uncooked', intent='sort',
            collection_id=-1, per_page=12), headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('collection_id=-1&per_page=12', response.headers['HX-Push-Url'])
        self.client.post('/recipes/1/actions/cooked', data=self.form(), follow_redirects=False)
        self.assertNotIn('data-recipe-id="1"', self.client.get('/?collection_id=-1').text)
        for size in (-1, 0, 500, 13):
            self.assertEqual(self.client.get(f'/?per_page={size}').status_code, 422)

    def test_plan_idempotence_grouping_soft_removal_and_back_navigation(self):
        data = self.form()
        for _ in range(2):
            self.assertEqual(self.client.post('/recipes/1/actions/plan-add', data=dict(data, return_to='/plan'), follow_redirects=False).status_code, 303)
        self.assertEqual(self.count(Recipe_Plan_Date), 1)
        body = self.client.get('/plan').text
        self.assertIn('data-plan-recipe-id="1"', body)
        self.assertIn('Added ', body)
        self.assertIn('Back to meal plan', self.client.get('/recipes/1?from_plan=true&log_visit=false').text)
        with Session(self.engine) as session:
            session.add(Recipe_Plan_Date(recipe_id=1))
            session.commit()
        self.assertEqual(self.client.get('/plan').text.count('data-plan-recipe-id="1"'), 1)
        self.client.post('/recipes/1/actions/plan-remove', data=data)
        with Session(self.engine) as session:
            plans = session.scalars(select(Recipe_Plan_Date)).all()
            self.assertEqual(len(plans), 2)
            self.assertTrue(all(p.removed_dt is not None for p in plans))
        self.assertIn('Your plan is clear.', self.client.get('/plan').text)

    def test_collection_search_sort_and_context_preservation(self):
        with Session(self.engine) as session:
            session.add(recipe_cooked_date(recipe_id=1, recipe_cooked_dt=datetime(2026, 1, 1)))
            session.add(recipe_view_date(recipe_id=1, recipe_view_dt=datetime(2026, 2, 1)))
            session.commit()
        for sort in ('cooked', 'visited'):
            body = self.client.get('/?sort=' + sort).text
            self.assertLess(body.index('data-recipe-id="1"'), body.index('data-recipe-id="2"'))
        body = self.client.get('/?collection_id=1&q=chicken&sort=visited').text
        self.assertIn('data-recipe-id="1"', body)
        self.assertNotIn('data-recipe-id="2"', body)
        self.assertIn('collection_id=1', body)
        response = self.client.post('/search', data=dict(self.form(), q='chicken', sort='cooked',
            collection_id='1', intent='sort'), headers={'HX-Request': 'true'})
        self.assertEqual(response.headers['HX-Push-Url'], '/?page=1&sort=cooked&q=chicken&collection_id=1')
        self.assertEqual(self.client.get('/?collection_id=999').status_code, 404)

    def test_collection_thumbnail_uses_cooking_count_not_recency_and_keeps_empty_collections(self):
        from recipe_app_v2.collections import collection_cards, all_recipes_thumbnail
        with Session(self.engine) as session:
            session.get(Collection, 1).collection_name = 'Kitchen'
            bread = session.get(Recipe, 2)
            bread.collections.append(session.get(Collection, 1))
            session.get(Recipe, 1).image_file = 'soup.jpg'
            session.get(Recipe, 2).image_file = 'bread.jpg'
            session.add(Collection(collection_id=2, collection_name='Empty'))
            session.add(Collection(collection_id=3, collection_name='Favorites'))
            session.add(Recipe(recipe_id=3, name='Global favorite', image_file='global.jpg'))
            session.add_all([recipe_cooked_date(recipe_id=1, recipe_cooked_dt=datetime(2024, 1, 1)),
                recipe_cooked_date(recipe_id=1, recipe_cooked_dt=datetime(2024, 1, 2)),
                recipe_cooked_date(recipe_id=2, recipe_cooked_dt=datetime(2026, 1, 1))])
            session.add_all([recipe_cooked_date(recipe_id=3) for _ in range(3)])
            session.commit()
            self.assertEqual(collection_cards(session)[0].collection_id, 3)
            self.assertEqual(all_recipes_thumbnail(session).thumbnail_recipe_id, 3)
            cards = {row.collection_id: row for row in collection_cards(session)}
            self.assertEqual(cards[1].thumbnail_recipe_id, 1)
            self.assertEqual(cards[1].image_file, 'soup.jpg')
            self.assertIsNone(cards[2].thumbnail_recipe_id)
        body = self.client.get('/?collection_id=1&q=chicken').text
        self.assertLess(body.index('data-collection-id="0"'), body.index('data-collection-id="-2"'))
        self.assertLess(body.index('data-collection-id="-2"'), body.index('data-collection-id="2"'))
        self.assertIn('data-collection-id="2"', body)
        self.assertIn('name="collection_id" value="1"', body)
        self.assertNotIn('<select id="collection-filter"', body)
        with Session(self.engine) as session:
            session.query(recipe_cooked_date).delete()
            session.commit()
            self.assertEqual(next(row for row in collection_cards(session) if row.collection_id == 1).thumbnail_recipe_id, 2)

    def test_reverse_sort_modes_and_navigation_context(self):
        with Session(self.engine) as session:
            session.get(Recipe, 2).name = 'Chicken bread'
            session.add_all([recipe_cooked_date(recipe_id=1, recipe_cooked_dt=datetime(2026, 1, 1)),
                recipe_view_date(recipe_id=1, recipe_view_dt=datetime(2026, 2, 1))])
            session.commit()
        for normal, reverse in [('recent', 'recent_asc'), ('name', 'name_desc'),
                                ('cooked', 'cooked_asc'), ('visited', 'visited_asc')]:
            ids = lambda body: re.findall(r'data-recipe-id="(\d+)"', body)
            forward = ids(self.client.get('/?sort=' + normal).text)
            body = self.client.get('/?sort=' + reverse).text
            self.assertEqual(ids(body), forward[::-1])
            self.assertIn('sort=' + reverse, body)
            response = self.client.post('/search', data=dict(self.form(), q='chicken', sort=reverse,
                collection_id='1', intent='sort'), headers={'HX-Request': 'true'})
            self.assertIn('sort=' + reverse, response.headers['HX-Push-Url'])
            detail = self.client.get(f'/recipes/1?sort={reverse}&collection_id=1&log_visit=false')
            self.assertEqual(detail.status_code, 200)
            self.assertIn('sort=' + reverse, detail.text)
            self.assertEqual(self.client.get(f'/recipes/1/delete?sort={reverse}').status_code, 200)

    def test_detail_htmx_actions_return_fragments_without_extra_visits(self):
        import json
        data = self.form('/recipes/1?log_visit=false')
        target = '/recipes/1?collection_id=-2&cuisine_id=0'
        response = self.client.post('/recipes/1/actions/cooked',
            data=dict(data, return_to=target), headers={'HX-Request': 'true'}, follow_redirects=False)
        self.assertEqual(response.status_code, 204)
        location = json.loads(response.headers['HX-Location'])
        self.assertEqual(location['target'], '#recipe-detail-page')
        self.assertEqual(location['path'], target)
        fragment = self.client.get(target, headers={'HX-Request': 'true'})
        self.assertEqual(fragment.status_code, 200)
        self.assertIn('id="recipe-detail-page"', fragment.text)
        self.assertIn('Cooked 1 time', fragment.text)
        self.assertIn('hx-swap-oob="outerHTML"', fragment.text)
        self.assertNotIn('<html', fragment.text)
        self.assertEqual(self.count(recipe_view_date), 0)
        self.assertEqual(self.count(recipe_cooked_date), 1)
        restored = self.client.get(target, headers={'HX-Request': 'true', 'HX-History-Restore-Request': 'true'})
        self.assertIn('<!doctype html>', restored.text)

    def test_cuisine_filter_survives_partials_search_and_detail_navigation(self):
        with Session(self.engine) as session:
            session.add(Cuisine(cuisine_id=1, cuisine_name='Korean'))
            session.get(Recipe, 1).cuisine_id = 1
            session.commit()
        target = '/?cuisine_id=1&collection_id=-2&per_page=12&sort=name'
        body = self.client.get(target, headers={'HX-Request': 'true'}).text
        self.assertIn('data-recipe-id="1"', body)
        self.assertNotIn('data-recipe-id="2"', body)
        self.assertIn('cuisine_id=1', body)
        self.assertIn('id="library-sidebar" class="library-sidebar" hx-swap-oob="outerHTML"', body)
        self.assertNotIn('<html', body)
        self.assertIn('id="cuisine-filter" name="cuisine_id"', self.client.get(target).text)
        detail = self.client.get('/recipes/1?cuisine_id=1&collection_id=-2&per_page=12&log_visit=false').text
        self.assertIn('collection_id=-2&amp;per_page=12&amp;cuisine_id=1', detail)
        response = self.client.post('/search', data=dict(self.form(), q='chicken', intent='sort',
            cuisine_id=1, collection_id=-2, per_page=12), headers={'HX-Request': 'true'})
        self.assertIn('cuisine_id=1', response.headers['HX-Push-Url'])
        self.assertEqual(self.client.get('/?cuisine_id=999').status_code, 404)
        self.assertEqual(self.client.post('/search', data=dict(self.form(), collection_id=999)).status_code, 404)

    def test_library_action_updates_counts_and_collection_membership(self):
        import json
        response = self.client.post('/recipes/1/actions/plan-add',
            data=dict(self.form(), return_to='/?collection_id=-3'),
            headers={'HX-Request': 'true'}, follow_redirects=False)
        location = json.loads(response.headers['HX-Location'])
        self.assertEqual(location['target'], '#recipes')
        self.assertNotIn('select', location)
        body = self.client.get(location['path'], headers={'HX-Request': 'true'}).text
        self.assertIn('id="app-plan-count" hx-swap-oob="outerHTML">1</span>', body)
        self.assertIn('data-recipe-id="1"', body)
        self.assertNotIn('data-recipe-id="2"', body)

    def test_detail_modal_deletes_using_current_version(self):
        body = self.client.get('/recipes/1?sort=name&q=chicken&collection_id=1&log_visit=false').text
        self.assertIn('<dialog id="delete-recipe-modal"', body)
        data = {key: re.search(f'name="{key}" value="([^\"]*)"', body)[1] for key in ('csrf_token', 'version')}
        target = '/?page=1&sort=name&q=chicken&collection_id=1'
        response = self.client.post('/recipes/1/delete', data=dict(data, return_to=target), follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], target)
        self.assertEqual(self.count(Recipe_Ingredient), 0)
        self.assertEqual(self.count(Recipe_Instruction), 0)

    def test_delete_removes_related_rows_but_preserves_other_recipes_and_tags(self):
        with Session(self.engine) as session:
            session.add_all([Recipe_Plan_Date(recipe_id=1), recipe_view_date(recipe_id=1), recipe_cooked_date(recipe_id=1)])
            session.commit()
        data = self.form('/recipes/1/delete?collection_id=1')
        response = self.client.post('/recipes/1/delete', data=dict(data, return_to='/?collection_id=1'), follow_redirects=False)
        self.assertEqual(response.headers['location'], '/?collection_id=1')
        for model in (Recipe_Ingredient, Recipe_Instruction, Recipe_Plan_Date, recipe_view_date, recipe_cooked_date):
            self.assertEqual(self.count(model), 0)
        with Session(self.engine) as session:
            self.assertIsNone(session.get(Recipe, 1))
            self.assertIsNotNone(session.get(Recipe, 2))
            self.assertIsNotNone(session.get(Collection, 1))
            self.assertEqual(session.scalar(select(func.count()).select_from(recipe_collection)), 0)

    def test_csrf_return_location_stale_confirmation_and_rollback(self):
        data = self.form()
        self.assertEqual(self.client.post('/recipes/1/actions/cooked', data={'csrf_token': 'bad'}).status_code, 403)
        for target in ('https://example.com', '//example.com', '/tags/collections'):
            self.assertEqual(self.client.post('/recipes/1/actions/cooked', data=dict(data, return_to=target)).status_code, 422)
        data = self.form('/recipes/1/delete')
        with Session(self.engine) as session:
            session.add(recipe_cooked_date(recipe_id=1))
            session.commit()
        self.assertIn('Reload confirmation', self.client.post('/recipes/1/delete', data=data).text)
        data = self.form('/recipes/1/delete')
        from sqlalchemy.exc import OperationalError
        with patch('recipe_app_v2.activity.Session.commit', side_effect=OperationalError('test', {}, Exception())):
            self.assertEqual(self.client.post('/recipes/1/delete', data=data).status_code, 503)
        self.assertEqual(self.count(Recipe), 2)
        self.assertEqual(self.count(Recipe_Ingredient), 1)
