import datetime
import os
from urllib.parse import urlparse

from flask import (current_app, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from sqlalchemy import desc, func, text
from sqlalchemy.orm import aliased

from myrecipes import (  # , get_recipies<<<<<<<<<<<<<<<<<<<<<<<<<<<disabled!
    app, db)
from myrecipes.forms import (add_collection_form, add_recipe_form,
                             edit_recipe_form)
from myrecipes.models import (Collection, Cuisine, Ingredient_Synonym,
                              Query_History, Recipe, Recipe_Ingredient,
                              Recipe_Instruction, Recipe_Plan_Date,
                              recipe_collection, recipe_cooked_date,
                              recipe_view_date)

#import secrets
from .helpers import (get_sort_reverse, parse_search_query, save_file,
                      save_image, search_recipe, search_recipe_ingredient)


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
    old_query_history = (
    db.session.query(Query_History.query_text, func.max(Query_History.query_dt).label('max_query_dt'))
    .group_by(Query_History.query_text)
    .order_by(func.max(Query_History.query_dt).desc())
    .limit(5)
    .all()
)
    
    collections = (
        db.session.query(
            Collection.collection_id,
            Collection.collection_name,
            func.max(Recipe.update_dt).label('latest_update_dt'),
            func.count(Recipe.recipe_id).label('recipe_count'),
            func.first_value(Recipe.image_file).over(
                order_by=Recipe.update_dt.desc(),
                partition_by=Collection.collection_id
            ).label('latest_image_file')
        )
        .select_from(Collection)
        .join(recipe_collection, Recipe)
        .group_by(Collection.collection_name)
        .order_by(Collection.collection_name, desc('latest_update_dt'))
    ).all()


    collection_id_filter = request.args.get('collection_id_filter', None)
    collection_name_filter = request.args.get('collection_name_filter', None)

   
    sorting_options = [
        ('A to Z', 'Recipe.name'),
        ('Recently Cooked', 'max_recipe_cooked_dt'),
        ('Recently Visited', 'max_recipe_view_dt'),
        ('Recently Added', 'Recipe.create_dt')

    ]
    
    session_sort_order = session.get('session_sort_order', 'create_dt')
    session_sort_reverse = session.get('session_sort_reverse')

    if request_sort := request.args.get('recipe_sort'):
        if session_sort_order == request_sort:
            sort_reverse = not session_sort_reverse 
        else:
            sort_reverse =  get_sort_reverse(request_sort)
        session_sort_order = request_sort
        session['session_sort_order'] = session_sort_order
        session['session_sort_reverse'] = sort_reverse

    else:
        #Default sorting for new session
        sort_reverse = True
        recipe_sort_label = "Recently Added"

    for i in sorting_options:
        if i[1] == session_sort_order:
            recipe_sort_label = i[0]
    
    should_prepopulate = request.args.get('retreive_search_query') == 'true'
    if not should_prepopulate:
        session.pop('session_form_data', '')
     
    # Initialize the 'query' variable
    query = ''

    if request.method == 'POST':
        # If the form is submitted via POST, retrieve the query from the form data
        query = request.form.get('search_for', '')

        session['session_form_data'] = query        

        if len(query.strip()) > 0:
        # Add search term DB
            saved_query = Query_History(query_text=query)
            db.session.add(saved_query)
            db.session.flush()
            db.session.refresh(saved_query)
            db.session.commit()
    elif not query:
        #this allows the previously searched query to repopulate (when add/remove from plan is used)
        query = session.get('session_form_data', '')
    else:
        # If it's a GET request, retrieve the query from the query parameters
        #This might need to be removed - it never happens?
        print(f"it happened!: {request.args.get('search_for', '')}")
        query = request.args.get('search_for', '')

    tokens, excluded_tokens = parse_search_query(query)

    # Initialize a set to store distinct recipe IDs that match all tokens
    all_recipe_ids = set()

    # Find the distinct recipe IDs for each token
    for token in tokens:
        token_recipe_ids = search_recipe(token)
        token_ingredient_ids = search_recipe_ingredient(token)
        
        # If this is the first token, initialize the all_recipe_ids set
        if not all_recipe_ids:
            all_recipe_ids = set(token_recipe_ids + token_ingredient_ids)
        else:
            # Update the set with the common recipe IDs among all tokens
            all_recipe_ids.intersection_update(token_recipe_ids + token_ingredient_ids)

    # Exclude recipes or ingredients containing excluded words
    for excluded_token in excluded_tokens:
        excluded_recipe_ids = search_recipe(excluded_token)
        excluded_ingredient_ids = search_recipe_ingredient(excluded_token)
        all_recipe_ids.difference_update(excluded_recipe_ids + excluded_ingredient_ids)

    # Retrieve recipes based on the common recipe IDs
    #all_results = Recipe.query.filter(Recipe.recipe_id.in_(all_recipe_ids)).order_by(Recipe.recipe_id.desc()).all()
    rp = aliased(Recipe_Plan_Date)
    rvd = db.aliased(recipe_view_date)
    rcd = db.aliased(recipe_cooked_date)
    rc = db.aliased(recipe_collection)
    

    # query
    all_results = db.session.query(Recipe, rp,
        func.coalesce(func.max(rvd.recipe_view_dt), Recipe.create_dt).label('max_recipe_view_dt'),
        func.coalesce(func.max(rcd.recipe_cooked_dt), Recipe.create_dt).label('max_recipe_cooked_dt'),
    ).\
        outerjoin(rp, (Recipe.recipe_id == rp.recipe_id) & (rp.removed_dt.is_(None))).\
        outerjoin(rvd, Recipe.recipe_id == rvd.recipe_id).\
        outerjoin(rcd, Recipe.recipe_id == rcd.recipe_id).\
        join(rc, Recipe.recipe_id == rc.c.recipe_id, isouter=True).\
        filter(Recipe.recipe_id.in_(all_recipe_ids), rc.c.collection_id == collection_id_filter if collection_id_filter is not None else True).\
        group_by(Recipe.recipe_id).\
        order_by(Recipe.recipe_id.desc()).\
        all()


    return render_template('home.html', 
                           all_results=all_results, 
                           title='Recipes', 
                           query=query, 
                           old_query_history=old_query_history,
                           session_sort_order=session_sort_order,
                           sort_reverse = sort_reverse,
                           collections = collections,
                           sorting_options=sorting_options,
                           recipe_sort_label = recipe_sort_label,
                           collection_name_filter = collection_name_filter
                           )


@app.route('/reset_session', methods=['GET'])
def reset_session():
    # Clear the specific session variable 'form_data'
    session.pop('form_data', None)

    # Alternatively, to clear the entire session, use session.clear()

    # Redirect back to the home page or any other route
    return redirect(url_for('home'))


@app.route('/import_recipes')
def import_recipes():
    return render_template('import_recipes.html')

@app.route('/cooking_tips')
def cooking_tips():
    return render_template('cooking_tips.html')

@app.route('/collections', methods=['GET', 'POST'])
def collections():
    form = add_collection_form()
    collections = Collection.query.order_by(Collection.collection_name.asc()).all()

    if form.validate_on_submit():
        # Get populted form data
        collection_name = request.form['collection_name']
        
        # Add new collection to DB
        collection = Collection(collection_name=collection_name)
        db.session.add(collection)
        db.session.flush()
        db.session.refresh(collection)
        db.session.commit()
        flash(f'{collection_name} added', 'success')

        return redirect(url_for('collections', collections=collections))  
    return render_template('collections.html', collections=collections, title='Collections', form=form)


@app.route('/synonyms', methods=['GET', 'POST'])
def synonyms():
    form = add_collection_form()
    collections = Collection.query.order_by(Collection.collection_name.asc()).all()

    if form.validate_on_submit():
        # Get populted form data
        collection_name = request.form['collection_name']
        
        # Add new collection to DB
        collection = Collection(collection_name=collection_name)
        db.session.add(collection)
        db.session.flush()
        db.session.refresh(collection)
        db.session.commit()
        flash(f'{collection_name} added', 'success')

        return redirect(url_for('synonyms', collections=collections))  
    return render_template('synonyms.html', collections=collections, title='Collections', form=form)



@app.route('/recipes/<int:recipe_id>', methods=['GET', 'POST'])
def recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)

    recipe_view_dt = recipe_view_date(recipe_id=recipe_id)
    db.session.add(recipe_view_dt)
    db.session.commit()

    view_count = recipe_view_date.query.filter_by(recipe_id=recipe_id).count()
    cook_count = recipe_cooked_date.query.filter_by(recipe_id=recipe.recipe_id).count()
    image_file = url_for('static', filename='recipe_images/' + recipe.image_file)
    ingredients = Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).all()
    instructions = Recipe_Instruction.query.filter_by(recipe_id=recipe_id, type=1).all()
    source_notes = Recipe_Instruction.query.filter_by(recipe_id=recipe_id, type=2).all()
    cuisine_name = Cuisine.query.filter_by(cuisine_id=recipe.cuisine_id).first()
    collections = recipe.collections
    
    if recipe.note_from_user is not None:
        note_from_user_list = recipe.note_from_user.split('\n')
    else:
        note_from_user_list = None
    recipe_planned = None
    # Query to check if a record exists with the given recipe_id and removed_dt is NULL
    recipe_planned = Recipe_Plan_Date.query.filter_by(recipe_id=recipe_id, removed_dt=None).first()
    #planned = planned is not None
    
    recipe_pdf = None
    for file in os.listdir(os.path.join(current_app.root_path, 'static/custom_prints/')):
        
        if file == f'{recipe_id}.pdf':
            recipe_pdf = file
            break

    return render_template('recipe.html', recipe=recipe, 
                           note_from_user_list=note_from_user_list, 
                           ingredients=ingredients, 
                           instructions=instructions, 
                           source_notes=source_notes, 
                           title=recipe.name, 
                           image_file=image_file, 
                           view_count=view_count, 
                           cuisine_name=cuisine_name, 
                           collections=collections, 
                           cook_count=cook_count, 
                           recipe_planned=recipe_planned, 
                           recipe_pdf=recipe_pdf)


@app.route('/recipes/add_recipe', methods=['GET', 'POST'])
def add_recipe():
    form =  add_recipe_form()
    image_file = None
  
    # Populate the dropdown fields with data from the database
    blank_default_dropdown = (0, '')
    form.cuisinelist.choices    = [(cuisine.cuisine_id, cuisine.cuisine_name) for cuisine in Cuisine.query.order_by(Cuisine.cuisine_name).all()]
    form.cuisinelist.choices.insert(0, (0, ''))

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
        if request.form['servings'] is not '':
            servings = request.form['servings']
        else:
            servings = None
        selected_collections = request.form.getlist('collection_list')

        selected_cuisine_id = form.cuisinelist.data
        cuisine_id = selected_cuisine_id if selected_cuisine_id != 0 else None

        # Add new recipe to DB
        recipe = Recipe(name=name, source_url=source_url, note_from_user=note_from_user, image_file=image_file, prep_time=prep_time, cook_time=cook_time, additional_time=additional_time, servings=servings, cuisine_id=cuisine_id)
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

        if form.pdf.data:
            save_file(form.pdf.data, recipe_id)
            #Get the newly inserted recipe to be used to UPDATE with the pdf_file
            #recipe = Recipe.query.get_or_404(recipe_id)
            #recipe.pdf_file = pdf_file

        #add the collections to recipe_collection table
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
    recipe = Recipe.query.get_or_404(recipe_id)
    form = edit_recipe_form(cuisinelist = recipe.cuisine_id)

    ingredients = Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).all()
    instructions = Recipe_Instruction.query.with_entities(Recipe_Instruction.text_contents).order_by(Recipe_Instruction.sequence).filter_by(recipe_id=recipe_id, type=1).all()
    source_notes = Recipe_Instruction.query.with_entities(Recipe_Instruction.text_contents).order_by(Recipe_Instruction.sequence).filter_by(recipe_id=recipe_id, type=2).all()
    #collections = recipe_collection.query.order_by(recipe_collection.collecton_id).filter_by(recipe_id=recipe_id).all()

    #populate form with all collection choices
    form.collection_list.choices = [(collection.collection_id, collection.collection_name) for collection in Collection.query.order_by(Collection.collection_name).all()]
   
       # Fetch the collections associated with the current recipe_id
    collections = Collection.query.order_by(Collection.collection_name.asc()).all()

    # Retrieve selected collection_ids for the current recipe
    selected_collection_ids = [collection.collection_id for collection in recipe.collections]

    # Define collections_data as a list of dictionaries
    collections_data = [{'collection_id': collection.collection_id, 'collection_name': collection.collection_name} for collection in collections]

    # Populate the dropdown fields with data from the database
    form.cuisinelist.choices    = [(cuisine.cuisine_id, cuisine.cuisine_name) for cuisine in Cuisine.query.order_by(Cuisine.cuisine_name).all()]
    form.cuisinelist.choices.insert(0, (0, ''))
    
    image_file = url_for('static', filename='recipe_images/' + recipe.image_file)
     
    #populate the retrieved (above) recipe into form
    form.name.data = recipe.name
    form.url.data = recipe.source_url
    form.prep_time.data = recipe.prep_time
    form.cook_time.data = recipe.cook_time
    form.additional_time.data = recipe.additional_time
    form.servings.data = recipe.servings
    #cuisine
    #collection
    form.note_from_user.data = recipe.note_from_user
    form.ingredient.data =  ingredients

    pdf_file = None
    #TODO:Should this os.path.join be a url_for instead? If using url_for, there may be a need to include the root directory. 
    pdf_file_path = os.path.join(app.root_path, 'static/custom_prints', str(recipe_id) + '.pdf')
    if os.path.exists(pdf_file_path):
        pdf_file = os.path.basename(pdf_file_path)

    # Extract the text_contents values and join them with newlines
    instructions_list = [item[0] for item in instructions]
    instructions_string = "\n".join(instructions_list)
    form.instructions.data = instructions_string

    source_notes_list = [item[0] for item in source_notes]
    source_notes_string = "\n".join(source_notes_list)
    form.source_notes.data = source_notes_string

    if form.validate_on_submit():
        if form.image.data is not None:
            if os.path.exists(image_file):
                os.remove(image_file) 
            image_file = save_image(request.files['image'],recipe_id)
            recipe.image_file = image_file

        recipe.name = request.form['name']
        recipe.source_url = request.form['url']
        recipe.note_from_user = request.form['note_from_user']
        recipe.prep_time = request.form['prep_time']
        recipe.cook_time = request.form['cook_time']
        recipe.additional_time = request.form['additional_time']        
        if request.form['servings'] is not '':
            recipe.servings = request.form['servings']
        else:
            recipe.servings = None
        recipe.cuisine_id = form.cuisinelist.data
        db.session.commit() 

        if form.pdf.data:
            save_file(form.pdf.data, recipe_id)
            #Get the newly inserted recipe to be used to UPDATE with the pdf_file
            #recipe = Recipe.query.get_or_404(recipe_id)
            #recipe.pdf_file = pdf_file

        #Get new form values for child tables
        ingredients = request.form.getlist('ingredient[]')
        ingredient_notes = request.form.getlist('ingredient_note[]')    
        
        instructions = request.form['instructions']
        source_notes = request.form['source_notes']
        selected_collections = request.form.getlist('collection_list')

        recipe_id= recipe.recipe_id

        #add the collections to collection table
        db.session.query(recipe_collection).filter_by(recipe_id=recipe_id).delete()
        db.session.commit() 

        for collection_id in selected_collections:
            insert_recipe_collection = recipe_collection.insert().values(
                collection_id=int(collection_id),
                recipe_id=recipe_id )
            db.session.execute(insert_recipe_collection)
        db.session.commit()

        # Delete existing ingredients first
        Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).delete()


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

        # Delete existing instructions first
        Recipe_Instruction.query.filter_by(recipe_id=recipe_id).delete()
         
         # Add related ingredients to DB
        instructions_list = instructions.splitlines()   
        sequence = 0
        for instruction in instructions_list:
            if len(instruction) > 0:  
                sequence =+ 1
                instruction = Recipe_Instruction(text_contents=instruction.strip(), sequence=sequence, type=1, recipe_id=recipe.recipe_id)
                db.session.add(instruction)
        db.session.commit()

        source_notes_list = source_notes.splitlines()   
         # Add related ingredients to DB
        sequence = 0
        for source_note in source_notes_list:
            if len(source_note) > 0:  
                sequence =+ 1
                source_note = Recipe_Instruction(text_contents=source_note.strip(), sequence=sequence, type=2, recipe_id=recipe.recipe_id)
                db.session.add(source_note)
        db.session.commit()

        flash(f'{recipe.name} updated!', 'success')
        return redirect(url_for('recipe', recipe_id=recipe_id))
    return render_template('edit_recipe.html', recipe=recipe, ingredients=ingredients, instructions=instructions, source_notes=source_notes, form=form, image_file=image_file, collections_data=collections_data, selected_collection_ids=selected_collection_ids, pdf_file=pdf_file)


@app.route('/recipes/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    db.session.delete(recipe)
    Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).delete()
    Recipe_Instruction.query.filter_by(recipe_id=recipe_id).delete()
    #TODO: add additional child table records to delete (ex recipe_collection)
    db.session.commit()

    if recipe.image_file != 'default.jpg':
        image_file = os.path.join(current_app.root_path, 'static', 'recipe_images', recipe.image_file)
        if os.path.exists(image_file):
            os.remove(image_file) 

    flash(f'{recipe.name} deleted!', 'success')
    return redirect(url_for('home'))
    

@app.route('/collections/<int:collection_id>/delete', methods=['POST'])
def delete_collection(collection_id):
    collection = Collection.query.get_or_404(collection_id)
    db.session.delete(collection)
   # recipe_collection.filter_by(collection_id=collection_id).delete()
       #form.name.data = recipe.name

    db.session.commit()

    flash(f'{collection.collection_name} deleted!', 'success')
    return redirect(url_for('collections', collections=collections))  


@app.route('/collections/<int:collection_id>/edit', methods=['GET', 'POST'])
def edit_collection(collection_id):
    collection = Collection.query.get_or_404(collection_id)
    form = add_collection_form()
    
    if form.validate_on_submit():
        collection.collection_name = form.collection_name.data
        db.session.commit()
        flash(f'{collection.collection_name} updated', 'success')
        return redirect(url_for('collections', collections=collections))  
    return render_template('collections.html', collections=collections, title='Collections', form=form)


@app.route('/mark_cooked', methods=['POST'])
def mark_cooked():
    recipe_id = request.form.get('recipe_id')
    add_date = recipe_cooked_date(recipe_id=recipe_id)
    db.session.add(add_date)
    db.session.commit()
    flash(f'Marked as cooked', 'success')
    return redirect(request.referrer)


@app.route('/plan', methods=['GET', 'POST'])
def plan():
    #plans = Recipe_Plan_Date.query.order_by(Recipe_Plan_Date.added_dt.desc()).all()

    #plans = db.session.query(Recipe).
    #        join(Recipe, (Recipe_Plan_Date.recipe_id == Recipe.recipe_id)).\
    #        order_by(Recipe_Plan_Date.added_dt.desc()).\
    #        all()
    
    plans = (
        db.session.query(Recipe, Recipe_Plan_Date)
        .select_from(Recipe_Plan_Date)
        .join(Recipe, Recipe.recipe_id == Recipe_Plan_Date.recipe_id)
        .filter(Recipe_Plan_Date.removed_dt.is_(None))
        .order_by(Recipe_Plan_Date.added_dt.desc())
        .all()
    )

       # Grouping by added_dt in Python code
    grouped_plans = {}
    for recipe, plan_date in plans:
        date_str =  plan_date.added_dt.date()
        days_since_added = (datetime.datetime.now() - plan_date.added_dt).days
        #grouped_plans['days_since_added'] = days_since_added

        if date_str not in grouped_plans:
            grouped_plans[date_str] = {'days_since_added': days_since_added, 'plans': []}
        grouped_plans[date_str]['plans'].append({'recipe': recipe})
    return render_template('plan.html', grouped_plans=grouped_plans)


@app.route('/plan/<int:recipe_id>', methods=['POST'])
def add_to_plan(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    plan = Recipe_Plan_Date(recipe_id=recipe_id)#, planned_dt=planned_dt)

    db.session.add(plan)
    db.session.flush()
    db.session.refresh(plan)
    db.session.commit()

    # Redirect back to the same page if the referer is not /home 
    # (example) when add/remove from plan from within the Recipe route
    referer = request.headers.get('Referer')
    referer_path = urlparse(referer).path
    if referer_path and referer_path != '/home':
        flash(f'{recipe.name} added to <a href="{url_for("plan")}">plan</a>!', 'success')
        return redirect(referer)

    flash(f'{recipe.name} added to <a href="{url_for("plan")}">plan</a>!', 'success')
    return redirect(url_for('home', usePlanScroll='true', retreive_search_query='true'))


@app.route('/plan/<int:recipe_id>/delete', methods=['POST'])
def remove_from_plan(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)

    recipe_planned = Recipe_Plan_Date.query.filter_by(recipe_id=recipe.recipe_id, removed_dt=None).first_or_404()
    recipe_planned.removed_dt = db.func.current_timestamp()
    db.session.commit()
    #<a href="/recipes/{{ recipe.recipe_id }}"> 
    # Redirect back to the same page if the referer is not /home 
    # (example) when add/remove from plan from within the Recipe route
    referer = request.headers.get('Referer')
    referer_path = urlparse(referer).path
    
    if referer_path and '/recipes/' in referer_path:
        flash(f'{recipe.name}      removed from <a href="{url_for("plan")}">plan</a>!', 'success')
        return redirect(referer)
    if referer_path and referer_path == '/plan':
        flash(f'<a href="/recipes/{ recipe.recipe_id }"> {recipe.name}</a>      removed from plan!', 'success')
        return redirect(referer)
    elif referer_path and referer_path != '/home':
        flash(f'<a href="/recipes/{ recipe.recipe_id }"> {recipe.name}</a>      removed from <a href="{url_for("plan")}">plan</a>!', 'success')
        return redirect(referer)
    flash(f'<a href="/recipes/{ recipe.recipe_id }"> {recipe.name}</a>      removed from <a href="{url_for("plan")}">plan</a>!', 'success')
    return redirect(url_for('home', usePlanScroll='true', retreive_search_query='true'))



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

