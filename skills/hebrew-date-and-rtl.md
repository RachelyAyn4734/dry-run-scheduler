# Hebrew UI, RTL, and Date Formatting — Project Guideline

This document applies to the **Grandma Visits** module. All user-facing text in that module must be in Hebrew. The Dry Run module retains its existing mixed Hebrew/English style.

---

## Language and Tone

Use warm, family-friendly Hebrew — not formal enterprise language.

**Good:**
- "שלום רחל! שמחים שאת כאן 🌸"
- "הביקור נקבע בהצלחה! סבתא מחכה לך."
- "איך היה הביקור? ספרי לנו..."
- "השם לא נמצא במערכת. אנא פני למנהל/ת התוכנית."

**Avoid:**
- "User not found in system."
- "Visit successfully scheduled." (mixed language)
- "Please enter your full name." (English in a Hebrew-first screen)
- Formal bureaucratic phrasing like "הפעולה בוצעה בהצלחה" — prefer "נקבע בהצלחה!"

---

## RTL Layout

Apply `direction: rtl; text-align: right;` to any Hebrew text rendered inside `unsafe_allow_html=True` HTML blocks.

```python
st.markdown(
    '<p style="direction:rtl; text-align:right;">שלום!</p>',
    unsafe_allow_html=True
)
```

For inputs and standard Streamlit widgets, RTL is handled automatically by the browser when the text is Hebrew. No extra CSS needed for `st.text_input`, `st.text_area`, etc.

---

## Date Formatting

### Israeli civil date
Always display dates in Israeli format: `dd/MM/yyyy` and times as `HH:mm`.

```python
# datetime → Israeli display
dt.strftime("%d/%m/%Y")   # "04/06/2026"
dt.strftime("%H:%M")      # "14:30"
```

**Never use `%A` (English weekday name) or `%B` (English month name) in any Hebrew-UI screen.**
`dt.strftime('%A, %d %B %Y')` produces `"Monday, 15 June 2026"` — English text inside a Hebrew UI. Use `%d/%m/%Y` only.

### Hebrew calendar date
Use `to_heb()` for full Hebrew date or `to_heb_short()` for short form (from `utils/dates.py`).

```python
from utils.dates import to_heb, to_heb_short

to_heb(date(2026, 6, 4))       # "ח׳ בסיוון ה׳תשפ״ו"
to_heb_short(date(2026, 6, 4)) # "ח׳ סיוון תשפ״ו"
```

Display Hebrew dates with `direction: rtl` in HTML or as plain `st.markdown` text.

### Slot time label
Use the existing helper from `utils/dates.py`:
```python
from utils.dates import slot_range_label
slot_range_label("14:00")  # "14:00 - 15:00"
```

### Email date formatting
In `grandma_visit_service.py`, use `_format_slot_for_email(slot_start_iso)` which returns `(date_str, time_str, heb_date_str)` for use in notification emails.

---

## Hebrew Month Names

These are already defined in `utils/dates.py`:

| Month | Hebrew |
|-------|--------|
| ניסן, אייר, סיוון, תמוז, אב, אלול | Spring/Summer |
| תשרי, חשון, כסלו, טבת, שבט, אדר | Fall/Winter |
| אדר ב׳ | Leap year |

---

## Common Hebrew UI Strings (Grandma Module)

```
# Identification screen
"ביקור אצל סבתא"
"שם מלא"
"המשך"
"השם לא נמצא במערכת. אנא פני למנהל/ת התוכנית."

# Dashboard
"שלום {name}! 🌸"
"הביקורים הקרובים שלך"
"אין ביקורים מתוכננים כרגע."
"קבעי ביקור חדש"
"ביקורים שעברו — הוסיפי סיכום"

# Schedule screen
"בחירת מועד לביקור"
"מועדים פנויים"
"אין מועדים פנויים כרגע."
"אישור"
"חזרה"
"הביקור נקבע בהצלחה! 🌸"
"מצטערים, המועד הזה כבר נתפס. אנא בחרי מועד אחר."

# Notes screen
"סיכום הביקור"
"איך היה הביקור?"
"הוסיפי תמונה (אופציונלי)"
"שמירה"
"תודה! פרטי הביקור נשמרו. 💛"

# Cancel
"ביטול הביקור"
"האם לבטל את הביקור?"
"כן, בטלי"
"השאירי"

# Module selection
"ניהול Dry Run"
"ביקורים אצל סבתא 🌸"
"ברוכים הבאים — בחרו מודול"
```

---

## Email Notification Template

Subject: `נקבע ביקור חדש אצל סבתא`

Body:
```
שלום {manager_name},

נקבע ביקור חדש אצל סבתא.

שם המבקר/ת: {visitor_name}
תאריך: {date_str}
שעה: {time_str}
תאריך עברי: {heb_date_str}

יום נעים 🌸
```

---

## Navigation Button Arrows

This project uses `→` on all back/exit buttons and `←` on forward/continue buttons. Be consistent.

```python
# Back buttons
st.button("חזרה לתפריט →")
st.button("חזרה לדשבורד →")
st.button("חזרה →")

# Forward/continue buttons
st.button("המשך ←")
st.button("בחרי ←")
```

Do **not** mix conventions in the same flow.

---

## Streamlit Alert RTL

Native `st.info()`, `st.warning()`, `st.error()`, `st.success()` are left-aligned by default.
The global CSS in `inject_css()` already fixes this via `[data-testid="stAlert"]`.
Do **not** move that CSS block or remove it.

For long Hebrew error messages, prefer the `_grandma_error_card()` helper in `app.py` for full RTL styling.

---

## Session State Keys — `_grandma_reset()`

Every new dynamic session key added to the Grandma Visits flow **must** be cleaned up by `_grandma_reset()`.

- Static named keys: add to the explicit list inside `_grandma_reset()`.
- Dynamic keys with a prefix (e.g., `confirm_cancel_visit_{id}`): use the prefix-scan pattern already in `_grandma_reset()`:
  ```python
  stale = [k for k in st.session_state if k.startswith("your_prefix_")]
  for k in stale:
      del st.session_state[k]
  ```

**If you add a new session key and forget to add it to `_grandma_reset()`, users will see ghost UI state when re-entering the module.**

---

## What to Avoid

- Do **not** mix English labels with Hebrew values in the same widget.
- Do **not** use `st.error("Error: ...")` — rewrite in Hebrew: `st.error("שגיאה: ...")`
- Do **not** display raw ISO timestamps to users — always format as `dd/MM/yyyy HH:mm`
- Do **not** use left-aligned text for Hebrew paragraphs in HTML blocks
- Do **not** use `strftime('%A')` or `strftime('%B')` — these produce English text
- Do **not** hardcode RTL CSS per-screen if it already exists in `inject_css()`
