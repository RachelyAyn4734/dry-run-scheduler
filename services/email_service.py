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


def _get_smtp_config(secrets) -> tuple[str, int, str, str] | None:
    """
    Read and validate SMTP secrets. Returns (server, port, user, password) or None.
    Logs which specific keys are missing — never logs their values.
    """
    smtp_server   = secrets.get("SMTP_SERVER", "")
    smtp_port_raw = secrets.get("SMTP_PORT", 587)
    smtp_user     = secrets.get("SMTP_USER", "")
    smtp_password = secrets.get("SMTP_PASSWORD", "")

    missing = [k for k, v in [
        ("SMTP_SERVER", smtp_server),
        ("SMTP_USER", smtp_user),
        ("SMTP_PASSWORD", smtp_password),
    ] if not v]

    if missing:
        logger.warning("[MAIL] Missing required secret(s): %s — email skipped", ", ".join(missing))
        return None

    try:
        smtp_port = int(smtp_port_raw)
    except (TypeError, ValueError):
        logger.warning("[MAIL] SMTP_PORT is not a valid integer (%r) — defaulting to 587", smtp_port_raw)
        smtp_port = 587

    return smtp_server, smtp_port, smtp_user, smtp_password


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
    cfg = _get_smtp_config(secrets)
    if cfg is None:
        return False
    smtp_server, smtp_port, smtp_user, smtp_password = cfg

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


def send_visit_notification(
    secrets,
    manager_email: str,
    manager_name: str,
    visitor_name: str,
    date_str: str,
    time_str: str,
    heb_date_str: str = "",
) -> bool:
    """
    Send a Hebrew visit-scheduled notification to a single manager.
    Returns True on success, False on any failure. Does NOT raise.
    """
    cfg = _get_smtp_config(secrets)
    if cfg is None:
        return False
    smtp_server, smtp_port, smtp_user, smtp_password = cfg

    subject = "נקבע ביקור חדש אצל סבתא"
    heb_line = f"תאריך עברי: {heb_date_str}\n" if heb_date_str else ""
    body = (
        f"שלום {manager_name},\n\n"
        f"נקבע ביקור חדש אצל סבתא.\n\n"
        f"שם המבקר/ת: {visitor_name}\n"
        f"תאריך: {date_str}\n"
        f"שעה: {time_str}\n"
        f"{heb_line}"
        f"\nיום נעים 🌸\n"
    )

    msg = MIMEMultipart()
    msg["From"]    = smtp_user
    msg["To"]      = manager_email
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        logger.info("[MAIL] Sending visit notification to %s", manager_email)
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, manager_email, msg.as_string())
        logger.info("[MAIL] Visit notification sent to %s", manager_email)
        return True
    except Exception:
        logger.exception("[MAIL] Failed to send visit notification to %s", manager_email)
        return False


def send_visit_notification_v2(
    secrets,
    manager_email: str,
    manager_name: str,
    visitor_name: str,
    grandma_name: str,
    date_str: str,
    time_str: str,
    heb_date_str: str = "",
    participant_count: int = 1,
    allow_joiners: bool = False,
) -> bool:
    """
    Send an HTML Hebrew visit notification that includes grandma name and participant count.
    Used by the multi-grandma booking flow (Phase 3+).
    Returns True on success, False on any failure. Does NOT raise.
    """
    cfg = _get_smtp_config(secrets)
    if cfg is None:
        return False
    smtp_server, smtp_port, smtp_user, smtp_password = cfg

    subject = f"נקבע ביקור חדש אצל {grandma_name}"
    joiners_text = "אפשרי להצטרף לביקור" if allow_joiners else "ביקור פרטי"
    heb_row = f"<strong>תאריך עברי:</strong> {heb_date_str}<br>" if heb_date_str else ""

    html_body = f"""
<div dir="rtl" style="text-align:right; font-family:Arial, sans-serif; line-height:1.8;">
  <h2>נקבע ביקור חדש אצל {grandma_name}</h2>
  <p>שלום {manager_name},</p>
  <p>נקבע ביקור חדש.</p>
  <p>
    <strong>שם המבקר/ת:</strong> {visitor_name}<br>
    <strong>סבתא:</strong> {grandma_name}<br>
    <strong>תאריך:</strong> {date_str}<br>
    {heb_row}
    <strong>שעה:</strong> {time_str}<br>
    <strong>מספר משתתפים:</strong> {participant_count}<br>
    <strong>הצטרפות:</strong> {joiners_text}
  </p>
  <p>יום נעים 🌸</p>
</div>
"""

    msg = MIMEMultipart("alternative")
    msg["From"]    = smtp_user
    msg["To"]      = manager_email
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        logger.info("[MAIL] Sending visit notification v2 to %s", manager_email)
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, manager_email, msg.as_string())
        logger.info("[MAIL] Visit notification v2 sent to %s", manager_email)
        return True
    except Exception:
        logger.exception("[MAIL] Failed to send visit notification v2 to %s", manager_email)
        return False


def send_visit_cancellation(
    secrets,
    manager_email: str,
    manager_name: str,
    visitor_name: str,
    grandma_name: str,
    date_str: str,
    time_str: str,
    participant_count: int = 1,
    heb_date_str: str = "",
) -> bool:
    """
    Send an HTML Hebrew cancellation notification to a single manager.
    Returns True on success, False on any failure. Does NOT raise.
    """
    cfg = _get_smtp_config(secrets)
    if cfg is None:
        return False
    smtp_server, smtp_port, smtp_user, smtp_password = cfg

    subject = f"בוטל ביקור אצל {grandma_name}"
    heb_row = f"<strong>תאריך עברי:</strong> {heb_date_str}<br>" if heb_date_str else ""

    html_body = f"""
<div dir="rtl" style="text-align:right; font-family:Arial, sans-serif; line-height:1.8;">
  <h2>בוטל ביקור אצל {grandma_name}</h2>
  <p>שלום {manager_name},</p>
  <p>ביקור שתוכנן בוטל.</p>
  <p>
    <strong>שם המבקר/ת:</strong> {visitor_name}<br>
    <strong>סבתא:</strong> {grandma_name}<br>
    <strong>תאריך:</strong> {date_str}<br>
    {heb_row}
    <strong>שעה:</strong> {time_str}<br>
    <strong>מספר משתתפים:</strong> {participant_count}
  </p>
  <p>יום נעים 🌸</p>
</div>
"""

    msg = MIMEMultipart("alternative")
    msg["From"]    = smtp_user
    msg["To"]      = manager_email
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        logger.info("[MAIL] Sending visit cancellation to %s", manager_email)
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, manager_email, msg.as_string())
        logger.info("[MAIL] Visit cancellation sent to %s", manager_email)
        return True
    except Exception:
        logger.exception("[MAIL] Failed to send visit cancellation to %s", manager_email)
        return False
