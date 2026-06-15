"""
Managers repository — scoped manager model (managers + manager_assignments).

A manager is a global person (identity). An assignment scopes that person to a
service (and, for grandma, a specific entity). Email recipient resolution for
ALL notification flows goes through get_recipients() so booking and
cancellation always use identical logic.

Pure DB queries — no Streamlit, no email/SMTP.
"""
import logging

from supabase import Client

from utils.constants import SERVICE_DRY_RUN, SERVICE_GRANDMA, SERVICE_TYPES

logger = logging.getLogger(__name__)


# ── Recipient resolution (the single source of truth) ─────────────────────────

def get_recipients(
    supabase: Client,
    service_type: str,
    entity_id: str | None = None,
) -> list[dict]:
    """
    Resolve notification recipients for a service/entity scope.

    Returns a list of {"name", "email"} dicts for managers who:
      - are globally active (managers.is_active = TRUE), AND
      - have an active assignment (manager_assignments.is_active = TRUE) for the
        given (service_type, entity_id) scope.

    Deduplicated by lowercased email, so an accidental double assignment never
    produces a duplicate email. Returns [] when nobody is assigned — callers
    must treat an empty list as "send to no one", never as an error.

    Scope rules (mirrors the DB CHECK constraint):
      - SERVICE_DRY_RUN → entity_id must be None
      - SERVICE_GRANDMA → entity_id must be the grandma's id
    """
    if service_type not in SERVICE_TYPES:
        logger.warning("[MANAGERS] get_recipients: unknown service_type=%r", service_type)
        return []

    if service_type == SERVICE_GRANDMA and not entity_id:
        logger.warning("[MANAGERS] get_recipients: grandma scope requires entity_id")
        return []
    if service_type == SERVICE_DRY_RUN and entity_id is not None:
        logger.warning("[MANAGERS] get_recipients: dry_run scope must not have entity_id")
        # Be strict: a stray entity_id would silently match nothing — fail loud-ish.
        return []

    # Fetch active assignments for this scope, embedding the manager row so we
    # can filter on the person's global is_active in one round-trip.
    query = (
        supabase.table("manager_assignments")
        .select("manager_id, service_type, entity_id, is_active, "
                "managers!inner(id, name, email, is_active)")
        .eq("service_type", service_type)
        .eq("is_active", True)
        .eq("managers.is_active", True)
    )
    if entity_id is None:
        query = query.is_("entity_id", "null")
    else:
        query = query.eq("entity_id", entity_id)

    try:
        rows = query.execute().data or []
    except Exception:
        logger.exception(
            "[MANAGERS] get_recipients query failed service=%s entity=%s",
            service_type, entity_id,
        )
        return []

    recipients: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        mgr = row.get("managers") or {}
        email = (mgr.get("email") or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        recipients.append({"name": mgr.get("name") or "", "email": email})

    logger.info(
        "[MANAGERS] Resolved %d recipient(s) for service=%s entity=%s",
        len(recipients), service_type, entity_id,
    )
    return recipients


# ── Managers (global people) CRUD ─────────────────────────────────────────────

def list_managers(supabase: Client, include_inactive: bool = True) -> list:
    """All managers ordered by name. Set include_inactive=False for active only."""
    query = supabase.table("managers").select("*").order("name")
    if not include_inactive:
        query = query.eq("is_active", True)
    return query.execute().data or []


def get_manager_by_email(supabase: Client, email: str) -> dict | None:
    norm = email.strip().lower()
    r = supabase.table("managers").select("*").eq("email", norm).limit(1).execute()
    return r.data[0] if r.data else None


def create_manager(supabase: Client, name: str, email: str) -> dict:
    """Insert a manager. Email is normalized to lowercase. Caller validates format."""
    payload = {"name": name.strip(), "email": email.strip().lower(), "is_active": True}
    r = supabase.table("managers").insert(payload).execute()
    logger.info("[MANAGERS] Created manager %s", payload["email"])
    return r.data[0]


def set_manager_active(supabase: Client, manager_id: str, is_active: bool) -> None:
    supabase.table("managers").update({"is_active": is_active}).eq("id", manager_id).execute()
    logger.info("[MANAGERS] Set is_active=%s for manager %s", is_active, manager_id)


# ── Assignments (scope) ───────────────────────────────────────────────────────

def list_assignments(
    supabase: Client,
    service_type: str,
    entity_id: str | None = None,
    active_only: bool = True,
) -> list:
    """
    Assignments for a scope, with the embedded manager row.
    Used by the admin UI to show who is assigned where.
    """
    query = (
        supabase.table("manager_assignments")
        .select("id, manager_id, service_type, entity_id, is_active, "
                "managers(id, name, email, is_active)")
        .eq("service_type", service_type)
    )
    if active_only:
        query = query.eq("is_active", True)
    if entity_id is None:
        query = query.is_("entity_id", "null")
    else:
        query = query.eq("entity_id", entity_id)
    return query.execute().data or []


def add_assignment(
    supabase: Client,
    manager_id: str,
    service_type: str,
    entity_id: str | None = None,
) -> dict | None:
    """
    Assign a manager to a scope. Idempotent: if an assignment already exists
    (active or inactive) it is reactivated rather than duplicated, keeping the
    DB unique indexes happy.

    Returns the assignment row, or None on invalid scope shape.
    """
    if service_type not in SERVICE_TYPES:
        logger.warning("[MANAGERS] add_assignment: unknown service_type=%r", service_type)
        return None
    if service_type == SERVICE_GRANDMA and not entity_id:
        logger.warning("[MANAGERS] add_assignment: grandma scope requires entity_id")
        return None
    if service_type == SERVICE_DRY_RUN:
        entity_id = None  # normalize — dry_run never carries an entity

    # Reactivate an existing (possibly soft-removed) assignment if present.
    existing_q = (
        supabase.table("manager_assignments").select("id, is_active")
        .eq("manager_id", manager_id).eq("service_type", service_type)
    )
    if entity_id is None:
        existing_q = existing_q.is_("entity_id", "null")
    else:
        existing_q = existing_q.eq("entity_id", entity_id)
    existing = existing_q.limit(1).execute().data

    if existing:
        assignment_id = existing[0]["id"]
        if not existing[0]["is_active"]:
            supabase.table("manager_assignments").update(
                {"is_active": True}
            ).eq("id", assignment_id).execute()
            logger.info("[MANAGERS] Reactivated assignment %s", assignment_id)
        return {"id": assignment_id, "manager_id": manager_id,
                "service_type": service_type, "entity_id": entity_id, "is_active": True}

    payload = {
        "manager_id": manager_id,
        "service_type": service_type,
        "entity_id": entity_id,
        "is_active": True,
    }
    r = supabase.table("manager_assignments").insert(payload).execute()
    logger.info(
        "[MANAGERS] Added assignment manager=%s service=%s entity=%s",
        manager_id, service_type, entity_id,
    )
    return r.data[0] if r.data else None


def remove_assignment(supabase: Client, assignment_id: str) -> None:
    """
    Soft-remove an assignment (is_active = FALSE). Soft delete preserves history
    and lets add_assignment reactivate the same row.
    """
    supabase.table("manager_assignments").update(
        {"is_active": False}
    ).eq("id", assignment_id).execute()
    logger.info("[MANAGERS] Removed (deactivated) assignment %s", assignment_id)


def list_grandma_ids_for_manager(supabase: Client, manager_id: str) -> list[str]:
    """Grandma entity_ids a manager is actively assigned to — for the admin UI."""
    rows = (
        supabase.table("manager_assignments")
        .select("entity_id")
        .eq("manager_id", manager_id)
        .eq("service_type", SERVICE_GRANDMA)
        .eq("is_active", True)
        .execute().data or []
    )
    return [r["entity_id"] for r in rows if r.get("entity_id")]
