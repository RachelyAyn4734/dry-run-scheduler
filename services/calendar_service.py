"""
Google Calendar service.
Pure Python — no Streamlit imports.
Pass st.secrets (or any dict-like) as `secrets`.
"""
import json
import logging
from datetime import datetime, timedelta
from datetime import date as Date

logger = logging.getLogger(__name__)

_GCAL_AVAILABLE = False
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    _GCAL_AVAILABLE = True
except ImportError:
    logger.warning("[GCAL] google-api-python-client not installed — Calendar disabled")


def _build_service(secrets):
    """Build a Google Calendar API service from secrets. Returns None on failure."""
    if not _GCAL_AVAILABLE:
        return None
    try:
        if "gcp_service_account" in secrets:
            creds_info = dict(secrets["gcp_service_account"])
            pk = creds_info.get("private_key", "")
            if "\\n" in pk:
                creds_info["private_key"] = pk.replace("\\n", "\n")
        elif "GCP_SERVICE_ACCOUNT_JSON" in secrets:
            creds_info = json.loads(secrets["GCP_SERVICE_ACCOUNT_JSON"])
        else:
            logger.warning("[GCAL] No GCP credentials found in secrets")
            return None

        creds = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        svc = build("calendar", "v3", credentials=creds, cache_discovery=False)
        logger.info("[GCAL] Service built successfully")
        return svc
    except Exception:
        logger.exception("[GCAL] Failed to build service")
        return None


def create_event(
    secrets,
    slot_date: Date,
    start_time: str,
    user_name: str,
    user_email: str,
) -> str:
    """
    Create a 1-hour calendar event.
    Returns event_id string on success, empty string on any failure.
    Does NOT raise — caller decides how to handle ''.
    """
    service = _build_service(secrets)
    if service is None:
        return ""

    calendar_id = secrets.get("CALENDAR_ID", "")
    if not calendar_id:
        logger.error("[GCAL] CALENDAR_ID secret is missing")
        return ""

    try:
        t = start_time[:5]
        start_dt = datetime.strptime(f"{slot_date.isoformat()} {t}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(hours=1)
        event = {
            "summary": f"Dry Run — {user_name}",
            "description": f"שם: {user_name}\nאימייל: {user_email}",
            "start": {"dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "Asia/Jerusalem"},
            "end":   {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),   "timeZone": "Asia/Jerusalem"},
        }
        result = service.events().insert(calendarId=calendar_id, body=event).execute()
        event_id = result.get("id", "")
        logger.info("[GCAL] Event created id=%s", event_id)
        return event_id
    except Exception:
        logger.exception("[GCAL] Failed to create event")
        return ""


def delete_event(secrets, event_id: str) -> bool:
    """
    Delete a calendar event by id.
    Returns True on success, False otherwise. Does NOT raise.
    """
    if not event_id:
        return False

    service = _build_service(secrets)
    if service is None:
        return False

    calendar_id = secrets.get("CALENDAR_ID", "")
    try:
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        logger.info("[GCAL] Event deleted id=%s", event_id)
        return True
    except Exception:
        logger.exception("[GCAL] Failed to delete event id=%s", event_id)
        return False
