"""
Grandma Visit Service — orchestrates DB + Email.
Pure Python — no Streamlit imports.
"""
import logging
from datetime import datetime

import pytz
from supabase import Client

from services import email_service
from utils.dates import to_heb_short

logger = logging.getLogger(__name__)
_IL_TZ = pytz.timezone("Asia/Jerusalem")


# ── RPC reason codes → Hebrew messages shown to the visitor ───────────────────

_BOOK_REASON_MESSAGES: dict[str, str] = {
    "slot_not_found":
        "המועד לא נמצא. ייתכן שנמחק. אנא בחרי מועד אחר.",
    "slot_grandma_mismatch":
        "אירעה שגיאה בבחירת המועד. אנא נסי שוב.",
    "slot_closed_by_admin":
        "המועד הזה סגור ואינו פתוח להזמנה.",
    "slot_not_available":
        "המועד הזה כבר אינו פנוי. אנא בחרי מועד אחר.",
    "slot_in_past":
        "לא ניתן לקבוע ביקור במועד שעבר.",
    "invalid_participant_count":
        "מספר המשתתפים אינו תקין. אנא בחרי שנית.",
    "descendant_not_found_or_inactive":
        "שמך לא נמצא במערכת או שהגישה הוגבלה. אנא פני למנהל/ת.",
    "slot_not_shareable":
        "המועד הזה מיועד לביקור אחד בלבד ואינו פנוי.",
    "slot_full":
        "המועד הזה מלא. אנא בחרי מועד אחר.",
    "private_visit_exists":
        "משפחה אחרת קבעה ביקור פרטי בשעה זו. אנא בחרי מועד אחר.",
    "slot_occupied_cannot_go_private":
        "לא ניתן לקבוע ביקור פרטי — ישנם כבר משתתפים אחרים בשעה זו.",
}

_CANCEL_REASON_MESSAGES: dict[str, str] = {
    "visit_not_found":   "הביקור לא נמצא.",
    "already_cancelled": "הביקור כבר בוטל.",
    "ownership_denied":  "אין לך הרשאה לבטל ביקור זה.",
}

_GENERIC_ERROR = "אירעה שגיאה. אנא נסי שוב מאוחר יותר."


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_active_managers(supabase: Client) -> list:
    return (
        supabase.table("visit_managers").select("*")
        .eq("is_active", True).execute().data or []
    )


def _format_slot_for_email(slot_start_iso: str) -> tuple[str, str, str]:
    """Returns (date_str dd/MM/yyyy, time_str HH:mm, heb_date_str)."""
    dt = datetime.fromisoformat(slot_start_iso).astimezone(_IL_TZ)
    return dt.strftime("%d/%m/%Y"), dt.strftime("%H:%M"), to_heb_short(dt.date())


# ── Public API ────────────────────────────────────────────────────────────────

def book_visit(
    supabase: Client,
    secrets,
    slot_id: str,
    slot_start: str,
    slot_end: str,
    descendant_id: str,
    descendant_name: str,
    grandma_id: str | None = None,
    grandma_name: str = "",
    participant_count: int = 1,
    allow_joiners: bool = False,
) -> dict:
    """
    Atomically book a grandma visit using the book_visit_slot RPC.

    grandma_id is required for the multi-grandma flow introduced in the redesign.
    Calls made without grandma_id (old UI, pre-Phase-5 update) are blocked
    gracefully — success=False with an informative Hebrew message — rather than
    falling back to the old two-step flow that bypassed the RPC.

    Returns: {success, visit_id, mail_ok, error_msg}
    """
    if not grandma_id:
        logger.warning(
            "[GRANDMA] book_visit called without grandma_id — "
            "UI not yet updated (Phase 5 pending)"
        )
        return {
            "success":   False,
            "visit_id":  None,
            "mail_ok":   False,
            "error_msg": "המערכת מתעדכנת. אנא רענני את הדף ונסי שוב.",
        }

    try:
        result = supabase.rpc("book_visit_slot", {
            "p_slot_id":           slot_id,
            "p_descendant_id":     descendant_id,
            "p_descendant_name":   descendant_name,
            "p_grandma_id":        grandma_id,
            "p_grandma_name":      grandma_name,
            "p_participant_count": participant_count,
            "p_allow_joiners":     allow_joiners,
        }).execute()
    except Exception:
        logger.exception("[GRANDMA] book_visit_slot RPC call failed")
        return {
            "success":   False,
            "visit_id":  None,
            "mail_ok":   False,
            "error_msg": "שגיאת תקשורת עם השרת. אנא נסי שוב.",
        }

    data = result.data
    if not data or not data.get("success"):
        reason = (data or {}).get("reason", "unknown")
        error_msg = _BOOK_REASON_MESSAGES.get(reason, _GENERIC_ERROR)
        logger.warning("[GRANDMA] book_visit_slot rejected: reason=%s slot=%s", reason, slot_id)
        return {"success": False, "visit_id": None, "mail_ok": False, "error_msg": error_msg}

    visit_id = str(data["visit_id"])
    date_str, time_str, heb_date_str = _format_slot_for_email(slot_start)

    managers = get_active_managers(supabase)
    mail_ok = True
    for manager in managers:
        ok = email_service.send_visit_notification_v2(
            secrets,
            manager_email=manager["email"],
            manager_name=manager["name"],
            visitor_name=descendant_name,
            grandma_name=grandma_name,
            date_str=date_str,
            time_str=time_str,
            heb_date_str=heb_date_str,
            participant_count=participant_count,
        )
        if not ok:
            mail_ok = False

    logger.info(
        "[GRANDMA] Booked visit=%s descendant=%s slot=%s grandma=%s",
        visit_id, descendant_name, slot_id, grandma_name,
    )
    return {"success": True, "visit_id": visit_id, "mail_ok": mail_ok, "error_msg": None}


def cancel_booked_visit(
    supabase: Client,
    visit_id: str,
    slot_id: str = "",
    descendant_id: str | None = None,
) -> dict:
    """
    Cancel a visit using the cancel_visit_booking RPC.

    slot_id: accepted for backward compatibility with existing UI calls but ignored —
             the RPC handles slot release internally.

    descendant_id: pass the logged-in visitor's UUID to enforce ownership (visitor path).
                   Omit or pass None for admin cancellation — ownership check is skipped.

    Returns: {success, error_msg}
    """
    try:
        result = supabase.rpc("cancel_visit_booking", {
            "p_visit_id":      visit_id,
            "p_descendant_id": descendant_id,
        }).execute()
    except Exception:
        logger.exception("[GRANDMA] cancel_visit_booking RPC call failed")
        return {"success": False, "error_msg": "שגיאת תקשורת עם השרת. אנא נסי שוב."}

    data = result.data
    if not data or not data.get("success"):
        reason = (data or {}).get("reason", "unknown")
        error_msg = _CANCEL_REASON_MESSAGES.get(reason, _GENERIC_ERROR)
        logger.warning(
            "[GRANDMA] cancel_visit_booking rejected: reason=%s visit=%s", reason, visit_id
        )
        return {"success": False, "error_msg": error_msg}

    logger.info("[GRANDMA] Cancelled visit=%s descendant=%s", visit_id, descendant_id)
    return {"success": True, "error_msg": None}
