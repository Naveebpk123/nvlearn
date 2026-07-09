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
    print(response_json)
    if 'chat' in response_json['action']:
        reply = response_json['content'][response_json['action'].index('chat')]

    html_output = markdown.markdown(reply, extensions=['fenced_code', 'tables','pymdownx.arithmatex'],extension_configs={
        'pymdownx.arithmatex': {
            'generic': True  
        }
    })
    return html_output

def ask_gemini(question):
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=messages,
    )
    return response.text

