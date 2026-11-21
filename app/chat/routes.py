from flask import current_app, jsonify
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from . import bp
from ..extensions import db
from ..models import ChatMessage, ChatSession


@bp.route("/api/chat/sessions", methods=["GET"])
@login_required
def list_sessions():
    """List all sessions for the current user."""
    try:
        sessions = db.session.scalars(
            db.select(ChatSession)
            .where(ChatSession.user_id == current_user.id)
            .order_by(ChatSession.updated_at.desc())
        ).all()
    except SQLAlchemyError as e:
        current_app.logger.error("[list_sessions] DB error: %s", e)
        return jsonify({"error": "Could not load sessions."}), 500

    return jsonify([
        {
            "id": s.id,
            "title": s.title,
            "message_count": len(s.messages),
            "updated_at": s.updated_at.isoformat(),
        }
        for s in sessions
    ])


@bp.route("/api/chat/sessions/<int:session_id>", methods=["GET"])
@login_required
def get_session(session_id):
    """Get a specific session and its messages."""
    session = db.session.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        return jsonify({"error": "Session not found"}), 404

    return jsonify({
        "id": session.id,
        "title": session.title,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in session.messages
        ],
    })


@bp.route("/api/chat/sessions/<int:session_id>", methods=["DELETE"])
@login_required
def delete_session(session_id):
    """Delete a specific session."""
    session = db.session.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        return jsonify({"error": "Session not found"}), 404

    try:
        db.session.delete(session)   # cascade deletes ChatMessage rows
        db.session.commit()
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.error("[delete_session] DB error: %s", e)
        return jsonify({"error": "Could not delete session."}), 500

    return jsonify({"status": "deleted"})