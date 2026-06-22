from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DateField, SubmitField, PasswordField, EmailField
from wtforms.validators import DataRequired, Length, Optional, ValidationError, Email, EqualTo
from flask_ckeditor import CKEditorField

class AddNoteForm(FlaskForm):
    title = StringField('Note title',validators=[DataRequired(),Length(min=4,max=30)])
    content = CKEditorField('Note Content', validators=[DataRequired()])
    submit = SubmitField('Add Note')