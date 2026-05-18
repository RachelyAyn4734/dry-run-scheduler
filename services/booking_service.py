"""
Booking service — orchestrates DB, Calendar, and Email.
Pure Python — no Streamlit imports.
"""
import logging
from datetime import date as Date

from supabase import Client

from repositories.slots_repository import atomic_book_slot, clear_slot, fetch_user_slot
from services import calendar_service, email_service

logger = logging.getLogger(__name__)


def book(
    supabase: Client,
    secrets,
    slot_id: int,
    user_email: str,
    user_name: str,
    slot_date: Date,
    start_time: str,
) -> dict:
    """
    Full booking flow:
      1. Create Google Calendar event (before DB write so we have the event_id).
      2. Atomically book the slot in DB (conditional on is_booked=False).
      3. If DB write fails (race), roll back the calendar event.

    Returns:
        {
          "success": bool,
          "gcal_event_id": str,
          "error_code": None | "already_booked",
          "gcal_ok": bool,
          "mail_ok": bool,
        }
    """
    # Step 1: Calendar (best-effort — slot still books even if calendar fails)
    gcal_event_id = calendar_service.create_event(
        secrets, slot_date, start_time, user_name, user_email
    )

    # Step 2: Atomic DB write
    booked = atomic_book_slot(supabase, slot_id, user_email, user_name, gcal_event_id)
    if not booked:
        # Race condition — another user got here first; roll back calendar event
        if gcal_event_id:
            calendar_service.delete_event(secrets, gcal_event_id)
        logger.warning("[BOOK] Race: slot %s already taken", slot_id)
        return {"success": False, "gcal_event_id": "", "error_code": "already_booked",
                "gcal_ok": False, "mail_ok": False}

    # Step 3: Confirmation email (non-blocking — failure does not undo booking)
    mail_ok = email_service.send_confirmation(
        secrets, user_email, user_name, slot_date.isoformat(), start_time
    )

    return {
        "success": True,
        "gcal_event_id": gcal_event_id,
        "error_code": None,
        "gcal_ok": bool(gcal_event_id),
        "mail_ok": mail_ok,
    }


def cancel(supabase: Client, secrets, slot_id: int, gcal_event_id: str = "") -> None:
    """
    Unified cancellation used by BOTH user and admin flows.
    Deletes the calendar event (if any), then clears the DB slot.
    """
    if gcal_event_id:
        calendar_service.delete_event(secrets, gcal_event_id)
    clear_slot(supabase, slot_id)
    logger.info("[BOOK] Slot %s cancelled", slot_id)


def cancel_user_booking(supabase: Client, secrets, user_email: str) -> None:
    """Cancel any active booking for a given user email."""
    slot = fetch_user_slot(supabase, user_email)
    if slot:
        cancel(supabase, secrets, slot["id"], slot.get("gcal_event_id") or "")
