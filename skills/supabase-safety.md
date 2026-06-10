# Supabase Safety — Project Guideline

---

## Never Use the Service Role Key in App Code

Only the anon key (`SUPABASE_KEY`) is used in the app. Never add or expose a service role key.

```python
# Correct
supabase = create_client(url, st.secrets["SUPABASE_KEY"])

# Wrong
supabase = create_client(url, st.secrets["SUPABASE_SERVICE_KEY"])
```

---

## Access Secrets Safely at Startup

Use `.get()` with a fallback and an explicit error message. A missing Supabase secret should show a clear error, not a cryptic `KeyError` crash.

```python
url = st.secrets.get("SUPABASE_URL", "")
key = st.secrets.get("SUPABASE_KEY", "")
if not url or not key:
    st.error("🔴 חסרות הגדרות Supabase — אנא הגדירי SUPABASE_URL ו-SUPABASE_KEY.")
    st.stop()
```

---

## Use RPC for Atomic Operations

Booking and cancellation use Supabase RPCs (`book_visit_slot`, `cancel_visit_booking`) to prevent race conditions. **Never replace RPC calls with direct table updates for these operations.**

Do not use the deprecated repository functions `create_visit()` or `cancel_visit()` in `grandma_visits_repository.py` — they bypass atomic locking.

---

## Storage Bucket: Manual Setup Required

The photo upload bucket `grandma-visit-photos` must be created manually in Supabase and set to **public**. The app code does not create it automatically.

If the bucket is missing, `upload_visit_photo()` will fail silently (returns `None` and logs an error). No user-visible crash, but photos will not be saved.

Bucket name is hardcoded in `repositories/grandma_visits_repository.py`:
```python
_BUCKET = "grandma-visit-photos"
```

If you rename the bucket in Supabase, update this constant too.

---

## RLS Policies

All tables use permissive RLS (open policies). This is intentional for this POC — the app relies on Streamlit session state and admin password for access control, not Supabase row-level security.

**Document any policy changes in migration SQL files, not just the Supabase dashboard.**

---

## Slot Visibility and Capacity

The `_remaining(s)` function in `grandma_schedule_view` computes remaining capacity client-side for display only. The actual atomic booking is enforced by the RPC.

Rules for `_remaining()`:
- For slots with `allows_shared_visits=False`: return 0 if **any** booking exists (regardless of `max_participants`).
- For slots with `allows_shared_visits=True`: return `max_participants - sum(participant_count)`.

The display filter `slots = [s for s in slots if _remaining(s) > 0]` hides full slots. This is a UX convenience — the RPC is the authoritative gate.

---

## Required Manual Setup Checklist (New Deployments)

- [ ] Create Supabase project and run `migration_grandma_v2.sql`
- [ ] Create Storage bucket `grandma-visit-photos` (public)
- [ ] Set all required secrets in `.streamlit/secrets.toml` (see CLAUDE.md)
- [ ] Add at least one active manager in `visit_managers` table
- [ ] Add at least one grandma in `grandmas` table
- [ ] Add descendants (family members) in `descendants` table
