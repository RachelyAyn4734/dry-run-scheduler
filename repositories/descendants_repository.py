import logging
from supabase import Client

logger = logging.getLogger(__name__)


def get_descendant_by_name(supabase: Client, name: str) -> dict | None:
    """Exact trimmed name lookup against active descendants."""
    r = (
        supabase.table("descendants").select("*")
        .eq("is_active", True)
        .eq("name", name.strip())
        .limit(1).execute()
    )
    return r.data[0] if r.data else None


def get_all_descendants(supabase: Client) -> list:
    return (
        supabase.table("descendants").select("*")
        .order("name").execute().data or []
    )


def create_descendant(
    supabase: Client,
    name: str,
    phone: str = "",
    email: str = "",
) -> dict:
    payload: dict = {"name": name.strip(), "is_active": True}
    if phone:
        payload["phone"] = phone.strip()
    if email:
        payload["email"] = email.strip().lower()
    r = supabase.table("descendants").insert(payload).execute()
    logger.info("[DESCENDANTS] Created %s", name)
    return r.data[0]


def deactivate_descendant(supabase: Client, descendant_id: str) -> None:
    supabase.table("descendants").update({"is_active": False}).eq("id", descendant_id).execute()
    logger.info("[DESCENDANTS] Deactivated %s", descendant_id)


def reactivate_descendant(supabase: Client, descendant_id: str) -> None:
    supabase.table("descendants").update({"is_active": True}).eq("id", descendant_id).execute()
    logger.info("[DESCENDANTS] Reactivated %s", descendant_id)
