import logging
from supabase import Client

logger = logging.getLogger(__name__)


def get_user(supabase: Client, email: str) -> dict | None:
    r = supabase.table("users").select("*").eq("email", email).execute()
    return r.data[0] if r.data else None


def create_user(supabase: Client, name: str, email: str, phone: str) -> None:
    supabase.table("users").insert(
        {"name": name.strip(), "email": email, "phone": phone.strip()}
    ).execute()
    logger.info("[USERS] Created %s", email)


def get_all_users(supabase: Client) -> list:
    return supabase.table("users").select("*").order("name").execute().data or []


def delete_user_record(supabase: Client, email: str) -> None:
    supabase.table("users").delete().eq("email", email).execute()
    logger.info("[USERS] Deleted %s", email)
