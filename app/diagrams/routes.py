import base64
from datetime import datetime, timezone

from flask import Response, abort, current_app, jsonify, request
from flask_login import current_user, login_required

from . import bp
from ..extensions import db
from ..models import Diagram


@bp.route("/save_diagram", methods=["POST"])
@login_required
def save_diagram():
    try:
        data = request.get_json() or {}
        diagram_id = data.get("id")
        img_data = (
            data.get("img_data")
            or data.get("diagram_data")
            or data.get("image_data")
        )
        if not img_data:
            return jsonify({"status": "error", "message": "Missing image data"}), 400

        diagram = None
        if diagram_id:
            try:
                diagram = db.session.get(Diagram, int(diagram_id))
            except (ValueError, TypeError):
                diagram = None

        if diagram and diagram.user_id == current_user.id:
            if diagram.note_id is not None and diagram.original_diagram_data is None:
                diagram.original_diagram_data = diagram.diagram_data
                diagram.dirty_since = datetime.now(timezone.utc).replace(tzinfo=None)
            diagram.diagram_data = img_data
            is_dirty = diagram.original_diagram_data is not None
        else:
            diagram = Diagram(diagram_data=img_data, user_id=current_user.id)
            db.session.add(diagram)
            db.session.flush()
            is_dirty = False

        db.session.commit()
        return jsonify(
            {
                "status": "success",
                "id": diagram.id,
                "img_url": f"/diagram_image/{diagram.id}.png",
                "img_data": diagram.diagram_data,
                "dirty": is_dirty,
            }
        )
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            "[save_diagram] Failed for user_id=%s: %s", current_user.id, e
        )
        return jsonify(
            {"status": "error", "message": "Failed to save diagram."}
        ), 500


@bp.route("/restore_diagrams", methods=["POST"])
@login_required
def restore_diagrams():
    ids = (request.get_json(silent=True) or {}).get("diagram_ids", [])
    for d_id in ids:
        d = db.session.get(Diagram, int(d_id))
        if (
            d
            and d.user_id == current_user.id
            and d.original_diagram_data is not None
        ):
            d.diagram_data = d.original_diagram_data
            d.original_diagram_data = None
            d.dirty_since = None
    db.session.commit()
    return jsonify({"status": "success"})


@bp.route("/diagram_image/<int:diagram_id>.png", methods=["GET"])
def get_diagram_image(diagram_id):
    try:
        diagram = db.session.get(Diagram, diagram_id)
        if not diagram or not diagram.diagram_data:
            abort(404)
        raw_data = diagram.diagram_data
        if "," in raw_data:
            base64_str = raw_data.split(",", 1)[1]
        else:
            base64_str = raw_data
        base64_str = base64_str.replace(" ", "+")
        missing_padding = len(base64_str) % 4
        if missing_padding:
            base64_str += "=" * (4 - missing_padding)
        image_bytes = base64.b64decode(base64_str)
        response = Response(image_bytes, mimetype="image/png")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
    except Exception as e:
        current_app.logger.error(
            "[get_diagram_image] Failed for diagram_id=%s: %s", diagram_id, e
        )
        abort(404)


@bp.route("/diagram_data/<int:diagram_id>", methods=["GET"])
@login_required
def get_diagram_data(diagram_id):
    try:
        diagram = db.session.get(Diagram, diagram_id)
        if not diagram or diagram.user_id != current_user.id:
            return jsonify({"status": "error", "message": "Diagram not found"}), 404
        return jsonify(
            {
                "status": "success",
                "id": diagram.id,
                "diagram_data": diagram.diagram_data,
            }
        )
    except Exception as e:
        current_app.logger.error(
            "[get_diagram_data] Error for diagram_id=%s: %s", diagram_id, e
        )
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/cleanup_draft_diagrams", methods=["POST"])
@login_required
def cleanup_draft_diagrams():
    try:
        ids = (request.get_json(silent=True) or {}).get("diagram_ids", [])
        for diagram_id in ids:
            diagram = db.session.get(Diagram, diagram_id)
            if (
                diagram
                and diagram.user_id == current_user.id
                and diagram.note_id is None
            ):
                db.session.delete(diagram)
        db.session.commit()
        return jsonify({"status": "success", "message": "Draft diagrams cleaned up."})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error("[cleanup_draft_diagrams] Error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500