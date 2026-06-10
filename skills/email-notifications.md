# Email Notifications — Project Guideline

Applies to `services/email_service.py` and all callers in `services/grandma_visit_service.py`.

---

## Recipients: Always Load from DB

**Never hardcode manager email addresses.**

```python
# Correct
managers = get_active_managers(supabase)
for manager in managers:
    email_service.send_visit_notification_v2(secrets, manager["email"], ...)

# Wrong
email_service.send_visit_notification_v2(secrets, "rachel@example.com", ...)
```

Only active managers (`is_active=True`) receive notifications. Always filter by `is_active`.

---

## Both Booking and Cancellation Must Notify Managers

- New visit booked → `send_visit_notification_v2()` to all active managers.
- Visit cancelled → `send_visit_cancellation()` to all active managers.

If you add a new booking or cancellation path (e.g., admin cancel button), wire up the email there too.

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
