import base64
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import pymupdf
import pytesseract
from flask import current_app, jsonify, request
from flask_login import current_user, login_required
from PIL import Image

from . import bp
from ..extensions import db
from ..models import Diagram, Note
from ..services.metadata_service import get_meta_data, normalize_metadata
from helpers import md_to_html
from vector_store import upsert_note_vector


def _normalize_image_to_png(img_bytes):
    try:
        img = Image.open(BytesIO(img_bytes))
        if img.mode in ("CMYK", "P"):
            img = img.convert("RGB")
        output = BytesIO()
        img.save(output, format="PNG")
        return output.getvalue()
    except Exception:
        return img_bytes


def _to_data_url(b_data, m_type):
    encoded = base64.b64encode(b_data).decode("ascii")
    return f"data:{m_type or 'image/png'};base64,{encoded}"


@bp.route("/upload_note_file", methods=["POST"])
@login_required
def upload_note_file():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file provided."}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"status": "error", "message": "No selected file."}), 400

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

    try:
        # 1. Text-only
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

        # 2. Image-only
        elif mimetype.startswith("image/") or extension in {
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        }:
            note = Note(
                title=title,
                md_content="[Placeholder]",
                html_content="<p>[Placeholder]</p>",
                in_bin=False,
                user_id=current_user.id,
                meta_data={},
            )
            db.session.add(note)
            db.session.flush()

            file_bytes = _normalize_image_to_png(file_bytes)
            img_data_url = _to_data_url(file_bytes, "image/png")
            diagram = Diagram(
                diagram_data=img_data_url,
                user_id=current_user.id,
                note_id=note.id,
            )
            db.session.add(diagram)
            db.session.flush()

            img_url = f"/diagram_image/{diagram.id}.png"
            note.md_content = f"![Diagram]({img_url})"
            note.html_content = md_to_html(note.md_content)
            metadata = get_meta_data(note.md_content, user_id=current_user.id)
            note.meta_data = normalize_metadata(metadata, note.id)
            db.session.commit()
            upsert_note_vector(note)
            return jsonify(
                {
                    "status": "success",
                    "note_id": note.id,
                    "diagram_id": diagram.id,
                    "md_content": note.md_content,
                }
            )

        # 3. PDF / DOCX
        elif extension in {".pdf", ".docx"}:
            note = Note(
                title=title,
                md_content="[Placeholder]",
                html_content="<p>[Placeholder]</p>",
                in_bin=False,
                user_id=current_user.id,
                meta_data={},
            )
            db.session.add(note)
            db.session.flush()

            extracted_text_parts = []
            extracted_diagrams = []

            if extension == ".pdf":
                doc = pymupdf.open(stream=file_bytes, filetype="pdf")
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    page_text = page.get_text().strip()
                    if not page_text:
                        pix = page.get_pixmap(dpi=150)
                        img = Image.open(BytesIO(pix.tobytes("png")))
                        page_text = pytesseract.image_to_string(img).strip()
                    if page_text:
                        extracted_text_parts.append(page_text)

                    for img_info in page.get_images(full=True):
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        img_bytes = base_image["image"]
                        img_bytes = _normalize_image_to_png(img_bytes)
                        img_data_url = _to_data_url(img_bytes, "image/png")
                        diagram = Diagram(
                            diagram_data=img_data_url,
                            user_id=current_user.id,
                            note_id=note.id,
                        )
                        db.session.add(diagram)
                        db.session.flush()
                        extracted_diagrams.append(diagram)

            elif extension == ".docx":
                with zipfile.ZipFile(BytesIO(file_bytes)) as document:
                    document_xml = document.read("word/document.xml")
                    root = ElementTree.fromstring(document_xml)
                    namespace = {
                        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                    }
                    for paragraph in root.findall(".//w:p", namespace):
                        text = "".join(
                            node.text or ""
                            for node in paragraph.findall(".//w:t", namespace)
                        ).strip()
                        if text:
                            extracted_text_parts.append(text)

                    for name in document.namelist():
                        if name.startswith("word/media/"):
                            media_bytes = document.read(name)
                            media_bytes = _normalize_image_to_png(media_bytes)
                            img_data_url = _to_data_url(media_bytes, "image/png")
                            diagram = Diagram(
                                diagram_data=img_data_url,
                                user_id=current_user.id,
                                note_id=note.id,
                            )
                            db.session.add(diagram)
                            db.session.flush()
                            extracted_diagrams.append(diagram)

            text_content = "\n\n".join(extracted_text_parts)
            diagram_markdowns = [
                f"![Diagram](/diagram_image/{diag.id}.png)"
                for diag in extracted_diagrams
            ]
            final_md = (
                "\n\n".join([text_content, *diagram_markdowns])
                if text_content or diagram_markdowns
                else "Uploaded file"
            )
            note.md_content = final_md
            note.html_content = md_to_html(final_md)
            metadata = get_meta_data(note.md_content, user_id=current_user.id)
            note.meta_data = normalize_metadata(metadata, note.id)
            db.session.commit()
            upsert_note_vector(note)
            return jsonify(
                {
                    "status": "success",
                    "note_id": note.id,
                    "md_content": note.md_content,
                }
            )

        else:
            db.session.rollback()
            return jsonify(
                {"status": "error", "message": "Unsupported file type."}
            ), 400

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[upload_note_file] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500