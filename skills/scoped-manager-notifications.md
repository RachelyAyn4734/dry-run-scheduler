# Scoped Manager Notifications — Project Guideline

Applies to `repositories/managers_repository.py`, `services/grandma_visit_service.py`,
`services/booking_service.py`, `services/email_service.py`, and the manager admin UI
in `app.py` (`_render_managers_admin`).

This replaces the old "notify all managers in `visit_managers`" model.

---

## The Model

- **A manager is a global person** — one row in `managers` (id, name, email, is_active).
  Identity is stored once and reused everywhere.
- **An assignment defines scope** — one row in `manager_assignments`
  (manager_id, service_type, entity_id, is_active).
  - `service_type = 'dry_run'` → `entity_id IS NULL` (one global Dry Run scope).
  - `service_type = 'grandma'` → `entity_id = grandmas.id` (one scope per grandma).
  A DB CHECK constraint (`chk_ma_scope_shape`) enforces this shape.
- A manager **can** hold multiple assignments (several grandmas, and/or Dry Run).

Service type strings live in `utils/constants.py` (`SERVICE_DRY_RUN`, `SERVICE_GRANDMA`).
Never inline the literals — import the constants.

---

## Never Notify All Managers Globally

There is no "all managers" recipient list any more. Every notification is scoped.

```python
# Correct — scoped resolution
from repositories import managers_repository
from utils.constants import SERVICE_GRANDMA

recipients = managers_repository.get_recipients(supabase, SERVICE_GRANDMA, grandma_id)

# Wrong — global list (removed) or hardcoded email
managers = get_active_managers(supabase)          # removed function
send(..., "rachel@example.com", ...)              # never hardcode
```

---

## One Resolver for Booking and Cancellation

Booking and cancellation **must** resolve recipients through the same function,
`managers_repository.get_recipients(supabase, service_type, entity_id)`, so the two
flows can never drift apart. Do not write a second recipient query.

The resolver already guarantees:
- only globally active managers (`managers.is_active`) **and** active assignments
  (`manager_assignments.is_active`);
- **deduplication by lowercased email** — an accidental double assignment yields one email;
- returns `[]` (never raises) — an empty list means "send to nobody", which is a valid
  state, not an error.

---

## Scope Isolation: Dry Run vs Grandma vs Grandma

- Dry Run booking → `get_recipients(SERVICE_DRY_RUN)` only.
- Grandma booking/cancellation → `get_recipients(SERVICE_GRANDMA, grandma_id)` for that
  grandma only.
- A booking for סבתא שושי must never email סבתא אסתר's managers, and vice versa.
- Dry Run and Grandma Visits must never share a recipient list implicitly.

Always pass the correct `grandma_id` from the visit record (`grandma_visits.grandma_id`),
not a name.

---

## Email Failure Never Rolls Back the Business Action

Unchanged rule (see also `email-notifications.md`): the booking/cancellation RPC has
already committed before recipients are resolved. Wrap notification loops so a failed
send — or a failed recipient lookup — is logged and swallowed, never propagated.

```python
recipients = managers_repository.get_recipients(supabase, SERVICE_DRY_RUN)
for manager in recipients:
    email_service.send_dry_run_notification(secrets, manager_email=manager["email"], ...)
# No managers / send failure → booking still stands.
```

---

## No Hardcoded Emails

All recipient emails come from the `managers` table via the resolver. Never inline a
personal address in code, SQL, tests, or docs. Migration/seed SQL must read existing
data dynamically (e.g. from `visit_managers`/`grandmas`), never literal addresses.

---

## Admin UI

`_render_managers_admin(supabase, key_prefix)` is the single shared UI (used by both
`grandma_admin_view` and `admin_view`). Keep it simple:
1. Add manager (global person).
2. Dry Run managers (multiselect → `dry_run` assignments).
3. Per-grandma managers (one expander per active grandma → `grandma` assignments).
4. All managers list with global activate/deactivate.

Assignments are reconciled with `_save_assignments` → `add_assignment` (idempotent
reactivate) / `remove_assignment` (soft delete). Soft delete preserves history and lets
the same assignment be reactivated without creating a duplicate row.

---

## Backward Compatibility

`visit_managers` is the legacy table. It is kept untouched for rollback but is **no
longer read by any code**. Do not add new reads/writes to it. Once production is verified
healthy, a future cleanup migration may drop it (and `rollback_managers_v3.sql` covers
reverting the new tables).
