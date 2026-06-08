import logging
from supabase import Client

logger = logging.getLogger(__name__)


def get_active_grandmas(supabase: Client) -> list:
    """Return all active grandmas ordered by name — for the visitor selection screen."""
    return (
        supabase.table("grandmas").select("*")
        .eq("is_active", True)
        .order("name").execute().data or []
    )


def get_all_grandmas(supabase: Client) -> list:
    """Return all grandmas including inactive — for the admin view."""
    return (
        supabase.table("grandmas").select("*")
        .order("name").execute().data or []
    )


def get_grandma_by_id(supabase: Client, grandma_id: str) -> dict | None:
    r = (
        supabase.table("grandmas").select("*")
        .eq("id", grandma_id).limit(1).execute()
    )
    return r.data[0] if r.data else None


def create_grandma(
    supabase: Client,
    name: str,
    photo_url: str = "",
    description: str = "",
) -> dict:
    payload: dict = {"name": name.strip(), "is_active": True}
    if photo_url:
        payload["photo_url"] = photo_url.strip()
    if description:
        payload["description"] = description.strip()
    r = supabase.table("grandmas").insert(payload).execute()
    logger.info("[GRANDMAS] Created %s", name)
    return r.data[0]


def update_grandma(
    supabase: Client,
    grandma_id: str,
    name: str | None = None,
    photo_url: str | None = None,
    description: str | None = None,
) -> None:
    payload: dict = {}
    if name is not None:
        payload["name"] = name.strip()
    if photo_url is not None:
        payload["photo_url"] = photo_url.strip()
    if description is not None:
        payload["description"] = description.strip()
    if payload:
        supabase.table("grandmas").update(payload).eq("id", grandma_id).execute()
        logger.info("[GRANDMAS] Updated grandma %s", grandma_id)


def set_grandma_active(supabase: Client, grandma_id: str, is_active: bool) -> None:
    supabase.table("grandmas").update({"is_active": is_active}).eq("id", grandma_id).execute()
    logger.info("[GRANDMAS] Set is_active=%s for %s", is_active, grandma_id)
