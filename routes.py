from myrecipes import app
from myrecipes import db
from myrecipes.forms import add_recipe_form, edit_recipe_form
from myrecipes.models import Recipe, Recipe_Ingredient
from flask import request, render_template, redirect, url_for, flash
import os
from PIL import Image
import secrets

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


@app.route('/recipes/<int:recipe_id>', methods=['GET'])
def recipe(recipe_id):
    #image_file = url_for('static', filename='recipe_pics\\' + Recipe.image_file)
    recipe = Recipe.query.get_or_404(recipe_id)
    image_file = url_for('static', filename='recipe_pics/' + recipe.image_file)

    ingredients = Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).all()
    return render_template('recipe.html', recipe=recipe, ingredients=ingredients, title=recipe.name, image_file=image_file)


def save_image(form_image, recipe_id):
    #Rename file
    #random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_image.filename)
    image_fn = str(recipe_id) + f_ext
    image_path = os.path.join(app.root_path, 'static/recipe_pics', image_fn)
    
    output_size = (1000, 1000)
    i = Image.open(form_image)
    i.thumbnail(output_size)
    
    if i.mode in ("RGBA", "P"):
        i = i.convert("RGB")

    i.save(image_path) 
    return image_fn


@app.route('/recipes/add_recipe', methods=['GET', 'POST'])
def add_recipe():
    form =  add_recipe_form()
    image_file = None

    if form.validate_on_submit():

        # Get populted form data
        name = request.form['name']
        url = request.form['url']
        instructions = request.form['instructions']
        ingredients = request.form.getlist('ingredient[]')

        # Add new recipe to DB
        recipe = Recipe(name=name, url=url, instructions=instructions, image_file=image_file)
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

        
        #recipe = Recipe(name=name, url=url, instructions=instructions, image_file=image_file)

        # Add related ingredients to DB
        for ingredient in ingredients:
            if len(ingredient) > 0:  
                ingredient = Recipe_Ingredient(name=ingredient.strip(), recipe_id=recipe.recipe_id)
                db.session.add(ingredient)
        db.session.commit()

        #return redirect(url_for('recipes'))
        flash(f'{recipe.name} added!', 'success')
        #return render_template('recipe.html', recipe=recipe, ingredients=ingredients)
        return redirect(url_for('recipe', recipe_id=recipe_id))  #return redirect Per Corey
    return render_template('add_recipe.html', title='Add Recipe', form=form)
    

@app.route('/recipes/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    #retrieve the existing recipe from DB
    recipe = Recipe.query.get_or_404(recipe_id)
    ingredients = Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).all()
    image_file = url_for('static', filename=f'recipe_pics/{Recipe.image_file}')
    form = edit_recipe_form()
     

    #populate the retrieved (above) recipe into form
    form.name.data = recipe.name
    form.url.data = recipe.url
    form.instructions.data = recipe.instructions
    form.ingredient.data =  ingredients


    if form.validate_on_submit():
        if form.image.data is not None:
            if os.path.exists(image_file):
                os.remove(image_file) 
            image_file = save_image(request.files['image'],recipe_id)
            recipe.image_file = image_file

        recipe.name = request.form['name']
        recipe.instructions = request.form['instructions']
        recipe.url = request.form['url']

        #recipe.name = form.name.data
        #recipe.url = form.url.data
        #recipe.instructions = form.instructions.data
        db.session.commit() 

        recipe_id= recipe.recipe_id
        # Delete existing ingredients first
        Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).delete()

       # Get populated form data
        ingredients = request.form.getlist('ingredient')

         # Add related ingredients to DB
        for ingredient in ingredients:
            if len(ingredient) > 0:  
                ingredient = Recipe_Ingredient(name=ingredient.strip(), recipe_id=recipe.recipe_id)
                db.session.add(ingredient)
        db.session.commit()

        flash(f'{recipe.name} updated!', 'success')
        return redirect(url_for('recipe', recipe_id=recipe_id))
    return render_template('edit_recipe.html', recipe=recipe, ingredients=ingredients, form=form, image_file=image_file)


@app.route('/recipes/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    db.session.delete(recipe)
    Recipe_Ingredient.query.filter_by(recipe_id=recipe_id).delete()

    db.session.commit()

    image_file = url_for('static', filename=f'recipe_pics/{Recipe.image_file}')
    if os.path.exists(image_file):
        os.remove(image_file) 
    flash(f'{recipe.name} deleted!', 'success')
    return redirect(url_for('home'))
    