import smtplib
from email.message import EmailMessage
import dotenv
import os
import random
import threading
import logging
from google import genai
from google.genai import types
import markdown
from groq import Groq
from mistralai.client import Mistral
import json
from prompts import *

logger = logging.getLogger(__name__)

dotenv.load_dotenv()

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL = os.getenv("EMAIL")
EMAIL_PASSWORD = os.getenv("APP_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")


def send_email(recipient, subject, msg_content):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL
    msg["To"] = recipient
    msg.set_content(msg_content)
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL, EMAIL_PASSWORD)
            server.send_message(msg)
        logger.info(
            "[send_email] Email sent successfully to %s (subject: %s)",
            recipient,
            subject,
        )
        return True
    except Exception as e:
        logger.exception(
            "[send_email] Failed to send email to %s (subject: %s): %s",
            recipient,
            subject,
            e,
        )
        raise Exception


def send_email_threaded(recipient, subject, msg_content):
    try:
        thread = threading.Thread(
            target=send_email,
            args=(recipient, subject, msg_content),
            daemon=True,
        )
        thread.start()
        return True
    except Exception as e:
        logger.error(
            "[send_email_threaded] Failed to start email thread for %s: %s",
            recipient,
            e,
        )
        return False


def md_to_html(content):
    html_content = markdown.markdown(
        content,
        extensions=["fenced_code", "tables", "pymdownx.arithmatex"],
        extension_configs={"pymdownx.arithmatex": {"generic": True}},
    )
    return html_content


def create_code():
    code = str(random.randint(100000, 999999))
    return code


def get_welcome_message(username):
    return random.choice(
        [
            f"Ready to learn something new {username}?",
            f"What are we conquering today {username}?",
            f"Back for more? Let's dive in {username}.",
            f"What are we up to today {username}?",
            f"Let’s get it {username}.",
            f"What's the plan today {username}?",
            f"Time to crush your goals {username}!",
            f"Make today count {username}!",
            f"Your future self will thank you {username}.",
            f"Ready to unlock your potential today {username}?",
        ]
    )


gemini_client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
mistral_client = Mistral(api_key=MISTRAL_API_KEY)


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
    """Helper function to create JSON for error messages"""
    return {"error": True, "type": error_type, "msg": msg}


def parse_json_object(raw, msg, allow_list=False):
    """Parse JSON and handle errors"""
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return ai_error("invalid_json", msg)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("[parse_json_object] JSON decode error: %s | raw=%s", e, raw[:200])
        return ai_error("invalid_json", msg)
    valid_types = (dict, list) if allow_list else dict
    if not isinstance(parsed, valid_types):
        return ai_error("invalid_json", msg)
    return parsed


def validate_router_response(response_json):
    """Helper function to validate actions and responses of AI"""
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
        logger.warning("[validate_router_response] Invalid actions found: %s", invalid)
        return ai_error(
            "invalid_action",
            "NVLearn AI is currently experiencing some errors. Please try again.",
        )
    return None


def ask_groq(contents, username="", chat_only=False):
    system_prompt = GROQ_CHAT_ONLY_PROMPT if chat_only else GROQ_SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system_prompt + f"username of user is:{username}"}
    ]
    for msg in contents:
        role = msg.get("role")
        msg_content = msg.get("contents")
        if role == "user":
            messages.append({"role": "user", "content": msg_content})
        elif role == "assistant":
            messages.append({"role": "assistant", "content": msg_content})
    try:
        response = groq_client.chat.completions.create(
            messages=messages,
            model="qwen/qwen3.6-27b",
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        response_json = parse_json_object(
            response.choices[0].message.content,
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
            logger.warning("[ask_groq] Rate limit hit: %s", e)
            return ai_error(
                "rate_limit",
                "NVLearn AI is receiving too many requests right now. Please wait a few minutes before trying again.",
            )
        logger.exception("[ask_groq] API error: %s", e)
        return ai_error(
            "api_error",
            "NVLearn AI is currently experiencing some issues. Please try again shortly.",
        )


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

    response_json = ask_groq(contents, username, chat_only=chat_only)
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
                instructions.append({"action": "error", "content": gemini_response})
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
            if not required_fields.issubset(json_gemini_response) or not isinstance(
                json_gemini_response.get("meta_data"), dict
            ):
                instructions.append(
                    {
                        "action": "error",
                        "content": ai_error(
                            "invalid_json", "Note creation failed. Please try again."
                        ),
                    }
                )
                continue
            json_gemini_response["html_content"] = markdown.markdown(
                json_gemini_response["content"], extensions=["fenced_code", "tables"]
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
                {"action": "create_flashcards", "content": response_json["content"][i]}
            )
        elif action == "create_quiz":
            instructions.append(
                {"action": "create_quiz", "content": response_json["content"][i]}
            )
    return instructions


def ask_gemini(question, action):
    models = [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.0-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]
    last_error = None
    for model in models:
        try:
            if action == "create_note":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=GEMINI_NOTE_CREATION_PROMPT + f"prompt: {question}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                return response.text
            elif action == "note_action":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=GEMINI_NOTE_ACTION_PROMPT + f"prompt: {question}",
                )
                html_content = md_to_html(response.text)
                return html_content, response.text
            elif action == "metadata":
                response = gemini_client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=GEMINI_NOTE_CREATION_PROMPT + f"prompt: {question}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                return response.text
            elif action == "summarize":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=GEMINI_SUMMARIZE_PROMPT + f"prompt: {question}",
                )
                return response.text
            elif action == "create_flashcards":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=GEMINI_FLASHCARD_CREATION_PROMPT + f"prompt: {question}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                parsed = parse_json_object(
                    response.text,
                    "Flashcard generation returned invalid format.",
                    allow_list=True,
                )
                if is_ai_error(parsed):
                    return ai_error(
                        "invalid_json", "Flashcard generation failed. Please try again."
                    )
                if not isinstance(parsed, list):
                    return ai_error(
                        "invalid_json", "Flashcard generation returned invalid format."
                    )
                return parsed
            elif action == "create_quiz":
                response = gemini_client.models.generate_content(
                    model=model,
                    contents=GEMINI_QUIZ_CREATION_PROMPT + f"prompt: {question}",
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                parsed = parse_json_object(
                    response.text,
                    "quiz generation returned invalid format.",
                    allow_list=True,
                )
                if is_ai_error(parsed):
                    return ai_error(
                        "invalid_json", "Quiz generation failed. Please try again."
                    )
                if not isinstance(parsed, list):
                    return ai_error(
                        "invalid_json", "Quiz generation returned invalid format."
                    )
                return parsed
        except Exception as e:
            last_error = e
            logger.warning(
                "[ask_gemini] Model '%s' failed for action='%s': %s", model, action, e
            )
            continue

    if last_error and is_rate_limit_error(last_error):
        logger.warning(
            "[ask_gemini] All models exhausted (rate limited) for action='%s'", action
        )
        return {
            "error": True,
            "type": "rate_limit",
            "msg": "Our AI services are experiencing high demand. Please avoid note-related requests for a few minutes.",
        }
    logger.error(
        "[ask_gemini] All models exhausted for action='%s'. Last error: %s",
        action,
        last_error,
    )
    return {
        "error": True,
        "type": "api_error",
        "msg": f'An error occurred while processing your {action.replace("_", " ")} request. Please try again later.',
    }


def ask_mistral(question):
    try:
        response = mistral_client.chat.complete(
            model="mistral-large-latest",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": MISTRAL_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
        response_json = parse_json_object(
            response.choices[0].message.content, "Note search failed. Please try again."
        )
        if is_ai_error(response_json):
            return response_json
        note_ids = response_json.get("note_ids")
        if not isinstance(note_ids, list):
            return ai_error("invalid_json", "Note search failed. Please try again.")
        return response_json
    except Exception as e:
        if is_rate_limit_error(e):
            logger.warning("[ask_mistral] Rate limit hit: %s", e)
            return {
                "error": True,
                "type": "rate_limit",
                "msg": "Our note search service is experiencing high demand. Please avoid note-related requests for a few minutes.",
            }
        logger.exception("[ask_mistral] API error: %s", e)
        return {
            "error": True,
            "type": "api_error",
            "msg": "An error occurred while searching your notes. Please try again later.",
        }
