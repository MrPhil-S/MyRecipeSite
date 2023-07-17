from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length

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
    cuisinelist = SelectField('Cuisine', coerce=int, validators=[DataRequired()])
    collection = StringField('Collection')#, validators=[Length(min=2, max=9000)])
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