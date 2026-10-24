import base64
import json
import re

from flask import current_app

from ..extensions import db
from ..models import Diagram


def associate_diagrams_with_note(note, draft_diagram_ids=None):
    combined_content = f"{note.md_content or ''} {note.html_content or ''}"

    patterns = [
        r'data-diagram-id=["\'](\d+)["\']',
        r'/diagram_image/(\d+)\.png',
    ]
    current_diagram_ids = set()
    if combined_content.strip():
        for pattern in patterns:
            matches = re.findall(pattern, combined_content)
            current_diagram_ids.update(int(d_id) for d_id in matches)

    if draft_diagram_ids:
        try:
            if isinstance(draft_diagram_ids, str):
                draft_ids = json.loads(draft_diagram_ids)
            else:
                draft_ids = draft_diagram_ids
            for d_id in draft_ids:
                d_id_int = int(d_id)
                if d_id_int not in current_diagram_ids:
                    diagram = db.session.get(Diagram, d_id_int)
                    if (
                        diagram
                        and diagram.user_id == note.user_id
                        and diagram.note_id is None
                    ):
                        db.session.delete(diagram)
        except Exception as e:
            current_app.logger.warning(
                "[associate_diagrams_with_note] Error processing draft_diagram_ids: %s", e
            )

    existing_diagrams = db.session.scalars(
        db.select(Diagram).where(Diagram.note_id == note.id)
    ).all()

    for diagram in existing_diagrams:
        if diagram.id not in current_diagram_ids:
            db.session.delete(diagram)

    for d_id in current_diagram_ids:
        diagram = db.session.get(Diagram, d_id)
        if diagram and diagram.user_id == note.user_id:
            diagram.note_id = note.id
            diagram.original_diagram_data = None
            diagram.dirty_since = None

    db.session.commit()


def prepare_note_and_diagrams(md_content, user_id):
    if not md_content:
        return md_content, []

    patterns = [
        r'/diagram_image/(\d+)\.png',
        r'data-diagram-id=["\'](\d+)["\']',
    ]
    diagram_ids = set()
    for pattern in patterns:
        matches = re.findall(pattern, md_content)
        diagram_ids.update(int(d_id) for d_id in matches)

    image_parts = []
    for d_id in diagram_ids:
        diagram = db.session.get(Diagram, d_id)
        if diagram and diagram.user_id == user_id and diagram.diagram_data:
            raw_data = diagram.diagram_data
            if "," in raw_data:
                base64_str = raw_data.split(",", 1)[1]
            else:
                base64_str = raw_data
            base64_str = base64_str.replace(" ", "+").strip()
            image_parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64_str,
                    }
                }
            )

    cleaned_md = re.sub(
        r'<img[^>]*\/diagram_image\/(\d+)\.png[^>]*>',
        r'\n[Diagram ID: \1]\n',
        md_content,
    )
    return cleaned_md, image_parts