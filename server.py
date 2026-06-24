from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Integer, Text, Boolean
from forms import AddNoteForm, EditNoteForm
from flask_ckeditor import CKEditor
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

class Base(DeclarativeBase):
    pass

app=Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///notes.db"
app.config['SECRET_KEY'] = 'secretkey'

db = SQLAlchemy(app, model_class=Base)
ckeditor = CKEditor(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class Note(db.Model):
    __tablename__ = 'notes'
    id: Mapped[int] = mapped_column(Integer, primary_key = True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    in_bin: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(1000), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    notes = relationship("Note", backref="author", lazy=True)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/notes')
def notes():
    try:
        result = db.session.execute(db.select(Note).where(Note.in_bin != True).where(Note.id==current_user.id))
        notes = result.scalars().all()
    except Exception:
        notes=[]
    return render_template('notes.html',notes=notes)

@app.route('/add', methods=['GET','POST'])
def add_note():
    form = AddNoteForm()
    if form.validate_on_submit():
        note = Note(title=form.title.data,content = form.content.data,in_bin=False)
        db.session.add(note)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('add_note.html',form=form)

@app.route('/edit/<int:note_id>',methods=['GET','POST'])
def edit_note(note_id):
    note = db.session.get(Note, note_id)
    form = EditNoteForm()
    if request.method == 'GET':
        form.content.data = note.content
    if form.validate_on_submit():
        note.content = form.content.data
        db.session.commit()
        return redirect(url_for('notes'))
    return render_template('edit_note.html',note=note,form=form)

@app.route('/move_to_bin/<int:note_id>')
def move_to_bin(note_id):
    note = db.session.get(Note,note_id)
    note.in_bin = True
    db.session.commit()
    return redirect(url_for('notes'))

@app.route('/note-bin')
def note_bin():
    result = db.session.execute(db.select(Note).where(Note.in_bin == True))
    notes = result.scalars().all()
    return render_template('bin.html',notes=notes)

@app.route('/delete/<int:note_id>')
def delete(note_id):
    note = db.session.get(Note,note_id)
    db.session.delete(note)
    db.session.commit()
    return redirect(url_for('note_bin'))

@app.route('/restore/<int:note_id>')
def restore(note_id):
    note = db.session.get(Note,note_id)
    note.in_bin = False
    db.session.commit()
    return redirect(url_for('notes'))

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == "__main__":
    app.run(debug=True)