
import os
import re

from PIL import Image
from sqlalchemy import text
from werkzeug.utils import secure_filename

from myrecipes import app, db
from myrecipes.models import Recipe, Recipe_Ingredient


# Function to parse the search query and identify excluded words after "NOT"
def parse_search_query(query):
    # Use regular expressions to identify quoted strings
    quoted_strings = re.findall(r'"(.*?)"', query)
    
    for quoted_string in quoted_strings:
        query = query.replace(f'"{quoted_string}"', '')

    # Tokenize the query, splitting on spaces
    query = query.strip()
    tokens = re.split(r'\s+', query)
    
    # Combine quoted strings into the tokens list
    tokens.extend(quoted_strings)
    
    # Find the "NOT" keyword and words following it
    excluded_tokens = []
    if 'NOT' in tokens:
        not_index = tokens.index('NOT')
        excluded_tokens = tokens[not_index + 1:]
        tokens = tokens[:not_index]
    
    return tokens, excluded_tokens

def search_recipe(token):
    # Build a dynamic SQLAlchemy query for the Recipe table
    search_query = db.session.query(Recipe.recipe_id)

    # Create an OR condition for the case-insensitive exact word match with MariaDB word boundaries
    #token_upper = token.upper()
    or_condition = (Recipe.name).like(f"%{token}%")

    # Apply the condition to the query
    search_query = search_query.filter(or_condition)

    # Execute the query and retrieve the distinct recipe IDs
    return [result[0] for result in search_query.distinct().all()]

def search_recipe_ingredient(token):
    # Build a dynamic SQLAlchemy query for the Recipe_Ingredient table
    search_query = db.session.query(Recipe_Ingredient.recipe_id)

    # Create an OR condition for the case-insensitive exact word match with MariaDB word boundaries
    #token_upper = token.upper()
    or_condition = db.func.concat(Recipe_Ingredient.name_written, ' ', Recipe_Ingredient.note).like(f"%{token}%")

    # Apply the condition to the query
    search_query = search_query.filter(or_condition)

    # Execute the query and retrieve the distinct recipe IDs
    return [result[0] for result in search_query.distinct().all()]


def save_image(form_image, recipe_id):
    #Rename file
    #random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_image.filename)
    image_fn = str(recipe_id) + f_ext
    image_path = os.path.join(app.root_path, 'static/recipe_images', image_fn)
    
    output_size = (1000, 1000)
    i = Image.open(form_image)
    i.thumbnail(output_size)
    
    if i.mode in ("RGBA", "P"):
        i = i.convert("RGB")

    i.save(image_path) 
    return image_fn

def save_file(form_file, recipe_id):
    filename = secure_filename(form_file.filename)
    
    #Build the filename to be recipe_id.extension
    _, f_ext = os.path.splitext(filename)
    recipe_filename = str(recipe_id) + f_ext

    form_file.save(os.path.join(
        app.root_path, 'static/custom_prints/', recipe_filename
    ))

    return filename 

def get_sort_reverse(session_sort_order):
    if session_sort_order.endswith('_dt'):
        return True
    else:
        return False
    
def process_ingredients(recipe_id, is_bulk_ingredients, ingredient_groups, ingredients, ingredient_notes):
    for index, ingredient in enumerate(ingredients):
        if len(ingredient.strip()) > 0: 
            ingredient = ingredient.strip()

            if is_bulk_ingredients:
                if ingredient[0] == '>':
                    is_group_header = 1
                    ingredient = ingredient.strip()[1:]
                    name_official = None
                    
            if not is_bulk_ingredients:
                if ingredient_groups[index]:
                    is_group_header = 1
                    name_official = None
            else:
                is_group_header = 0

                stmt = text(''' #TODO: fix hardcoded ingredient lookup values
                            SELECT name_official 
                            FROM 
                                (SELECT  
                                name_official
                                FROM `recipe__ingredient`
                                UNION
                                SELECT 'soy_sauce'
                                ) x
                            WHERE LOCATE(REPLACE(name_official, '_', ' '), :ingredient_param) > 0
                            ORDER BY length(name_official) DESC
                            LIMIT 1''')
                result  = db.engine.execute(stmt, ingredient_param=ingredient)
                row = result.fetchone()
                name_official = row[0] if row is not None else 'default_ingredient'

            if ingredient_notes[index]:
                ingredient_note = ingredient_notes[index].strip()
            else:
                ingredient_note = None
            sequence = index + 1
            ingredient_record = Recipe_Ingredient(name_written=ingredient, note=ingredient_note, recipe_id=recipe_id, name_official=name_official, sequence=sequence, is_group_header=is_group_header)
            db.session.add(ingredient_record)
        db.session.commit()
