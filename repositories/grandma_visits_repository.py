import logging
import os
from datetime import datetime

import pytz
from supabase import Client

logger = logging.getLogger(__name__)
_BUCKET = "grandma-visit-photos"
_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _now_iso() -> str:
    return datetime.now(pytz.utc).isoformat()


def get_future_visits(
    supabase: Client,
    descendant_id: str,
    grandma_id: str | None = None,
) -> list:
    """
    Scheduled visits with slot_start in the future.
    Pass grandma_id to scope to one grandma; omit for all (backward-compatible).
    """
    q = (
        supabase.table("grandma_visits").select("*")
        .eq("descendant_id", descendant_id)
        .eq("status", "scheduled")
        .gt("slot_start", _now_iso())
        .order("slot_start")
    )
    if grandma_id is not None:
        q = q.eq("grandma_id", grandma_id)
    return q.execute().data or []


def get_past_visits(
    supabase: Client,
    descendant_id: str,
    grandma_id: str | None = None,
) -> list:
    """
    Visits whose slot_end has passed, excluding cancelled.
    Eligible for notes and photo upload.
    """
    q = (
        supabase.table("grandma_visits").select("*")
        .eq("descendant_id", descendant_id)
        .lte("slot_end", _now_iso())
        .neq("status", "cancelled")
        .order("slot_start", desc=True)
    )
    if grandma_id is not None:
        q = q.eq("grandma_id", grandma_id)
    return q.execute().data or []


def get_all_visits(
    supabase: Client,
    grandma_id: str | None = None,
) -> list:
    """Return all visits, most recent first. Admin view. Optional grandma filter."""
    q = supabase.table("grandma_visits").select("*").order("slot_start", desc=True)
    if grandma_id is not None:
        q = q.eq("grandma_id", grandma_id)
    return q.execute().data or []


def get_visits_with_photos(
    supabase: Client,
    grandma_id: str | None = None,
    descendant_id: str | None = None,
) -> list:
    """
    Return completed visits that have a photo, ordered most recent first.
    Pass grandma_id to scope to one grandma; omit for all grandmas (admin use).
    Pass descendant_id for the visitor's personal gallery.
    """
    q = (
        supabase.table("grandma_visits").select("*")
        .eq("status", "completed")
        .filter("photo_url", "not.is", "null")
        .order("slot_start", desc=True)
    )
    if grandma_id is not None:
        q = q.eq("grandma_id", grandma_id)
    if descendant_id is not None:
        q = q.eq("descendant_id", descendant_id)
    return q.execute().data or []


def update_visit_notes_photo(
    supabase: Client,
    visit_id: str,
    notes: str | None = None,
    photo_url: str | None = None,
    actual_start: str | None = None,
    actual_end: str | None = None,
) -> None:
    """
    Save post-visit summary fields. All parameters are optional.
    actual_start and actual_end must be ISO-format TIMESTAMPTZ strings when provided.
    Setting any field marks the visit as completed.
    """
    now = _now_iso()
    payload: dict = {
        "status": "completed",
        "updated_at": now,
        "completed_at": now,
    }
    if notes is not None:
        payload["notes"] = notes
    if photo_url is not None:
        payload["photo_url"] = photo_url
    if actual_start is not None:
        payload["actual_start"] = actual_start
    if actual_end is not None:
        payload["actual_end"] = actual_end
    supabase.table("grandma_visits").update(payload).eq("id", visit_id).execute()
    logger.info("[GRANDMA_VISITS] Updated notes/photo for visit %s", visit_id)


def upload_visit_photo(
    supabase: Client,
    visit_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> str | None:
    """Upload photo to Supabase Storage. Returns public URL or None on failure."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTS:
        ext = ".jpg"
    timestamp = int(datetime.now(pytz.utc).timestamp())
    path = f"grandma-visits/{visit_id}/{timestamp}{ext}"
    try:
        supabase.storage.from_(_BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": content_type, "upsert": False},
        )
        url = supabase.storage.from_(_BUCKET).get_public_url(path)
        logger.info("[STORAGE] Uploaded photo for visit %s → %s", visit_id, url)
        return url
    except Exception as exc:
        logger.error(
            "[STORAGE] Upload failed for visit %s — bucket=%s path=%s error=%s",
            visit_id, _BUCKET, path, exc,
        )
        return None


# ── Deprecated ────────────────────────────────────────────────────────────────
# Kept only to avoid import errors in services/grandma_visit_service.py until
# Phase 3 replaces them with RPC calls. Do not use in new code.

def create_visit(
    supabase: Client,
    descendant_id: str,
    descendant_name: str,
    slot_id: str,
    slot_start: str,
    slot_end: str,
) -> dict:
    """Deprecated — booking now goes through the book_visit_slot RPC."""
    logger.warning("[GRANDMA_VISITS] create_visit is deprecated; use book_visit_slot RPC")
    r = supabase.table("grandma_visits").insert({
        "descendant_id": descendant_id,
        "descendant_name": descendant_name,
        "slot_id": slot_id,
        "slot_start": slot_start,
        "slot_end": slot_end,
        "status": "scheduled",
    }).execute()
    return r.data[0]


def cancel_visit(supabase: Client, visit_id: str) -> None:
    """Deprecated — use the cancel_visit_booking RPC instead."""
    logger.warning("[GRANDMA_VISITS] cancel_visit is deprecated; use cancel_visit_booking RPC")
    supabase.table("grandma_visits").update({
        "status": "cancelled",
        "updated_at": _now_iso(),
    }).eq("id", visit_id).execute()
