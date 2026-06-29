from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, EmailField, TextAreaField
from wtforms.validators import DataRequired, Length, Email

class AddNoteForm(FlaskForm):
    title = StringField('Note title',validators=[DataRequired(),Length(min=4,max=30)])
    content = TextAreaField('Note Content', validators=[DataRequired()])
    submit = SubmitField('Add Note')

class EditNoteForm(FlaskForm):
    content=TextAreaField('Edit Note Content', validators=[DataRequired()])
    submit = SubmitField('Save Changes')

class RegisterForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=250)])
    email = EmailField('Email', validators=[DataRequired(), Email(), Length(max=100)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Create Account')

class LoginForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')