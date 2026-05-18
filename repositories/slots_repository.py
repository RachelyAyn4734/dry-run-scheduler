import logging
from datetime import date, datetime, timedelta

import pytz
from supabase import Client

logger = logging.getLogger(__name__)
_IL_TZ = pytz.timezone("Asia/Jerusalem")


def _tomorrow_il() -> str:
    return (datetime.now(_IL_TZ).date() + timedelta(days=1)).isoformat()


# ── Read ──────────────────────────────────────────────────────────────────────

def fetch_slots(supabase: Client, filter_date: date = None, only_available: bool = False) -> list:
    q = supabase.table("slots").select("*")
    if filter_date:
        q = q.eq("date", filter_date.isoformat())
    elif only_available:
        q = q.gte("date", _tomorrow_il())
    if only_available:
        q = q.eq("is_booked", False)
    return q.order("date").order("time_slot").execute().data or []


def fetch_booked_slots(supabase: Client) -> list:
    return (
        supabase.table("slots").select("*")
        .eq("is_booked", True).order("date").order("time_slot").execute().data or []
    )


def fetch_user_slot(supabase: Client, user_email: str) -> dict | None:
    """Return the single active booking for this user (deterministic via order+limit)."""
    r = (
        supabase.table("slots").select("*")
        .eq("is_booked", True).eq("user_email", user_email)
        .order("id").limit(1).execute()
    )
    return r.data[0] if r.data else None


# ── Write ─────────────────────────────────────────────────────────────────────

def add_slot(supabase: Client, slot_date: date, time_slot: str) -> bool:
    """Insert a new slot. Returns False if the slot already exists."""
    ex = (
        supabase.table("slots").select("id")
        .eq("date", slot_date.isoformat()).eq("time_slot", time_slot).execute()
    )
    if ex.data:
        return False
    supabase.table("slots").insert(
        {"date": slot_date.isoformat(), "time_slot": time_slot, "is_booked": False}
    ).execute()
    logger.info("[SLOTS] Added slot %s %s", slot_date, time_slot)
    return True


def atomic_book_slot(
    supabase: Client,
    slot_id: int,
    user_email: str,
    user_name: str,
    gcal_event_id: str = "",
) -> bool:
    """
    Conditionally book a slot only when is_booked=False.
    Returns True if this client won the race, False if already taken.
    The conditional .eq("is_booked", False) makes the update a no-op when
    another request won first, giving us optimistic-lock semantics without
    a stored procedure.
    """
    payload: dict = {"is_booked": True, "user_email": user_email, "booked_by": user_name}
    if gcal_event_id:
        payload["gcal_event_id"] = gcal_event_id

    result = (
        supabase.table("slots").update(payload)
        .eq("id", slot_id).eq("is_booked", False).execute()
    )
    success = len(result.data) > 0
    logger.info("[SLOTS] atomic_book id=%s email=%s success=%s", slot_id, user_email, success)
    return success


def clear_slot(supabase: Client, slot_id: int) -> None:
    """Remove all booking data from a slot (keeps the row)."""
    supabase.table("slots").update({
        "is_booked": False,
        "user_email": None,
        "booked_by": None,
        "gcal_event_id": None,
    }).eq("id", slot_id).execute()
    logger.info("[SLOTS] Slot %s cleared", slot_id)


def delete_slot_record(supabase: Client, slot_id: int) -> None:
    supabase.table("slots").delete().eq("id", slot_id).execute()
    logger.info("[SLOTS] Slot %s deleted", slot_id)
