import os

from flask import flash, jsonify, redirect, render_template, request, url_for
from PIL import Image
from sqlalchemy import text

#import secrets
from myrecipes import app, db, get_recipies
from myrecipes.forms import add_recipe_form, edit_recipe_form
from myrecipes.models import (Collection, Cuisine, Page_View, Recipe,
                              Recipe_Cooked_Date, Recipe_Ingredient,
                              Recipe_Instruction, Recipe_Plan_Date,
                              recipe_collection)


@app.route('/setup')
def setup():
    db.create_all()
    return 'Tables created'


@app.route('/frontlights')
def frontlights():
    return render_template('frontlights.html', title='Front Lights')


@app.route('/', methods=['GET', 'POST'])
@app.route('/home', methods=['GET', 'POST'])
def home():
    recipes = Recipe.query.order_by(Recipe.recipe_id.desc()).all()
    if request.method == 'POST':
        search_for = request.form['search_for']
        recipes = Recipe.query.join(Recipe_Ingredient).\
            filter((Recipe_Ingredient.name_written == search_for )|( Recipe.name.contains(search_for))).all()
        return render_template('home.html', recipes=recipes)
    return render_template('home.html', recipes=recipes, title='Recipes')


@app.route('/import_recipes')
def import_recipes():
    #return get_recipies.main()  
    return render_template('import_recipes.html')

@app.route('/import_recipes/process/<int:option>', methods=['GET', 'POST'])
def process_recipes(option):
    #options: 1-Onlyaddnew, 2-Upsertall, 3-AROnly, 4-BAOnly
    if option == 2:
        get_recipies.main(option)
        flash(f'Upserted all recipes.', 'success')
    elif option == 1:
        get_recipies.main(option)
        flash(f'Added new recipes', 'success')
    elif option in (3, 4):
        recipes = Recipe.query.order_by(Recipe.recipe_id.asc()).all()
        if option == 3:
            for recipe in recipes:
                get_recipies.update_AR_recipe(recipe.recipe_id, recipe.source_url)  
            flash('AR recipes updated', 'success')
        elif option == 4:
            for recipe in recipes:
                get_recipies.update_AR_recipe(recipe.recipe_id, recipe.source_url)  
            flash('BA recipes updated', 'success')     
    return redirect(url_for('import_recipes'))

@app.route('/recipes/<int:recipe_id>', methods=['GET', 'POST'])
def recipe(recipe_id):

    recipe = Recipe.query.get_or_404(recipe_id)

    page_view = Page_View(page_name=recipe.name)
    db.session.add(page_view)
    db.session.commit()
    view_count = Page_View.query.filter_by(page_name=recipe.name).count()
    cook_count = Recipe_Cooked_Date.query.filter_by(recipe_id=recipe.recipe_id).count()
    image_file = url_for('static', filename='recipe_images/' + recipe.image_file)
    ingredients = Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).all()
    instructions = Recipe_Instruction.query.filter_by(recipe_id=recipe_id, type=1).all()
    source_notes = Recipe_Instruction.query.filter_by(recipe_id=recipe_id, type=2).all()
    cuisine = Cuisine.query.filter_by(cuisine_id=recipe.cuisine_id).first()
    collections = recipe.collections
    if recipe.note_from_user is not None:
        note_from_user_list = recipe.note_from_user.split('\n')
    else:
        note_from_user_list = None

    # Query to check if a record exists with the given recipe_id and removed_dt is NULL
    is_planned = Recipe_Plan_Date.query .filter_by(recipe_id=recipe_id, removed_dt=None).first() is not None
    #planned = planned is not None

    if request.method == 'POST':
        button_action = request.form.get('button_action')
        if button_action == 'add_to_plan':
            add_date = Recipe_Plan_Date(recipe_id=recipe.recipe_id)
            db.session.add(add_date)
            is_planned = True
            flash(f'Added to plan', 'success')

        elif button_action == 'remove_from_plan':
            #  user = User.query.filter_by(username=username).first_or_404()

            recipe_planned = Recipe_Plan_Date.query.filter_by(recipe_id=recipe.recipe_id, removed_dt=None).first_or_404()
            recipe_planned.removed_dt = db.func.current_timestamp()
            is_planned = False
            flash(f'Removed from plan', 'success')

        elif button_action == 'mark_cooked':
            add_date = Recipe_Cooked_Date(recipe_id=recipe.recipe_id)
            db.session.add(add_date)
            flash(f'Marked as cooked', 'success')

        else:
            return "Invalid action"
        db.session.commit()
        return redirect(url_for('recipe', recipe_id=recipe_id, is_planned=is_planned))

    return render_template('recipe.html', recipe=recipe, note_from_user_list=note_from_user_list, ingredients=ingredients, instructions=instructions, source_notes=source_notes, title=recipe.name, image_file=image_file, view_count=view_count, cuisine=cuisine, collections=collections, cook_count=cook_count, is_planned=is_planned)



@app.route('/recipes/add_recipe', methods=['GET', 'POST'])
def add_recipe():
    form =  add_recipe_form()
    image_file = None
  
    # Populate the dropdown fields with data from the database
    blank_default_dropdown = (0, '')
    form.cuisinelist.choices    = [(cuisine.cuisine_id, cuisine.cuisine_name) for cuisine in Cuisine.query.order_by(Cuisine.cuisine_name).all()]
    form.cuisinelist.choices.insert(0, (0, ''))

    #form.collectionlist.choices.insert(0, (0, ''))
    #collections = Collection.query.order_by(Collection.collection_name).all()

    #populate form with all collection choices
    form.collection_list.choices = [(collection.collection_id, collection.collection_name) for collection in Collection.query.order_by(Collection.collection_name).all()]
    #collection_list = [(collection.collection_id, collection.collection_name) for collection in Collection.query.order_by(Collection.collection_name).all()]

    if form.validate_on_submit():
        # Get populted form data
        name = request.form['name']
        source_url = request.form['url']
        ingredients = request.form.getlist('ingredient[]')
        ingredient_notes = request.form.getlist('ingredient_note[]')    
        ingredient_bulk = request.form['ingredient_bulk']
        instructions = request.form['instructions']
        note_from_user = request.form['note_from_user']
        source_notes = request.form['source_notes']
        prep_time = request.form['prep_time']
        cook_time = request.form['cook_time']
        additional_time = request.form['additional_time']

        selected_cuisine_id = form.cuisinelist.data
        #selected_options = form.multiselect_field.data
        #selected_collections = form.collection_list.data
        selected_collections = request.form.getlist('collection_list')


        cuisine_id = selected_cuisine_id if selected_cuisine_id != 0 else None


        # Add new recipe to DB
        recipe = Recipe(name=name, source_url=source_url, note_from_user=note_from_user, image_file=image_file, prep_time=prep_time, cook_time=cook_time, additional_time=additional_time, cuisine_id=cuisine_id)
        db.session.add(recipe)
        db.session.flush()
        db.session.refresh(recipe)
        recipe_id = recipe.recipe_id
        db.session.commit()
        
        if form.image.data:
            image_file = save_image(request.files['image'],recipe_id)
        else:
            image_file = 'default.jpg'
        #Get the newly inserted recipe to be used to UPDATE with the image_file
        recipe = Recipe.query.get_or_404(recipe_id)
        recipe.image_file = image_file

        #add the collections to collection table
        for collection_id in selected_collections:

            insert_recipe_collection = recipe_collection.insert().values(
                collection_id=int(collection_id),
                recipe_id=recipe_id )

        
            db.session.execute(insert_recipe_collection)
        db.session.commit()

        # Add related ingredients to DB
        for index, ingredient in enumerate(ingredients):
            if len(ingredient) > 0: 

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

                ingredient_note = ingredient_notes[index]

                ingredient = Recipe_Ingredient(name_written=ingredient.strip(), note=ingredient_note.strip(), recipe_id=recipe.recipe_id, name_official=name_official)
                db.session.add(ingredient)
        db.session.commit()


        ingredient_bulk_list = ingredient_bulk.splitlines() #TODO: Add split on , for ingredient notes   
        sequence = 0
        for ingredient_bulk_item in ingredient_bulk_list:
            if len(ingredient_bulk_item) > 0:
                ingredient_parsed = ingredient_bulk_item.split(',', maxsplit=1)      
                ingredient = ingredient_parsed[0]
                try: 
                    ingredient_note = ingredient_parsed[1]
                except:
                    ingredient_note = None
                stmt = text(''' 
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

                ingredient =  Recipe_Ingredient(name_written=ingredient_bulk_item.strip(), recipe_id=recipe.recipe_id, name_official=name_official, note=ingredient_note)
                db.session.add(ingredient)
        db.session.commit()


        instructions_list = instructions.splitlines()   
        sequence = 0
        for instruction in instructions_list:
            if len(instruction) > 0:  
                sequence += 1
                instruction = Recipe_Instruction(text_contents=instruction.strip(), sequence=sequence, type=1, recipe_id=recipe.recipe_id)
                db.session.add(instruction)
        db.session.commit()

        source_notes_list = source_notes.splitlines()   
        sequence = 0
        for source_note in source_notes_list:
            if len(source_note) > 0:  
                sequence += 1
                source_note = Recipe_Instruction(text_contents=source_note.strip(), sequence=sequence, type=2, recipe_id=recipe.recipe_id)
                db.session.add(source_note)
        db.session.commit()

        #return redirect(url_for('recipes'))
        flash(f'{recipe.name} added!', 'success')
        #return render_template('recipe.html', recipe=recipe, ingredients=ingredients)
        return redirect(url_for('recipe', recipe_id=recipe_id))  #return redirect Per Corey
    return render_template('add_recipe.html', title='Add Recipe', form=form)

@app.route('/add_recipe_api', methods=['POST'])
def add_recipe_api():
    data =  request.get_json()
    
    name = data.get("name")

    recipe = Recipe(name=name)

    db.session.add(recipe)
    #db.session.flush()
   # db.session.refresh(recipe)
    db.session.commit()
    return jsonify(data), 201


@app.route('/recipes/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    #retrieve the existing recipe from DB
    recipe = Recipe.query.get_or_404(recipe_id)
    ingredients = Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).all()
    instructions = Recipe_Instruction.query.order_by(Recipe_Instruction.sequence).filter_by(recipe_id=recipe_id, type=1).all()
    source_notes = Recipe_Instruction.query.order_by(Recipe_Instruction.sequence).filter_by(recipe_id=recipe_id, type=2).all()

    image_file = url_for('static', filename=f'recipe_images/{Recipe.image_file}')
    form = edit_recipe_form()
     
    #populate the retrieved (above) recipe into form
    form.name.data = recipe.name
    form.url.data = recipe.source_url
    form.user_note.data = recipe.note_from_user
    form.ingredient.data =  ingredients
    form.instructions.data = instructions
    form.source_notes.data = source_notes

    if form.validate_on_submit():
        if form.image.data is not None:
            if os.path.exists(image_file):
                os.remove(image_file) 
            image_file = save_image(request.files['image'],recipe_id)
            recipe.image_file = image_file

        recipe.name = request.form['name']
        recipe.source_url = request.form['url']
        recipe.note_from_user = request.form['user_note']
        db.session.commit() 

        recipe_id= recipe.recipe_id
        # Delete existing ingredients first
        Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).delete()
         # Get populated form data
        ingredients = request.form.getlist('ingredient')
         # Add related ingredients to DB
        for ingredient in ingredients:
            if len(ingredient) > 0:  
                ingredient = Recipe_Ingredient(text_contents=ingredient.strip(), recipe_id=recipe.recipe_id)
                db.session.add(ingredient)
        db.session.commit()

        # Delete existing instrunctions first
        Recipe_Instruction.query.filter_by(recipe_id=recipe_id).delete()
         # Get populated form data
        instructions = request.form.getlist('instructions')
         # Add related ingredients to DB
        sequence = 0
        for instruction in instructions:
            if len(instruction) > 0:  
                sequence =+ 1
                instruction = Recipe_Instruction(text_contents=instruction.strip(), sequence=sequence, type=1, recipe_id=recipe.recipe_id)
                db.session.add(instruction)
        db.session.commit()

        notes = request.form.getlist('source_notes')
         # Add related ingredients to DB
        sequence = 0
        for source_note in source_notes:
            if len(source_note) > 0:  
                sequence =+ 1
                source_note = Recipe_Instruction(text_contents=source_note.strip(), sequence=sequence, type=2, recipe_id=recipe.recipe_id)
                db.session.add(source_note)
        db.session.commit()

        flash(f'{recipe.name} updated!', 'success')
        return redirect(url_for('recipe', recipe_id=recipe_id))
    return render_template('edit_recipe.html', recipe=recipe, ingredients=ingredients, instructions=instructions, source_notes=source_notes, form=form, image_file=image_file)


@app.route('/recipes/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    db.session.delete(recipe)
    Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).delete()
    Recipe_Instruction.query.filter_by(recipe_id=recipe_id).delete()

    db.session.commit()

    image_file = url_for('static', filename=f'recipe_images/{Recipe.image_file}')
    if os.path.exists(image_file):
        os.remove(image_file) 
    flash(f'{recipe.name} deleted!', 'success')
    return redirect(url_for('home'))
    

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
