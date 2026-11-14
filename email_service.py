"""
SMTP email integration.

Wraps smtplib for sending verification codes and other transactional
emails. Env vars are read at import time; ensure `dotenv.load_dotenv()`
has run before this module is imported (app/config.py handles this on
app bootstrap).
"""

import logging
import os
import smtplib
import threading
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL = os.getenv("EMAIL")
EMAIL_PASSWORD = os.getenv("APP_PASSWORD")


def send_email(recipient, subject, msg_content):
    """Send an email synchronously. Raises on failure."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL
    msg["To"] = recipient
    msg.set_content(msg_content)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL, EMAIL_PASSWORD)
            server.send_message(msg)
        logger.info(
            "[send_email] Email sent successfully to %s (subject: %s)",
            recipient, subject,
        )
        return True
    except Exception as e:
        logger.exception(
            "[send_email] Failed to send email to %s (subject: %s): %s",
            recipient, subject, e,
        )
        raise


def send_email_threaded(recipient, subject, msg_content):
    """Send an email in a background thread. Returns True if the thread started."""
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
            recipient, e,
        )
        return False