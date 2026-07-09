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
import json

dotenv.load_dotenv()

GROQ_SYSTEM_PROMPT = r"""
You are NVLearn AI, the intent router for the NVLearn app.
Identify user intent. Handle normal chat requests directly. For notes, quizzes, and flashcards, ONLY extract the requested topic, source text, or instructions—never generate their actual content.
Respond ONLY with a valid JSON object. No extra text or markdown.
The JSON must contain exactly two arrays of equal length:
- "action": One or more of ["chat", "create_note", "edit_note", "create_quiz", "create_flashcard"].
- "content": Each item matches the same-index action.
  - "chat": A direct Markdown response.
  - All other actions: ONLY the extracted topic, note text, or instructions.
Examples:
{"action":["chat"],"content":["### Trigonometry\nTrigonometry is the study of **triangles**..."]}
{"action":["create_note","create_flashcard"],"content":["Photosynthesis overview","Photosynthesis vocabulary"]}
Use LaTeX for all math:
- Inline: `$...$`
- Display: `$$...$$`
- Never use plain `^` notation outside LaTeX.
Since the output is JSON, escape every LaTeX backslash (e.g. `"\\\\frac{a}{b}"`, `"\\\\tan(x)"`).
"""

GEMINI_SYSTEM_PROMPT = """You are NVLearn AI's content generation engine.
Generate high-quality study notes from the user's request.
Return ONLY valid JSON. Do not include markdown code fences or any extra text.
Schema:
{
  "title": "A concise, descriptive title",
  "content": "The complete note in Markdown"
}
Rules:
- Return only the JSON object.
- The title should be short (2 to 8 words) and accurately describe the note.
- The content should be well-structured Markdown using headings, lists, tables, and examples where appropriate.
- Be concise but comprehensive.
- Do not include conversational text such as "Sure" or "Here's your note."
- Do not explain your reasoning."""

SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
EMAIL = os.getenv('EMAIL')
EMAIL_PASSWORD = os.getenv('APP_PASSWORD')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

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

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

def ask_ai(contents,username):
    messages=[{'role':'system','content':GROQ_SYSTEM_PROMPT+f"username of user is:{username}"}]
    for msg in contents:
        role = msg.get('role')
        msg_content = msg.get('contents')
        if role == 'user':
            messages.append({'role': 'user', 'content':msg_content})
        elif role == 'assistant':
            messages.append({'role': 'assistant', 'content':msg_content})
    response = groq_client.chat.completions.create(
    messages=messages,
    model="llama-3.3-70b-versatile",
    response_format={"type": "json_object"}
    )
    response_json = json.loads(response.choices[0].message.content)
    if 'chat' in response_json['action']:
        reply = response_json['content'][response_json['action'].index('chat')]
    if 'create_note' in response_json['action']:
        instruction = response_json['content'][response_json['action'].index('create_note')]
        gemini_response = ask_gemini(question=f"Create note on:{instruction}")
        json_gemini_response = json.loads(gemini_response)
        json_gemini_response['html_content'] = markdown.markdown(json_gemini_response['content'],extensions=['fenced_code', 'tables'])
        return 'create_note', json_gemini_response

    html_output = markdown.markdown(reply, extensions=['fenced_code', 'tables','pymdownx.arithmatex'],extension_configs={
        'pymdownx.arithmatex': {
            'generic': True  
        }
    })
    return 'chat',html_output

def ask_gemini(question):
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=GEMINI_SYSTEM_PROMPT+f"prompt: {question}",
        config=types.GenerateContentConfig(
        response_mime_type="application/json",
    )
    )
    return response.text

