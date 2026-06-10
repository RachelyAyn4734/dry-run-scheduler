# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Streamlit (Python) scheduling app with two modules sharing a single Supabase database and SMTP email infrastructure:

1. **Dry Run Management** — schedule "Dry Run" sessions; users authenticate by email; admins manage slots via `?mode=admin`.
2. **Grandma Visits (ביקורים אצל סבתא)** — schedule family visits to grandma; family members identify by name; managers receive Hebrew email notifications.

## Running the App

```bash
pip install -r requirements.txt
streamlit run app.py
```

Copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml` and fill in real values. Never commit `secrets.toml`.

Required secrets: `SUPABASE_URL`, `SUPABASE_KEY`, `ADMIN_PASSWORD`, `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`. Optional: `CALENDAR_ID`, `gcp_service_account` (Google Calendar integration for Dry Run).

## Architecture

Strict three-layer separation — never cross layers:

```
app.py                          ← Streamlit UI only; no business logic
services/
  booking_service.py            ← Dry Run: orchestrates DB + Calendar + Email
  email_service.py              ← SMTP for all modules
  calendar_service.py           ← Google Calendar (Dry Run only)
  grandma_visit_service.py      ← Grandma Visits: orchestrates DB + Email
repositories/
  slots_repository.py           ← Dry Run slots table
  users_repository.py           ← Dry Run users table
  descendants_repository.py     ← Grandma: descendants table
  visit_slots_repository.py     ← Grandma: visit_slots table
  grandma_visits_repository.py  ← Grandma: grandma_visits table
utils/
  dates.py                      ← Hebrew date conversion (pyluach), slot_range_label()
  validation.py                 ← valid_email(), normalize_email(), safe() for HTML escaping
```

**Services must never import Streamlit. Repositories contain only DB queries.**

## Module Routing

- `?mode=admin` → `admin_view()` — password-protected admin dashboard (both modules)
- `?mode=user` → `user_view()` — direct Dry Run (backward compat)
- Default (no param) → `module_selection_view()`, then session state drives navigation

Session state keys for grandma module:
- `active_module` — `"dryrun"` | `"grandma"` | `None`
- `grandma_screen` — `"identify"` | `"dashboard"` | `"schedule"` | `"notes"`
- `grandma_visitor` — the descendant dict
- `grandma_pending_slot` — slot awaiting confirmation
- `grandma_note_visit_id` — visit being updated with notes/photo
- `confirm_cancel_visit_{uuid}` — dynamic per-visit cancellation confirmation flag

**Every new session key must be cleaned up in `_grandma_reset()`.** Dynamic-prefix keys use the prefix-scan pattern already in that function.

## Supabase

- Client created once via `@st.cache_resource`; passed down to all layers as `Client`
- Use the **anon key** (`SUPABASE_KEY`) — never the service role key in app code
- RLS enabled on all tables with open policies (permissive — relies on backend auth)
- Atomic optimistic-lock pattern: `UPDATE ... WHERE is_booked=FALSE` avoids double booking without stored procedures (same pattern used in both Dry Run and Grandma Visits)
- All timestamps are `TIMESTAMPTZ`; always compare with timezone-aware ISO strings
- Supabase Storage bucket `grandma-visit-photos` must be created manually and set to **public**

## Hebrew / RTL Guidelines

- All Grandma Visits UI text is in Hebrew; use warm, family-friendly wording
- Israeli date format: `dd/MM/yyyy` and `HH:mm`
- **Never use `strftime('%A')` or `strftime('%B')` in Hebrew-UI screens** — these produce English day/month names
- Hebrew calendar dates via `to_heb()` / `to_heb_short()` from `utils/dates.py` (uses `pyluach`)
- RTL applied via inline `direction: rtl` in HTML blocks
- **Always** escape user-provided strings with `safe()` from `utils/validation.py` before embedding in `unsafe_allow_html=True` blocks
- In `email_service.py`, use `html.escape()` directly — do not import `safe()` from app layers
- Avoid mixing Hebrew and English in the same UI element
- Navigation buttons: `→` for back/exit, `←` for forward/continue — pick one convention and stay consistent
- See `skills/hebrew-date-and-rtl.md` for full RTL/Hebrew guidance

## Date Handling

- System timezone: always `Asia/Jerusalem` via `pytz` (constant `IL_TZ` in `app.py`)
- `now_il()` → current Israel datetime (used for all "is this in the future?" checks)
- Grandma Visits: slots from `now` onward are eligible (not just from tomorrow)
- `slot_range_label(start_time)` formats `"HH:MM"` → `"HH:MM - HH:MM"` (1-hour slot)
- Hebrew date in emails: format via `_format_slot_for_email()` in `grandma_visit_service.py`

## Dry Run Module

Users authenticate via email lookup in `users` table. Admins manage slots and users at `?mode=admin`. Booking is atomic: Calendar event created first, then DB update with `WHERE is_booked=FALSE`; calendar event deleted on race condition loss.

## Grandma Visits Module

- Visitors identify by **name** (case-insensitive lookup in `descendants` table)
- Available slots managed by admin in the Grandma tab of `?mode=admin`
- Booking: atomic slot claim (`visit_slots.is_available` → False) + `grandma_visits` record creation + email to all active `visit_managers`
- Notes and photo can be added after `slot_end` has passed
- Photos uploaded to Supabase Storage, path: `grandma-visits/{visit_id}/{timestamp}{ext}`

## File Upload Rules

- Validate `file.type.startswith("image/")` — reject non-images
- Max size: 10 MB (`file.size <= 10 * 1024 * 1024`)
- Generate safe storage path server-side (UUID-based timestamp + extension); never use the raw uploaded filename as path

## Hard Rules

- Do not break existing Dry Run flow when editing `app.py` or shared services
- Do not hardcode manager emails — always fetch from `visit_managers` table
- Do not use the Supabase service role key in app code
- All user data in HTML blocks must be escaped with `safe()`
- All user data embedded in email HTML bodies must be escaped with `html.escape()`
- HTML emails must include both a plain-text fallback and an HTML part (`MIMEMultipart("alternative")`)
- Do not use deprecated repository functions (`create_visit`, `cancel_visit`) — use RPCs
- Ask before deleting or rewriting large parts of the project

## Skills Reference

- `skills/hebrew-date-and-rtl.md` — Hebrew UI, RTL layout, date formatting, session state cleanup
- `skills/email-notifications.md` — Email HTML/escaping, plain-text fallback, manager loading, secrets
- `skills/dry-run-protection.md` — Rules for keeping Dry Run intact when changing Grandma Visits
- `skills/supabase-safety.md` — Secrets access, RPC usage, bucket setup, capacity logic
