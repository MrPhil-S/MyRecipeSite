from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length

class add_recipe_form(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=200)])
    url = StringField('URL', validators=[Length(max=500)])
    instructions = TextAreaField('Instructions', validators=[Length(min=2, max=9000)])
    ingredient = StringField('Ingredient')#, validators=[Length(min=1, max=100)])
    image = FileField('Upload image', validators=[FileAllowed(['jpg', 'png'])])
    submit = SubmitField("Add Recipe")

class edit_recipe_form(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=1, max=200)])
    url = StringField('URL', validators=[Length(max=500)])
    instructions = TextAreaField('Instructions', validators=[Length(min=1, max=9000)])
    ingredient = StringField('Ingredient')#, validators=[Length(min=1, max=100)])
    image = FileField('Image')#, validators=[FileAllowed(['jpg', 'png'])])  #Validator issue: upon render_template, the ingredient values will not re-load into the ajax fields
    submit = SubmitField("Save Changes")