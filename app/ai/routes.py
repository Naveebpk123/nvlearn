from collections import Counter
from datetime import datetime, timezone, timedelta

from flask import current_app, jsonify, render_template, request, session
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from . import bp
from ..config import Config
from ..extensions import db
from ..models import Flashcard, Note, Quiz
from ..services.diagram_service import prepare_note_and_diagrams
from ..services.metadata_service import normalize_metadata
from ..services.note_service import (
    check_mermaid,
    chunk_notes_content,
    extract_topic_for_search,
    get_notes_for_action,
    get_vector_matched_notes,
    summarize_notes_in_batches,
)
from helpers import (
    ask_gemini,
    build_ai_instructions,
    get_welcome_message,
    is_ai_error,
    md_to_html,
)
from vector_store import upsert_note_vector

@bp.route("/ai-chat")
@login_required
def ai_chat():
    welcome_message = get_welcome_message(current_user.name)
    return render_template("ai-chat.html", welcome_message=welcome_message)


"""
Route: /ai-response [POST]
Description: Multi-step AI orchestrator endpoint. Accepts message history context, enforces action cooldowns,
invokes Gemini AI with instructions, executes actions (create_note, get_note, note_action, flashcards/quizzes),
performs vector search retrieval on ChromaDB, and returns structured JSON responses for frontend bubbles.
"""
@bp.route("/ai-response", methods=["POST"])
@login_required
def ai_response():
    username = current_user.name
    data = request.get_json()
    message = data.get("contents")

    cooldown_until = session.get("note_action_cooldown_until")
    is_on_cooldown = (
        cooldown_until and datetime.now(timezone.utc).timestamp() < cooldown_until
    )

    all_instructions = build_ai_instructions(
        contents=message, username=username, chat_only=is_on_cooldown
    )
    current_app.logger.info(
        "[ai_response] Instructions built for user_id=%s: %s", current_user.id, all_instructions)
    all_results = []
    all_get_notes = ""
    note_action_html_content = ""
    flashcard_id = None
    quiz_id = None
    chat = None
    all_errors = []
    hit_rate_limit = False
    mermaid_notes = [] #List to store notes with mermaid diagrams

    for instruction in all_instructions:
        action = instruction["action"]
        ai_reply = instruction["content"]

        if action == "error":
            if isinstance(ai_reply, dict):
                current_app.logger.error(
                    "[ai_response] AI error (type=%s): %s",
                    ai_reply.get("type"),
                    ai_reply.get("msg"),
                )
                all_errors.append(
                    ai_reply.get(
                        "msg", "An unexpected error occurred. Please try again later."
                    )
                )
                if ai_reply.get("type") == "rate_limit":
                    hit_rate_limit = True
            else:
                current_app.logger.error(
                    "[ai_response] AI returned unexpected non-dict error: %s", ai_reply
                )
                all_errors.append(
                    "NVLearn AI encountered an unexpected error. Please try again later."
                )

        elif action == "chat":
            chat = ai_reply

        elif action == "create_note":
            try:
                new_note = Note(
                    title=ai_reply["title"],
                    md_content=ai_reply["content"],
                    html_content=ai_reply["html_content"],
                    in_bin=False,
                    user_id=current_user.id,
                    meta_data=normalize_metadata(ai_reply.get("meta_data")),
                )
                db.session.add(new_note)
                db.session.flush()
                new_note.meta_data = normalize_metadata(new_note.meta_data, new_note.id)
                db.session.commit()
                upsert_note_vector(new_note)
                has_mermaid = check_mermaid(new_note.md_content)
                if has_mermaid:
                    mermaid_notes.append({"note_id": new_note.id, "md_content": new_note.md_content})
                all_results.append(f"Made new note '{ai_reply['title']}'")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(
                    "[ai_response/create_note] DB error saving AI-created note for user_id=%s: %s",
                    current_user.id,
                    e,
                )
                all_errors.append(
                    "An error occurred while saving the new note to the database. Please try again."
                )

        elif action == "get_note":
            if ai_reply == "all_notes":
                try:
                    result = db.session.execute(
                        db.select(Note)
                        .where(Note.user_id == current_user.id)
                        .where(Note.in_bin != True)
                    )
                    matched_notes = result.scalars().all()
                    note_content_list = ""
                    for note in matched_notes:
                        note_content_list += (note.html_content or "") + "\n"
                    all_get_notes += note_content_list
                except SQLAlchemyError as e:
                    current_app.logger.error(
                        "[ai_response/get_note] DB error fetching all notes for user_id=%s: %s",
                        current_user.id,
                        e,
                    )
                    all_errors.append(
                        "An error occurred while fetching your notes. Please try again later."
                    )
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_vector_matched_notes(
                search_topic, current_user.id
            )
            note_content_list = ""

            if vector_error:
                current_app.logger.error(
                    "[ai_response/get_note] Vector search error: %s",
                    vector_msg,
                )
                all_errors.append(
                    vector_msg
                    or "An error occurred while fetching notes. Please try again later."
                )
            else:
                if matched_notes:
                    for note in matched_notes:
                        note_content_list += (note.html_content or "") + "\n"
                else:
                    all_results.append(
                        vector_msg or f"I could not find your notes about {search_topic}."
                    )
            all_get_notes += note_content_list

        elif action == "note_action":
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_notes_for_action(
                search_topic, current_user.id
            )

            if vector_error:
                current_app.logger.error(
                    "[ai_response/note_action] Note retrieval error: %s",
                    vector_msg,
                )
                all_errors.append(
                    vector_msg
                    or "An error occurred while searching for notes. Please try again later."
                )
                continue

            if not matched_notes:
                all_results.append(
                    vector_msg or f"I could not find your notes about {search_topic}."
                )
                continue

            batches = chunk_notes_content(matched_notes, user_id=current_user.id)
            if len(batches) > 1:
                accumulated_summary, hit_rl, err_dict = summarize_notes_in_batches(batches)
                if accumulated_summary:
                    note_action_html_content += md_to_html(accumulated_summary) + "\n"
                if hit_rl:
                    hit_rate_limit = True
                    all_errors.append("Rate limit reached during batch processing. Partial summary returned.")
                elif err_dict:
                    all_errors.append(err_dict.get("msg", "An error occurred during note processing."))
            else:
                batch_item = batches[0] if batches else ""
                if isinstance(batch_item, list):
                    note_content_text = batch_item[0]
                    note_images = batch_item[1:]
                else:
                    note_content_text = batch_item
                    note_images = []

                prompt_text = f"Instructions:{ai_reply} content:{note_content_text}"
                prompt_payload = [prompt_text, *note_images] if note_images else prompt_text

                gemini_result = ask_gemini(
                    action="note_action",
                    question=prompt_payload,
                )
                if is_ai_error(gemini_result):
                    current_app.logger.error(
                        "[ai_response/note_action] Gemini error (type=%s): %s",
                        gemini_result.get("type"),
                        gemini_result.get("msg"),
                    )
                    all_errors.append(
                        gemini_result.get(
                            "msg",
                            "An error occurred while processing notes. Please try again later.",
                        )
                    )
                    if gemini_result.get("type") == "rate_limit":
                        hit_rate_limit = True
                else:
                    response_html, _ = gemini_result
                    note_action_html_content += response_html + "\n"

        elif action == 'edit_note':
            
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_notes_for_action(
                search_topic, current_user.id, edit_mode=True
            )            
            matched_note = matched_notes[0] if matched_notes else None

            if vector_error:
                current_app.logger.error(
                    "[ai_response/note_action] Note retrieval error: %s",
                    vector_msg,
                )
                all_errors.append(
                    vector_msg
                    or "An error occurred while searching for notes. Please try again later."
                )
                continue

            if not matched_note:
                all_results.append(
                    vector_msg or f"I could not find your notes about {search_topic}."
                )
                continue
            if matched_note:
                cleaned_md, images = prepare_note_and_diagrams(matched_note.md_content, current_user.id)
                prompt_text = f"Instruction: {ai_reply} note: {cleaned_md}"
                prompt_payload = [prompt_text, *images] if images else prompt_text

                edited_note = ask_gemini(
                    action="edit_note",
                    question=prompt_payload
                )
                if is_ai_error(edited_note):
                    current_app.logger.error(
                        "[ai_response/edit_note] Gemini error (type=%s): %s",
                        edited_note.get("type"),
                        edited_note.get("msg"),
                    )
                    all_errors.append(
                        edited_note.get(
                            "msg",
                            "An error occurred while editing the note. Please try again later.",
                        )
                    )
                    if edited_note.get("type") == "rate_limit":
                        hit_rate_limit = True
                else:
                    try:
                        matched_note.md_content = edited_note
                        matched_note.html_content = md_to_html(edited_note)
                        db.session.commit()
                        upsert_note_vector(matched_note)
                        has_mermaid = check_mermaid(matched_note.md_content) 
                        if has_mermaid:
                            mermaid_notes.append({"note_id": matched_note.id, "md_content": matched_note.md_content})
                    except SQLAlchemyError as e:
                        db.session.rollback()
                        current_app.logger.error(
                            "[ai_response/edit_note] DB error updating note_id=%s for user_id=%s: %s",
                            matched_note.id,
                            current_user.id,
                            e,
                        )
                        all_errors.append(
                            "An error occurred while saving the edited note to the database. Please try again."
                        )
        elif action == "create_flashcards":
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_notes_for_action(
                search_topic, current_user.id
            )
            note_content_payload = ""

            if vector_error:
                current_app.logger.warning(
                    "[ai_response/create_flashcards] Note search failed, falling back to topic. msg=%s",
                    vector_msg,
                )
                note_content_payload = f"Topic: {ai_reply}"
            else:
                if matched_notes:
                    batches = chunk_notes_content(matched_notes, user_id=current_user.id)
                    if len(batches) > 1:
                        accumulated_summary, hit_rl, err_dict = summarize_notes_in_batches(batches)
                        if hit_rl or err_dict or not accumulated_summary:
                            if hit_rl:
                                hit_rate_limit = True
                            all_errors.append(
                                "AI service is busy or rate limited. Please avoid using note-related actions for a while."
                            )
                            continue
                        note_content_payload = accumulated_summary
                    else:
                        batch_item = batches[0] if batches else f"Topic: {ai_reply}"
                        if isinstance(batch_item, list):
                            note_content_payload = [batch_item[0], *batch_item[1:]]
                        else:
                            note_content_payload = batch_item
                else:
                    note_content_payload = f"Topic: {ai_reply}"

            gemini_result = ask_gemini(
                action="create_flashcards", question=note_content_payload
            )
            if is_ai_error(gemini_result):
                current_app.logger.error(
                    "[ai_response/create_flashcards] Gemini flashcard generation failed (type=%s): %s",
                    gemini_result.get("type"),
                    gemini_result.get("msg"),
                )
                all_errors.append(
                    gemini_result.get(
                        "msg",
                        "An error occurred while processing notes. Flashcard could not be created. Please try again later.",
                    )
                )
                if gemini_result.get("type") == "rate_limit":
                    hit_rate_limit = True
            else:
                flashcard = Flashcard(card_data=gemini_result, user_id=current_user.id)
                db.session.add(flashcard)
                db.session.commit()
                flashcard_id = flashcard.id
                all_results.append(f"Created flashcards on topic: {ai_reply}")

        elif action == "create_quiz":
            search_topic = extract_topic_for_search(str(ai_reply))
            matched_notes, vector_msg, vector_error = get_notes_for_action(
                search_topic, current_user.id
            )
            note_content_payload = ""
            collected_tags = []

            if vector_error:
                current_app.logger.warning(
                    "[ai_response/create_quiz] Note search failed, falling back to topic. msg=%s",
                    vector_msg,
                )
                note_content_payload = f"Topic: {ai_reply}"
            else:
                if matched_notes:
                    for note in matched_notes:
                        if isinstance(note.meta_data, dict):
                            collected_tags.extend(note.meta_data.get("tags", []))
                    batches = chunk_notes_content(matched_notes, user_id=current_user.id)
                    if len(batches) > 1:
                        accumulated_summary, hit_rl, err_dict = summarize_notes_in_batches(batches)
                        if hit_rl or err_dict or not accumulated_summary:
                            if hit_rl:
                                hit_rate_limit = True
                            all_errors.append(
                                "AI service is busy or rate limited. Please avoid using note-related actions for a while."
                            )
                            continue
                        note_content_payload = accumulated_summary
                    else:
                        batch_item = batches[0] if batches else f"Topic: {ai_reply}"
                        if isinstance(batch_item, list):
                            note_content_payload = [batch_item[0], *batch_item[1:]]
                        else:
                            note_content_payload = batch_item
                else:
                    note_content_payload = f"Topic: {ai_reply}"

            gemini_result = ask_gemini(action="create_quiz", question=note_content_payload)
            if is_ai_error(gemini_result):
                current_app.logger.error(
                    "[ai_response/create_quiz] Gemini quiz generation failed (type=%s): %s",
                    gemini_result.get("type"),
                    gemini_result.get("msg"),
                )
                all_errors.append(
                    gemini_result.get(
                        "msg",
                        "An error occurred while processing notes. Quiz could not be created. Please try again later.",
                    )
                )
                if gemini_result.get("type") == "rate_limit":
                    hit_rate_limit = True
            else:
                if collected_tags:
                    tag_counts = Counter(collected_tags)
                    quiz_tags = [tag for tag, count in tag_counts.most_common(5)]
                else:
                    quiz_tags = [ai_reply.strip()]

                quiz_obj = Quiz(
                    quiz_data=gemini_result, user_id=current_user.id, tags=quiz_tags
                )
                db.session.add(quiz_obj)
                db.session.commit()
                quiz_id = quiz_obj.id
                all_results.append(f"Created quiz on topic: {ai_reply}")

    if hit_rate_limit:
        session["note_action_cooldown_until"] = (
            datetime.now(timezone.utc) + timedelta(seconds=Config.NOTE_ACTION_COOLDOWN_SECONDS)
        ).timestamp()
        cooldown_msg = "Note-related features are temporarily paused due to high demand. You can still chat normally — note features will be back in about 5 minutes."
        if cooldown_msg not in all_errors:
            all_errors.append(cooldown_msg)

    final_result = {"results": all_results, "errors": all_errors, "chat": chat}
    errors = len(all_errors)
    results = len(all_results)

    if (
        results == 0
        and errors == 0
        and not chat
        and note_action_html_content
        and all_get_notes == ""
    ):
        return jsonify(
            {
                "note_action": note_action_html_content,
                "flashcard_id": flashcard_id,
                "quiz_id": quiz_id,
                "mermaid_notes": mermaid_notes,
            }
        )

    if results <= 1 and errors <= 1 and not chat and not note_action_html_content:
        if results == 1 and errors == 0 and all_get_notes == "":
            return jsonify(
                {
                    "chat": all_results[0],
                    "flashcard_id": flashcard_id,
                    "quiz_id": quiz_id,
                    "mermaid_notes": mermaid_notes,
                }
            )
        elif results == 0 and errors == 1 and all_get_notes == "":
            return jsonify(
                {
                    "chat": all_errors[0],
                    "flashcard_id": flashcard_id,
                    "quiz_id": quiz_id,
                    "mermaid_notes": mermaid_notes,
                }
            )
        elif results == 0 and errors == 0 and all_get_notes != "":
            return jsonify(
                {
                    "chat": all_get_notes,
                    "flashcard_id": flashcard_id,
                    "quiz_id": quiz_id,
                    "mermaid_notes": mermaid_notes,
                }
            )
    if results == 0 and errors == 0 and chat:
        return jsonify({"chat": chat, "flashcard_id": flashcard_id, "quiz_id": quiz_id, "mermaid_notes": mermaid_notes})

    final_summary = ask_gemini(question=final_result, action="summarize")
    if is_ai_error(final_summary):
        current_app.logger.error(
            "[ai_response] Gemini summarize failed (type=%s): %s",
            final_summary.get("type"),
            final_summary.get("msg"),
        )
        final_summary = (
            chat or "An error occurred while executing your task. Please try again."
        )
    output = {
        "chat": md_to_html(final_summary),
        "notes": all_get_notes,
        "note_action": note_action_html_content,
        "flashcard_id": flashcard_id,
        "quiz_id": quiz_id,
        "mermaid_notes": mermaid_notes,
    }
    return jsonify(output)