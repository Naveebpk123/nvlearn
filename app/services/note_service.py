import re
from typing import Any, Dict, List, Optional

from flask import current_app
from helpers import ask_gemini, is_ai_error
from vector_store import search_notes_vector

from ..extensions import db
from ..models import Note
from .diagram_service import prepare_note_and_diagrams

import logging

logger = logging.getLogger(__name__)

MAX_CONTENT_CHAR_LIMIT = 30000

# Hard cap: skip formatting if the note is larger than this.
# (Chunked formatting for very large notes to be implemented in the future.)
MAX_FORMAT_CHARS = 40_000

# Placeholder for diagrams. Unlikely to be written by a user, so safe to use as a marker for diagrams in the text.
PLACEHOLDER_RE = re.compile(r"%%__DIAGRAM_(\d+)__%%")

# Acceptable word-count drift before considering the AI has paraphrased.
# Word drift is calculated as the absolute difference between the original and formatted word counts, divided by the original word count.
WORD_DRIFT_TOLERANCE = 0.05  # 5%


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

def _extract_diagram_ids_from_md(md_content):
    """Return the set of diagram IDs referenced in the markdown."""
    if not md_content:
        return set()
    ids = set()
    for pattern in (
        r"/diagram_image/(\d+)\.png",
        r'data-diagram-id=["\'](\d+)["\']',
    ):
        ids.update(int(m) for m in re.findall(pattern, md_content))
    return ids


def _md_to_placeholders(md_content, user_id):
    """
    Convert markdown to the AI-input form:
      - ![Diagram](/diagram_image/N.png)   → %%__DIAGRAM_N__%%
      - <img ... /diagram_image/N.png ...> → %%__DIAGRAM_N__%%
      - [Diagram ID: N]                    → %%__DIAGRAM_N__%%

    Returns (placeholder_md, image_parts, valid_ids).
    image_parts is a list of Gemini inline_data dicts built from DB.
    """

    cleaned_md, image_parts = prepare_note_and_diagrams(md_content, user_id)

    # Convert remaining ![Diagram](/diagram_image/N.png) markdown images if any
    cleaned_md = re.sub(
        r"!\[[^\]]*\]\(/diagram_image/(\d+)\.png\)",
        r"%%__DIAGRAM_\1__%%",
        cleaned_md,
    )
    # Convert the [Diagram ID: N] markers produced by prepare_note_and_diagrams
    cleaned_md = re.sub(
        r"\[Diagram ID:\s*(\d+)\]",
        r"%%__DIAGRAM_\1__%%",
        cleaned_md,
    )
    # Convert bare data-diagram-id attributes (defensive, in case HTML survives)
    cleaned_md = re.sub(
        r'<img[^>]*data-diagram-id=["\'](\d+)["\'][^>]*>',
        r"%%__DIAGRAM_\1__%%",
        cleaned_md,
    )

    valid_ids = {int(m) for m in PLACEHOLDER_RE.findall(cleaned_md)}
    return cleaned_md, image_parts, valid_ids


def _placeholders_to_md(md_content, valid_ids):
    """Replace %%__DIAGRAM_N__%% with real image URLs. Drop invented IDs."""
    def repl(match):
        d_id = int(match.group(1))
        if d_id not in valid_ids:
            logger.warning(
                "[note_service] AI invented diagram id=%s; dropping", d_id
            )
            return ""
        return f"![Diagram](/diagram_image/{d_id}.png)"

    return PLACEHOLDER_RE.sub(repl, md_content)


def _word_count(md_content):
    """Rough word count ignoring markdown syntax and placeholders."""
    stripped = PLACEHOLDER_RE.sub("", md_content)
    # Strip fenced code blocks (don't count their contents)
    stripped = re.sub(r"```.*?```", "", stripped, flags=re.DOTALL)
    # Strip markdown punctuation
    stripped = re.sub(r"[#*_`~\[\]()>|]", " ", stripped)
    return len(re.findall(r"\w+", stripped))


def format_note_content(md_content, user_id):
    """
    Run a Gemini pass that cleans up OCR formatting and repositions
    diagram placeholders. Returns the reformatted markdown, or the
    original md_content if:
      - the note has no diagrams and is short (no format needed)
      - the note exceeds MAX_FORMAT_CHARS
      - the AI call fails
      - the AI drops placeholders, invents them, or drifts word count
    """
    if not md_content or not md_content.strip():
        return md_content

    diagram_ids = _extract_diagram_ids_from_md(md_content)

    # Short and no diagrams: skip formatting to conserve API quota. (We could still run it, but it's not worth the cost.)
    if not diagram_ids and len(md_content) < 800:
        return md_content

    # Too large: skip (chunked formatting to be implemented in the future)
    if len(md_content) > MAX_FORMAT_CHARS:
        logger.info(
            "[format_note_content] Skipping — note is %d chars (max %d)",
            len(md_content), MAX_FORMAT_CHARS,
        )
        return md_content

    try:
        placeholder_md, image_parts, valid_ids = _md_to_placeholders(
            md_content, user_id
        )
        payload = [placeholder_md, *image_parts] if image_parts else placeholder_md

        ai_result = ask_gemini(action="format_note", question=payload)
        if is_ai_error(ai_result):
            logger.warning(
                "[format_note_content] AI error type=%s; returning original",
                ai_result.get("type"),
            )
            return md_content

        if not isinstance(ai_result, str) or not ai_result.strip():
            logger.warning(
                "[format_note_content] AI returned empty/non-string; returning original"
            )
            return md_content

        # ── Validation 1: all original placeholders are present
        returned_ids = {int(m) for m in PLACEHOLDER_RE.findall(ai_result)}
        missing = valid_ids - returned_ids
        if missing:
            logger.warning(
                "[format_note_content] AI dropped placeholders %s; appending",
                sorted(missing),
            )
            for d_id in sorted(missing):
                ai_result = ai_result.rstrip() + f"\n\n%%__DIAGRAM_{d_id}__%%\n"

        # ── Validation 2: no invented placeholders
        invented = returned_ids - valid_ids
        if invented:
            logger.warning(
                "[format_note_content] AI invented placeholders %s; will drop on rehydrate",
                sorted(invented),
            )

        # ── Validation 3: word-count drift
        before = _word_count(placeholder_md)
        after = _word_count(ai_result)
        if before > 50:  # only check on large notes
            drift = abs(after - before) / before
            if drift > WORD_DRIFT_TOLERANCE:
                logger.warning(
                    "[format_note_content] Word drift %.1f%% (%d → %d); "
                    "returning original",
                    drift * 100, before, after,
                )
                return md_content

        # Return the formatted content
        final_md = _placeholders_to_md(ai_result, valid_ids)
        logger.info(
            "[format_note_content] Formatted note for user_id=%s "
            "(%d chars → %d chars, %d diagrams)",
            user_id, len(md_content), len(final_md), len(valid_ids),
        )
        return final_md

    except Exception as e:
        logger.exception("[format_note_content] Unexpected error: %s", e)
        return md_content