import smtplib
from email.message import EmailMessage
import dotenv
import os
import random
import threading
from google import genai
from google.genai import types
import markdown
from groq import Groq
from mistralai.client import Mistral
import json

dotenv.load_dotenv()

GROQ_SYSTEM_PROMPT = r"""
You are NVLearn AI's intent router. Refer to yourself as NVLearn AI or NVL AI. To users do not declare you are an intent router.

Respond ONLY with a valid JSON object containing exactly two arrays of equal length:

{
  "action": [...],
  "content": [...]
}

Valid actions:
- chat
- create_note
- edit_note
- create_quiz
- create_flashcard
- get_note
- note_action

Rules:
- chat: Respond directly to the user in Markdown.
- create_note, edit_note, create_quiz, create_flashcard: Extract ONLY the topic or instructions. Do NOT generate any content.
- get_note: Use only when the user explicitly requests the complete original note.
- note_action: Use for any operation on an existing note (e.g. summarize, extract key points, explain, rewrite, answer questions, find information, list formulas, convert format). Extract ONLY the requested operation or instructions.
- Support multiple actions by returning multiple entries in order(indices must be corresponding)
- Never invent missing information.

Examples:
{"action":["create_note"],"content":["Photosynthesis"]}
{"action":["note_action"],"content":["Summarize the note"]}
{"action":["get_note"],"content":["Hydraulic Lift"]}

Use LaTeX for math:
- Inline: `$...$`
- Display: `$$...$$`
- Escape backslashes in JSON (e.g. `"\\\\frac{a}{b}"`).

The username of the active user is provided in the initial user context context. Use it only if addressing them.
"""

GROQ_CHAT_ONLY_PROMPT = r"""
You are NVLearn AI. You are currently in chat-only mode because note-related services are temporarily unavailable due to high demand.

Respond ONLY with a valid JSON object:
{"action": ["chat"], "content": ["your response"]}

Rules:
- You can ONLY use the "chat" action. Do NOT use create_note, edit_note, create_quiz, create_flashcard, get_note, or note_action.
- If the user asks to create, edit, get, summarize, or perform any operation on notes, quizzes, or flashcards, politely inform them that note-related features are temporarily unavailable due to high demand and suggest trying again in a few minutes.
- Respond to general questions and conversations in Markdown.
- Use LaTeX for math: Inline: `$...$` Display: `$$...$$` Escape backslashes in JSON.
- The username of the active user is provided in the initial user context. Use it only if addressing them.
"""

GEMINI_SUMMARIZE_PROMPT = """You are NVLearn AI. Your task is to take a raw summary of recent background actions (which may include note creation results, user chat messages, or system errors) and turn it into a single, cohesive, and friendly response addressed directly to the user.

Rules:
- Speak directly to the user in a helpful, encouraging tone.
- Do not mention implementation details like "dictionary", "execution state", "arrays", or "backend results". 
- Smoothly blend multiple events together. For example, if a note was created but an error occurred elsewhere, acknowledge both naturally (e.g., "I've saved your new note! However, things are a bit busy right now, so I couldn't process your summary request. Let's try that part again in a few minutes.").
- Write your final response entirely in well-formatted Markdown.
- Return ONLY the final conversational message. Do not include conversational introduction filler like "Here is your response:" or wrap it in markdown code fences.
"""

GEMINI_NOTE_CREATION_PROMPT = """You are NVLearn AI's content generation engine.
Generate high-quality study notes from the user's request.
Return ONLY valid JSON. Do not include markdown code fences or any extra text.
Schema:
{
  "title": "A concise, descriptive title",
  "content": "The complete note in Markdown",
  "meta_data": {'tags':[tag1,tag2], 'summary': a short 2-3 sentence summary}
}
Rules:
- Return only the JSON object.
- The title should be short (2 to 8 words) and accurately describe the note.
- The content should be well-structured Markdown using headings, lists, tables, and examples where appropriate.
- Be concise but comprehensive.
- Do not include conversational text such as "Sure" or "Here's your note."
- Do not explain your reasoning.
- If asked for only metadata, return ONLY that based on content sent and metadata must follow the schema above."""

GEMINI_NOTE_ACTION_PROMPT = """
You are NVLearn AI's note processing engine.
You will receive:
- A user request describing what they want to do with the notes.
- The content of one or more notes.
Your task is to perform exactly what the user requests using ONLY the provided note content unless the user explicitly asks for external knowledge.
Possible requests include (but are not limited to):
- Summarizing notes
- Extracting key points
- Listing formulas, definitions, dates, or important facts
- Explaining a concept from the notes
- Finding or extracting information about a specific topic
- Answering questions using the notes
- Comparing concepts within the notes
- Organizing information into tables or lists
- Rewriting, simplifying, or improving the clarity of the notes
- Converting notes into a different format (e.g., bullet points, outline, timeline)
Rules:
- Follow the user's request exactly.
- Use ONLY information found in the provided notes unless the user explicitly instructs otherwise.
- Never invent facts or fill in missing information.
- If the requested information is not present in the notes, clearly state that it is not found.
- Preserve factual accuracy.
- Keep responses clear, concise, and well-organized.
- Use Markdown formatting whenever the output is textual.
- Do not explain your reasoning.
- Return ONLY the requested output. Do not include conversational text, JSON, markdown code fences, or any explanations.
"""

MISTRAL_SYSTEM_PROMPT = r"""
You are NVLearn AI's note retrieval engine.

Your task is to identify which existing notes are relevant to the user's request.

Input:
- User request
- A list of note metadata containing:
  - id
  - summary
  - tags

Return ONLY valid JSON:

{
  "note_ids": ["id1", "id2"]
}

Rules:
- Return only existing IDs from the provided metadata.
- Rank IDs from most relevant to least relevant.
- Return one ID if there is a clear best match.
- Return multiple IDs if the request relates to multiple notes.
- If no relevant note exists, return:
  {
    "note_ids": [], "msg":  "I could not find your notes about (topic)"
  }
- Never invent or modify IDs.
- Never answer the user's question.
- Never generate notes, quizzes, flashcards, or summaries.
- Never explain your reasoning.
- Never output anything except the JSON object.

Matching:
- Match semantically, not just by keywords.
- Consider summaries, tags, synonyms, abbreviations, and related concepts.
- For edit requests, prefer the most specific matching note.
- For retrieval requests, include all highly relevant notes, ordered by relevance.
"""

SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
EMAIL = os.getenv('EMAIL')
EMAIL_PASSWORD = os.getenv('APP_PASSWORD')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')

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
        return True
    except Exception:
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
    except Exception:
        return False

def md_to_html(content):
    html_content = markdown.markdown(content, extensions=['fenced_code', 'tables','pymdownx.arithmatex'],extension_configs={
            'pymdownx.arithmatex': {
                'generic': True  
            }
        })
    return html_content

def create_code():
    code = str(random.randint(100000, 999999))
    return code

def get_welcome_message(username):
    return random.choice([
    f"Ready to learn something new {username}?",
    f"What are we conquering today {username}?",
    f"Back for more? Let's dive in {username}.",
    f"What are we up to today {username}?",
    f"Let’s get it {username}.",
    f"What's the plan today {username}?",    
    f"Time to crush your goals {username}!",
    f"Make today count {username}!",
    f"Your future self will thank you {username}.",
    f"Ready to unlock your potential today {username}?"
])

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
mistral_client = Mistral(api_key = MISTRAL_API_KEY)

def is_rate_limit_error(e):
    """Check if an exception is a 429 / rate-limit error."""
    error_str = str(e).lower()
    if '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str or 'resource exhausted' in error_str:
        return True
    if hasattr(e, 'status_code') and e.status_code == 429:
        return True
    if hasattr(e, 'code') and e.code == 429:
        return True
    return False

def is_ai_error(response):
    """Check if an AI function returned a structured error dict."""
    return isinstance(response, dict) and response.get('error') is True


def ai_error(error_type, msg):
    return {'error': True, 'type': error_type, 'msg': msg}


def parse_json_object(raw, msg):
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return ai_error('invalid_json', msg)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ai_error('invalid_json', msg)
    if not isinstance(parsed, dict):
        return ai_error('invalid_json', msg)
    return parsed


def validate_router_response(response_json):
    if not isinstance(response_json, dict):
        return ai_error('invalid_json', 'NVLearn AI is currently experiencing some errors. Please try again.')
    actions = response_json.get('action')
    contents = response_json.get('content')
    if not isinstance(actions, list) or not isinstance(contents, list):
        return ai_error('invalid_json', 'NVLearn AI is currently experiencing some errors. Please try again.')
    if len(actions) != len(contents):
        return ai_error('invalid_json', 'NVLearn AI returned is currently experiencing some errors. Please try again.')
    valid_actions = {'chat', 'create_note', 'get_note', 'note_action'}
    if any(action not in valid_actions for action in actions):
        return ai_error('invalid_action', 'NVLearn AI is currently experiencing some errors. Please try again.')
    return None

def ask_groq(contents, username, metadata=False, chat_only=False):
    instructions = []
    if metadata:
        try:
            result = ask_gemini(f'Return the metadata of this note:\n{contents}', action='metadata')
            if is_ai_error(result):
                return 'error'
            json_metadata = parse_json_object(result, 'Metadata generation returned invalid JSON.')
            if is_ai_error(json_metadata) or not isinstance(json_metadata.get('meta_data'), dict):
                return 'error'
            return json_metadata['meta_data']
        except Exception:
            return 'error'

    system_prompt = GROQ_CHAT_ONLY_PROMPT if chat_only else GROQ_SYSTEM_PROMPT
    messages = [{'role': 'system', 'content': system_prompt + f"username of user is:{username}"}]
    for msg in contents:
        role = msg.get('role')
        msg_content = msg.get('contents')
        if role == 'user':
            messages.append({'role': 'user', 'content': msg_content})
        elif role == 'assistant':
            messages.append({'role': 'assistant', 'content': msg_content})
    try:
        response = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )
        response_json = parse_json_object(response.choices[0].message.content, 'NVLearn AI is currently experiencing some errors. Please try again.')
        if is_ai_error(response_json):
            return [{'action': 'error', 'content': response_json}]
        validation_error = validate_router_response(response_json)
        if validation_error:
            return [{'action': 'error', 'content': validation_error}]
    except Exception as e:
        if is_rate_limit_error(e):
            return [{'action': 'error', 'content': {'type': 'rate_limit', 'msg': 'NVLearn AI is receiving too many requests right now. Please wait a few minutes before trying again.'}}]
        return [{'action': 'error', 'content': {'type': 'api_error', 'msg': 'NVLearn AI is currently experiencing some issues. Please try again shortly.'}}]
    actions = response_json['action']
    for i, action in enumerate(actions):
        if action == 'chat':
            reply = response_json['content'][i]
            html_output = md_to_html(reply)
            instructions.append({'action': 'chat', 'content': html_output})
        elif action == 'create_note':
            instruction = response_json['content'][i]
            gemini_response = ask_gemini(question=f"Create note on:{instruction}", action='create_note')
            if is_ai_error(gemini_response):
                instructions.append({'action': 'error', 'content': gemini_response})
                continue
            json_gemini_response = parse_json_object(gemini_response, 'Note creation failed. Please try again.')
            if is_ai_error(json_gemini_response):
                instructions.append({'action': 'error', 'content': json_gemini_response})
                continue
            required_fields = {'title', 'content', 'meta_data'}
            if not required_fields.issubset(json_gemini_response) or not isinstance(json_gemini_response.get('meta_data'), dict):
                instructions.append({'action': 'error', 'content': ai_error('invalid_json', 'Note creation failed. Please try again.')})
                continue
            json_gemini_response['html_content'] = markdown.markdown(json_gemini_response['content'], extensions=['fenced_code', 'tables'])
            instructions.append({'action': 'create_note', 'content': json_gemini_response})
        elif action == 'get_note':
            instructions.append({'action': 'get_note', 'content': response_json['content'][i]})
        elif action == 'note_action':
            instructions.append({'action': 'note_action', 'content': response_json['content'][i]})
    return instructions
    
def ask_gemini(question, action):
    try:
        if action == 'create_note':
            response = gemini_client.models.generate_content(
                model="gemini-3.5-flash",
                contents=GEMINI_NOTE_CREATION_PROMPT + f"prompt: {question}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                )
            )
        elif action == 'note_action':
            response = gemini_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=GEMINI_NOTE_ACTION_PROMPT + f"prompt: {question}",
            )
            html_content = md_to_html(response.text)
            return html_content, response.text
        elif action == 'metadata':
            response = gemini_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=GEMINI_NOTE_CREATION_PROMPT + f"prompt: {question}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                )
            )
        elif action == 'summarize':
            response = gemini_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=GEMINI_SUMMARIZE_PROMPT + f"prompt: {question}",
            )
        return response.text
    except Exception as e:
        if is_rate_limit_error(e):
            return {'error': True, 'type': 'rate_limit', 'msg': 'Our AI services are experiencing high demand. Please avoid note-related requests for a few minutes.'}
        return {'error': True, 'type': 'api_error', 'msg': f'An error occurred while processing your {action.replace("_", " ")} request. Please try again later.'}

def ask_mistral(question):
    try:
        response = mistral_client.chat.complete(
            model="mistral-large-latest",
            response_format={"type": "json_object"},
            messages=[{'role': 'system', 'content': MISTRAL_SYSTEM_PROMPT}, {'role': 'user', 'content': question}]
        )
        response_json = parse_json_object(response.choices[0].message.content, 'Note search failed. Please try again.')
        if is_ai_error(response_json):
            return response_json
        note_ids = response_json.get('note_ids')
        if not isinstance(note_ids, list):
            return ai_error('invalid_json', 'Note search failed. Please try again.')
        return response_json
    except Exception as e:
        if is_rate_limit_error(e):
            return {'error': True, 'type': 'rate_limit', 'msg': 'Our note search service is experiencing high demand. Please avoid note-related requests for a few minutes.'}
        return {'error': True, 'type': 'api_error', 'msg': 'An error occurred while searching your notes. Please try again later.'}

