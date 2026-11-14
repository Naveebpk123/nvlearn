"""
AI integrations — Gemini for content generation, Cloudflare Workers AI
for intent routing.

All validation helpers (is_ai_error, parse_json_object, etc.) live here
because they're only meaningful in the context of AI responses.

Env vars are read at import time; ensure `dotenv.load_dotenv()` has run
before this module is imported (app/config.py handles this on app
bootstrap).
"""

import json
import logging
import os

import requests
from google import genai
from google.genai import types

from prompts import (
    ACTION_SUMMARIZE_PROMPT,
    BATCH_SUMMARY_PROMPT,
    CHAT_ONLY_PROMPT,
    FLASHCARD_CREATION_PROMPT,
    NOTE_ACTION_PROMPT,
    NOTE_CREATION_PROMPT,
    NOTE_EDITING_PROMPT,
    NOTE_FORMATTING_PROMPT,
    QUIZ_CREATION_PROMPT,
    SYSTEM_PROMPT,
)
from utils import md_to_html

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# ── Error + validation helpers ────────────────────────────────────────

def is_rate_limit_error(e):
    """Check if an exception is a 429 / rate-limit error."""
    error_str = str(e).lower()
    if (
        "429" in error_str
        or "rate limit" in error_str
        or "too many requests" in error_str
        or "resource exhausted" in error_str
    ):
        return True
    if hasattr(e, "status_code") and e.status_code == 429:
        return True
    if hasattr(e, "code") and e.code == 429:
        return True
    return False


def is_ai_error(response):
    """Check if an AI function returned a structured error dict."""
    return isinstance(response, dict) and response.get("error") is True


def ai_error(error_type, msg):
    """Build a structured AI error dict."""
    return {"error": True, "type": error_type, "msg": msg}


def parse_json_object(raw, msg, allow_list=False):
    """Parse JSON from an AI response, returning a structured error on failure."""
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return ai_error("invalid_json", msg)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(
            "[parse_json_object] JSON decode error: %s | raw=%s", e, raw[:200]
        )
        return ai_error("invalid_json", msg)
    valid_types = (dict, list) if allow_list else dict
    if not isinstance(parsed, valid_types):
        return ai_error("invalid_json", msg)
    return parsed


def validate_router_response(response_json):
    """Validate the shape of a Cloudflare intent-router response."""
    if not isinstance(response_json, dict):
        return ai_error(
            "invalid_json",
            "NVLearn AI is currently experiencing some errors. Please try again.",
        )
    actions = response_json.get("action")
    contents = response_json.get("content")
    if not isinstance(actions, list) or not isinstance(contents, list):
        return ai_error(
            "invalid_json",
            "NVLearn AI is currently experiencing some errors. Please try again.",
        )
    if len(actions) != len(contents):
        return ai_error(
            "invalid_json",
            "NVLearn AI returned is currently experiencing some errors. Please try again.",
        )
    for i in range(len(actions)):
        if actions[i] == "create_flashcard":
            actions[i] = "create_flashcards"
    valid_actions = {
        "chat",
        "create_note",
        "get_note",
        "note_action",
        "create_flashcards",
        "create_quiz",
    }
    if any(action not in valid_actions for action in actions):
        invalid = [a for a in actions if a not in valid_actions]
        logger.warning(
            "[validate_router_response] Invalid actions found: %s", invalid
        )
        return ai_error(
            "invalid_action",
            "NVLearn AI is currently experiencing some errors. Please try again.",
        )
    return None


# ── Intent router (Cloudflare Workers AI) ────────────────────────────

def ask_intent_router(contents, username="", chat_only=False):
    system_prompt = CHAT_ONLY_PROMPT if chat_only else SYSTEM_PROMPT

    messages = [
        {
            "role": "system",
            "content": system_prompt
            + f"\nusername of user is: {username}\nRespond ONLY in valid JSON format matching the schema.",
        }
    ]

    for msg in contents:
        role = msg.get("role")
        msg_content = msg.get("contents")
        if role == "user":
            messages.append({"role": "user", "content": msg_content})
        elif role == "assistant":
            messages.append({"role": "assistant", "content": msg_content})

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/meta/llama-3.1-8b-instruct"
    )
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"messages": messages}

    try:
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 429:
            return ai_error(
                "rate_limit",
                "NVLearn AI is receiving too many requests right now. Please wait a few minutes before trying again.",
            )

        res_data = response.json()
        if not res_data.get("success", False):
            logger.error(
                "[ask_intent_router] Intent router returned error: %s", res_data
            )
            return ai_error(
                "api_error",
                "NVLearn AI is currently experiencing some issues. Please try again shortly.",
            )

        raw_content = res_data.get("result", {}).get("response", "")

        response_json = parse_json_object(
            raw_content,
            "NVLearn AI is currently experiencing some errors. Please try again.",
        )

        if is_ai_error(response_json):
            return response_json

        validation_error = validate_router_response(response_json)
        if validation_error:
            return validation_error

        return response_json

    except Exception as e:
        if is_rate_limit_error(e):
            logger.warning("[ask_intent_router] Rate limit hit: %s", e)
            return ai_error(
                "rate_limit",
                "NVLearn AI is receiving too many requests right now. Please wait a few minutes before trying again.",
            )
        logger.exception("[ask_intent_router] API error: %s", e)
        return ai_error(
            "api_error",
            "NVLearn AI is currently experiencing some issues. Please try again shortly.",
        )


# ── Instruction builder ──────────────────────────────────────────────

def build_ai_instructions(contents, username, metadata=False, chat_only=False):
    instructions = []

    if metadata:
        try:
            result = ask_gemini(
                f"Return the metadata of this note:\n{contents}", action="metadata"
            )
            if is_ai_error(result):
                return "error"
            json_metadata = parse_json_object(
                result, "Metadata generation returned invalid JSON."
            )
            if is_ai_error(json_metadata) or not isinstance(
                json_metadata.get("meta_data"), dict
            ):
                return "error"
            return json_metadata["meta_data"]
        except Exception as e:
            logger.exception(
                "[build_ai_instructions] Metadata generation failed: %s", e
            )
            return "error"

    response_json = ask_intent_router(contents, username, chat_only=chat_only)
    if is_ai_error(response_json):
        return [{"action": "error", "content": response_json}]

    actions = response_json["action"]
    for i, action in enumerate(actions):
        if action == "chat":
            reply = response_json["content"][i]
            html_output = md_to_html(reply)
            instructions.append({"action": "chat", "content": html_output})
        elif action == "create_note":
            instruction = response_json["content"][i]
            gemini_response = ask_gemini(
                question=f"Create note on:{instruction}", action="create_note"
            )
            if is_ai_error(gemini_response):
                instructions.append(
                    {"action": "error", "content": gemini_response}
                )
                continue
            json_gemini_response = parse_json_object(
                gemini_response, "Note creation failed. Please try again."
            )
            if is_ai_error(json_gemini_response):
                instructions.append(
                    {"action": "error", "content": json_gemini_response}
                )
                continue
            required_fields = {"title", "content", "meta_data"}
            if not required_fields.issubset(
                json_gemini_response
            ) or not isinstance(json_gemini_response.get("meta_data"), dict):
                instructions.append(
                    {
                        "action": "error",
                        "content": ai_error(
                            "invalid_json",
                            "Note creation failed. Please try again.",
                        ),
                    }
                )
                continue
            json_gemini_response["html_content"] = md_to_html(
                json_gemini_response["content"]
            )
            instructions.append(
                {"action": "create_note", "content": json_gemini_response}
            )
        elif action == "get_note":
            instructions.append(
                {"action": "get_note", "content": response_json["content"][i]}
            )
        elif action == "note_action":
            instructions.append(
                {"action": "note_action", "content": response_json["content"][i]}
            )
        elif action == "create_flashcards":
            instructions.append(
                {
                    "action": "create_flashcards",
                    "content": response_json["content"][i],
                }
            )
        elif action == "create_quiz":
            instructions.append(
                {"action": "create_quiz", "content": response_json["content"][i]}
            )
    return instructions


# ── Gemini caller ────────────────────────────────────────────────────

def ask_gemini(question, action):
    lite_models = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
    ]

    all_models = [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-3-flash",
    ]

    lite_only_actions = {"batch_summary", "metadata", "summarize"}
    models_to_try = lite_models if action in lite_only_actions else all_models

    def build_contents(prompt_prefix, payload):
        if isinstance(payload, list):
            text_prompt = prompt_prefix + f"prompt: {payload[0]}"
            return [text_prompt, *payload[1:]]
        return [prompt_prefix + f"prompt: {payload}"]

    last_error = None
    for model in models_to_try:
        try:
            if action == "create_note":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=build_contents(NOTE_CREATION_PROMPT, question),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                return response.text

            elif action == "note_action":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=build_contents(NOTE_ACTION_PROMPT, question),
                )
                html_content = md_to_html(response.text)
                return html_content, response.text

            elif action == "metadata":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=build_contents(NOTE_CREATION_PROMPT, question),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                return response.text

            elif action == "batch_summary":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=build_contents(BATCH_SUMMARY_PROMPT, question),
                )
                return response.text

            elif action == "summarize":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=build_contents(ACTION_SUMMARIZE_PROMPT, question),
                )
                return response.text

            elif action == "create_flashcards":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=build_contents(FLASHCARD_CREATION_PROMPT, question),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                parsed = parse_json_object(
                    response.text,
                    "Flashcard generation returned invalid format.",
                    allow_list=True,
                )
                if is_ai_error(parsed) or not isinstance(parsed, list):
                    return ai_error(
                        "invalid_json",
                        "Flashcard generation failed. Please try again.",
                    )
                return parsed

            elif action == "create_quiz":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=build_contents(QUIZ_CREATION_PROMPT, question),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                parsed = parse_json_object(
                    response.text,
                    "quiz generation returned invalid format.",
                    allow_list=True,
                )
                if is_ai_error(parsed) or not isinstance(parsed, list):
                    return ai_error(
                        "invalid_json",
                        "Quiz generation failed. Please try again.",
                    )
                return parsed

            elif action == "format_note":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=build_contents(NOTE_FORMATTING_PROMPT, question),
                )
                return response.text

            elif action == "edit_note":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=build_contents(NOTE_EDITING_PROMPT, question),
                    config=types.GenerateContentConfig(),
                )
                return response.text

        except Exception as e:
            last_error = e
            logger.warning(
                "[ask_gemini] Model '%s' failed for action='%s': %s",
                model, action, e,
            )
            continue

    if last_error and is_rate_limit_error(last_error):
        return {
            "error": True,
            "type": "rate_limit",
            "msg": "Our AI services are experiencing high demand. Please avoid note-related requests for a few minutes.",
        }

    return {
        "error": True,
        "type": "api_error",
        "msg": (
            f"An error occurred while processing your "
            f"{action.replace('_', ' ')} request. Please try again later."
        ),
    }