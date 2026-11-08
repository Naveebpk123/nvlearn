from datetime import datetime, timedelta, timezone

from .extensions import db, scheduler
from .models import Diagram, Flashcard, Note, Quiz
from .services.metadata_service import (
    get_meta_data,
    metadata_needs_ai,
    normalize_metadata,
)


def generate_meta_data(app):
    with app.app_context():
        note = db.session.get(Note, note_id)
        if not note:
            return
        content = note.md_content
        user_id = note.user_id
        note_id_for_update = note.id
        db.session.close()   
        metadata = get_meta_data(content, user_id=user_id)

        note = db.session.get(Note, note_id_for_update)  
        if not note:
            return
        note.meta_data = normalize_metadata(metadata, note.id)
        db.session.commit()


def rollback_stale_diagrams(app):
    try:
        with app.app_context():
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
            stale = db.session.scalars(
                db.select(Diagram).where(
                    Diagram.original_diagram_data.is_not(None),
                    Diagram.dirty_since.is_not(None),
                    Diagram.dirty_since < cutoff,
                )
            ).all()
            for d in stale:
                d.diagram_data = d.original_diagram_data
                d.original_diagram_data = None
                d.dirty_since = None
            if stale:
                db.session.commit()
                app.logger.info(
                    "[rollback_stale_diagrams] Rolled back %s diagram(s).", len(stale)
                )
    except Exception as e:
        db.session.rollback()
        app.logger.error("[rollback_stale_diagrams] Error: %s", e)


def delete_flashcards(app):
    try:
        with app.app_context():
            oldest = db.session.scalars(
                db.select(Flashcard)
                .where(Flashcard.is_saved == False)  # noqa: E712
                .order_by(Flashcard.id.asc())
            ).first()
            if oldest:
                db.session.delete(oldest)
                db.session.commit()
                app.logger.info(
                    "Successfully deleted oldest unsaved flashcard (id=%s).", oldest.id
                )
    except Exception as e:
        app.logger.error("Failed to delete flashcard in background job: %s", e)
        db.session.rollback()


def delete_expired_quizzes(app):
    try:
        with app.app_context():
            cutoff = datetime.now(timezone.utc) - timedelta(hours=5)
            deleted_count = db.session.execute(
                db.delete(Quiz).where(
                    Quiz.is_saved == False,  # noqa: E712
                    Quiz.created_at < cutoff,
                )
            ).rowcount
            db.session.commit()
            if deleted_count > 0:
                app.logger.info(
                    "Successfully deleted %s expired unsaved quiz(zes).", deleted_count
                )
    except Exception as e:
        app.logger.error("Failed to delete quizzes in background job: %s", e)
        db.session.rollback()


def start_scheduler(app):
    if scheduler.running:
        return
    scheduler.add_job(
        generate_meta_data, "interval", minutes=10,
        max_instances=1, coalesce=True, args=[app],
    )
    scheduler.add_job(
        delete_flashcards, "interval", minutes=10,
        max_instances=1, coalesce=True, args=[app],
    )
    scheduler.add_job(
        delete_expired_quizzes, "interval", hours=3,
        max_instances=1, coalesce=True, args=[app],
    )
    scheduler.add_job(
        rollback_stale_diagrams, "interval", minutes=30,
        max_instances=1, coalesce=True, args=[app],
    )
    scheduler.start()
    app.logger.info("Background scheduler started.")