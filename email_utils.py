import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
from dotenv import load_dotenv

load_dotenv()

def send_email(subject, body, to_addr="939342547@qq.com"):
    sender = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_PASSWORD")
    
    if not sender or not password:
        print("Email credentials not found in .env")
        return False

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['From'] = Header(sender)
    msg['To'] = Header(to_addr)
    msg['Subject'] = Header(subject, 'utf-8')

    try:
        # QQ mail uses port 465 for SSL or 587 for TLS
        smtp_server = "smtp.qq.com"
        server = smtplib.SMTP_SSL(smtp_server, 465)
        server.login(sender, password)
        server.sendmail(sender, [to_addr], msg.as_string())
        server.quit()
        print(f"Email sent to {to_addr} with subject: {subject}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
