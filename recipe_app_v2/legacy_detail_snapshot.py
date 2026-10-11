"""Render legacy detail templates without calling the visit-writing route.

Run with MyRecipesVenv. Output is consumed privately by verify_details.py.
"""
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from flask import render_template
from sqlalchemy import event

from recipe_app_v2.run_flask_preview import app, db
from myrecipes.models import (Cuisine, Recipe, Recipe_Ingredient, Recipe_Instruction,
                              recipe_cooked_date, recipe_view_date)


def forbid_flush(session, context, instances):
    raise RuntimeError("Legacy comparison cannot write to the database")


def snapshot():
    event.listen(db.session, "before_flush", forbid_flush)
    with app.app_context(), app.test_request_context('/'):
        ingredients = defaultdict(list)
        instructions = defaultdict(list)
        notes = defaultdict(list)
        for row in Recipe_Ingredient.query.order_by(Recipe_Ingredient.sequence, Recipe_Ingredient.recipe_ingredient_id):
            values = {col.name: getattr(row, col.name) for col in row.__table__.columns}
            values['name_official'] = values['name_official'] or ''
            ingredients[row.recipe_id].append(SimpleNamespace(**values))
        for row in Recipe_Instruction.query.order_by(Recipe_Instruction.sequence, Recipe_Instruction.recipe_instruction_id):
            values = {col.name: getattr(row, col.name) for col in row.__table__.columns}
            if row.type == 1:
                instructions[row.recipe_id].append(SimpleNamespace(**values))
            elif row.type == 2:
                notes[row.recipe_id].append(SimpleNamespace(**values))
        cuisines = {row.cuisine_id: row for row in Cuisine.query.all()}
        result = []
        before = recipe_view_date.query.count()
        for recipe in Recipe.query.order_by(Recipe.recipe_id):
            steps = instructions[recipe.recipe_id]
            count = sum(step.is_group_header == 0 for step in steps)
            number = 0
            for step in steps:
                if step.is_group_header:
                    number = 0
                elif count > 1:
                    number += 1
                    step.text_contents = f'{number}. {step.text_contents}'
            pdf_path = Path(app.root_path) / 'static/custom_prints' / f'{recipe.recipe_id}.pdf'
            cook_count = recipe_cooked_date.query.filter_by(recipe_id=recipe.recipe_id).count()
            view_count = recipe_view_date.query.filter_by(recipe_id=recipe.recipe_id).count()
            # Clone nullable display values; never mutate mapped objects.
            display_recipe = SimpleNamespace(**{c.name: getattr(recipe, c.name) for c in recipe.__table__.columns})
            display_recipe.image_file = display_recipe.image_file or 'default.jpg'
            rendered = render_template('recipe.html', recipe=display_recipe,
                note_from_user_list=(recipe.note_from_user or '').split('\n'),
                ingredients=ingredients[recipe.recipe_id], instructions=steps,
                source_notes=notes[recipe.recipe_id], title=recipe.name,
                cuisine_name=cuisines.get(recipe.cuisine_id), collections=recipe.collections,
                cook_count=cook_count, view_count=view_count, recipe_planned=None,
                recipe_pdf=pdf_path.name if pdf_path.is_file() else None)
            result.append({'id': recipe.recipe_id, 'name': recipe.name, 'legacy_html': rendered,
                'ingredient_ids': [i.recipe_ingredient_id for i in ingredients[recipe.recipe_id]],
                'instruction_ids': [s.recipe_instruction_id for s in steps],
                'source_note_ids': [s.recipe_instruction_id for s in notes[recipe.recipe_id]],
                'texts': [i.name_written for i in ingredients[recipe.recipe_id]] +
                         [i.note for i in ingredients[recipe.recipe_id] if i.note] +
                         [s.text_contents for s in steps] +
                         [s.text_contents for s in notes[recipe.recipe_id]],
                'collections': [c.collection_name for c in recipe.collections],
                'cuisine': cuisines[recipe.cuisine_id].cuisine_name if recipe.cuisine_id in cuisines else None,
                'notes': recipe.note_from_user, 'cook_count': cook_count, 'view_count': view_count,
                'facts': [getattr(recipe, key) for key in ['prep_time', 'cook_time', 'additional_time', 'servings']
                          if getattr(recipe, key)],
                'pdf': pdf_path.is_file()})
        assert recipe_view_date.query.count() == before
        db.session.rollback()
        return {'recipes': result, 'visit_count': before}


if __name__ == '__main__':
    print(json.dumps(snapshot()))
