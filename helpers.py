import smtplib
from email.message import EmailMessage
import dotenv
import os

dotenv.load_dotenv()

SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
EMAIL = os.getenv('EMAIL')
EMAIL_PASSWORD = os.getenv('APP_PASSWORD')

def send_email(recipient,subject, msg_content):
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
            print("Email sent successfully!")
        
    except Exception as e:
        print(f"An error occurred: {e}")


