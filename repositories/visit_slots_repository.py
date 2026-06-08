import logging
from datetime import datetime

import pytz
from supabase import Client

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(pytz.utc).isoformat()


def fetch_available_visit_slots(
    supabase: Client,
    grandma_id: str | None = None,
) -> list:
    """
    Return future slots that are admin-enabled (is_active) and have capacity (is_available).
    Pass grandma_id to scope to one grandma; omit to return all (backward-compatible).
    """
    q = (
        supabase.table("visit_slots").select("*")
        .eq("is_active", True)
        .eq("is_available", True)
        .gt("slot_start", _now_iso())
        .order("slot_start")
    )
    if grandma_id is not None:
        q = q.eq("grandma_id", grandma_id)
    return q.execute().data or []


def fetch_all_visit_slots(
    supabase: Client,
    grandma_id: str | None = None,
) -> list:
    """Return all slots regardless of state (admin view). Optional grandma filter."""
    q = supabase.table("visit_slots").select("*").order("slot_start")
    if grandma_id is not None:
        q = q.eq("grandma_id", grandma_id)
    return q.execute().data or []


def add_visit_slot(
    supabase: Client,
    slot_start: datetime,
    slot_end: datetime,
    grandma_id: str | None = None,
    max_participants: int = 1,
    allows_shared_visits: bool = False,
) -> bool:
    """
    Insert a new visit slot.
    Returns False if a slot with the same (grandma_id, slot_start) already exists.
    grandma_id defaults to None for backward compatibility; set it for all new slots.
    """
    q = supabase.table("visit_slots").select("id").eq("slot_start", slot_start.isoformat())
    if grandma_id is not None:
        q = q.eq("grandma_id", grandma_id)
    if q.execute().data:
        return False

    payload: dict = {
        "slot_start": slot_start.isoformat(),
        "slot_end": slot_end.isoformat(),
        "is_available": True,
        "is_active": True,
        "max_participants": max(1, max_participants),
        "allows_shared_visits": allows_shared_visits,
    }
    if grandma_id is not None:
        payload["grandma_id"] = grandma_id

    supabase.table("visit_slots").insert(payload).execute()
    logger.info("[VISIT_SLOTS] Added slot %s grandma=%s", slot_start, grandma_id)
    return True


def fetch_private_blocked_slot_ids(supabase: Client, grandma_id: str) -> set:
    """
    Return IDs of future slots that have at least one scheduled visit with
    allow_joiners=False. Used by the UI to hide those slots from new visitors —
    the booking family requested privacy, so the slot must not appear available.
    """
    r = (
        supabase.table("grandma_visits").select("slot_id")
        .eq("grandma_id", grandma_id)
        .eq("status", "scheduled")
        .eq("allow_joiners", False)
        .gt("slot_start", _now_iso())
        .execute()
    )
    return {row["slot_id"] for row in (r.data or []) if row.get("slot_id")}


def set_slot_active(supabase: Client, slot_id: str, is_active: bool) -> None:
    """
    Admin-controlled enable/disable.
    Setting is_active=False closes the slot to new bookings without touching
    is_available (the capacity cache) or any existing visits.
    Cancellations never call this function.
    """
    supabase.table("visit_slots").update({"is_active": is_active}).eq("id", slot_id).execute()
    logger.info("[VISIT_SLOTS] Set is_active=%s for slot %s", is_active, slot_id)


def delete_visit_slot(supabase: Client, slot_id: str) -> None:
    supabase.table("visit_slots").delete().eq("id", slot_id).execute()
    logger.info("[VISIT_SLOTS] Deleted slot %s", slot_id)


# ── Deprecated ────────────────────────────────────────────────────────────────
# Kept only to avoid import errors in services/grandma_visit_service.py until
# Phase 3 replaces them with RPC calls. Do not use in new code.

def atomic_book_visit_slot(supabase: Client, slot_id: str) -> bool:
    """Deprecated — use the book_visit_slot RPC instead."""
    logger.warning("[VISIT_SLOTS] atomic_book_visit_slot is deprecated; use book_visit_slot RPC")
    result = (
        supabase.table("visit_slots").update({"is_available": False})
        .eq("id", slot_id).eq("is_available", True).execute()
    )
    return len(result.data) > 0


def release_visit_slot(supabase: Client, slot_id: str) -> None:
    """Deprecated — use the cancel_visit_booking RPC instead."""
    logger.warning("[VISIT_SLOTS] release_visit_slot is deprecated; use cancel_visit_booking RPC")
    supabase.table("visit_slots").update({"is_available": True}).eq("id", slot_id).execute()
