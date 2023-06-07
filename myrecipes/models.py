from myrecipes import db
from sqlalchemy.sql import func

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
    cuisine = db.Column(db.String(50), nullable=True)
    rating = db.Column(db.Integer, nullable=True)
    servings = db.Column(db.Integer, nullable=True)
    note_from_user = db.Column(db.String(1000), nullable=True)
    cooked_count = db.Column(db.Integer, nullable=True)
#    notes = db.Column(db.String(200), nullable=True)
    create_dt = db.Column(db.DateTime, nullable=True, default=db.func.current_timestamp())
    update_dt = db.Column(db.DateTime, nullable=True, onupdate=func.now())

    def __repr__(self):
        return f"Recipe('{self.name}','{self.source_url}','{self.instructions}','{self.image_file}')"

class Recipe_Ingredient(db.Model):
    recipe_ingredient_id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, nullable=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.recipe_id', ondelete='CASCADE'), nullable=False)
    name_written = db.Column(db.String(100), nullable=False)
    note = db.Column(db.String(100), nullable=True)
    name_official = db.Column(db.String(100), nullable=True)
    #icon_file = db.Column(db.String(100), nullable=True)

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
    page_name = db.Column(db.String(30), nullable=False)
    page_view_dt = db.Column(db.DateTime, nullable=True, default=db.func.current_timestamp())


    def __repr__(self):
        return f"Page_View('{self.page_name}')"