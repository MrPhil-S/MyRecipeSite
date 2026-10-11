"""Private read-only snapshot and legacy helper comparison; never POST search."""
import json

from recipe_app_v2.run_flask_preview import app, db
from recipe_app_v2.search_cases import CASES
from myrecipes.helpers import parse_search_query, search_recipe, search_recipe_ingredient
from myrecipes.models import (Ingredient_Synonym, Query_History, Recipe,
                              Recipe_Ingredient, Recipe_Instruction, recipe_view_date)


def snapshot():
    with app.app_context():
        recipes = [{'id': r.recipe_id, 'name': r.name, 'notes': r.note_from_user or ''}
                   for r in Recipe.query.order_by(Recipe.create_dt.desc(), Recipe.recipe_id.desc())]
        ingredients = [{'id': r.recipe_id, 'text': (r.name_written or '') + ' ' + (r.note or '')}
                       for r in Recipe_Ingredient.query.all()]
        instructions = [{'id': r.recipe_id, 'text': r.text_contents}
                        for r in Recipe_Instruction.query.all()]
        synonyms = [(r.primary_term, r.secondary_term) for r in Ingredient_Synonym.query.all()]
        legacy = {}
        for query, _, _ in CASES:
            if '%' in query or '_' in query or query.count('"') % 2:
                # SQL wildcards and incomplete quotes have intentionally new semantics.
                continue
            tokens, excluded = parse_search_query(query)
            ids = set()
            for term in tokens:
                matches = set(search_recipe(term) + search_recipe_ingredient(term))
                if not ids:
                    ids = matches
                else:
                    ids.intersection_update(matches)
            for term in excluded:
                ids.difference_update(search_recipe(term) + search_recipe_ingredient(term))
            legacy[query] = sorted(ids)
        result = {'recipes': recipes, 'ingredients': ingredients, 'instructions': instructions,
                  'synonyms': synonyms, 'legacy': legacy,
                  'name_order': [r.recipe_id for r in Recipe.query.order_by(Recipe.name, Recipe.recipe_id)],
                  'history_count': Query_History.query.count(), 'visit_count': recipe_view_date.query.count()}
        db.session.rollback()
        return result


if __name__ == '__main__':
    print(json.dumps(snapshot()))
