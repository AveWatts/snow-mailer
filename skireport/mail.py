import os
import smtplib
from email.message import EmailMessage


def send(subject, text_body, html_body):
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = os.environ["REPORT_TO"]
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, os.environ["SMTP_APP_PASSWORD"])
        s.send_message(msg)
