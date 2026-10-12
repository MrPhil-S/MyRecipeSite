"""Discover affected recipes and apply only explicitly reviewed image-name changes."""
import base64
import hashlib
import hmac
import json
import time
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_write_engine, writes_enabled
from .image_aliases import Matcher, catalogue_lock, image_url
from .models import Recipe, Recipe_Ingredient


def row_version(row):
    return hashlib.sha256(json.dumps({c.name: getattr(row, c.name) for c in row.__table__.columns},
                                   sort_keys=True, default=str).encode()).hexdigest()


def sign_preview(row, catalogue_version, target):
    from .editor_routes import SECRET
    payload = {'recipe': row.recipe_id, 'row': row.recipe_ingredient_id, 'row_version': row_version(row),
               'catalogue': catalogue_version, 'target': target, 'time': int(time.time())}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
    signature = hmac.new(SECRET, ('ingredient-image:' + encoded).encode(), hashlib.sha256).hexdigest()
    return encoded + '.' + signature


def read_preview(token):
    from .editor_routes import SECRET
    try:
        if len(token) > 2048:
            raise ValueError()
        encoded, signature = token.rsplit('.', 1)
        expected = hmac.new(SECRET, ('ingredient-image:' + encoded).encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(encoded))
        if not 0 <= time.time() - payload['time'] <= 7200:
            raise ValueError()
        return payload
    except (ValueError, KeyError, TypeError):
        raise ValueError('Re-match this ingredient again before saving.') from None


class RematchError(ValueError):
    def __init__(self, message, status=422):
        self.status = status
        super().__init__(message)


def affected_ingredients(session, name=''):
    matcher = Matcher()
    rows = session.execute(select(Recipe_Ingredient, Recipe.name).join(
        Recipe, Recipe.recipe_id == Recipe_Ingredient.recipe_id).order_by(
        Recipe.recipe_id, Recipe_Ingredient.recipe_ingredient_id)).all()
    changes = []
    for row, recipe_name in rows:
        if row.is_group_header:
            continue
        target = matcher.match(row.name_written)
        if target == 'default_ingredient' or target == row.name_official:
            continue
        if name and target != name and row.name_official != name:
            continue
        changes.append({'recipe_id': row.recipe_id, 'row_id': row.recipe_ingredient_id,
            'recipe_name': recipe_name, 'ingredient': row.name_written,
            'current': row.name_official or 'default_ingredient', 'proposed': target,
            'current_image': image_url(row.name_official), 'proposed_image': image_url(target),
            'token': sign_preview(row, matcher.version, target)})
    return changes


def apply_selected(tokens):
    if not writes_enabled():
        raise RematchError('Dev saves are disabled.', 403)
    if not 1 <= len(tokens) <= 50:
        raise RematchError('Select 1–50 ingredient image changes to apply.')
    try:
        previews = [read_preview(token) for token in tokens]
        ids = [int(p['row']) for p in previews]
        recipe_ids = sorted({int(p['recipe']) for p in previews})
        if len(ids) != len(set(ids)):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise RematchError('Invalid or expired selection. Review the affected recipes again.') from None
    with catalogue_lock(), Session(get_write_engine()) as session:
        matcher = Matcher()
        # Match the normal editor/delete lock order: parents, then ingredients.
        parents = session.scalars(select(Recipe).where(Recipe.recipe_id.in_(recipe_ids))
                                 .order_by(Recipe.recipe_id).with_for_update()).all()
        if len(parents) != len(recipe_ids):
            raise RematchError('A recipe was removed. Review the affected recipes again.', 409)
        ingredients = {row.recipe_ingredient_id: row for row in session.scalars(select(Recipe_Ingredient)
            .where(Recipe_Ingredient.recipe_ingredient_id.in_(ids))
            .order_by(Recipe_Ingredient.recipe_ingredient_id).with_for_update())}
        for preview in previews:
            row = ingredients.get(int(preview['row']))
            if (row is None or row.recipe_id != preview['recipe'] or row.is_group_header
                    or row_version(row) != preview.get('row_version')
                    or matcher.version != preview.get('catalogue')):
                raise RematchError('An ingredient or the alias catalogue changed. Nothing was applied; review again.', 409)
            target = matcher.match(row.name_written)
            if target == 'default_ingredient' or target != preview.get('target'):
                raise RematchError('The proposed match changed. Nothing was applied; review again.', 409)
            row.name_official = target
        session.commit()
    return len(previews)
