from email_utils import send_email
import os

def test_send_email():
    print("Testing email sending...")
    subject = "Test Email from Trae Agent"
    body = "This is a test email to verify the email notification functionality. http://obs.dimond.top/test_link"
    
    success = send_email(subject, body)
    if success:
        print("Email sent successfully!")
    else:
        print("Failed to send email.")

if __name__ == "__main__":
    test_send_email()
