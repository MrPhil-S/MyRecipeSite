from flask import Flask, request, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///MyRecipes.db'
db = SQLAlchemy(app)

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    instructions = db.Column(db.Text, nullable=False)

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)

@app.route('/setup')
def setup():
    db.create_all()
    return 'Tables created'

@app.route('/')
def index():
    name = request.args.get('name')
    return render_template('base.html', name=name) 

@app.route('/recipes')
def all_recipes():
    recipes = Recipe.query.all()
    return render_template('recipes.html', recipes=recipes)

@app.route('/recipes/search_recipes', methods=['GET', 'POST'])
def search_recipes():
    if request.method == 'POST':
        ingredient = request.form['ingredient']
        recipes = Recipe.query.join(Ingredient).filter(Ingredient.name == ingredient).all()
        return render_template('search_recipes.html', recipes=recipes)
    return render_template('search_recipes.html')


@app.route('/recipes/add_recipe', methods=['GET', 'POST'])
def add_recipe():
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
        return render_template('recipe.html', recipe=recipe, ingredients=ingredients)
    return render_template('add_recipe.html')
    
@app.route('/recipes/add_recipe', methods=['GET', 'POST'])
def add_recipe():
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
        return render_template('recipe.html', recipe=recipe, ingredients=ingredients)
    return render_template('edit_recipe.html')



@app.route('/recipes/<int:recipe_id>')
def recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    ingredients = Ingredient.query.filter_by(recipe_id=recipe_id).all()
    return render_template('recipe.html', recipe=recipe, ingredients=ingredients)




if __name__ == "__name__":
    app.run(debug=True)