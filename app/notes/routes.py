import re

from flask import (
    current_app, flash, jsonify, redirect, render_template, request, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from . import bp
from ..config import Config
from ..extensions import db
from ..models import Diagram, Note
from ..services.diagram_service import associate_diagrams_with_note
from ..services.metadata_service import get_meta_data, normalize_metadata
from ..services.note_service import (
    check_mermaid,
    get_keyword_and_vector_matched_notes,
)
from forms import AddNoteForm, EditNoteForm
from helpers import md_to_html
from vector_store import delete_note_vector, upsert_note_vector


@bp.route("/notes")
@login_required
def notes():
    try:
        notes = db.session.execute(
            db.select(Note)
            .where(Note.in_bin != True)  # noqa: E712
            .where(Note.user_id == current_user.id)
        ).scalars().all()
    except SQLAlchemyError as e:
        current_app.logger.error(
            "[notes] DB error for user_id=%s: %s", current_user.id, e
        )
        flash("An error occurred while fetching your notes. Please retry.", "error")
        notes = []

    main_tags, extra_tags = [], []
    if len(notes) > 1:
        tag_counts = {}
        for note in notes:
            metadata = note.meta_data if isinstance(note.meta_data, dict) else {}
            for tag in metadata.get("tags", []):
                if isinstance(tag, str) and tag.strip():
                    tag = tag.strip()
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        main_tags = [t for t, c in tag_counts.items() if c > 2]
        extra_tags = [t for t, c in tag_counts.items() if c > 1 and t not in main_tags]
        for tag in tag_counts:
            if tag.lower() in Config.DEFAULT_TAGS and tag not in (main_tags + extra_tags):
                main_tags.append(tag)

    return render_template(
        "notes.html",
        notes=notes,
        main_tags=main_tags if len(notes) > 1 else [],
        extra_tags=extra_tags if len(notes) > 1 else [],
    )


@bp.route("/add_note", methods=["GET", "POST"])
@login_required
def add_note():
    form = AddNoteForm()
    if form.validate_on_submit():
        try:
            content = form.content.data
            metadata = get_meta_data(content, user_id=current_user.id)
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
            draft_ids = request.form.get("draft_diagram_ids")
            associate_diagrams_with_note(note, draft_diagram_ids=draft_ids)
            upsert_note_vector(note)
            flash("Note created successfully", "success")
            return redirect(url_for("notes.notes"))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error(
                "[add_note] DB error for user_id=%s: %s", current_user.id, e
            )
            flash("Failed to create note due to a database error. Try again.", "error")
    return render_template("add_note.html", form=form)


@bp.route("/edit/<int:note_id>", methods=["GET", "POST"])
@login_required
def edit_note(note_id):
    try:
        note = db.session.get(Note, note_id)
        if not note or note.user_id != current_user.id:
            flash("Note not found.", "error")
            return redirect(url_for("notes.notes"))
    except SQLAlchemyError as e:
        current_app.logger.error("[edit_note] DB error: %s", e)
        flash("Error pulling note transaction records.", "error")
        return redirect(url_for("notes.notes"))

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
                "This note contains mathematical formulas (LaTeX). "
                "Switch to Read Mode for the best rendering experience!",
                "info",
            )

    if form.validate_on_submit():
        try:
            if form.content.data != note.md_content:
                metadata = get_meta_data(form.content.data, user_id=current_user.id)
                note.meta_data = normalize_metadata(metadata, note.id)
            note.md_content = form.content.data
            note.html_content = request.form.get("html_content")
            db.session.commit()
            draft_ids = request.form.get("draft_diagram_ids")
            associate_diagrams_with_note(note, draft_diagram_ids=draft_ids)
            upsert_note_vector(note)
            flash("Changes saved successfully!", "success")
            return redirect(url_for("notes.notes"))
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error("[edit_note] DB error: %s", e)
            flash("Could not update changes. Please check parameters.", "error")

    return render_template("edit_note.html", note=note, form=form)


@bp.route("/move_to_bin/<int:note_id>", methods=["POST"])
@login_required
def move_to_bin(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            note.in_bin = True
            db.session.commit()
            delete_note_vector(note.id, note.user_id)
            return jsonify(["Note moved to bin", "success"])
        return jsonify(["Note not found", "error"])
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error("[move_to_bin] DB error: %s", e)
        return jsonify(["Could not move note to bin", "error"])


@bp.route("/note-bin")
@login_required
def note_bin():
    try:
        notes = db.session.execute(
            db.select(Note)
            .where(Note.in_bin == True)  # noqa: E712
            .where(Note.user_id == current_user.id)
        ).scalars().all()
    except SQLAlchemyError as e:
        current_app.logger.error("[note_bin] DB error: %s", e)
        flash("Error checking database trash allocations.", "error")
        notes = []
    return render_template("bin.html", notes=notes)


@bp.route("/delete/<int:note_id>", methods=["POST"])
@login_required
def delete(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            user_id = note.user_id
            diagrams = db.session.execute(
                db.select(Diagram).where(Diagram.note_id == note.id)
            ).scalars().all()
            for d in diagrams:
                db.session.delete(d)
            db.session.delete(note)
            db.session.commit()
            delete_note_vector(note_id, user_id)
            return jsonify(["Note permanently deleted", "success"])
        return jsonify(["Note not found", "error"])
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error("[delete] DB error: %s", e)
        return jsonify(["Failed to delete note", "error"])


@bp.route("/restore/<int:note_id>", methods=["POST"])
@login_required
def restore(note_id):
    try:
        note = db.session.get(Note, note_id)
        if note and note.user_id == current_user.id:
            note.in_bin = False
            db.session.commit()
            upsert_note_vector(note)
            return jsonify(["Note restored", "success"])
        return jsonify(["Note not found.", "error"])
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error("[restore] DB error: %s", e)
        return jsonify(["Failed to restore note.", "error"])


@bp.route("/search/<path:query>")
@login_required
def search(query):
    query = query.strip()
    if not query:
        return {"results": []}
    try:
        notes = get_keyword_and_vector_matched_notes(query, current_user.id)
        return jsonify(
            {"results": [{"id": n.id, "title": n.title} for n in notes]}
        )
    except SQLAlchemyError as e:
        current_app.logger.error("[search] DB error: %s", e)
        return jsonify({"results": []})


@bp.route("/search-results/<path:query>")
@login_required
def search_results(query):
    query = query.strip()
    if not query:
        return render_template("search-results.html", query=query, notes=[])
    try:
        notes = get_keyword_and_vector_matched_notes(query, current_user.id)
    except SQLAlchemyError as e:
        current_app.logger.error("[search_results] DB error: %s", e)
        notes = []
    return render_template("search-results.html", query=query, notes=notes)


@bp.route("/save_mermaid_notes", methods=["POST"])
@login_required
def save_mermaid_notes():
    try:
        data = request.get_json()
        for item in data:
            note_id = item["note_id"]
            replaced_md_content = item["replaced_md_content"]
            if not note_id or not replaced_md_content:
                return jsonify(
                    {"status": "error", "message": "Missing fields"}
                ), 400
            note = db.session.get(Note, note_id)
            if not note or note.user_id != current_user.id:
                return jsonify(
                    {"status": "error", "message": "Note not found or unauthorized"}
                ), 404
            note.md_content = replaced_md_content
            note.html_content = md_to_html(replaced_md_content)
            note.mermaid_needs_conversion = False
            associate_diagrams_with_note(note)
            db.session.commit()
            upsert_note_vector(note)
        return jsonify({"status": "success"}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error("[save_mermaid_notes] DB error: %s", e)
        return jsonify({"status": "error", "message": "Database error occurred"}), 500


@bp.route("/mark_mermaid_pending", methods=["POST"])
@login_required
def mark_mermaid_pending():
    try:
        data = request.get_json(silent=True) or {}
        for note_id in data.get("note_ids", []):
            note = db.session.get(Note, int(note_id))
            if note and note.user_id == current_user.id:
                note.mermaid_needs_conversion = True
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("[mark_mermaid_pending] Error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/get_pending_mermaid_notes", methods=["GET"])
@login_required
def pending_mermaid_notes():
    try:
        notes = db.session.scalars(
            db.select(Note).where(
                Note.user_id == current_user.id,
                Note.in_bin != True,  # noqa: E712
                Note.mermaid_needs_conversion == True,  # noqa: E712
            )
        ).all()
        pending = [{"note_id": n.id, "md_content": n.md_content} for n in notes]
        return jsonify({"status": "success", "pending_notes": pending})
    except Exception as e:
        current_app.logger.error("[pending_mermaid_notes] Error: %s", e)
        return jsonify({"status": "error", "pending_notes": []})