from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Integer, Text
from forms import AddNoteForm, EditNoteForm

class Base(DeclarativeBase):
    pass

app=Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///notes.db"
app.config['SECRET_KEY'] = 'secretkey'

db = SQLAlchemy(app, model_class=Base)

class Note(db.Model):
    __tablename__ = 'notes'
    id: Mapped[int] = mapped_column(Integer, primary_key = True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=True, default=None)

with app.app_context():
    db.create_all()
#✎
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/notes')
def notes():
    try:
        result = db.session.execute(db.select(Note))
        notes = result.scalars().all()
    except Exception:
        notes=[]
    return render_template('notes.html',notes=notes)

@app.route('/add', methods=['GET','POST'])
def add_note():
    form = AddNoteForm()
    if form.validate_on_submit():
        note = Note(title=form.title.data,content = form.content.data)
        db.session.add(note)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('add_note.html',form=form)

@app.route('/edit/<int:note_id>',methods=['GET','POST'])
def edit_note(note_id):
    note = db.session.get(Note, note_id)

@app.route('/delete/<int:note_id>')
def delete_note(note_id):
    pass

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == "__main__":
    app.run(debug=True)