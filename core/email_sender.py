"""
GEOPulse Email Sender — Gmail API Integration

Sends HTML emails via Gmail API or SMTP fallback.
Used by:
  - driver_feed.py (Friday driver coaching emails)
  - manager_email.py (daily morning briefs)

Setup:
  1. Enable Gmail API in Google Cloud Console
  2. Create OAuth2 credentials
  3. Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN in .env
"""

import os
import logging
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.audio import MIMEAudio
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def send_email(to_email, subject, html_content, from_name="GEOPulse", attachment_path=None):
    """
    Send an HTML email via Gmail API or SMTP fallback.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_content: HTML body content
        from_name: Display name for sender
        attachment_path: Optional path to MP3/audio attachment

    Returns:
        dict with success status and message_id or error
    """
    # Try Gmail API first
    client_id = os.getenv("GMAIL_CLIENT_ID")
    if client_id:
        return _send_via_gmail_api(to_email, subject, html_content, from_name, attachment_path)

    # Fallback: SMTP (works with Gmail App Passwords)
    smtp_user = os.getenv("SMTP_USER") or os.getenv("GMAIL_USER")
    if smtp_user:
        return _send_via_smtp(to_email, subject, html_content, from_name, attachment_path)

    # No email credentials configured — log the email instead
    logger.warning(f"No email credentials configured. Would send to {to_email}: {subject}")
    return {
        "success": False,
        "error": "No email credentials configured. Set GMAIL_CLIENT_ID or SMTP_USER in .env",
        "would_send_to": to_email,
        "subject": subject,
    }


def _send_via_gmail_api(to_email, subject, html_content, from_name, attachment_path):
    """Send email via Gmail API with OAuth2."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GMAIL_CLIENT_ID"),
            client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
        )

        service = build("gmail", "v1", credentials=creds)

        message = MIMEMultipart()
        message["to"] = to_email
        message["from"] = f"{from_name} <noreply@geopulse.app>"
        message["subject"] = subject

        message.attach(MIMEText(html_content, "html"))

        # Attach audio file if provided
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                audio = MIMEAudio(f.read(), _subtype="mpeg")
                audio.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=os.path.basename(attachment_path),
                )
                message.attach(audio)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        result = service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        logger.info(f"Gmail API: sent to {to_email}, id={result.get('id')}")
        return {"success": True, "message_id": result.get("id")}

    except Exception as e:
        logger.error(f"Gmail API send failed: {e}")
        return {"success": False, "error": str(e)}


def _send_via_smtp(to_email, subject, html_content, from_name, attachment_path):
    """Send email via SMTP (Gmail with App Password)."""
    try:
        smtp_user = os.getenv("SMTP_USER") or os.getenv("GMAIL_USER")
        smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))

        message = MIMEMultipart()
        message["From"] = f"{from_name} <{smtp_user}>"
        message["To"] = to_email
        message["Subject"] = subject

        message.attach(MIMEText(html_content, "html"))

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as f:
                audio = MIMEAudio(f.read(), _subtype="mpeg")
                audio.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=os.path.basename(attachment_path),
                )
                message.attach(audio)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(message)

        logger.info(f"SMTP: sent to {to_email}")
        return {"success": True, "method": "smtp"}

    except Exception as e:
        logger.error(f"SMTP send failed: {e}")
        return {"success": False, "error": str(e)}


def send_driver_email(driver_email, driver_name, html_content, audio_path=None):
    """Send the weekly driver coaching email."""
    from datetime import datetime
    week_num = datetime.now().strftime("%W")
    first_name = driver_name.split()[0] if driver_name else "Driver"
    subject = f"Your Week {week_num} Summary, {first_name} 🚗"
    return send_email(driver_email, subject, html_content, attachment_path=audio_path)


def send_manager_brief(manager_email, html_content):
    """Send the daily manager morning brief email."""
    from datetime import datetime
    today = datetime.now().strftime("%A, %B %d")
    subject = f"📡 Fleet Morning Brief — {today}"
    return send_email(manager_email, subject, html_content)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("📧 Testing email sender...")

    result = send_email(
        "test@example.com",
        "GEOPulse Test Email",
        "<h1>Hello from GEOPulse!</h1><p>This is a test email.</p>",
    )
    print(f"   Result: {result}")
