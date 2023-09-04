from sqlalchemy.sql import func

from myrecipes import db

recipe_collection = db.Table('recipe_collection',
                    db.Column('recipe_id', db.Integer, db.ForeignKey('recipe.recipe_id')),
                    db.Column('collection_id', db.Integer, db.ForeignKey('collection.collection_id'))
                    )

class Recipe(db.Model):
    recipe_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    source_url = db.Column(db.String(255), nullable=True)
    source_url_short = db.Column(db.String(50), nullable=True)
    whisk_url = db.Column(db.String(255), nullable=True, unique=True)
    ingredient_count = db.Column(db.Integer, nullable=True)
    image_file = db.Column(db.String(20), nullable=True, default='default.jpg')
    total_time = db.Column(db.String(20), nullable=True) 
    prep_time = db.Column(db.String(20), nullable=True)
    cook_time = db.Column(db.String(20), nullable=True)
    additional_time = db.Column(db.String(20), nullable=True)
    cuisine_id = db.Column(db.Integer, nullable=True)
    servings = db.Column(db.Integer, nullable=True)
    note_from_user = db.Column(db.String(1000), nullable=True)
    cooked_count = db.Column(db.Integer, nullable=True, default=0)
    create_dt = db.Column(db.DateTime, nullable=True, default=db.func.current_timestamp())
    update_dt = db.Column(db.DateTime, nullable=True, onupdate=func.now())
    collections = db.relationship('Collection', secondary='recipe_collection', back_populates='recipes')

    def __repr__(self):
        return f"Recipe('{self.name}','{self.source_url}','{self.instructions}','{self.image_file}')"

class Recipe_Ingredient(db.Model):
    recipe_ingredient_id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.recipe_id', ondelete='CASCADE'), nullable=False)
    name_written = db.Column(db.String(100), nullable=False)
    note = db.Column(db.String(100), nullable=True)
    name_official = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f"Recipe_Ingredient('{self.name_written}','{self.name_official}')"
    
class Recipe_Instruction(db.Model):
    recipe_instruction_id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.recipe_id', ondelete='CASCADE'), nullable=False)
    text_contents = db.Column(db.String(1000), nullable=False)
    type = db.Column(db.Integer, nullable=True)
    sequence = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f"Recipe_Instructions('{self.text_contents}','{self.type}','{self.sequence}')"
    
class Page_View(db.Model):
    page_view_id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, nullable=False)
    page_view_dt = db.Column(db.DateTime, nullable=True, default=db.func.current_timestamp())

    def __repr__(self):
        count = db.session.query(func.count(Page_View.page_view_id)).filter_by(recipe_id=self.recipe_id).scalar()
        return count

    
class Recipe_Cooked_Date(db.Model):
    recipe_cook_count_id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, nullable=False)
    cooked_dt = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())


class Recipe_Plan_Date(db.Model):
    recipe_plan_date_id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, nullable=False)
    added_dt = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    removed_dt = db.Column(db.DateTime, nullable=True)


class Collection(db.Model):
    collection_id = db.Column(db.Integer, primary_key=True)
    collection_name = db.Column(db.String(30), nullable=False)
    create_dt = db.Column(db.DateTime, nullable=True, default=db.func.current_timestamp())
    recipes = db.relationship('Recipe', secondary='recipe_collection', back_populates='collections')

    def __repr__(self):
        return f'{self.collection_name}'
    


class Cuisine(db.Model):
    cuisine_id = db.Column(db.Integer, primary_key=True)
    cuisine_name = db.Column(db.String(30), nullable=False)
    create_dt = db.Column(db.DateTime, nullable=True, default=db.func.current_timestamp())


    def __repr__(self):
        return f"('{self.cuisine_name}')"