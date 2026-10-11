"""Dev-only recipe saves with validation and a single database commit."""
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_write_engine, writes_enabled
from .editor import choices, recipe_rows, total_time, validate, version_for
from .models import Collection, Recipe, Recipe_Ingredient, Recipe_Instruction
from .uploads import StagedUploads


class SaveError(Exception):
    def __init__(self, messages, status=422):
        self.messages = messages
        self.status = status


def short_url(value):
    if not value:
        return None
    parts = urlsplit(value).hostname.split('.')
    return (parts[-2] if len(parts) > 2 else parts[0]).title()[:50]


def save_recipe(recipe_id, values, image=None, pdf=None):
    if not writes_enabled():
        raise SaveError(['Saving to the dev database is disabled.'], 403)
    staged = StagedUploads()
    with Session(get_write_engine(), autoflush=False) as session:
        try:
            recipe = None
            old_ingredients, old_steps = [], []
            if recipe_id is not None:
                recipe = session.scalar(select(Recipe).where(Recipe.recipe_id == recipe_id).with_for_update())
                if recipe is None:
                    raise SaveError(['Recipe not found.'], 404)
                old_ingredients, old_steps = recipe_rows(session, recipe_id)
                if values['version'] != version_for(recipe, old_ingredients, old_steps):
                    raise SaveError(['This recipe changed after you opened the form. Reload it before saving; your submitted values are shown below.'], 409)
            clean, errors = validate(values, choices(session))
            if clean['whisk_url']:
                duplicate = session.scalar(select(Recipe.recipe_id).where(
                    Recipe.whisk_url == clean['whisk_url'], Recipe.recipe_id != (recipe_id or 0)))
                if duplicate:
                    errors.append('That Whisk URL is already assigned to another recipe.')
            existing = {str(i.recipe_ingredient_id): i for i in old_ingredients}
            identifiers = [i['id'] for i in clean['ingredients'] if i['id']]
            if (len(identifiers) != len(set(identifiers))
                    or any(i not in existing for i in identifiers)):
                errors.append('Ingredient row identifiers do not belong to this recipe. Reload the form.')
            if errors:
                raise SaveError(errors)
            if recipe is None:
                recipe = Recipe(image_file='default.jpg')
                session.add(recipe)
            for key in ('name', 'source_url', 'whisk_url', 'prep_time', 'cook_time',
                        'additional_time', 'note_from_user'):
                setattr(recipe, key, clean[key] or None)
            recipe.source_url_short = short_url(recipe.source_url)
            recipe.servings = clean['servings']
            recipe.cuisine_id = int(clean['cuisine_id']) if clean['cuisine_id'] else None
            recipe.total_time = total_time(clean)
            recipe.ingredient_count = sum(i['group'] == '0' for i in clean['ingredients'])
            recipe.collections = session.scalars(select(Collection).where(
                Collection.collection_id.in_([int(c) for c in clean['collection_ids']]))).all()
            # Obtain an ID for new children/uploads; this is still uncommitted.
            session.flush()
            official_names = set(session.scalars(select(Recipe_Ingredient.name_official).where(
                Recipe_Ingredient.name_official.is_not(None))).all()) | {'soy_sauce'}
            official_names = sorted((n for n in official_names if n), key=lambda n: (-len(n), n))
            used = set()
            for sequence, row in enumerate(clean['ingredients'], 1):
                ingredient = existing.get(row['id'])
                # Bulk paste keeps hidden metadata for unchanged ordered rows.
                if ingredient is None and clean['ingredient_mode'] == 'bulk' and sequence <= len(old_ingredients):
                    candidate = old_ingredients[sequence - 1]
                    if candidate.name_written == row['name'] and bool(candidate.is_group_header) == (row['group'] == '1'):
                        ingredient = candidate
                if ingredient is None:
                    ingredient = Recipe_Ingredient(recipe_id=recipe.recipe_id)
                    session.add(ingredient)
                else:
                    used.add(ingredient.recipe_ingredient_id)
                if row['group'] == '1':
                    ingredient.name_official = None
                elif ingredient.name_written != row['name'] or not ingredient.name_official:
                    ingredient.name_official = next((n for n in official_names
                        if n.replace('_', ' ').casefold() in row['name'].casefold()), 'default_ingredient')
                ingredient.name_written = row['name']
                ingredient.note = row['note'] or None
                ingredient.sequence = sequence
                ingredient.is_group_header = row['group'] == '1'
            for ingredient in old_ingredients:
                if ingredient.recipe_ingredient_id not in used:
                    session.delete(ingredient)
            # Preserve IDs and any instruction types outside the two form fields.
            for kind in (1, 2):
                old = [i for i in old_steps if i.type == kind]
                new = [i for i in clean['steps'] if i['type'] == kind]
                for index, row in enumerate(new):
                    step = old[index] if index < len(old) else Recipe_Instruction(recipe_id=recipe.recipe_id)
                    step.text_contents, step.type = row['text'], kind
                    step.sequence, step.is_group_header = row['sequence'], row['group']
                    session.add(step)
                for step in old[len(new):]:
                    session.delete(step)
            staged.apply(recipe, image, pdf)
            saved_id = recipe.recipe_id
            session.commit()
            # Avoid an expired-object SELECT after commit: a later connection
            # failure must not be mistaken for a failed save and remove uploads.
            return saved_id
        except IntegrityError:
            session.rollback()
            staged.rollback()
            raise SaveError(['The recipe could not be saved because a value conflicts with existing data. Check the Whisk URL and selected tags.']) from None
        except Exception:
            session.rollback()
            staged.rollback()
            raise
