from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (BooleanField, IntegerField, RadioField, SelectField,
                     SelectMultipleField, StringField, SubmitField,
                     TextAreaField, validators, widgets)
from wtforms.validators import DataRequired, Length, Optional


# Define a custom widget for the multiselect dropdown with checkboxes
class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class add_recipe_form(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=200)])
    url = StringField('URL', validators=[Length(max=500)])
    user_note = TextAreaField('Notes')    
    is_bulk_ingredients = RadioField(
        'How do you want to add ingredients?',
        choices=[('False', 'Individually'), ('True', 'Bulk')],
     #   default='bulk',
        render_kw={'class': 'inputMethod'}  # Adding a general class if needed
    )
    is_ingredient_group = BooleanField('Group?', false_values=(False, 'false', 0, '0'))
    ingredient = StringField('Ingredient')#, validators=[Length(min=1, max=100)])
    ingredient_note = StringField('Note')#, validators=[Length(min=1, max=100)]) 
    ingredient_bulk = TextAreaField('Ingredients (Start a line with > to make it a group)')#, validators=[Length(min=1, max=100)])
    instructions = TextAreaField('Instructions (Start a line with > to make it a group)')#, validators=[Length(min=2, max=9000)])
    prep_time = StringField('Prep Time')#, validators=[Length(min=2, max=9000)])
    cook_time = StringField('Cook Time')#, validators=[Length(min=2, max=9000)])
    additional_time = StringField('Additional Time')#, validators=[Length(min=2, max=9000)])
    note_from_user = TextAreaField('My notes')#, validators=[Length(min=2, max=9000)])
    servings = StringField('Servings')#, validators=[Length(min=2, max=9000)])
    cuisinelist = SelectField('Cuisine')
    collection_list = SelectMultipleField('Collection(s)', choices=[], validate_choice=False)#, validators=[validators.DataRequired()])
    source_notes = TextAreaField('Source notes')#, validators=[Length(min=2, max=9000)])
    image = FileField('Upload image', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])
    pdf = FileField('Upload recipe PDF', validators=[FileAllowed(['pdf'])])
    submit = SubmitField("Add Recipe")

class edit_recipe_form(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=1, max=200)])
    url = StringField('URL', validators=[Length(max=500)])
    whisk_url = StringField('Whisk URL', validators=[Length(max=500)])
    user_note = TextAreaField('Notes')
    is_bulk_ingredients = RadioField(
        'How do you want to add ingredients?',
        choices=[('False', 'Individually'), ('True', 'Bulk')],
     #   default='bulk',
        render_kw={'class': 'inputMethod'}  # Adding a general class if needed
    )
    submit = SubmitField('Submit')
    ingredient = StringField('Ingredient')#, validators=[Length(min=1, max=100)])
    ingredient_note = StringField('Note')#, validators=[Length(min=1, max=100)]) 
    ingredient_bulk = TextAreaField('Ingredients (Start a line with > to make it a group)')#, validators=[Length(min=1, max=100)])
    instructions = TextAreaField('Instructions (Start a line with > to make it a group)')#, validators=[Length(min=1, max=9000)])
    prep_time = StringField('Prep Time')#, validators=[Length(min=2, max=9000)])
    cook_time = StringField('Cook Time')#, validators=[Length(min=2, max=9000)])
    additional_time = StringField('Additional Time')#, validators=[Length(min=2, max=9000)])
    note_from_user = TextAreaField('My notes')#, validators=[Length(min=2, max=9000)])
    servings = IntegerField('Servings', validators=[Optional()])
    cuisinelist = SelectField('Cuisine')
    collection_list = SelectMultipleField('Collection(s)', choices=[], validate_choice=False)#, validators=[validators.DataRequired()])
    source_notes = TextAreaField('Source Notes')#, validators=[Length(min=2, max=9000)])
    image = FileField('Change Image', validators=[FileAllowed(['jpg', 'png', 'jpeg'])])  #Validator issue: upon render_template, the ingredient values will not re-load into the ajax fields
    pdf = FileField('Upload recipe PDF', validators=[FileAllowed(['pdf'])])
    submit = SubmitField("Save Changes")

class add_collection_form(FlaskForm):
    collection_name = StringField('Name')#, validators=[DataRequired(), Length(min=2, max=200)])
    