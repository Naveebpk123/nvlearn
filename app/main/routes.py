from flask import render_template
from flask_login import current_user

from . import bp
from ..extensions import db
from ..models import Flashcard, Note
from helpers import get_welcome_message


@bp.route("/")
def home():
    welcome_msg = None
    recent_notes = []
    cards_to_review = []

    if current_user.is_authenticated:
        welcome_msg = get_welcome_message(current_user.name)
        try:
            recent_notes = db.session.execute(
                db.select(Note)
                .where(Note.in_bin != True)  # noqa: E712
                .where(Note.user_id == current_user.id)
                .order_by(Note.last_opened.desc())
            ).scalars().all()
        except Exception:
            recent_notes = []
        try:
            cards_to_review = db.session.execute(
                db.select(Flashcard)
                .where(Flashcard.user_id == current_user.id)
                .where(Flashcard.is_saved == True)  # noqa: E712
                .where(Flashcard.incorrect_ratio > 0.0)
                .order_by(Flashcard.incorrect_ratio.desc())
                .limit(5)
            ).scalars().all()
        except Exception:
            cards_to_review = []

    return render_template(
        "index.html",
        welcome_msg=welcome_msg,
        recent_notes=recent_notes[:5],
        cards_to_review=cards_to_review,
    )


@bp.route("/about")
def about():
    return render_template("about.html")