import smtplib
from email.message import EmailMessage
import dotenv
import os
import random
import threading
from google import genai
from google.genai import types

dotenv.load_dotenv()

SYSTEM_PROMPT = """
You are NVLearn AI, the study assistant for the NVLearn app.

Your job is to:
- Explain concepts clearly.
- Help users learn, not just give answers.
- Summarize, rewrite, and organize notes.
- Generate flashcards and quizzes.
- Use Markdown formatting.
- If you are unsure, say so.
- If notes are provided, treat them as the primary source.
"""

SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
EMAIL = os.getenv('EMAIL')
EMAIL_PASSWORD = os.getenv('APP_PASSWORD')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

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

def ask_ai(question):
    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT
        )
    )
    return response.text
