import tempfile
import unittest
import runpy
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from recipe_app_v2.config import dev_database_url
from recipe_app_v2.database import ReadOnlySession, get_session, guard_statement
from recipe_app_v2.main import app
from recipe_app_v2.models import (Base, Collection, Cuisine, Recipe, Recipe_Ingredient,
                                 Recipe_Instruction, recipe_cooked_date)


class SafetyTests(unittest.TestCase):
    def test_online_alembic_guard_without_connection(self):
        env = Path(__file__).resolve().parents[1] / "migrations/env.py"
        with patch("alembic.context.is_offline_mode", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "Online Alembic operations are disabled"):
                runpy.run_path(str(env))

    def test_production_and_wrong_targets_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.ini"
            for uri in ["mysql+pymysql://user:secret@192.168.1.14:3307/MyRecipes",
                        "mysql+pymysql://user:secret@example.com:3307/MyRecipes_DEV",
                        "mysql+pymysql://user:secret@192.168.1.14:3307/MyRecipes_DEV?database=MyRecipes"]:
                config.write_text("[dev]\ndb_uri=" + uri)
                with self.assertRaises(RuntimeError) as error:
                    dev_database_url(config)
                self.assertNotIn("secret", str(error.exception))

    def test_percent_in_password_is_not_interpolated(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.ini"
            config.write_text("[dev]\ndb_uri=mysql+pymysql://user:pass%25word@192.168.1.14:3307/MyRecipes_DEV")
            self.assertEqual(dev_database_url(config).password, "pass%word")

    def test_sql_write_and_override_statements_rejected(self):
        for sql in ["INSERT INTO recipe VALUES (1)", "DELETE FROM recipe",
                    "CREATE TABLE test (id int)", "SET SESSION TRANSACTION READ WRITE"]:
            with self.assertRaises(RuntimeError):
                guard_statement(None, None, sql, None, None, False)

    def test_orm_flush_rejected(self):
        engine = create_engine("sqlite://")
        with ReadOnlySession(engine) as session:
            session.add(Recipe(name="Must not be written"))
            with self.assertRaises(RuntimeError):
                session.flush()
        engine.dispose()


class ListTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            for i in range(1, 27):
                session.add(Recipe(recipe_id=i, name=f"Recipe {i:02d}", create_dt=datetime(2026, 1, 1), image_file=None))
            session.add_all([
                Recipe_Ingredient(recipe_id=26, name_written="Section", is_group_header=True),
                Recipe_Ingredient(recipe_id=26, name_written="Onion", is_group_header=None),
                Recipe_Ingredient(recipe_id=26, name_written="Oil", is_group_header=False),
                recipe_cooked_date(recipe_id=26), recipe_cooked_date(recipe_id=26),
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

    def test_pagination_sort_partial_and_counts(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertEqual(body.count('data-recipe-id="'), 24)
        self.assertLess(body.index('data-recipe-id="26"'), body.index('data-recipe-id="25"'))
        self.assertIn("2 ingredients", body)
        self.assertIn("Cooked 2 times", body)
        partial = self.client.get("/?page=2", headers={"HX-Request": "true"}).text
        self.assertEqual(partial.count('data-recipe-id="'), 2)
        self.assertNotIn("<!doctype", partial)
        restored = self.client.get("/", headers={"HX-Request": "true", "HX-History-Restore-Request": "true"})
        self.assertIn("<!doctype", restored.text)
        alphabetical = self.client.get("/?sort=name").text
        self.assertLess(alphabetical.index('data-recipe-id="1"'), alphabetical.index('data-recipe-id="2"'))
        self.assertIn("Page 2 of 2", self.client.get("/?page=999999").text)

    def test_validation_no_write_routes_or_view_records(self):
        for path in ["/?page=0", "/?sort=invalid"]:
            self.assertEqual(self.client.get(path).status_code, 422)
        self.assertEqual(self.client.post("/").status_code, 405)
        self.assertEqual(self.client.get("/recipes/26").status_code, 200)
        self.assertEqual(self.client.post("/recipes/26").status_code, 405)
        with Session(self.engine) as session:
            self.assertEqual(len(session.scalars(select(Recipe)).all()), 26)
            self.assertEqual(session.scalar(text("SELECT count(*) FROM recipe_view_date")), 0)

    def test_empty_list_and_html_escaping(self):
        with Session(self.engine) as session:
            recipe = session.get(Recipe, 26)
            recipe.name = '<script>alert("x")</script>'
            session.commit()
        self.assertIn("&lt;script&gt;", self.client.get("/").text)
        with Session(self.engine) as session:
            session.execute(text("DELETE FROM recipe"))
            session.commit()
        body = self.client.get("/").text
        self.assertIn("No recipes found.", body)
        self.assertIn("Page 1 of 1", body)

    def test_detail_group_order_numbering_notes_and_navigation(self):
        with Session(self.engine) as session:
            recipe = session.get(Recipe, 26)
            recipe.note_from_user = 'First line\n<script>unsafe</script>'
            recipe.source_url = 'javascript:alert(1)'
            recipe.cuisine_id = 1
            session.add(Cuisine(cuisine_id=1, cuisine_name='Test cuisine'))
            recipe.collections.append(Collection(collection_name='Favorites'))
            session.add_all([
                Recipe_Instruction(recipe_instruction_id=11, recipe_id=26, type=1, sequence=1, text_contents='Sauce', is_group_header=True),
                Recipe_Instruction(recipe_instruction_id=13, recipe_id=26, type=1, sequence=2, text_contents='Simmer', is_group_header=False),
                Recipe_Instruction(recipe_instruction_id=12, recipe_id=26, type=1, sequence=2, text_contents='Stir', is_group_header=False),
                Recipe_Instruction(recipe_instruction_id=14, recipe_id=26, type=1, sequence=3, text_contents='Serve', is_group_header=True),
                Recipe_Instruction(recipe_instruction_id=15, recipe_id=26, type=1, sequence=4, text_contents='Plate', is_group_header=False),
                Recipe_Instruction(recipe_instruction_id=16, recipe_id=26, type=2, sequence=1, text_contents='Source advice'),
            ])
            session.commit()
        body = self.client.get('/recipes/26?page=2&sort=name').text
        self.assertIn('/?page=2&amp;sort=name', body)
        self.assertIn('Ingredients <span>2</span>', body)
        self.assertIn('3 steps', body)
        self.assertEqual(body.count('<h3>Step 1</h3>'), 2)
        self.assertEqual(body.count('<h3>Step 2</h3>'), 1)
        self.assertNotIn('<h3>Step 3</h3>', body)
        self.assertLess(body.index('>Stir</p>'), body.index('>Simmer</p>'))
        self.assertLess(body.index('>Simmer</p>'), body.index('>Plate</p>'))
        self.assertIn('class="recipe-deck preserve-lines">First line', body)
        self.assertNotIn('class="personal-note"', body)
        self.assertNotIn('/static/app.css', body)
        for value in ['Test cuisine', 'Favorites', 'Source advice', '&lt;script&gt;']:
            self.assertIn(value, body)
        self.assertNotIn('javascript:', body)
        with Session(self.engine) as session:
            self.assertEqual(session.get(Recipe_Instruction, 12).text_contents, 'Stir')
            self.assertEqual(session.scalar(text('SELECT count(*) FROM recipe_view_date')), 0)

    def test_detail_missing_empty_and_single_instruction(self):
        response = self.client.get('/recipes/99999')
        self.assertEqual(response.status_code, 404)
        self.assertIn('Recipe not found', response.text)
        body = self.client.get('/recipes/1').text
        self.assertIn('No ingredients recorded.', body)
        self.assertIn('No instructions recorded.', body)
        self.assertNotIn('None', body)
        with Session(self.engine) as session:
            session.add(Recipe_Instruction(recipe_id=1, type=1, text_contents='Combine everything', is_group_header=False))
            session.commit()
        body = self.client.get('/recipes/1').text
        self.assertIn('Combine everything', body)
        self.assertNotIn('1. Combine everything', body)
        self.assertEqual(self.client.get('/recipes/0').status_code, 422)


if __name__ == "__main__":
    unittest.main()
