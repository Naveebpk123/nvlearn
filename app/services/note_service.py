import re
from typing import Any, Dict, List, Optional

from flask import current_app
from helpers import ask_gemini, is_ai_error
from vector_store import search_notes_vector

from ..extensions import db
from ..models import Note
from .diagram_service import prepare_note_and_diagrams


MAX_CONTENT_CHAR_LIMIT = 30000


def extract_topic_for_search(instruction: str) -> str:
    text = (instruction or "").strip()
    cleaned = re.sub(
        r"^(summarize|explain|extract key points from|extract formulas from|rewrite|simplify|notes? on|notes? about)\s*(the\s*)?(notes?\s*)?(on|about|for|from)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return cleaned if cleaned else text


def get_vector_matched_notes(
    topic: str, user_id: int, edit_mode: bool = False, for_search: bool = False
):
    if edit_mode:
        vector_res = search_notes_vector(topic=topic, user_id=user_id, n_results=1)
    elif for_search:
        vector_res = search_notes_vector(topic=topic, user_id=user_id, n_results=25)
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


def get_keyword_and_vector_matched_notes(query: str, user_id: int):
    title_notes = db.session.scalars(
        db.select(Note)
        .where(Note.user_id == user_id)
        .where(Note.in_bin != True)  # noqa: E712
        .where(Note.title.contains(query))
        .order_by(Note.title)
    ).all()

    vector_notes, _, _ = get_vector_matched_notes(
        topic=query, user_id=user_id, for_search=True
    )
    seen_ids = {note.id for note in title_notes}
    return title_notes + [note for note in vector_notes if note.id not in seen_ids]


def get_notes_for_action(topic: str, user_id: int, edit_mode: bool = False):
    clean_topic = (topic or "").strip().lower()
    if clean_topic in ("all_notes", "all notes") and not edit_mode:
        all_notes = db.session.scalars(
            db.select(Note).where(Note.user_id == user_id).where(Note.in_bin != True)  # noqa: E712
        ).all()
        if not all_notes:
            return [], "You do not have any notes saved yet.", False
        return all_notes, None, False
    return get_vector_matched_notes(topic, user_id, edit_mode=edit_mode)


def chunk_notes_content(
    notes: list, char_limit: int = MAX_CONTENT_CHAR_LIMIT, user_id: int = None
):
    batches = []
    current_text = ""
    current_images = []

    for note in notes:
        content = (note.md_content or "").strip()
        if not content:
            continue

        images = []
        if user_id:
            content, images = prepare_note_and_diagrams(content, user_id)

        if len(content) > char_limit:
            if current_text:
                batches.append(
                    [current_text, *current_images] if current_images else current_text
                )
                current_text = ""
                current_images = []
            paragraphs = content.split("\n\n")
            for para in paragraphs:
                if len(current_text) + len(para) + 2 > char_limit and current_text:
                    batches.append(
                        [current_text, *current_images]
                        if current_images
                        else current_text
                    )
                    current_text = para
                    current_images = list(images)
                else:
                    current_text = (current_text + "\n\n" + para).strip()
                    current_images.extend(images)
        else:
            if len(current_text) + len(content) + 2 > char_limit and current_text:
                batches.append(
                    [current_text, *current_images] if current_images else current_text
                )
                current_text = content
                current_images = list(images)
            else:
                current_text = (current_text + "\n\n" + content).strip()
                current_images.extend(images)

    if current_text:
        batches.append(
            [current_text, *current_images] if current_images else current_text
        )

    return batches


def summarize_notes_in_batches(batches: list):
    accumulated_summary = ""
    for i, batch in enumerate(batches):
        if isinstance(batch, list):
            batch_text = batch[0]
            batch_images = batch[1:]
        else:
            batch_text = batch
            batch_images = []

        prompt_text = f"Batch {i + 1} content:\n{batch_text}"
        if accumulated_summary:
            prompt_text = (
                f"Previous accumulated summary:\n{accumulated_summary}\n\n" + prompt_text
            )

        prompt_payload = [prompt_text, *batch_images] if batch_images else prompt_text

        result = ask_gemini(action="batch_summary", question=prompt_payload)
        if is_ai_error(result):
            hit_rl = result.get("type") == "rate_limit"
            return accumulated_summary, hit_rl, result
        accumulated_summary = result

    return accumulated_summary, False, None


def check_mermaid(md_content):
    if not md_content:
        return False
    MERMAID_REGEX = re.compile(r"\[\[MERMAID_START\]\]([\s\S]*?)\[\[MERMAID_END\]\]")
    return bool(MERMAID_REGEX.search(md_content))