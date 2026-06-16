# Email Notifications — Project Guideline

Applies to `services/email_service.py` and all callers in `services/grandma_visit_service.py`.

---

## Recipients: Always Resolve via the Scoped Resolver

**Never hardcode manager email addresses, and never notify "all managers" globally.**

Recipients come from `managers_repository.get_recipients(supabase, service_type, entity_id)`.
See `scoped-manager-notifications.md` for the full model.

```python
# Correct — scoped to one grandma
from repositories import managers_repository
from utils.constants import SERVICE_GRANDMA

recipients = managers_repository.get_recipients(supabase, SERVICE_GRANDMA, grandma_id)
for manager in recipients:
    email_service.send_visit_notification_v2(secrets, manager["email"], ...)

# Wrong — global list (removed) or hardcoded email
email_service.send_visit_notification_v2(secrets, "rachel@example.com", ...)
```

The resolver already filters on `managers.is_active` AND `manager_assignments.is_active`,
and deduplicates by email. It returns `[]` (never raises) when nobody is assigned.

---

## Both Booking and Cancellation Must Notify the Same Recipients

- New grandma visit booked → `send_visit_notification_v2()` to that grandma's managers.
- Grandma visit cancelled → `send_visit_cancellation()` to that grandma's managers.
- New Dry Run booking → `send_dry_run_notification()` to Dry Run managers.

Booking and cancellation must use the **same** `get_recipients(...)` call for a given
scope so they never drift. If you add a new booking or cancellation path (e.g., admin
cancel button), wire up the scoped email there too.

---

## Email Failure Must Never Roll Back the Business Action

Email is fire-and-forget. A failed email must not cancel a booking or undo a cancellation.

```python
# Correct pattern
ok = email_service.send_visit_notification_v2(...)
if not ok:
    logger.warning("[GRANDMA] Email failed for manager=%s", manager["email"])
# Continue — visit is still booked
```

The booking/cancellation RPC already committed. Do not raise or propagate email errors to the user.

---

## HTML Email with Plain-Text Fallback

All manager notification emails are HTML RTL with a plain-text fallback.

Use `MIMEMultipart("alternative")`. Attach plain text **first**, HTML **second** (clients pick the last supported part):

```python
msg = MIMEMultipart("alternative")
msg.attach(MIMEText(plain_body, "plain", "utf-8"))
msg.attach(MIMEText(html_body,  "html",  "utf-8"))
```

The HTML part must include `dir="rtl"` and `text-align:right`:
```html
<div dir="rtl" style="text-align:right; font-family:Arial, sans-serif; line-height:1.8;">
  ...
</div>
```

---

## HTML Escaping in Email Bodies

**Always escape user-supplied values before embedding them in HTML.**

`email_service.py` imports `html` from the standard library. Use `html.escape()` on any value that came from user input or the database before putting it in an f-string HTML template.

```python
import html

h_visitor = html.escape(visitor_name)
h_grandma = html.escape(grandma_name)

html_body = f"<strong>שם המבקר/ת:</strong> {h_visitor}<br>"
```

The `safe()` helper in `utils/validation.py` does the same thing but is for use in `app.py` HTML blocks. Use `html.escape()` directly in `email_service.py` (no Streamlit/app imports in services).

A name like `"Cohen & Sons"` must render as `Cohen &amp; Sons` in HTML — not as a broken entity.

---

## Never Log Secret Values

```python
# Wrong
logger.info("Connecting with password %s", smtp_password)

# Correct
logger.info("[MAIL] Connecting to %s:%s", smtp_server, smtp_port)
```

`_get_smtp_config()` already logs which keys are *missing* without logging their values. Keep it that way.

---

## Booking Email Content Checklist

`send_visit_notification_v2` must include:
- [ ] Grandma name (in subject and body)
- [ ] Visitor/descendant name
- [ ] Date (`dd/MM/yyyy`)
- [ ] Hebrew date (if available)
- [ ] Time (`HH:mm`)
- [ ] Participant count
- [ ] Whether joiners are allowed (הצטרפות)

## Cancellation Email Content Checklist

`send_visit_cancellation` must include:
- [ ] Grandma name (in subject and body)
- [ ] Visitor/descendant name
- [ ] Original date and time
- [ ] Participant count
- [ ] Clear cancellation wording ("ביקור שתוכנן בוטל")

## Dry Run Notification Content Checklist

`send_dry_run_notification` must include:
- [ ] Booker name (in subject and body)
- [ ] Booker email
- [ ] Date (`dd/MM/yyyy`)
- [ ] Time (`HH:mm`)
- [ ] HTML + plain-text fallback, all user values escaped with `html.escape()`
