from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SelectMultipleField, validators
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SubmitField, widgets
from wtforms.validators import DataRequired, Length


# Define a custom widget for the multiselect dropdown with checkboxes
class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class add_recipe_form(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=200)])
    url = StringField('URL', validators=[Length(max=500)])
    user_note = TextAreaField('Notes')    
    ingredient = StringField('Ingredient')#, validators=[Length(min=1, max=100)])
    ingredient_note = StringField('Note')#, validators=[Length(min=1, max=100)])    
    instructions = TextAreaField('Instructions')#, validators=[Length(min=2, max=9000)])
    prep_time = StringField('Prep Time')#, validators=[Length(min=2, max=9000)])
    cook_time = StringField('Cook Time')#, validators=[Length(min=2, max=9000)])
    additional_time = StringField('Additional Time')#, validators=[Length(min=2, max=9000)])
    note_from_user = TextAreaField('My notes')#, validators=[Length(min=2, max=9000)])
    Servings = StringField('Servings')#, validators=[Length(min=2, max=9000)])
    rating = TextAreaField('Rating')#, validators=[Length(min=2, max=9000)])
    cuisine = StringField('Cuisine')#, validators=[Length(min=2, max=9000)])
    cuisinelist = SelectField('Cuisine')
    
    choices = [('option1', 'Option 1'), ('option2', 'Option 2'), ('option3', 'Option 3')]
    multiselect_field = SelectMultipleField('Select Options', choices=choices, validators=[validators.DataRequired()])


    instructions = TextAreaField('Instructions')#, validators=[Length(min=2, max=9000)])
    source_notes = TextAreaField('Source_notes')#, validators=[Length(min=2, max=9000)])
    image = FileField('Upload image', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    submit = SubmitField("Add Recipe")

class edit_recipe_form(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=1, max=200)])
    url = StringField('URL', validators=[Length(max=500)])
    user_note = TextAreaField('Notes')
    ingredient = StringField('Ingredient')#, validators=[Length(min=1, max=100)])
    instructions = TextAreaField('Instructions')#, validators=[Length(min=1, max=9000)])
    source_notes = TextAreaField('Source_notes')#, validators=[Length(min=2, max=9000)])
    image = FileField('Change Image', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])  #Validator issue: upon render_template, the ingredient values will not re-load into the ajax fields
    submit = SubmitField("Save Changes")