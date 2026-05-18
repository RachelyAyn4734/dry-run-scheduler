"""
Email service.
Pure Python — no Streamlit imports.
Pass st.secrets (or any dict-like) as `secrets`.
"""
import logging
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_confirmation(
    secrets,
    user_email: str,
    user_name: str,
    date_str: str,
    time_str: str,
) -> bool:
    """
    Send a Hebrew booking-confirmation email via SMTP.
    Returns True on success, False on any failure. Does NOT raise.
    """
    smtp_server   = secrets.get("SMTP_SERVER", "")
    smtp_port     = int(secrets.get("SMTP_PORT", 587))
    smtp_user     = secrets.get("SMTP_USER", "")
    smtp_password = secrets.get("SMTP_PASSWORD", "")

    if not smtp_server or not smtp_user or not smtp_password:
        logger.warning("[MAIL] SMTP secrets incomplete — skipping email")
        return False

    subject = f"אישור פגישה: {user_name}"
    body = (
        f"שלום {user_name},\n\n"
        f"פגישת ה-Dry Run שלך אושרה!\n\n"
        f"📅 תאריך: {date_str}\n"
        f"🕐 שעה: {time_str}\n\n"
        f"נשמח לראותך!\n"
        f"צוות Dry Run"
    )

    msg = MIMEMultipart()
    msg["From"]    = smtp_user
    msg["To"]      = user_email
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        logger.info("[MAIL] Connecting to %s:%s", smtp_server, smtp_port)
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            logger.info("[MAIL] Logging in as %s", smtp_user)
            server.login(smtp_user, smtp_password)
            logger.info("[MAIL] Sending to %s", user_email)
            server.sendmail(smtp_user, user_email, msg.as_string())
        logger.info("[MAIL] Sent successfully to %s", user_email)
        return True
    except Exception:
        logger.exception("[MAIL] Failed to send email to %s", user_email)
        return False
