import re
import unittest
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from recipe_app_v2.database import ReadOnlySession, get_session
from recipe_app_v2.main import app
from recipe_app_v2.models import (Base, Ingredient_Synonym, Query_History, Recipe,
                                 Recipe_Ingredient, Recipe_Instruction, recipe_view_date)
from recipe_app_v2.search import search_terms, synonym_groups


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([
                Recipe(recipe_id=1, name='Turkey cups', create_dt=datetime(2026, 1, 1)),
                Recipe(recipe_id=2, name='Meatballs', note_from_user='Add cinnamon', create_dt=datetime(2026, 1, 1)),
                Recipe(recipe_id=3, name='Herb tray', create_dt=datetime(2026, 1, 1)),
                Recipe(recipe_id=4, name='100%_special', create_dt=datetime(2026, 1, 1)),
                Recipe_Ingredient(recipe_id=1, name_written='ground turkey', note=None),
                Recipe_Ingredient(recipe_id=2, name_written='ground beef', note='chopped onion'),
                Recipe_Ingredient(recipe_id=3, name_written='fresh coriander', note=None),
                Ingredient_Synonym(primary_term='cilantro', secondary_term='coriander'),
                Recipe_Instruction(recipe_id=1, type=1, text_contents='Broil until crisp'),
                Recipe_Instruction(recipe_id=2, type=2, text_contents='Heavy cream works well'),
            ])
            session.commit()
        def sessions():
            with ReadOnlySession(self.engine, autoflush=False) as session:
                yield session
        app.dependency_overrides[get_session] = sessions
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def ids(self, q, **kwargs):
        response = self.client.get('/', params={'q': q, **kwargs})
        self.assertEqual(response.status_code, 200)
        return [int(n) for n in re.findall(r'data-recipe-id="(\d+)"', response.text)]

    def test_fields_case_null_notes_and_synonyms(self):
        for query, expected in [('TURKEY', [1]), ('ground turkey', [1]), ('chopped onion', [2]),
                                ('cinnamon', [2]), ('broil', [1]), ('heavy cream', [2]),
                                ('cilantro', [3]), ('coriander', [3])]:
            self.assertEqual(self.ids(query), expected)

    def test_and_phrases_and_exclusion(self):
        self.assertEqual(self.ids('missing turkey'), [])
        self.assertEqual(self.ids('turkey missing'), [])
        self.assertEqual(self.ids('ground NOT beef'), [1])
        self.assertEqual(self.ids('NOT beef'), [4, 3, 1])
        self.assertEqual(self.ids('NOT cilantro'), [4, 2, 1])
        self.assertEqual(self.ids('"ground turkey" NOT cream'), [1])
        self.assertEqual(self.ids('"ground tur'), [1])
        self.assertEqual(search_terms('"NOT" chicken NOT "heavy cream"'), (['NOT', 'chicken'], ['heavy cream']))

    def test_literal_wildcards_and_search_state(self):
        self.assertEqual(self.ids('%'), [4])
        self.assertEqual(self.ids('_'), [4])
        self.assertEqual(self.ids('100%_'), [4])
        self.assertEqual(self.ids(''), [4, 3, 2, 1])
        self.assertEqual(self.ids(' ground turkey '), [1])
        typed = self.client.get('/', params={'q': 'ground '}, headers={'HX-Request': 'true'})
        self.assertNotIn('id="search-query"', typed.text)
        self.assertIn('value="ground "', self.client.get('/', params={'q': 'ground '}).text)
        page = self.client.get('/', params={'q': 'ground turkey', 'sort': 'name'}, headers={'HX-Request': 'true'})
        self.assertNotIn('<!doctype', page.text)
        self.assertIn('q=ground+turkey', page.text)
        detail = self.client.get('/recipes/1', params={'q': 'ground turkey', 'page': 2, 'sort': 'name'})
        self.assertIn('/?page=2&amp;sort=name&amp;q=ground+turkey', detail.text)
        self.assertIn('Back to search results', detail.text)
        self.assertEqual(self.client.get('/', params={'q': 'a' * 201}).status_code, 422)
        self.ids('"<script>"')
        self.assertNotIn('<script>"', self.client.get('/', params={'q': '"<script>"'}).text)
        with Session(self.engine) as session:
            self.assertEqual(session.scalars(select(Query_History)).all(), [])
            self.assertEqual(session.scalars(select(recipe_view_date)).all(), [])

    def test_connected_multiword_groups_cycles_and_exclusions(self):
        with Session(self.engine) as session:
            for recipe_id, name in ((5, 'spring onion'), (6, 'scallion'), (7, 'green onion')):
                session.add(Recipe(recipe_id=recipe_id, name=f'Ingredient test {recipe_id}'))
                session.add(Recipe_Ingredient(recipe_id=recipe_id, name_written=name))
            session.add_all([
                Ingredient_Synonym(primary_term=' Green Onion ', secondary_term='spring onion'),
                Ingredient_Synonym(primary_term='GREEN ONION', secondary_term='scallion'),
                Ingredient_Synonym(primary_term='Spring Onion', secondary_term='SCALLION'),
                Ingredient_Synonym(primary_term='red onion', secondary_term='purple onion'),
            ])
            session.commit()
        for q in ('green onion', 'spring onion', 'scallion', '"green onion"', '"spring onion"', 'SCALL'):
            self.assertEqual(set(self.ids(q)), {5, 6, 7}, q)
        self.assertEqual(set(self.ids('NOT "spring onion"')), {1, 2, 3, 4})
        self.assertEqual(self.ids('"red onion"'), [])
        with ReadOnlySession(self.engine) as session:
            groups = synonym_groups(session)
            self.assertIn(['green onion', 'scallion', 'spring onion'], groups)
            self.assertIn(['purple onion', 'red onion'], groups)

    def test_removed_link_splits_group_without_cached_matches(self):
        with Session(self.engine) as session:
            for recipe_id, name in ((5, 'spring onion'), (6, 'scallion'), (7, 'green onion')):
                session.add(Recipe(recipe_id=recipe_id, name=f'Ingredient test {recipe_id}'))
                session.add(Recipe_Ingredient(recipe_id=recipe_id, name_written=name))
            session.add_all([
                Ingredient_Synonym(primary_term='green onion', secondary_term='spring onion'),
                Ingredient_Synonym(primary_term='spring onion', secondary_term='scallion'),
            ])
            session.commit()
        self.assertEqual(set(self.ids('scallion')), {5, 6, 7})
        with Session(self.engine) as session:
            edge = session.scalar(select(Ingredient_Synonym).where(Ingredient_Synonym.secondary_term == 'scallion'))
            session.delete(edge)
            session.commit()
        self.assertEqual(self.ids('scallion'), [6])
        self.assertEqual(set(self.ids('"spring onion"')), {5, 7})


if __name__ == '__main__':
    unittest.main()
