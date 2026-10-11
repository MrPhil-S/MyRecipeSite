"""Read-only localhost parity checks against legacy Flask and real dev rows."""
import json
import re

import httpx
from sqlalchemy import func, select

from recipe_app_v2.database import get_engine
from recipe_app_v2.models import Recipe, Recipe_Ingredient, recipe_cooked_date


def verify():
    with get_engine().connect() as conn:
        expected_ids = list(conn.scalars(select(Recipe.recipe_id).order_by(Recipe.create_dt.desc(), Recipe.recipe_id.desc())))
        ingredient_counts = dict(conn.execute(
            select(Recipe_Ingredient.recipe_id, func.count())
            .where(func.coalesce(Recipe_Ingredient.is_group_header, False) != True)
            .group_by(Recipe_Ingredient.recipe_id)).all())
        cooked_counts = dict(conn.execute(
            select(recipe_cooked_date.recipe_id, func.count()).group_by(recipe_cooked_date.recipe_id)).all())
    with httpx.Client(timeout=30) as client:
        legacy = client.get("http://127.0.0.1:8080/")
        legacy.raise_for_status()
        legacy_ids = {int(value) for value in re.findall(r'href="/recipes/(\d+)"', legacy.text)}
        assert legacy_ids == set(expected_ids), "Flask recipe set differs"
        seen = []
        cards_checked = 0
        for page in range(1, max(1, (len(expected_ids) + 23) // 24) + 1):
            response = client.get(f"http://127.0.0.1:8001/?page={page}")
            response.raise_for_status()
            for recipe_id, body in re.findall(r'data-recipe-id="(\d+)"\s*>(.*?)</article>', response.text, re.S):
                recipe_id = int(recipe_id)
                seen.append(recipe_id)
                assert f"{ingredient_counts.get(recipe_id, 0)} ingredients" in body
                cooked = cooked_counts.get(recipe_id, 0)
                if cooked:
                    assert f"Cooked {cooked} times" in body
                cards_checked += 1
        assert seen == expected_ids, "Pagination order or recipe set differs"
        partial = client.get("http://127.0.0.1:8001/?sort=name", headers={"HX-Request": "true"})
        partial.raise_for_status()
        assert '<section id="recipes"' in partial.text and "<!doctype" not in partial.text
        first = client.get("http://127.0.0.1:8001/")
        image_paths = re.findall(r'src="(/recipe-images/[^\"]+)"', first.text)
        image_statuses = {}
        for path in image_paths[:3]:
            image_statuses[path] = client.get("http://127.0.0.1:8001" + path).status_code
        for path in ["/static/app.css", "/static/vendor/htmx.min.js", "/static/vendor/alpine.min.js", "/health"]:
            client.get("http://127.0.0.1:8001" + path).raise_for_status()
        assert client.post("http://127.0.0.1:8001/").status_code == 405
    print(json.dumps({"flask_status": legacy.status_code, "fastapi_status": first.status_code,
                      "matching_recipes": len(seen), "cards_checked": cards_checked,
                      "htmx_partial": "ok", "assets_and_health": "ok", "sample_images": image_statuses}, indent=2))


if __name__ == "__main__":
    verify()
