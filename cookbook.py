import os

from fpdf import FPDF

from myrecipes import app  # Import app directly from your myrecipes package
from myrecipes import models  # Import the models for accessing your data


class PDF(FPDF):
    def __init__(self):
        super().__init__()
        # Add custom fonts before using them
        self.add_font('DejaVuSans', '', os.path.join('myrecipes', 'static', 'fonts', 'DejaVuSans.ttf'), uni=True)
        self.add_font('DejaVuSans-Bold', '', os.path.join('myrecipes', 'static', 'fonts', 'DejaVuSans-Bold.ttf'), uni=True)
        self.add_page()

    def header(self):
        self.set_font('DejaVuSans', size=12)  # Smaller font size for the header
        self.cell(0, 10, 'My Recipe Cookbook', 0, 1, 'C')

    def chapter_title(self, recipe_name):
        self.set_font('DejaVuSans-Bold', size=14)  # Using DejaVuSans-Bold for the recipe name
        self.cell(0, 10, recipe_name, 0, 1, 'L')
        self.ln(5)  # Smaller line space after recipe title

    def chapter_body(self, body):
        self.set_font('DejaVuSans', size=10)  # Smaller font size for the body text
        self.multi_cell(0, 6, body)  # Adjust the line height to 6 for a tighter line spacing
        self.ln()

    def add_recipe(self, recipe):
        self.chapter_title(recipe.name)

        # Set the current y-position before adding the ingredients and image
        current_y = self.get_y()  # Get the current y-position after the recipe title

        # Get ingredients text
        ingredients = models.Recipe_Ingredient.query.filter_by(recipe_id=recipe.recipe_id).all()
        ingredients_text = "\n".join([ingredient.name_written for ingredient in ingredients])
        
        # Get instructions text (only type=1)
        instructions = models.Recipe_Instruction.query.filter_by(recipe_id=recipe.recipe_id, type=1).all()
        
        # Instructions without numbering
        # Number the instructions
        instructions_text = ""
        for idx, instruction in enumerate(instructions, start=1):
            instructions_text += f"{idx}. {instruction.text_contents}\n"  # Add number before each instruction



        # Left column for ingredients
        self.set_xy(10, current_y)  # Start at the top of the page for ingredients
        body = "Ingredients:\n" + ingredients_text + "\n\n"  # Ingredients text
        self.chapter_body(body)  # Ingredients will be added here

        # Update the y-position after the ingredients are added
        #current_y = self.get_y()  # Update the y-position after ingredients

        # Right column for the image (50% width of the page)
        image_x = 105  # Align the image in the right column, starting from the middle of the page
        image_width = 95  # Right column width (50% of the page width)

        # Add the image for the recipe (if exists)
        if recipe.image_file:
            # Correct image path relative to the script location
            image_path = os.path.join('myrecipes', 'static', 'recipe_images', recipe.image_file)
            if os.path.exists(image_path):
                # Scale the image to fit the column width, maintaining the aspect ratio
                self.image(image_path, x=image_x, y=current_y, w=image_width)

        # Move the current y-position down after placing the image and ingredients
        current_y = self.get_y() + 20  # Add a bit more space after the columns for the instructions

        # Now add instructions **after** the columns (ingredients and image)
        self.set_xy(10, current_y)  # Reset position for instructions section
        body = "Instructions:\n" + instructions_text
        self.chapter_body(body)

        # Add a page break after each recipe to start a new page
        self.add_page()

def generate_pdf():
    with app.app_context():  # Ensure you're within the app context
        pdf = PDF()
        recipes = models.Recipe.query.order_by(models.Recipe.name).all()  # Adjust based on how you retrieve recipes
        for recipe in recipes:
            pdf.add_recipe(recipe)
        pdf.output('cookbook.pdf')

if __name__ == '__main__':
    generate_pdf()
