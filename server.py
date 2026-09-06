from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    abort,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, String, Integer, Text, Boolean, JSON, DateTime, Float
from forms import AddNoteForm, EditNoteForm, LoginForm, RegisterForm, VerificationForm
from flask_login import (
    UserMixin,
    login_user,
    LoginManager,
    login_required,
    logout_user,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from helpers import (
    send_email_threaded,
    create_code,
    build_ai_instructions,
    ask_gemini,
    get_welcome_message,
    md_to_html,
    is_ai_error,
)
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
import json
import re
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from collections import Counter
from vector_store import (
    upsert_note_vector,
    delete_note_vector,
    search_notes_vector,
    sync_notes_to_chroma,
)

import os


class Base(DeclarativeBase):
    pass


app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # Ensure styling updates properly
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///notes.db"
app.config["SECRET_KEY"] = os.urandom(24)
VERIFICATION_TTL_SECONDS = 10 * 60
NOTE_ACTION_COOLDOWN_SECONDS = 5 * 60

# ── Logging Configuration ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Set Flask's built-in logger to DEBUG so all app.logger calls show up
app.logger.setLevel(logging.DEBUG)
app.logger.info("Flask application initialized — logging is active.")

db = SQLAlchemy(app, model_class=Base)

scheduler = BackgroundScheduler()

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "error"


class Note(db.Model):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    md_content: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    in_bin: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    meta_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    last_opened: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(1000), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    notes = relationship("Note", backref="author", lazy=True)


class Flashcard(db.Model):
    __tablename__ = "flashcards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    is_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )


class Quiz(db.Model):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    is_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incorrect_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    percentage_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tags: Mapped[List[str]] = mapped_column(JSON, nullable=True, default=list)


def get_meta_data(content):
    metadata = build_ai_instructions(content, username="", metadata=True)
    return metadata


def normalize_metadata(metadata, note_id=None):
    """Create note metadata and fill in missing or invalid fields if any.
    Makes metadata error tagged if any errors"""
    if isinstance(metadata, dict):
        normalized = dict(metadata)
    else:
        normalized = {
            "tags": ["error"],
            "summary": "Metadata could not be generated for this note.",
            "is_invalid": True,
        }
    tags = normalized.get("tags")
    if not isinstance(tags, list):
        normalized["tags"] = []
    if not isinstance(normalized.get("summary"), str):
        normalized["summary"] = ""
    if note_id is not None:
        normalized["id"] = note_id
    return normalized


def metadata_needs_ai(metadata):
    """Checks if metadata needs to be generated by ai"""
    if not isinstance(metadata, dict):
        return True
    tags = metadata.get("tags", [])
    return metadata.get("is_invalid") is True or "error" in tags


def extract_topic_for_search(instruction: str) -> str:
    """Extracts the semantic topic from an instruction string for vector search."""
    text = (instruction or "").strip()
    # Strip common leading operation phrases like 'summarize the note on/about', etc.
    cleaned = re.sub(
        r"^(summarize|explain|extract key points from|extract formulas from|rewrite|simplify|notes? on|notes? about)\s*(the\s*)?(notes?\s*)?(on|about|for|from)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned if cleaned else text


def get_vector_matched_notes(topic: str, user_id: int, edit_mode: bool = False):
    """Return active user notes matched by vector search."""
    if edit_mode:
        vector_res = search_notes_vector(topic=topic, user_id=user_id,n_results=1)
    else:
        vector_res = search_notes_vector(topic=topic, user_id=user_id)
    if is_ai_error(vector_res):
        return [], vector_res.get("msg"), True

    notes = []
    for note_id in vector_res.get("note_ids", []):
        try:
            note = db.session.get(Note, int(note_id))
        except (TypeError, ValueError):
            continue
        if note and note.user_id == user_id and not note.in_bin:
            notes.append(note)
    return notes, vector_res.get("msg"), False


MAX_CONTENT_CHAR_LIMIT = 8000


def get_notes_for_action(topic: str, user_id: int):
    """
    Returns (notes_list, error_msg, is_error).
    If topic is 'all_notes' or search_topic clean text equals 'all notes',
    fetches ALL non-binned notes for the user.
    Otherwise, uses ChromaDB vector search.
    """
    clean_topic = (topic or "").strip().lower()
    if clean_topic in ("all_notes", "all notes"):
        all_notes = db.session.scalars(
            db.select(Note).where(Note.user_id == user_id).where(Note.in_bin != True)
        ).all()
        if not all_notes:
            return [], "You do not have any notes saved yet.", False
        return all_notes, None, False

    return get_vector_matched_notes(topic, user_id)


def chunk_notes_content(notes: list, char_limit: int = MAX_CONTENT_CHAR_LIMIT):
    """
    Splits a list of Note objects into text batches, each guaranteed to be
    under char_limit characters.
    """
    batches = []
    current_batch = ""

    for note in notes:
        content = (note.md_content or "").strip()
        if not content:
            continue

        # If a single note exceeds char_limit, split it by paragraphs
        if len(content) > char_limit:
            if current_batch:
                batches.append(current_batch)
                current_batch = ""
            paragraphs = content.split("\n\n")
            for para in paragraphs:
                if len(current_batch) + len(para) + 2 > char_limit and current_batch:
                    batches.append(current_batch)
                    current_batch = para
                else:
                    current_batch = (current_batch + "\n\n" + para).strip()
        else:
            if len(current_batch) + len(content) + 2 > char_limit and current_batch:
                batches.append(current_batch)
                current_batch = content
            else:
                current_batch = (current_batch + "\n\n" + content).strip()

    if current_batch:
        batches.append(current_batch)

    return batches


def summarize_notes_in_batches(batches: list):
    """
    Summarizes content batches iteratively into accumulated_summary.
    Returns: (accumulated_summary, hit_rate_limit, error_dict)
    """
    accumulated_summary = ""
    for i, batch in enumerate(batches):
        prompt = f"Batch {i + 1} content:\n{batch}"
        if accumulated_summary:
            prompt = f"Previous accumulated summary:\n{accumulated_summary}\n\n" + prompt

        result = ask_gemini(action="batch_summary", question=prompt)
        if is_ai_error(result):
            hit_rl = result.get("type") == "rate_limit"
            return accumulated_summary, hit_rl, result
        accumulated_summary = result

    return accumulated_summary, False, None



def backfill_metadata_ids():
    """Sets metadata['id'] if not already set."""
    notes = db.session.scalars(db.select(Note)).all()
    changed = False
    for note in notes:
        if isinstance(note.meta_data, dict) and note.meta_data.get("id") != note.id:
            note.meta_data = normalize_metadata(note.meta_data, note.id)
            changed = True
    if changed:
        db.session.commit()
        app.logger.info(
            "Backfilled metadata IDs for notes with missing or mismatched IDs."
        )


def generate_meta_data():
    """Generates meta data for notes with error notes or missing ids"""
    try:
        with app.app_context():
            notes = db.session.scalars(db.select(Note).order_by(Note.id.desc())).all()
            for note in notes:
                if (
                    isinstance(note.meta_data, dict)
                    and note.meta_data.get("id") != note.id
                ):
                    note.meta_data = normalize_metadata(note.meta_data, note.id)
            db.session.commit()
            # Select the first note which needs proper metadata
            note = next((n for n in notes if metadata_needs_ai(n.meta_data)), None)
            if not note:
                return

            metadata = get_meta_data(note.md_content)
            if metadata == "error":
                app.logger.warning(
                    "Metadata generation returned 'error' for note_id=%s. Skipping.",
                    note.id,
                )
                return
            note.meta_data = normalize_metadata(metadata, note.id)
            db.session.commit()
            app.logger.info("Successfully generated metadata for note_id=%s.", note.id)
    except Exception:
        app.logger.exception(
            "Unhandled exception in generate_meta_data background job."
        )
        return


def _clear_pending_auth():
    session.pop("pending_register", None)
    session.pop("pending_login", None)
    session.pop("pending_auth_code", None)
    session.pop("pending_auth_expires_at", None)
    session.pop("pending_auth_email", None)


def _verification_is_valid(submitted_code):
    """Checks if email verification code is correct"""
    expected_code = session.get("pending_auth_code")
    expires_at = session.get("pending_auth_expires_at")
    if not expected_code or not expires_at:
        return False, "Your verification session expired. Please start again."
    if datetime.now(timezone.utc).timestamp() > expires_at:
        _clear_pending_auth()
        return False, "Your verification code expired. Please start again."
    if submitted_code != expected_code:
        return False, "That verification code is incorrect."
    return True, ""


def delete_flashcards():
    """Delete the single oldest unsaved flashcard"""
    try:
        with app.app_context():
            oldest_flashcard = db.session.scalars(
                db.select(Flashcard)
                .where(Flashcard.is_saved == False)
                .order_by(Flashcard.id.asc())
            ).first()
            if oldest_flashcard:
                db.session.delete(oldest_flashcard)
                db.session.commit()
                app.logger.info(
                    "Successfully deleted oldest unsaved flashcard (id=%s).",
                    oldest_flashcard.id,
                )
    except Exception as e:
        app.logger.error("Failed to delete flashcard in background job: %s", e)
        db.session.rollback()


def delete_quizzes():
    """Delete the single oldest unsaved quiz every 10 minutes"""
    try:
        with app.app_context():
            oldest_quiz = db.session.scalars(
                db.select(Quiz).where(Quiz.is_saved == False).order_by(Quiz.id.asc())
            ).first()
            if oldest_quiz:
                db.session.delete(oldest_quiz)
                db.session.commit()
                app.logger.info(
                    "Successfully deleted oldest unsaved quiz (id=%s).", oldest_quiz.id
                )
    except Exception as e:
        app.logger.error("Failed to delete quiz in background job: %s", e)
        db.session.rollback()


# Add the background job of generating metadata
scheduler.add_job(
    generate_meta_data, "interval", minutes=10, max_instances=1, coalesce=True
)

# Add background job of deleting unsaved flashcards
scheduler.add_job(
    delete_flashcards, "interval", minutes=10, max_instances=1, coalesce=True
)

# Add background job of deleting quizzes
scheduler.add_job(
    delete_quizzes, "interval", minutes=10, max_instances=1, coalesce=True
)

with app.app_context():
    db.create_all()
    app.logger.info("Database tables created / verified.")
    try:
        with db.engine.connect() as conn:
            conn.execute(
                db.text(
                    "ALTER TABLE flashcards ADD COLUMN user_id INTEGER REFERENCES users(id)"
                )
            )
            conn.commit()
            app.logger.info("Added user_id column to flashcards table.")
    except Exception:
        app.logger.debug(
            "user_id column already exists in flashcards table (migration skipped)."
        )
    backfill_metadata_ids()
    sync_notes_to_chroma(db.session, Note)
scheduler.start()  # Start the background process
app.logger.info("Background scheduler started.")


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (SQLAlchemyError, ValueError) as e:
        app.logger.error("Failed to load user_id=%s: %s", user_id, e)
        return None


@app.route("/")
def home():
    welcome_msg = None
    recent_notes = []
    if current_user.is_authenticated:
        welcome_msg = get_welcome_message(current_user.name)
        try:
            result = db.session.execute(
                db.select(Note)
                .where(Note.in_bin != True)
                .where(Note.user_id == current_user.id)
                .order_by(Note.last_opened.desc())
            )
            recent_notes = result.scalars().all()
        except Exception as e:
            app.logger.error(
                "[home] Failed to fetch recent notes for user_id=%s: %s",
                current_user.id,
                e,
            )
            recent_notes = []
    return render_template(
        "index.html", welcome_msg=welcome_msg, recent_notes=recent_notes[:5]
    )


@app.route("/notes")
@login_required
def notes():
    try:
        result = db.session.execute(
            db.select(Note)
            .where(Note.in_bin != True)
            .where(Note.user_id == current_user.id)
        )
        notes = result.scalars().all()
    except SQLAlchemyError as e:
        app.logger.error(
            "[notes] DB error fetching notes for user_id=%s: %s", current_user.id, e
        )
        flash("An error occurred while fetching your notes. Please retry.", "error")
        notes = []
    return render_template("notes.html", notes=notes)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_note():
    form = AddNoteForm()
    if form.validate_on_submit():
        try:
            content = form.content.data
            metadata = get_meta_data(content)
            note = Note(
                title=form.title.data,
                md_content=content,
                html_content=request.form.get("html_content"),
                in_bin=False,
                user_id=current_user.id,
                meta_data=normalize_metadata(metadata),
            )
            db.session.add(note)
            db.session.flush()
            note.meta_data = normalize_metadata(metadata, note.id)
            db.session.commit()
            upsert_note_vector(note)
            flash("Note created successfully", "success")
            return redirect(url_for("notes"))
        except SQLAlchemyError as e:
            db.session.rollback()
            app.logger.error(
                "[add_note] DB error creating note for user_id=%s: %s",
                current_user.id,
                e,
            )
            flash("Failed to create note due to a database error. Try again.", "error")
    return render_template("add_note.html", form=form)


@app.route("/edit/<int:note_id>", methods=["GET", "POST"])
@login_required
def edit_note(note_id):
    try:
        note = db.session.get(Note, note_id)
        if not note or note.user_id != current_user.id:
            app.logger.warning(
                "[edit_note] Note not found or unauthorized — note_id=%s, user_id=%s",
                note_id,
                current_user.id,
            )
            flash("Note not found.", "error")
            return redirect(url_for("notes"))
    except SQLAlchemyError as e:
        app.logger.error(
            "[edit_note] DB error fetching note_id=%s for user_id=%s: %s",
            note_id,
            current_user.id,
            e,
        )
        flash("Error pulling note transaction records.", "error")
        return redirect(url_for("notes"))

    form = EditNoteForm()
    if request.method == "GET":
        form.content.data = note.md_content
        content = note.md_content or ""
        if re.search(
            r"(\$\$.*?\$\$|\$.*?\$|\\\(.*?\\\)|\\\[.*?\\\]|\\frac|\\sqrt|\\sum|\\int|\\begin|\\alpha|\\beta|\\theta)",
            content,
            re.DOTALL,
        ):
            flash(
                "This note contains mathematical formulas (LaTeX). Switch to Read Mode for the best rendering experience!",
                "info",
            )

    if form.validate_on_submit():
        try:
            if (
                form.content.data != note.md_content
            ):  # Check if user editted note content
                metadata = get_meta_data(form.content.data)
                note.meta_data = normalize_metadata(metadata, note.id)
            note.md_content = form.content.data
            note.html_content = request.form.get("html_content")
            db.session.commit()
            upsert_note_vector(note)
            flash("Changes saved successfully!", "success")
            return redirect(url_for("notes"))
        except SQLAlchemyError as e:
            db.session.rollback()
            app.logger.error(
                "[edit_note] DB error updating note_id=%s for user_id=%s: %s",
                note_id,
                current_user.id,
                e,
            )
            flash("Could not update changes. Please check parameters.", "error")

    return render_template("edit_note.html", note=note, form=form)


@app.route("/move_to_bin/<int:note_id>", methods=["POST"])
@login_required
def move_to_bin(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            note.in_bin = True
            db.session.commit()
            delete_note_vector(note.id, note.user_id)
            return jsonify(["Note moved to bin", "success"])
        else:
            app.logger.warning(
                "[move_to_bin] Note not found or unauthorized — note_id=%s, user_id=%s",
                note_id,
                current_user.id,
            )
            return jsonify(["Note not found", "error"])
    except SQLAlchemyError as e:
        db.session.rollback()
        app.logger.error(
            "[move_to_bin] DB error for note_id=%s, user_id=%s: %s",
            note_id,
            current_user.id,
            e,
        )
        return jsonify(["Could not move note to bin", "error"])


@app.route("/note-bin")
@login_required
def note_bin():
    try:
        result = db.session.execute(
            db.select(Note)
            .where(Note.in_bin == True)
            .where(Note.user_id == current_user.id)
        )
        notes = result.scalars().all()
    except SQLAlchemyError as e:
        app.logger.error(
            "[note_bin] DB error fetching binned notes for user_id=%s: %s",
            current_user.id,
            e,
        )
        flash("Error checking database trash allocations.", "error")
        notes = []
    return render_template("bin.html", notes=notes)


@app.route("/delete/<int:note_id>", methods=["POST"])
@login_required
def delete(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            user_id = note.user_id
            db.session.delete(note)
            db.session.commit()
            delete_note_vector(note_id, user_id)
            return jsonify(["Note permanently deleted", "success"])
        else:
            app.logger.warning(
                "[delete] Note not found or unauthorized — note_id=%s, user_id=%s",
                note_id,
                current_user.id,
            )
            return jsonify(["Note not found", "error"])
    except SQLAlchemyError as e:
        db.session.rollback()
        app.logger.error(
            "[delete] DB error permanently deleting note_id=%s for user_id=%s: %s",
            note_id,
            current_user.id,
            e,
        )
        return jsonify(["Failed to delete note", "error"])


@app.route("/restore/<int:note_id>", methods=["POST"])
@login_required
def restore(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            note.in_bin = False
            db.session.commit()
            upsert_note_vector(note)
            return jsonify(["Note restored", "success"])
        else:
            app.logger.warning(
                "[restore] Note not found or unauthorized — note_id=%s, user_id=%s",
                note_id,
                current_user.id,
            )
            return jsonify(["Note not found.", "error"])
    except SQLAlchemyError as e:
        db.session.rollback()
        app.logger.error(
            "[restore] DB error restoring note_id=%s for user_id=%s: %s",
            note_id,
            current_user.id,
            e,
        )
        return jsonify(["Failed to restore note.", "error"])


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("pending_register"):
        form = VerificationForm()
        if form.validate_on_submit():
            is_valid, message = _verification_is_valid(form.code.data.strip())
            if not is_valid:
                flash(message, "error")
                return render_template(
                    "register.html",
                    form=form,
                    show_code=True,
                    verification_email=session.get("pending_auth_email"),
                )
            pending_register = session.get("pending_register")
            try:
                user = User(
                    email=pending_register["email"],
                    name=pending_register["name"],
                    password=pending_register["password"],
                )
                db.session.add(user)
                db.session.commit()
                login_user(user)
                _clear_pending_auth()
                flash(f"Created new account for {user.name}", "success")
                return redirect(url_for("notes"))
            except IntegrityError as e:
                db.session.rollback()
                _clear_pending_auth()
                app.logger.warning(
                    "[register] Duplicate email on verification commit: %s", e
                )
                flash("That email address is already registered.", "error")
            except SQLAlchemyError as e:
                db.session.rollback()
                app.logger.error("[register] DB error creating user account: %s", e)
                flash("An unexpected error occurred. Please try again.", "error")
        return render_template(
            "register.html",
            form=form,
            show_code=True,
            verification_email=session.get("pending_auth_email"),
        )

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            _clear_pending_auth()
            existing_user = db.session.execute(
                db.select(User).where(User.email == form.email.data)
            ).scalar()
            if existing_user:
                flash("That email address is already registered.", "error")
                return render_template("register.html", form=form, show_code=False)

            verification_code = create_code()
            # Store the pending register details
            session["pending_register"] = {
                "name": form.name.data,
                "email": form.email.data,
                "password": generate_password_hash(
                    form.password.data, method="pbkdf2:sha256", salt_length=16
                ),
            }
            session["pending_auth_code"] = verification_code
            session["pending_auth_expires_at"] = (
                datetime.now(timezone.utc).timestamp() + VERIFICATION_TTL_SECONDS
            )
            session["pending_auth_email"] = form.email.data
            if not send_email_threaded(
                form.email.data,
                "Your verification code",
                f"Type this 6 digit code to finish your account setup: {verification_code}",
            ):
                raise RuntimeError("Failed to send verification email.")

            flash(f"Type the 6 digit code sent to {form.email.data}.", "success")
            return render_template(
                "register.html",
                form=VerificationForm(),
                show_code=True,
                verification_email=form.email.data,
            )
        except IntegrityError as e:
            db.session.rollback()
            app.logger.warning("[register] Duplicate email during registration: %s", e)
            flash("That email address is already registered.", "error")
        except SQLAlchemyError as e:
            db.session.rollback()
            app.logger.error("[register] DB error during registration flow: %s", e)
            flash("An unexpected error occurred. Please try again.", "error")
        except Exception as e:
            db.session.rollback()
            app.logger.exception(
                "[register] Unexpected error during registration (email send or other): %s",
                e,
            )
            flash("Failed to send email. Try to register again.", "error")
    return render_template("register.html", form=form)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("pending_login"):
        form = VerificationForm()
        if form.validate_on_submit():
            is_valid, message = _verification_is_valid(form.code.data.strip())
            if not is_valid:
                flash(message, "error")
                return render_template(
                    "login.html",
                    form=form,
                    show_code=True,
                    verification_email=session.get("pending_auth_email"),
                )
            pending_login = session.get("pending_login")
            try:
                user = db.session.get(User, pending_login["user_id"])
                if not user:
                    _clear_pending_auth()
                    flash(
                        "Your account could not be found. Please login again.", "error"
                    )
                    return redirect(url_for("login"))
                login_user(user)
                _clear_pending_auth()
                flash(f"Welcome back {user.name}", "success")
                return redirect(url_for("notes"))
            except SQLAlchemyError as e:
                app.logger.error(
                    "[login] DB error during login verification for user_id=%s: %s",
                    pending_login.get("user_id"),
                    e,
                )
                flash("Internal database communication mismatch.", "error")
        return render_template(
            "login.html",
            form=form,
            show_code=True,
            verification_email=session.get("pending_auth_email"),
        )

    form = LoginForm()
    if form.validate_on_submit():
        try:
            _clear_pending_auth()
            user = db.session.execute(
                db.select(User).where(User.email == form.email.data)
            ).scalar()
            if user and check_password_hash(user.password, form.password.data):
                verification_code = create_code()
                session["pending_login"] = {"user_id": user.id}
                session["pending_auth_code"] = verification_code
                session["pending_auth_expires_at"] = (
                    datetime.now(timezone.utc).timestamp() + VERIFICATION_TTL_SECONDS
                )
                session["pending_auth_email"] = user.email
                send_email_threaded(
                    user.email,
                    "Your verification code",
                    f"Type this 6 digit code to finish your login: {verification_code}",
                )
                flash(f"Type the 6 digit code sent to {user.email}.", "success")
                return render_template(
                    "login.html",
                    form=VerificationForm(),
                    show_code=True,
                    verification_email=user.email,
                )
            else:
                flash("Incorrect login credentials.", "error")
        except SQLAlchemyError as e:
            app.logger.error(
                "[login] DB error during login for email=%s: %s", form.email.data, e
            )
            flash("Internal database communication mismatch.", "error")
    return render_template("login.html", form=form, show_code=False)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    try:
        logout_user()
        app.logger.info("[logout] User logged out successfully.")
        return jsonify(["Logged out successfully", "success"])
    except Exception as e:
        app.logger.error("[logout] Logout failed: %s", e)
        return jsonify(["Logout failed", "error"])


@app.route("/search/<query>")
@login_required
def search(query):
    query = query.strip()
    if not query:
        return {"results": []}
    try:
        result = db.session.execute(
            db.select(Note)
            .where(Note.user_id == current_user.id)
            .where(Note.title.contains(query))
        )
        notes = result.scalars().all()
        results = [{"id": note.id, "title": note.title} for note in notes]
        return jsonify({"results": results})
    except SQLAlchemyError as e:
        app.logger.error(
            "[search] DB error searching notes for user_id=%s, query='%s': %s",
            current_user.id,
            query,
            e,
        )
        return jsonify({"results": []})


@app.route("/search-results/<query>")
@login_required
def search_results(query):
    query = query.strip()
    if not query:
        return render_template("search-results.html", query=query, notes=[])
    try:
        result = db.session.execute(
            db.select(Note)
            .where(Note.user_id == current_user.id)
            .where(Note.title.contains(query))
        )
        notes = result.scalars().all()
        return render_template("search-results.html", query=query, notes=notes)
    except SQLAlchemyError as e:
        app.logger.error(
            "[search_results] DB error for user_id=%s, query='%s': %s",
            current_user.id,
            query,
            e,
        )
        return render_template("search-results.html", query=query, notes=[])


@app.route("/ai-chat")
@login_required
def ai_chat():
    welcome_message = get_welcome_message(current_user.name)
    return render_template("ai-chat.html", welcome_message=welcome_message)


@app.route("/ai-response", methods=["POST"])
@login_required
def ai_response():
    username = current_user.name
    data = request.get_json()
    message = data.get("contents")

    cooldown_until = session.get("note_action_cooldown_until")
    is_on_cooldown = (
        cooldown_until and datetime.now(timezone.utc).timestamp() < cooldown_until
    )

    all_instructions = build_ai_instructions(
        contents=message, username=username, chat_only=is_on_cooldown
    )
    app.logger.info(
        "[ai_response] Instructions built for user_id=%s: %s", current_user.id, all_instructions)
    all_results = []
    all_get_notes = ""
    note_action_html_content = ""
    flashcard_id = None
    quiz_id = None
    chat = None
    all_errors = []
    hit_rate_limit = False

    for instruction in all_instructions:
        action = instruction["action"]
        ai_reply = instruction["content"]

        if action == "error":
            if isinstance(ai_reply, dict):
                app.logger.error(
                    "[ai_response] AI error (type=%s): %s",
                    ai_reply.get("type"),
                    ai_reply.get("msg"),
                )
                all_errors.append(
                    ai_reply.get(
                        "msg", "An unexpected error occurred. Please try again later."
                    )
                )
                if ai_reply.get("type") == "rate_limit":
                    hit_rate_limit = True
            else:
                app.logger.error(
                    "[ai_response] AI returned unexpected non-dict error: %s", ai_reply
                )
                all_errors.append(
                    "NVLearn AI encountered an unexpected error. Please try again later."
                )

        elif action == "chat":
            chat = ai_reply

        elif action == "create_note":
            try:
                new_note = Note(
                    title=ai_reply["title"],
                    md_content=ai_reply["content"],
                    html_content=ai_reply["html_content"],
                    in_bin=False,
                    user_id=current_user.id,
                    meta_data=normalize_metadata(ai_reply.get("meta_data")),
                )
                db.session.add(new_note)
                db.session.flush()
                new_note.meta_data = normalize_metadata(new_note.meta_data, new_note.id)
                db.session.commit()
                upsert_note_vector(new_note)
                all_results.append(f"Made new note '{ai_reply['title']}'")
            except Exception as e:
                db.session.rollback()
                app.logger.error(
                    "[ai_response/create_note] DB error saving AI-created note for user_id=%s: %s",
                    current_user.id,
                    e,
                )
                all_errors.append(
                    "An error occurred while saving the new note to the database. Please try again."
                )

        elif action == "get_note":
            if ai_reply == "all_notes":
                try:
                    result = db.session.execute(
                        db.select(Note)
                        .where(Note.user_id == current_user.id)
                        .where(Note.in_bin != True)
                    )
                    matched_notes = result.scalars().all()
                    note_content_list = ""
                    for note in matched_notes:
                        note_content_list += (note.html_content or "") + "\n"
                    all_get_notes += note_content_list
                except SQLAlchemyError as e:
                    app.logger.error(
                        "[ai_response/get_note] DB error fetching all notes for user_id=%s: %s",
                        current_user.id,
                        e,
                    )
                    all_errors.append(
                        "An error occurred while fetching your notes. Please try again later."
                    )
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_vector_matched_notes(
                search_topic, current_user.id
            )
            note_content_list = ""

            if vector_error:
                app.logger.error(
                    "[ai_response/get_note] Vector search error: %s",
                    vector_msg,
                )
                all_errors.append(
                    vector_msg
                    or "An error occurred while fetching notes. Please try again later."
                )
            else:
                if matched_notes:
                    for note in matched_notes:
                        note_content_list += (note.html_content or "") + "\n"
                else:
                    all_results.append(
                        vector_msg or f"I could not find your notes about {search_topic}."
                    )
            all_get_notes += note_content_list

        elif action == "note_action":
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_notes_for_action(
                search_topic, current_user.id
            )

            if vector_error:
                app.logger.error(
                    "[ai_response/note_action] Note retrieval error: %s",
                    vector_msg,
                )
                all_errors.append(
                    vector_msg
                    or "An error occurred while searching for notes. Please try again later."
                )
                continue

            if not matched_notes:
                all_results.append(
                    vector_msg or f"I could not find your notes about {search_topic}."
                )
                continue

            batches = chunk_notes_content(matched_notes)
            if len(batches) > 1:
                accumulated_summary, hit_rl, err_dict = summarize_notes_in_batches(batches)
                if accumulated_summary:
                    note_action_html_content += md_to_html(accumulated_summary) + "\n"
                if hit_rl:
                    hit_rate_limit = True
                    all_errors.append("Rate limit reached during batch processing. Partial summary returned.")
                elif err_dict:
                    all_errors.append(err_dict.get("msg", "An error occurred during note processing."))
            else:
                note_content_list = batches[0] if batches else ""
                gemini_result = ask_gemini(
                    action="note_action",
                    question=f"Instructions:{ai_reply} content:{note_content_list}",
                )
                if is_ai_error(gemini_result):
                    app.logger.error(
                        "[ai_response/note_action] Gemini error (type=%s): %s",
                        gemini_result.get("type"),
                        gemini_result.get("msg"),
                    )
                    all_errors.append(
                        gemini_result.get(
                            "msg",
                            "An error occurred while processing notes. Please try again later.",
                        )
                    )
                    if gemini_result.get("type") == "rate_limit":
                        hit_rate_limit = True
                else:
                    response_html, _ = gemini_result
                    note_action_html_content += response_html + "\n"

        elif action == 'edit_note':
            
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_notes_for_action(
                search_topic, current_user.id, edit_mode=True
            )            
            matched_note = matched_notes[0] if matched_notes else None

            if vector_error:
                app.logger.error(
                    "[ai_response/note_action] Note retrieval error: %s",
                    vector_msg,
                )
                all_errors.append(
                    vector_msg
                    or "An error occurred while searching for notes. Please try again later."
                )
                continue

            if not matched_note:
                all_results.append(
                    vector_msg or f"I could not find your notes about {search_topic}."
                )
                continue
            if matched_note:
                edited_note = ask_gemini(
                    action="edit_note",
                    question=f"Instruction: {ai_reply} note: {matched_note.content}"
                )
                if is_ai_error(edited_note):
                    app.logger.error(
                        "[ai_response/edit_note] Gemini error (type=%s): %s",
                        edited_note.get("type"),
                        edited_note.get("msg"),
                    )
                    all_errors.append(
                        edited_note.get(
                            "msg",
                            "An error occurred while editing the note. Please try again later.",
                        )
                    )
                    if edited_note.get("type") == "rate_limit":
                        hit_rate_limit = True
                else:
                    try:
                        matched_note.md_content = edited_note
                        matched_note.html_content = md_to_html(edited_note)
                        db.session.commit()
                        upsert_note_vector(matched_note)
                        all_results.append(f"Edited note '{matched_note.title}'")
                    except SQLAlchemyError as e:
                        db.session.rollback()
                        app.logger.error(
                            "[ai_response/edit_note] DB error updating note_id=%s for user_id=%s: %s",
                            matched_note.id,
                            current_user.id,
                            e,
                        )
                        all_errors.append(
                            "An error occurred while saving the edited note to the database. Please try again."
                        )
        elif action == "create_flashcards":
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_notes_for_action(
                search_topic, current_user.id
            )
            note_content_list = ""

            if vector_error:
                app.logger.warning(
                    "[ai_response/create_flashcards] Note search failed, falling back to topic. msg=%s",
                    vector_msg,
                )
                note_content_list = f"Topic: {ai_reply}"
            else:
                if matched_notes:
                    batches = chunk_notes_content(matched_notes)
                    if len(batches) > 1:
                        accumulated_summary, hit_rl, err_dict = summarize_notes_in_batches(batches)
                        if hit_rl or err_dict or not accumulated_summary:
                            if hit_rl:
                                hit_rate_limit = True
                            all_errors.append(
                                "AI service is busy or rate limited. Please avoid using note-related actions for a while."
                            )
                            continue
                        note_content_list = accumulated_summary
                    else:
                        note_content_list = batches[0] if batches else f"Topic: {ai_reply}"
                else:
                    note_content_list = f"Topic: {ai_reply}"

            gemini_result = ask_gemini(
                action="create_flashcards", question=note_content_list
            )
            if is_ai_error(gemini_result):
                app.logger.error(
                    "[ai_response/create_flashcards] Gemini flashcard generation failed (type=%s): %s",
                    gemini_result.get("type"),
                    gemini_result.get("msg"),
                )
                all_errors.append(
                    gemini_result.get(
                        "msg",
                        "An error occurred while processing notes. Flashcard could not be created. Please try again later.",
                    )
                )
                if gemini_result.get("type") == "rate_limit":
                    hit_rate_limit = True
            else:
                flashcard = Flashcard(card_data=gemini_result, user_id=current_user.id)
                db.session.add(flashcard)
                db.session.commit()
                flashcard_id = flashcard.id
                all_results.append(f"Created flashcards on topic: {ai_reply}")

        elif action == "create_quiz":
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_notes_for_action(
                search_topic, current_user.id
            )
            note_content_list = ""
            collected_tags = []

            if vector_error:
                app.logger.warning(
                    "[ai_response/create_quiz] Note search failed, falling back to topic. msg=%s",
                    vector_msg,
                )
                note_content_list = f"Topic: {ai_reply}"
            else:
                if matched_notes:
                    for note in matched_notes:
                        if isinstance(note.meta_data, dict):
                            collected_tags.extend(note.meta_data.get("tags", []))
                    batches = chunk_notes_content(matched_notes)
                    if len(batches) > 1:
                        accumulated_summary, hit_rl, err_dict = summarize_notes_in_batches(batches)
                        if hit_rl or err_dict or not accumulated_summary:
                            if hit_rl:
                                hit_rate_limit = True
                            all_errors.append(
                                "AI service is busy or rate limited. Please avoid using note-related actions for a while."
                            )
                            continue
                        note_content_list = accumulated_summary
                    else:
                        note_content_list = batches[0] if batches else f"Topic: {ai_reply}"
                else:
                    note_content_list = f"Topic: {ai_reply}"

            gemini_result = ask_gemini(action="create_quiz", question=note_content_list)
            if is_ai_error(gemini_result):
                app.logger.error(
                    "[ai_response/create_quiz] Gemini quiz generation failed (type=%s): %s",
                    gemini_result.get("type"),
                    gemini_result.get("msg"),
                )
                all_errors.append(
                    gemini_result.get(
                        "msg",
                        "An error occurred while processing notes. Quiz could not be created. Please try again later.",
                    )
                )
                if gemini_result.get("type") == "rate_limit":
                    hit_rate_limit = True
            else:
                if collected_tags:
                    tag_counts = Counter(collected_tags)
                    quiz_tags = [tag for tag, count in tag_counts.most_common(5)]
                else:
                    quiz_tags = [ai_reply.strip()]

                quiz_obj = Quiz(
                    quiz_data=gemini_result, user_id=current_user.id, tags=quiz_tags
                )
                db.session.add(quiz_obj)
                db.session.commit()
                quiz_id = quiz_obj.id
                all_results.append(f"Created quiz on topic: {ai_reply}")

    if hit_rate_limit:
        session["note_action_cooldown_until"] = (
            datetime.now(timezone.utc) + timedelta(seconds=NOTE_ACTION_COOLDOWN_SECONDS)
        ).timestamp()
        cooldown_msg = "Note-related features are temporarily paused due to high demand. You can still chat normally — note features will be back in about 5 minutes."
        if cooldown_msg not in all_errors:
            all_errors.append(cooldown_msg)

    final_result = {"results": all_results, "errors": all_errors, "chat": chat}
    errors = len(all_errors)
    results = len(all_results)

    if (
        results == 0
        and errors == 0
        and not chat
        and note_action_html_content
        and all_get_notes == ""
    ):
        return jsonify(
            {
                "note_action": note_action_html_content,
                "flashcard_id": flashcard_id,
                "quiz_id": quiz_id,
            }
        )

    if results <= 1 and errors <= 1 and not chat and not note_action_html_content:
        if results == 1 and errors == 0 and all_get_notes == "":
            return jsonify(
                {
                    "chat": all_results[0],
                    "flashcard_id": flashcard_id,
                    "quiz_id": quiz_id,
                }
            )
        elif results == 0 and errors == 1 and all_get_notes == "":
            return jsonify(
                {
                    "chat": all_errors[0],
                    "flashcard_id": flashcard_id,
                    "quiz_id": quiz_id,
                }
            )
        elif results == 0 and errors == 0 and all_get_notes != "":
            return jsonify(
                {
                    "chat": all_get_notes,
                    "flashcard_id": flashcard_id,
                    "quiz_id": quiz_id,
                }
            )
    if results == 0 and errors == 0 and chat:
        return jsonify({"chat": chat, "flashcard_id": flashcard_id, "quiz_id": quiz_id})

    final_summary = ask_gemini(question=final_result, action="summarize")
    if is_ai_error(final_summary):
        app.logger.error(
            "[ai_response] Gemini summarize failed (type=%s): %s",
            final_summary.get("type"),
            final_summary.get("msg"),
        )
        final_summary = (
            chat or "An error occurred while executing your task. Please try again."
        )
    output = {
        "chat": md_to_html(final_summary),
        "notes": all_get_notes,
        "note_action": note_action_html_content,
        "flashcard_id": flashcard_id,
        "quiz_id": quiz_id,
    }
    return jsonify(output)


@app.route("/read_note/<int:note_id>")
@login_required
def read_note(note_id):
    try:
        note = db.session.get(Note, note_id)
        if not note or note.user_id != current_user.id:
            app.logger.warning(
                "[read_note] Note not found or unauthorized — note_id=%s, user_id=%s",
                note_id,
                current_user.id,
            )
            abort(404)
        note.last_opened = datetime.now(timezone.utc)
        db.session.commit()
    except SQLAlchemyError as e:
        app.logger.error(
            "[read_note] DB error reading note_id=%s for user_id=%s: %s",
            note_id,
            current_user.id,
            e,
        )
        abort(404)
    return render_template("read_note.html", note=note)


@app.route("/flashcards/<int:flashcard_id>")
@login_required
def view_flashcards(flashcard_id):
    flashcard_obj = db.session.get(Flashcard, flashcard_id)
    if not flashcard_obj or flashcard_obj.user_id != current_user.id:
        app.logger.warning(
            "[view_flashcards] Flashcard not found or unauthorized — flashcard_id=%s, user_id=%s",
            flashcard_id,
            current_user.id,
        )
        abort(404)
    return render_template(
        "view-flashcards.html",
        flashcards=flashcard_obj.card_data[1:],
        cards_id=flashcard_obj.id,
        is_saved=flashcard_obj.is_saved,
    )


@app.route("/save-flashcards/<int:flashcard_id>", methods=["POST"])
@login_required
def save_flashcard(flashcard_id):
    flashcard_obj = db.session.get(Flashcard, flashcard_id)
    if flashcard_obj and flashcard_obj.user_id == current_user.id:
        flashcard_obj.is_saved = True
        db.session.commit()
        return jsonify({"status": "saved"})
    return jsonify({"status": "failed"})


@app.route("/delete-flashcards/<int:flashcard_id>", methods=["POST"])
@login_required
def delete_flashcard(flashcard_id):
    flashcard_obj = db.session.get(Flashcard, flashcard_id)
    if flashcard_obj and flashcard_obj.user_id == current_user.id:
        db.session.delete(flashcard_obj)
        db.session.commit()
        return jsonify(["Set deleted", "success"])
    return jsonify(["Failed to delete", "error"])


@app.route("/quiz/<int:quiz_id>")
@login_required
def take_quiz(quiz_id):
    quiz_obj = db.session.get(Quiz, quiz_id)
    if not quiz_obj or quiz_obj.user_id != current_user.id:
        app.logger.warning(
            "[take_quiz] Quiz not found or unauthorized — quiz_id=%s, user_id=%s",
            quiz_id,
            current_user.id,
        )
        return render_template(
            "take-quiz.html", quiz_id=quiz_id, quiz_data_json="[]", error=True
        )

    raw_data = quiz_obj.quiz_data
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except Exception:
            pass

    if isinstance(raw_data, dict) and "questions" in raw_data:
        raw_data = raw_data["questions"]
    elif isinstance(raw_data, dict) and "quiz" in raw_data:
        raw_data = raw_data["quiz"]

    return render_template(
        "take-quiz.html",
        quiz_id=quiz_id,
        quiz_data_json=json.dumps(raw_data),
        error=False,
    )


@app.route("/get-quiz-data/<int:quiz_id>", methods=["POST"])
@login_required
def get_quiz_data(quiz_id):
    quiz_obj = db.session.get(Quiz, quiz_id)
    if not quiz_obj or quiz_obj.user_id != current_user.id:
        app.logger.warning(
            "[get_quiz_data] Quiz not found or unauthorized — quiz_id=%s, user_id=%s",
            quiz_id,
            current_user.id,
        )
        return jsonify({"error": "Quiz not found"}), 404
    return jsonify(quiz_obj.quiz_data)


@app.route("/save-quiz/<int:quiz_id>", methods=["POST"])
@login_required
def save_quiz(quiz_id):
    quiz_obj = db.session.get(Quiz, quiz_id)
    if not quiz_obj or quiz_obj.user_id != current_user.id:
        app.logger.warning(
            "[get_quiz_data] Quiz not found or unauthorized — quiz_id=%s, user_id=%s",
            quiz_id,
            current_user.id,
        )
        return jsonify({"error": "failed"})
    quiz_obj.is_saved = True
    quiz_obj.total_questions = request.json.get("total_questions", 0)
    quiz_obj.correct_answers = request.json.get("correct_answers", 0)
    quiz_obj.incorrect_answers = request.json.get("incorrect_answers", 0)
    quiz_obj.percentage_score = request.json.get("percentage_score", 0.0)
    db.session.commit()
    return jsonify({"status": "saved"})


@app.route("/delete-quiz/<int:quiz_id>", methods=["POST"])
@login_required
def delete_quiz(quiz_id):
    quiz_obj = db.session.get(Quiz, quiz_id)
    if quiz_obj and quiz_obj.user_id == current_user.id:
        db.session.delete(quiz_obj)
        db.session.commit()
        return jsonify(["Quiz deleted", "success"])
    return jsonify(["Failed to delete", "error"])


@app.route("/practice-hub")
@login_required
def practice_hub():
    all_flashcards = db.session.scalars(
        db.select(Flashcard)
        .where(Flashcard.user_id == current_user.id)
        .where(Flashcard.is_saved == True)
    ).all()
    all_quizzes = db.session.scalars(
        db.select(Quiz)
        .where(Quiz.user_id == current_user.id)
        .where(Quiz.is_saved == True)
    ).all()
    return render_template(
        "practice-hub.html",
        flashcards=all_flashcards,
        quizzes=all_quizzes,
        saved_flashcards=len(all_flashcards),
        saved_quizzes=len(all_quizzes),
    )


@app.route("/about")
def about():
    return render_template("about.html")


@app.errorhandler(404)
def page_not_found(error):
    app.logger.warning("[404] Page not found: %s %s", request.method, request.url)
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
