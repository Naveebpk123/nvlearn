import base64
from pathlib import Path

from flask import current_app, jsonify, request
from flask_login import current_user, login_required

from . import bp
from ..extensions import db
from ..models import Diagram, Note
from ..services.extraction_service import (
    Region,
    extract_docx_regions,
    extract_images_regions,
    extract_pdf_regions,
)
from ..services.metadata_service import get_meta_data, normalize_metadata
from ..services.note_service import format_note_content
from utils import md_to_html
from vector_store import upsert_note_vector


MAX_IMAGE_UPLOAD_BYTES = 50 * 1024 * 1024


def _to_data_url(b_data, m_type):
    """Encode raw bytes and MIME type into a base64 data URL."""
    encoded = base64.b64encode(b_data).decode("ascii")
    return f"data:{m_type or 'image/png'};base64,{encoded}"


def _save_regions_as_note(regions: list[Region], title: str, user_id: int) -> Note:
    """Persist ordered text/diagram regions as a Note + Diagram rows and polish formatting."""
    note = Note(
        title=title,
        md_content="[Placeholder]",
        html_content="<p>[Placeholder]</p>",
        in_bin=False,
        user_id=user_id,
        meta_data={},
    )
    db.session.add(note)
    db.session.flush()

    parts: list[str] = []
    for region in regions:
        if region.kind == "diagram" and region.image_bytes:
            diagram = Diagram(
                diagram_data=_to_data_url(region.image_bytes, "image/png"),
                user_id=user_id,
                note_id=note.id,
            )
            db.session.add(diagram)
            db.session.flush()
            parts.append(f"![Diagram](/diagram_image/{diagram.id}.png)")
        elif region.kind == "text" and region.text and region.text.strip():
            parts.append(region.text.strip())

    raw_md = "\n\n".join(parts) if parts else "Uploaded file"
    final_md = format_note_content(raw_md, user_id)

    note.md_content = final_md
    note.html_content = md_to_html(final_md)
    metadata = get_meta_data(note.md_content, user_id=user_id)
    note.meta_data = normalize_metadata(metadata, note.id)
    db.session.commit()
    upsert_note_vector(note)
    return note


@bp.route("/upload_note_file", methods=["POST"])
@login_required
def upload_note_file():
    """Extract markdown/text and inline diagrams from uploaded files via extraction_service."""
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        single = request.files.get("file")
        if single and single.filename:
            files = [single]

    if not files:
        return jsonify({"status": "error", "message": "No file provided."}), 400

    image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

    def _is_image(f):
        return (f.mimetype or "").startswith("image/") or Path(f.filename).suffix.lower() in image_exts

    if len(files) > 1 and not all(_is_image(f) for f in files):
        return jsonify(
            {"status": "error", "message": "Multi-file upload only supports images."}
        ), 400

    try:
        # Image(s) path: single image or multi-photo camera upload
        if all(_is_image(f) for f in files):
            raw_images = []
            for f in files:
                f.stream.seek(0)
                data = f.read()
                if data:
                    raw_images.append(data)
            if not raw_images:
                return jsonify(
                    {"status": "error", "message": "The selected file is empty."}
                ), 400

            total_bytes = sum(len(b) for b in raw_images)
            if total_bytes > MAX_IMAGE_UPLOAD_BYTES:
                return jsonify(
                    {"status": "error", "message": "Total image upload size exceeds the 50 MB limit."}
                ), 400

            title = (files[0].filename or "Camera note")[:20]
            regions = extract_images_regions(raw_images)
            note = _save_regions_as_note(regions, title, current_user.id)
            return jsonify({
                "status": "success",
                "note_id": note.id,
                "md_content": note.md_content,
            })

        file = files[0]
        filename = file.filename
        title = filename[:20]
        mimetype = file.mimetype or ""
        extension = Path(filename).suffix.lower()
        file_bytes = file.read()

        if not file_bytes:
            return jsonify(
                {"status": "error", "message": "The selected file is empty."}
            ), 400

        audio_video_extensions = {
            ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".mp4",
            ".mov", ".avi", ".mkv", ".webm",
        }
        if (
            extension in audio_video_extensions
            or mimetype.startswith("audio/")
            or mimetype.startswith("video/")
        ):
            return jsonify(
                {"status": "error", "message": "Audio and video files are not allowed."}
            ), 400

        # Text-only
        if extension in {".md", ".txt", ".doc"} or mimetype.startswith("text/"):
            text_content = file_bytes.decode("utf-8", errors="replace")
            note = Note(
                title=title,
                md_content=text_content,
                html_content=md_to_html(text_content),
                in_bin=False,
                user_id=current_user.id,
                meta_data={},
            )
            db.session.add(note)
            db.session.flush()
            metadata = get_meta_data(note.md_content, user_id=current_user.id)
            note.meta_data = normalize_metadata(metadata, note.id)
            db.session.commit()
            upsert_note_vector(note)
            return jsonify({"status": "success", "note_id": note.id})

        if extension == ".pdf":
            regions = extract_pdf_regions(file_bytes)
        elif extension == ".docx":
            regions = extract_docx_regions(file_bytes)
        else:
            return jsonify(
                {"status": "error", "message": "Unsupported file type."}
            ), 400

        note = _save_regions_as_note(regions, title, current_user.id)
        return jsonify({
            "status": "success",
            "note_id": note.id,
            "md_content": note.md_content,
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[upload_note_file] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500