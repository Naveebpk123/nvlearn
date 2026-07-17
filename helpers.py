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
- Support multiple actions by returning multiple entries in order.
- Never invent missing information.

Examples:
{"action":["create_note"],"content":["Photosynthesis"]}
{"action":["note_action"],"content":["Summarize the note"]}
{"action":["get_note"],"content":["Hydraulic Lift"]}

Use LaTeX for math:
- Inline: `$...$`
- Display: `$$...$$`
- Escape backslashes in JSON (e.g. `"\\\\frac{a}{b}"`).
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
        return True, f"Email sent successfully to {recipient}."
    except Exception as e:
        return False, f"Failed to send email to {recipient}: {e}"


def send_email_threaded(recipient, subject, msg_content):
    thread = threading.Thread(
        target=send_email,
        args=(recipient, subject, msg_content),
        daemon=True,
    )
    thread.start()
    return True, f"Email delivery started for {recipient}."

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

def ask_groq(contents,username,metadata=False):
    if metadata:
        try:
            metadata = ask_gemini(f'Return the metadata of this note:\n{contents}',action='metadata')
            json_metadata = json.loads(metadata)
            print(json_metadata)
            return json_metadata['meta_data']
        except Exception:
            return 'error'

    messages=[{'role':'system','content':GROQ_SYSTEM_PROMPT+f"username of user is:{username}"}]
    for msg in contents:
        role = msg.get('role')
        msg_content = msg.get('contents')
        if role == 'user':
            messages.append({'role': 'user', 'content':msg_content})
        elif role == 'assistant':
            messages.append({'role': 'assistant', 'content':msg_content})
    try:
        response = groq_client.chat.completions.create(
        messages=messages,
        model="llama-3.3-70b-versatile",
        response_format={"type": "json_object"}
        )
        response_json = json.loads(response.choices[0].message.content)
    except Exception:
        return 'error','error'
    action = response_json['action']
    if 'chat' in action:
        reply = response_json['content'][action.index('chat')]
    if 'create_note' in action:
        instruction = response_json['content'][action.index('create_note')]
        gemini_response = ask_gemini(question=f"Create note on:{instruction}",action = 'create_note')
        if gemini_response == 'error':
            return 'error','error'
        json_gemini_response = json.loads(gemini_response)
        json_gemini_response['html_content'] = markdown.markdown(json_gemini_response['content'],extensions=['fenced_code', 'tables'])
        return 'create_note', json_gemini_response
    if 'get_note' in action:
        return 'get_note', response_json['content'][action.index('get_note')]
    if 'note_action' in action:
        return 'note_action', response_json['content'][action.index('note_action')]

    html_output = markdown.markdown(reply, extensions=['fenced_code', 'tables','pymdownx.arithmatex'],extension_configs={
        'pymdownx.arithmatex': {
            'generic': True  
        }
    })
    return 'chat',html_output

def ask_gemini(question,action):
    try:
        if action == 'create_note':
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=GEMINI_NOTE_CREATION_PROMPT+f"prompt: {question}",
                config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
            )
        if action == 'note_action':
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=GEMINI_NOTE_ACTION_PROMPT+f"prompt: {question}",         
            )
            html_content = markdown.markdown(response.text, extensions=['fenced_code', 'tables','pymdownx.arithmatex'],extension_configs={
            'pymdownx.arithmatex': {
                'generic': True  
            }
        })
            return html_content

        if action =='metadata':
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=GEMINI_NOTE_CREATION_PROMPT+f"prompt: {question}",config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
            )
        return response.text
    except Exception:
        return 'error'
def ask_mistral(question):
    try:
        response = mistral_client.chat.complete(
        model="mistral-large-latest",
        response_format={"type": "json_object"},
        messages=[{'role':'system','content':(MISTRAL_SYSTEM_PROMPT)},{'role':'user','content':question}]    
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return 'error'

