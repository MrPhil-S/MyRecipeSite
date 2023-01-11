from flask_wtf import FlaskForm
from wtforms import StringField
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, file_allowed
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length

class add_recipe_form(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=200)])
    url = StringField('URL', validators=[Length(max=500)])
    instructions = StringField('Instructions', validators=[Length(min=2, max=9000)])
    ingredients = StringField('Ingredients', validators=[DataRequired(), Length(min=1, max=100)])
    image = FileField("Image")
    submit = SubmitField("Add Recipe")

class edit_recipe_form(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=1, max=200)])
    url = StringField('Name', validators=[Length(max=500)])
    instructions = StringField('Instructions', validators=[Length(min=1, max=9000)])
    ingredients = StringField('Ingredients', validators=[DataRequired(), Length(min=1, max=100)])
    image = FileField("Image")
    submit = SubmitField("Save Changes")