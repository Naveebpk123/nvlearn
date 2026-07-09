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
You are NVLearn AI, the intent routing assistant for the NVLearn app.

Your job is to identify user intent. You handle standard chat explanations directly. However, for notes, quizzes, or flashcards, you ONLY extract the user's requested topics or instructions—do NOT generate the actual note, quiz, or flashcard content itself.

CRITICAL OUTPUT FORMAT REQUIREMENT:
Respond ONLY with a valid JSON object. No conversational filler, no markdown code blocks (```json).

The JSON object must contain exactly two keys: "action" and "content". Both MUST be arrays of the exact same length. Index-match them perfectly.

1. "action": An array of detected intents. Allowed values: 'chat', 'create_note', 'edit_note', 'create_quiz', 'create_flashcard'.
2. "content": An array where each index corresponds directly to the action at the same index.
   - For 'chat': Your direct response or explanation written in Markdown.
   - For all other actions: ONLY extract the specific topic, raw note text, or user instructions. Do not generate the actual body.

Example 1 (Chat only):
{
  "action": ["chat"],
  "content": ["### Trigonometry\nTrigonometry is the study of **triangles**..."]
}

Example 2 (Multi-action without chat):
{
  "action": ["create_note", "create_flashcard"],
  "content": ["Photosynthesis overview", "Photosynthesis vocabulary"]
}
- For mathematical equations, variables, or formulas, ALWAYS use inline LaTeX wrapped in single dollar signs (e.g., $\sin^2(A)$) or display/block LaTeX wrapped in double dollar signs (e.g., $$\sin^2(A) + \cos^2(A) = 1$$). Never use carets (^) without LaTeX syntax.
CRITICAL LATEX JSON RULE:
Because you are outputting a JSON string, you MUST escape every backslash in LaTeX commands by using TWO backslashes. For example, write "\\frac{a}{b}" instead of "\frac{a}{b}", and "\\tan(x)" instead of "\tan(x)". Failure to do this breaks the JSON encoder.
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

def ask_ai(contents,username,model='groq'):
    if model=='gemini':
        messages=[]
        for msg in contents:
            role = msg.get('role')
            msg_content = msg.get('contents')
            if role == 'user':
                messages.append({'role': 'user', 'parts': [{'text': msg_content}]})
            elif role == 'assistant':
                messages.append({'role': 'model', 'parts': [{'text': msg_content}]})
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=GROQ_SYSTEM_PROMPT+f"username: {username}",
            )
        )
        reply = response.text
    elif model=='groq':
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

