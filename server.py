from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Integer, Text, Boolean
from forms import AddNoteForm, EditNoteForm, LoginForm, RegisterForm
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
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'error'

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
    try:
        return db.session.get(User, int(user_id))
    except (SQLAlchemyError, ValueError):
        return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/notes')
@login_required
def notes():
    try:
        result = db.session.execute(
            db.select(Note).where(Note.in_bin != True).where(Note.user_id == current_user.id)
        )
        notes = result.scalars().all()
    except SQLAlchemyError:
        flash("An error occurred while fetching your notes. Please retry.", "error")
        notes = []
    return render_template('notes.html', notes=notes)

@app.route('/add', methods=['GET','POST'])
@login_required
def add_note():
    form = AddNoteForm()
    if form.validate_on_submit():
        try:
            note = Note(title=form.title.data, content=form.content.data, in_bin=False, user_id=current_user.id)
            db.session.add(note)
            db.session.commit()
            flash('Note created successfully', 'success')
            return redirect(url_for('notes'))
        except SQLAlchemyError:
            db.session.rollback()
            flash("Failed to create note due to a database error. Try again.", "error")
    return render_template('add_note.html', form=form)

@app.route('/edit/<int:note_id>', methods=['GET','POST'])
@login_required
def edit_note(note_id):
    try:
        note = db.session.get(Note, note_id)
        if not note or note.user_id != current_user.id:
            flash("Note not found or access denied.", "error")
            return redirect(url_for('notes'))
    except SQLAlchemyError:
        flash("Error pulling note transaction records.", "error")
        return redirect(url_for('notes'))

    form = EditNoteForm()
    if request.method == 'GET':
        form.content.data = note.content
        
    if form.validate_on_submit():
        try:
            note.content = form.content.data
            db.session.commit()
            flash("Changes saved successfully!", "success")
            return redirect(url_for('notes'))
        except SQLAlchemyError:
            db.session.rollback()
            flash("Could not update changes. Please check parameters.", "error")
            
    return render_template('edit_note.html', note=note, form=form)

@app.route('/move_to_bin/<int:note_id>')
@login_required
def move_to_bin(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            note.in_bin = True
            db.session.commit()
            flash("Note moved to bin.", 'success')
        else:
            flash("Action prohibited or record not found.", "error")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Could not change note structural path status.", "error")
    return redirect(url_for('notes'))

@app.route('/note-bin')
@login_required
def note_bin():
    try:
        result = db.session.execute(db.select(Note).where(Note.in_bin == True).where(Note.user_id == current_user.id))
        notes = result.scalars().all()
    except SQLAlchemyError:
        flash("Error checking database trash allocations.", "error")
        notes = []
    return render_template('bin.html', notes=notes)

@app.route('/delete/<int:note_id>')
@login_required
def delete(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            db.session.delete(note)
            db.session.commit()
            flash("Note permanently deleted", "success")
        else:
            flash("Record missing or permission denied.", "error")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Database execution error during record expulsion.", "error")
    return redirect(url_for('note_bin'))

@app.route('/restore/<int:note_id>')
@login_required
def restore(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            note.in_bin = False
            db.session.commit()
            flash('Note restored', 'success')
        else:
            flash("Record mapping unavailable.", "error")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Failed restoration sequence parameters.", "error")
    return redirect(url_for('notes'))

@app.route('/register', methods=['GET','POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            user = User(
                email=form.email.data, 
                name=form.name.data, 
                password=generate_password_hash(form.password.data, method='pbkdf2:sha256', salt_length=16)
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(f'Created new account for {user.name}', 'success')
            return redirect(url_for('notes'))
        except IntegrityError:
            db.session.rollback()
            flash("That email address is already registered.", "error")
        except SQLAlchemyError:
            db.session.rollback()
            flash("An unexpected error occurred. Please try again.", "error")
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET','POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
            if user and check_password_hash(user.password, form.password.data):
                login_user(user)
                flash(f'Welcome back {user.name}', 'success')
                return redirect(url_for('notes'))
            else:
                flash('Incorrect login credentials.', 'error')
        except SQLAlchemyError:
            flash("Internal database communication mismatch.", "error")
    return render_template('login.html', form=form)
    
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('home'))

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == "__main__":
    app.run(debug=True)