import socket
from flask import Flask, request, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from forms import add_recipe_form, edit_recipe_form

app = Flask(__name__)
app.config['SECRET_KEY'] = 'testing - need to replace!'


if socket.gethostname() == 'raspberrypi':
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://phil:pythonproj2@192.168.1.143/MyRecipes'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://phil:pythonproj2@192.168.1.143/MyRecipes_DEV'

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

#app.config['MYSQL_PORT'] = '3307'
db = SQLAlchemy(app)

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    instructions = db.Column(db.Text, nullable=False)
    image_file = db.Column(db.String(20), nullable=True, default='default.jpg')

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
    icon_file = db.Column(db.String(100), nullable=True, default='no_ingredient_image.jpg')


@app.route('/setup')
def setup():
    db.create_all()
    return 'Tables created'

@app.route('/', methods=['GET', 'POST'])
@app.route('/home')
def home():
    recipes = Recipe.query.all()
    if request.method == 'POST':
        search_for = request.form['search_for']
        recipes = Recipe.query.join(Ingredient).\
            filter((Ingredient.name == search_for )|( Recipe.name.contains(search_for))).all()   
        return render_template('home.html', recipes=recipes)
    return render_template('home.html', recipes=recipes, title='Recipes')


@app.route('/recipes/<int:recipe_id>', methods=['GET'])
def recipe(recipe_id):
    image_file = url_for('static', filename=f'recipe_pics/{Recipe.image_file}')
    recipe = Recipe.query.get_or_404(recipe_id)
    ingredients = Ingredient.query.filter_by(recipe_id=recipe_id).all()
    
    return render_template('recipe.html', recipe=recipe, ingredients=ingredients, title=recipe.name)


@app.route('/recipes/add_recipe', methods=['GET', 'POST'])
def add_recipe():
    form =  add_recipe_form()
    if request.method == 'POST':
        # Get form data
        name = request.form['name']
        instructions = request.form['instructions']
        ingredients = request.form['ingredients'].split(',')

        # Create new recipe
        recipe = Recipe(name=name, instructions=instructions)
        db.session.add(recipe)
        db.session.commit()

        # Create ingredients for the recipe
        for ingredient in ingredients:
            ingredient = Ingredient(name=ingredient.strip(), recipe_id=recipe.id)
            db.session.add(ingredient)
        db.session.commit()

        #return redirect(url_for('recipes'))
        if form.validate_on_submit():
            flash(f'{recipe.name} added!', 'success')
        return render_template('recipe.html', recipe=recipe, ingredients=ingredients)
    return render_template('add_recipe.html', title='Add Recipe', form=form)
    

@app.route('/recipes/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    form = edit_recipe_form()
    image_file = url_for('static', filename=f'recipe_pics/{Recipe.image_file}')

    recipe = Recipe.query.get_or_404(recipe_id)
    ingredients = Ingredient.query.filter_by(recipe_id=recipe_id).all()


    form.name.data = recipe.name
    form.url.data = recipe.url
    form.instructions.data = recipe.instructions
    
    form.ingredients.data = ingredients[1]
    #image

    if request.method == 'POST':
        recipe.name = request.form['name']
        recipe.instructions = request.form['instructions']
        ingredients = request.form['ingredients'].split(',')

        db.session.commit()

        for ingredient in ingredients:
            ingredient = Ingredient(name=ingredient, recipe_id=recipe.id)
            db.session.add(ingredient)
        db.session.commit()
        flash(f'{recipe.name} saved', 'success')
        return redirect(url_for('recipe', recipe_id=recipe_id))
    return render_template('edit_recipe.html', recipe=recipe, ingredients=ingredients, form=form)




if __name__ == "__main__":
    #app.run(debug=True)
    app.run(host="0.0.0.0", port=8000, debug=True)

#to start dubug in cmd:
#set FLASK_DEBUG=1