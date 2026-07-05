import smtplib
from email.message import EmailMessage
import dotenv
import os
import random
import threading

dotenv.load_dotenv()

SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
EMAIL = os.getenv('EMAIL')
EMAIL_PASSWORD = os.getenv('APP_PASSWORD')

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
