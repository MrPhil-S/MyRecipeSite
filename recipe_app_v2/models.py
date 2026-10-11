"""Existing Flask schema mirrored without importing Flask."""
import sqlalchemy as sa
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

recipe_collection = sa.Table('recipe_collection', Base.metadata, sa.Column('recipe_id', sa.Integer, sa.ForeignKey('recipe.recipe_id')), sa.Column('collection_id', sa.Integer, sa.ForeignKey('collection.collection_id')))

class Recipe(Base):
    __tablename__ = 'recipe'
    recipe_id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(200), nullable=False)
    source_url = sa.Column(sa.String(255), nullable=True)
    source_url_short = sa.Column(sa.String(50), nullable=True)
    whisk_url = sa.Column(sa.String(255), nullable=True, unique=True)
    ingredient_count = sa.Column(sa.Integer, nullable=True)
    image_file = sa.Column(sa.String(20), nullable=True, default='default.jpg')
    total_time = sa.Column(sa.String(20), nullable=True)
    prep_time = sa.Column(sa.String(20), nullable=True)
    cook_time = sa.Column(sa.String(20), nullable=True)
    additional_time = sa.Column(sa.String(20), nullable=True)
    cuisine_id = sa.Column(sa.Integer, nullable=True)
    servings = sa.Column(sa.Integer, nullable=True)
    note_from_user = sa.Column(sa.String(1000), nullable=True)
    cooked_count = sa.Column(sa.Integer, nullable=True, default=0)
    create_dt = sa.Column(sa.DateTime, nullable=True, default=sa.func.current_timestamp())
    update_dt = sa.Column(sa.DateTime, nullable=True, onupdate=func.now())
    collections = relationship('Collection', secondary='recipe_collection', back_populates='recipes')

class Recipe_Ingredient(Base):
    __tablename__ = 'recipe__ingredient'
    recipe_ingredient_id = sa.Column(sa.Integer, primary_key=True)
    ingredient_id = sa.Column(sa.Integer, nullable=True)
    recipe_id = sa.Column(sa.Integer, sa.ForeignKey('recipe.recipe_id', ondelete='CASCADE'), nullable=False)
    name_written = sa.Column(sa.String(100), nullable=False)
    note = sa.Column(sa.String(100), nullable=True)
    name_official = sa.Column(sa.String(100), nullable=True)
    sequence = sa.Column(sa.Integer, nullable=True)
    is_group_header = sa.Column(sa.Boolean, nullable=True)

class Recipe_Instruction(Base):
    __tablename__ = 'recipe__instruction'
    recipe_instruction_id = sa.Column(sa.Integer, primary_key=True)
    recipe_id = sa.Column(sa.Integer, sa.ForeignKey('recipe.recipe_id', ondelete='CASCADE'), nullable=False)
    text_contents = sa.Column(sa.String(1000), nullable=False)
    type = sa.Column(sa.Integer, nullable=True)
    sequence = sa.Column(sa.Integer, nullable=True)
    is_group_header = sa.Column(sa.Boolean, nullable=True)

class recipe_view_date(Base):
    __tablename__ = 'recipe_view_date'
    recipe_view_date_id = sa.Column(sa.Integer, primary_key=True)
    recipe_id = sa.Column(sa.Integer, sa.ForeignKey('recipe.recipe_id', ondelete='CASCADE'), nullable=False)
    recipe_view_dt = sa.Column(sa.DateTime, nullable=True, default=sa.func.current_timestamp())

class recipe_cooked_date(Base):
    __tablename__ = 'recipe_cooked_date'
    recipe_cooked_date_id = sa.Column(sa.Integer, primary_key=True)
    recipe_id = sa.Column(sa.Integer, sa.ForeignKey('recipe.recipe_id', ondelete='CASCADE'), nullable=False)
    recipe_cooked_dt = sa.Column(sa.DateTime, nullable=False, default=sa.func.current_timestamp())

class Recipe_Plan_Date(Base):
    __tablename__ = 'recipe__plan__date'
    recipe_plan_date_id = sa.Column(sa.Integer, primary_key=True)
    recipe_id = sa.Column(sa.Integer, sa.ForeignKey('recipe.recipe_id', ondelete='CASCADE'), nullable=False)
    added_dt = sa.Column(sa.DateTime, nullable=False, default=sa.func.current_timestamp())
    removed_dt = sa.Column(sa.DateTime, nullable=True)

class Collection(Base):
    __tablename__ = 'collection'
    collection_id = sa.Column(sa.Integer, primary_key=True)
    collection_name = sa.Column(sa.String(30), nullable=False)
    create_dt = sa.Column(sa.DateTime, nullable=True, default=sa.func.current_timestamp())
    recipes = relationship('Recipe', secondary='recipe_collection', back_populates='collections')

class Cuisine(Base):
    __tablename__ = 'cuisine'
    cuisine_id = sa.Column(sa.Integer, primary_key=True)
    cuisine_name = sa.Column(sa.String(30), nullable=False)
    create_dt = sa.Column(sa.DateTime, nullable=True, default=sa.func.current_timestamp())

class Ingredient_Synonym(Base):
    __tablename__ = 'ingredient__synonym'
    ingredient_synonym_id = sa.Column(sa.Integer, primary_key=True)
    primary_term = sa.Column(sa.String(100), nullable=False)
    secondary_term = sa.Column(sa.String(100), nullable=False)

class Query_History(Base):
    __tablename__ = 'query__history'
    query_history_id = sa.Column(sa.Integer, primary_key=True)
    query_text = sa.Column(sa.String(100), nullable=False)
    query_dt = sa.Column(sa.DateTime, nullable=True, default=sa.func.current_timestamp())
