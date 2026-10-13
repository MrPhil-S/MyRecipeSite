"""Collection carousel thumbnails from recorded cooking history."""
from sqlalchemy import case, func, select

from .models import Collection, Recipe, recipe_collection, recipe_cooked_date


def favorite_membership():
    return select(recipe_collection.c.recipe_id).join(Collection).where(
        recipe_collection.c.recipe_id == Recipe.recipe_id,
        func.lower(func.trim(Collection.collection_name)).in_(('favorites', 'favorite'))).exists()


def collection_filter(collection_id):
    if collection_id == -1:  # A computed collection; never stored as a tag.
        return ~select(recipe_cooked_date.recipe_id).where(
            recipe_cooked_date.recipe_id == Recipe.recipe_id).exists()
    return select(recipe_collection.c.recipe_id).where(
        recipe_collection.c.recipe_id == Recipe.recipe_id,
        recipe_collection.c.collection_id == collection_id).exists()


def collection_cards(session):
    cooked = select(recipe_cooked_date.recipe_id, func.count().label('times_cooked')).group_by(
        recipe_cooked_date.recipe_id).subquery()
    ranked = select(recipe_collection.c.collection_id, Recipe.recipe_id.label('thumbnail_recipe_id'),
        Recipe.name.label('recipe_name'), Recipe.image_file,
        func.row_number().over(partition_by=recipe_collection.c.collection_id,
            order_by=(func.coalesce(cooked.c.times_cooked, 0).desc(),
                      Recipe.create_dt.desc(), Recipe.recipe_id.desc())).label('rank')
    ).join(Recipe, Recipe.recipe_id == recipe_collection.c.recipe_id).outerjoin(
        cooked, cooked.c.recipe_id == Recipe.recipe_id).subquery()
    cards = list(session.execute(select(Collection.collection_id, Collection.collection_name,
        ranked.c.thumbnail_recipe_id, ranked.c.recipe_name, ranked.c.image_file).outerjoin(
        ranked, (ranked.c.collection_id == Collection.collection_id) & (ranked.c.rank == 1)
    ).order_by(case((func.lower(func.trim(Collection.collection_name)).in_(('favorites', 'favorite')), 0),
                       else_=1), Collection.collection_name, Collection.collection_id)).mappings())
    thumbnail = session.execute(select(Recipe.recipe_id.label('thumbnail_recipe_id'),
        Recipe.name.label('recipe_name'), Recipe.image_file).where(collection_filter(-1))
        .order_by(Recipe.create_dt.desc(), Recipe.recipe_id.desc()).limit(1)).mappings().first()
    # Keep Favorites directly after All recipes, then the computed collection.
    position = sum(c['collection_name'].strip().lower() in ('favorites', 'favorite') for c in cards)
    from types import SimpleNamespace
    cards.insert(position, dict(collection_id=-1, collection_name='Never cooked',
        **(dict(thumbnail) if thumbnail else dict(thumbnail_recipe_id=None, recipe_name=None, image_file=None))))
    return [SimpleNamespace(**c) for c in cards]


def all_recipes_thumbnail(session):
    cooked = select(recipe_cooked_date.recipe_id, func.count().label('times_cooked')).group_by(
        recipe_cooked_date.recipe_id).subquery()
    return session.execute(select(Recipe.recipe_id.label('thumbnail_recipe_id'),
        Recipe.name.label('recipe_name'), Recipe.image_file).outerjoin(
        cooked, cooked.c.recipe_id == Recipe.recipe_id).order_by(
        func.coalesce(cooked.c.times_cooked, 0).desc(), Recipe.create_dt.desc(), Recipe.recipe_id.desc()
    ).limit(1)).first()
