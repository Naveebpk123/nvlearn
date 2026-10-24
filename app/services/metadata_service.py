from helpers import build_ai_instructions

from .diagram_service import prepare_note_and_diagrams


def get_meta_data(content, user_id=None):
    if user_id:
        content, images = prepare_note_and_diagrams(content, user_id)
        if images:
            content = [content, *images]
    return build_ai_instructions(content, username="", metadata=True)


def normalize_metadata(metadata, note_id=None):
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
    if not isinstance(metadata, dict):
        return True
    tags = metadata.get("tags", [])
    return metadata.get("is_invalid") is True or "error" in tags