from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Integer, Text, Boolean, JSON, DateTime
from forms import AddNoteForm, EditNoteForm, LoginForm, RegisterForm, VerificationForm
from flask_login import UserMixin, login_user, LoginManager, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from helpers import send_email_threaded, create_code, ask_groq, ask_mistral, ask_gemini, get_welcome_message, md_to_html, is_ai_error
from typing import Dict,Any
from datetime import datetime, timezone, timedelta
import json

class Base(DeclarativeBase):
    pass

app=Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///notes.db"
app.config['SECRET_KEY'] = 'secretkey'
VERIFICATION_TTL_SECONDS = 10 * 60
NOTE_ACTION_COOLDOWN_SECONDS = 5 * 60

db = SQLAlchemy(app, model_class=Base)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'error'

class Note(db.Model):
    __tablename__ = 'notes'
    id: Mapped[int] = mapped_column(Integer, primary_key = True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    md_content: Mapped[str] = mapped_column(Text, nullable=True, default=None)    
    in_bin: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    meta_data: Mapped[Dict[str,Any]] = mapped_column(JSON)
    last_opened : Mapped[datetime] = mapped_column(DateTime,default = lambda: datetime.now(timezone.utc), onupdate = lambda: datetime.now(timezone.utc))

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(1000), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    notes = relationship("Note", backref="author", lazy=True)

def get_meta_data(content):
    metadata = ask_groq(content,username=current_user.name,metadata=True)
    return metadata

def _clear_pending_auth():
    session.pop('pending_register', None)
    session.pop('pending_login', None)
    session.pop('pending_auth_code', None)
    session.pop('pending_auth_expires_at', None)
    session.pop('pending_auth_email', None)


def _verification_is_valid(submitted_code):
    expected_code = session.get('pending_auth_code')
    expires_at = session.get('pending_auth_expires_at')
    if not expected_code or not expires_at:
        return False, "Your verification session expired. Please start again."
    if datetime.now(timezone.utc).timestamp() > expires_at:
        _clear_pending_auth()
        return False, "Your verification code expired. Please start again."
    if submitted_code != expected_code:
        return False, "That verification code is incorrect."
    return True, ""

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
    welcome_msg = None
    recent_notes = []
    if current_user.is_authenticated:
        welcome_msg = get_welcome_message(current_user.name)
        try: 
            result = db.session.execute(
                        db.select(Note).where(Note.in_bin != True).where(Note.user_id == current_user.id).order_by(Note.last_opened.desc())
                    ) 
            recent_notes = result.scalars().all()
        except Exception:
            recent_notes = []   
    return render_template('index.html', welcome_msg = welcome_msg, recent_notes = recent_notes[:5])

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
            content = form.content.data
            metadata = get_meta_data(content)
            note = Note(title=form.title.data, md_content=content,html_content = request.form.get('html_content') ,in_bin=False, user_id=current_user.id,meta_data=metadata)
            db.session.add(note)
            db.session.flush()
            if metadata != 'error':
                note.meta_data['id'] = note.id
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
            flash("Note not found.", "error")
            return redirect(url_for('notes'))
    except SQLAlchemyError:
        flash("Error pulling note transaction records.", "error")
        return redirect(url_for('notes'))

    form = EditNoteForm()
    if request.method == 'GET':
        form.content.data = note.md_content
        
    if form.validate_on_submit():
        try:
            if form.content.data != note.md_content:
                metadata = get_meta_data(form.content.data)
                if metadata != 'error':
                    metadata['id'] = note.id
                    note.meta_data = metadata
            note.md_content = form.content.data
            note.html_content = request.form.get('html_content')
            db.session.commit()
            flash("Changes saved successfully!", "success")
            return redirect(url_for('notes'))
        except SQLAlchemyError:
            db.session.rollback()
            flash("Could not update changes. Please check parameters.", "error")
            
    return render_template('edit_note.html', note=note, form=form)

@app.route('/move_to_bin/<int:note_id>',methods=['POST'])
@login_required
def move_to_bin(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            note.in_bin = True
            db.session.commit()
            return jsonify(['Note moved to bin','success'])
        else:
            return jsonify(["Note not found", "error"])
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(["Could not change note structural path status.", "error"])

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
            flash("Note not found", "error")
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
    if session.get('pending_register'):
        form = VerificationForm()
        if form.validate_on_submit():
            is_valid, message = _verification_is_valid(form.code.data.strip())
            if not is_valid:
                flash(message, "error")
                return render_template(
                    'register.html',
                    form=form,
                    show_code=True,
                    verification_email=session.get('pending_auth_email'),
                )
            pending_register = session.get('pending_register')
            try:
                user = User(
                    email=pending_register['email'],
                    name=pending_register['name'],
                    password=pending_register['password'],
                )
                db.session.add(user)
                db.session.commit()
                login_user(user)
                _clear_pending_auth()
                flash(f'Created new account for {user.name}', 'success')
                return redirect(url_for('notes'))
            except IntegrityError:
                db.session.rollback()
                _clear_pending_auth()
                flash("That email address is already registered.", "error")
            except SQLAlchemyError:
                db.session.rollback()
                flash("An unexpected error occurred. Please try again.", "error")
        return render_template(
            'register.html',
            form=form,
            show_code=True,
            verification_email=session.get('pending_auth_email'),
        )

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            _clear_pending_auth()
            existing_user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
            if existing_user:
                flash("That email address is already registered.", "error")
                return render_template('register.html', form=form, show_code=False)

            verification_code = create_code()
            session['pending_register'] = {
                'name': form.name.data,
                'email': form.email.data,
                'password': generate_password_hash(form.password.data, method='pbkdf2:sha256', salt_length=16),
            }
            session['pending_auth_code'] = verification_code
            session['pending_auth_expires_at'] = datetime.now(timezone.utc).timestamp() + VERIFICATION_TTL_SECONDS
            session['pending_auth_email'] = form.email.data
            send_email_threaded(
                form.email.data,
                "Your verification code",
                f"Type this 6 digit code to finish your account setup: {verification_code}",
            )
            flash(f'Type the 6 digit code sent to {form.email.data}.', 'success')
            return render_template(
                'register.html',
                form=VerificationForm(),
                show_code=True,
                verification_email=form.email.data,
            )
        except IntegrityError:
            db.session.rollback()
            flash("That email address is already registered.", "error")
        except SQLAlchemyError:
            db.session.rollback()
            flash("An unexpected error occurred. Please try again.", "error")
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET','POST'])
def login():
    #-----------FOR TESTING-------------------
    user=db.session.get(User,1)
    login_user(user)
    return redirect(url_for('home'))
    #-----------------------------------------------
    if session.get('pending_login'):
        form = VerificationForm()
        if form.validate_on_submit():
            is_valid, message = _verification_is_valid(form.code.data.strip())
            if not is_valid:
                flash(message, "error")
                return render_template(
                    'login.html',
                    form=form,
                    show_code=True,
                    verification_email=session.get('pending_auth_email'),
                )
            pending_login = session.get('pending_login')
            try:
                user = db.session.get(User, pending_login['user_id'])
                if not user:
                    _clear_pending_auth()
                    flash("Your account could not be found. Please login again.", "error")
                    return redirect(url_for('login'))
                login_user(user)
                _clear_pending_auth()
                flash(f'Welcome back {user.name}', 'success')
                return redirect(url_for('notes'))
            except SQLAlchemyError:
                flash("Internal database communication mismatch.", "error")
        return render_template(
            'login.html',
            form=form,
            show_code=True,
            verification_email=session.get('pending_auth_email'),
        )

    form = LoginForm()
    if form.validate_on_submit():
        try:
            _clear_pending_auth()
            user = db.session.execute(db.select(User).where(User.email == form.email.data)).scalar()
            if user and check_password_hash(user.password, form.password.data):
                verification_code = create_code()
                session['pending_login'] = {'user_id': user.id}
                session['pending_auth_code'] = verification_code
                session['pending_auth_expires_at'] = time.time() + VERIFICATION_TTL_SECONDS
                session['pending_auth_email'] = user.email
                send_email_threaded(
                    user.email,
                    "Your verification code",
                    f"Type this 6 digit code to finish your login: {verification_code}",
                )
                flash(f'Type the 6 digit code sent to {user.email}.', 'success')
                return render_template(
                    'login.html',
                    form=VerificationForm(),
                    show_code=True,
                    verification_email=user.email,
                )
            else:
                flash('Incorrect login credentials.', 'error')
        except SQLAlchemyError:
            flash("Internal database communication mismatch.", "error")
    return render_template('login.html', form=form, show_code=False)
    
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully', 'success')
    return redirect(url_for('home'))

@app.route('/search/<query>')
@login_required
def search(query):
    query = query.strip()
    if not query:
        return {"results": []}    
    try:
        result = db.session.execute(
            db.select(Note).where(Note.user_id == current_user.id).where(Note.title.contains(query))
        )
        notes = result.scalars().all()
        results = [{"id": note.id, "title": note.title} for note in notes]
        return {"results": results}
    except SQLAlchemyError:
        return {"results": []}

@app.route('/search-results/<query>')
@login_required
def search_results(query):
    query = query.strip()
    if not query:
        return render_template('search-results.html', query=query, notes=[])
    try:
        result = db.session.execute(
            db.select(Note).where(Note.user_id == current_user.id).where(Note.title.contains(query))
        )
        notes = result.scalars().all()
        return render_template('search-results.html', query=query, notes=notes)
    except SQLAlchemyError:
        return render_template('search-results.html', query=query, notes=[])

@app.route('/ai-chat')
@login_required
def ai_chat():
    return render_template('ai-chat.html')

@app.route('/ai-response', methods=['POST'])
@login_required
def ai_response():
    username = current_user.name
    data = request.get_json()
    message = data.get('contents')

    cooldown_until = session.get('note_action_cooldown_until')
    is_on_cooldown = cooldown_until and datetime.now(timezone.utc).timestamp() < cooldown_until

    all_instructions = ask_groq(contents=message, username=username, chat_only=is_on_cooldown)
    all_results = []
    all_get_notes = ''
    note_action_html_content = ''
    chat = None
    all_errors = []
    hit_rate_limit = False

    for instruction in all_instructions:
        action = instruction['action']
        ai_reply = instruction['content']

        if action == 'error':
            if isinstance(ai_reply, dict):
                all_errors.append(ai_reply.get('msg', 'An unexpected error occurred. Please try again later.'))
                if ai_reply.get('type') == 'rate_limit':
                    hit_rate_limit = True
            else:
                all_errors.append('NVLearn AI encountered an unexpected error. Please try again later.')

        elif action == 'chat':
            chat = ai_reply

        elif action == 'create_note':
            try:
                new_note = Note(
                    title=ai_reply['title'],
                    md_content=ai_reply['content'],
                    html_content=ai_reply['html_content'],
                    in_bin=False,
                    user_id=current_user.id,
                    meta_data=ai_reply['meta_data']
                )
                db.session.add(new_note)
                db.session.flush()
                new_note.meta_data['id'] = new_note.id
                db.session.commit()
                all_results.append(f"Made new note '{ai_reply['title']}'")
            except Exception:
                db.session.rollback()
                all_errors.append('An error occurred while saving the new note to the database. Please try again.')

        elif action == 'get_note':
            metadata_list = []
            notes = db.session.execute(
                db.select(Note).where(Note.in_bin != True).where(Note.user_id == current_user.id)
            ).scalars().all()
            for note in notes:
                if note.meta_data != 'error':
                    if 'error' not in note.meta_data['tags'] and 'is_invalid' not in note.meta_data['tags']:
                        metadata_list.append(note.meta_data)

            note_ids = ask_mistral(f"Instruction: {ai_reply} Metadata list: {metadata_list}")
            note_content_list = ""

            if is_ai_error(note_ids):
                all_errors.append(note_ids.get('msg', f'An error occurred while fetching notes on "{ai_reply}". Please try again later.'))
                if note_ids.get('type') == 'rate_limit':
                    hit_rate_limit = True
            else:
                if note_ids.get('note_ids'):
                    for note_id in note_ids['note_ids']:
                        note = db.session.get(Note, int(note_id))
                        if note:
                            note_content_list += (note.html_content or "") + '\n'
                else:
                    all_results.append(note_ids.get('msg', 'I could not find any relevant notes.'))
            all_get_notes += note_content_list

        elif action == 'note_action':
            metadata_list = []
            notes = db.session.execute(
                db.select(Note).where(Note.in_bin != True).where(Note.user_id == current_user.id)
            ).scalars().all()
            for note in notes:
                if note.meta_data != 'error':
                    if 'error' not in note.meta_data['tags'] and 'is_invalid' not in note.meta_data['tags']:
                        metadata_list.append(note.meta_data)

            note_ids = ask_mistral(f"Instruction: {ai_reply} Metadata list: {metadata_list}")
            note_content_list = ''

            if is_ai_error(note_ids):
                all_errors.append(note_ids.get('msg', 'An error occurred while searching for notes. Please try again later.'))
                if note_ids.get('type') == 'rate_limit':
                    hit_rate_limit = True
                continue
            else:
                if note_ids.get('note_ids'):
                    for note_id in note_ids['note_ids']:
                        note = db.session.get(Note, int(note_id))
                        if note:
                            note_content_list += (note.md_content or "") + '\n'
                else:
                    all_results.append(note_ids.get('msg', 'I could not find any relevant notes.'))
                    continue

            gemini_result = ask_gemini(action='note_action', question=f"Instructions:{ai_reply} content:{note_content_list}")
            if is_ai_error(gemini_result):
                all_errors.append(gemini_result.get('msg', 'An error occurred while processing notes. Please try again later.'))
                if gemini_result.get('type') == 'rate_limit':
                    hit_rate_limit = True
            else:
                response_html, md_response = gemini_result
                all_results.append({'reply': md_response})
                note_action_html_content += response_html + '\n'

    if hit_rate_limit:
        session['note_action_cooldown_until'] = (datetime.now(timezone.utc) + timedelta(seconds=NOTE_ACTION_COOLDOWN_SECONDS)).timestamp()
        cooldown_msg = 'Note-related features are temporarily paused due to high demand. You can still chat normally — note features will be back in about 5 minutes.'
        if cooldown_msg not in all_errors:
            all_errors.append(cooldown_msg)

    final_result = {'results': all_results, 'errors': all_errors, 'chat': chat}
    errors = len(all_errors)
    results = len(all_results)

    if results <= 1 and errors <= 1 and not chat:
        if results == 1 and errors == 0 and all_get_notes == '':
            return jsonify({'chat': all_results[0]})
        elif results == 0 and errors == 1 and all_get_notes == '':
            return jsonify({'chat': all_errors[0]})
        elif results == 0 and errors == 0 and all_get_notes != '':
            return jsonify({'chat': all_get_notes})
    if results == 0 and errors == 0 and chat:
        return jsonify({'chat': chat})

    final_summary = ask_gemini(question=final_result, action='summarize')
    if is_ai_error(final_summary):
        final_summary = chat or 'An error occurred while executing your task. Please try again.'
    output = {'chat': md_to_html(final_summary), 'notes': all_get_notes, 'note_action': note_action_html_content}
    return jsonify(output)



@app.route('/read_note/<int:note_id>')
@login_required
def read_note(note_id):
    try:
        note = db.session.get(Note,note_id)
        note.last_opened = datetime.now(timezone.utc)
        db.session.commit()
        if not note or note.user_id != current_user.id:
            abort(404)
    except SQLAlchemyError:
        abort(404)
    return render_template('read_note.html',note=note)

@app.route('/about')
def about():
    return render_template('about.html')

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

if __name__ == "__main__":
    app.run(debug=True)
