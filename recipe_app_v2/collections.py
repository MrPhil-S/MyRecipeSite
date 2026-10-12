"""Collection carousel thumbnails from recorded cooking history."""
from sqlalchemy import case, func, select

from .models import Collection, Recipe, recipe_collection, recipe_cooked_date


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
    return session.execute(select(Collection.collection_id, Collection.collection_name,
        ranked.c.thumbnail_recipe_id, ranked.c.recipe_name, ranked.c.image_file).outerjoin(
        ranked, (ranked.c.collection_id == Collection.collection_id) & (ranked.c.rank == 1)
    ).order_by(case((func.lower(func.trim(Collection.collection_name)).in_(('favorites', 'favorite')), 0),
                       else_=1), Collection.collection_name, Collection.collection_id)).all()


def all_recipes_thumbnail(session):
    cooked = select(recipe_cooked_date.recipe_id, func.count().label('times_cooked')).group_by(
        recipe_cooked_date.recipe_id).subquery()
    return session.execute(select(Recipe.recipe_id.label('thumbnail_recipe_id'),
        Recipe.name.label('recipe_name'), Recipe.image_file).outerjoin(
        cooked, cooked.c.recipe_id == Recipe.recipe_id).order_by(
        func.coalesce(cooked.c.times_cooked, 0).desc(), Recipe.create_dt.desc(), Recipe.recipe_id.desc()
    ).limit(1)).first()
