# Manual Test Guide — Grandma Visits Module

## Prerequisites

Before running tests, ensure the following data exists in Supabase:

### Seed data (run once in Supabase SQL Editor)

```sql
-- 1. At least one active descendant
INSERT INTO public.descendants (name, phone, is_active)
VALUES ('רחל כהן', '050-1234567', true)
ON CONFLICT (name) DO NOTHING;

-- 2. At least one active manager (replace with real email)
INSERT INTO public.visit_managers (name, email, is_active)
VALUES ('מנהלת ראשית', 'your-email@example.com', true)
ON CONFLICT (email) DO NOTHING;

-- 3. At least two future visit slots (adjust dates as needed)
INSERT INTO public.visit_slots (slot_start, slot_end, is_available)
VALUES
  (NOW() + INTERVAL '2 days' + INTERVAL '10 hours', NOW() + INTERVAL '2 days' + INTERVAL '11 hours', true),
  (NOW() + INTERVAL '3 days' + INTERVAL '14 hours', NOW() + INTERVAL '3 days' + INTERVAL '15 hours', true)
ON CONFLICT (slot_start) DO NOTHING;
```

### Running the app locally

```bash
streamlit run app.py
# opens at http://localhost:8501
```

---

## Test Scenarios

---

### TEST 1 — Direct Grandma Visits link bypasses module selection

**URL:** `http://localhost:8501/?mode=grandma`

**Steps:**
1. Open the URL above in a browser.

**Expected:**
- The page shows the Grandma Visits identification screen immediately.
- The hero banner reads "🌸 ביקור אצל סבתא".
- No module selection cards (Dry Run / Grandma Visits) are shown.
- A name input field and "המשך ←" button are visible.

**Pass criteria:** Module selection is never shown.

---

### TEST 2 — Normal home route still shows module selection

**URL:** `http://localhost:8501/`

**Steps:**
1. Open the URL above.

**Expected:**
- Two large cards appear: "ניהול Dry Run" and "ביקורים אצל סבתא 🌸".
- Clicking "כניסה → Dry Run" opens the Dry Run email login (existing flow).
- Clicking "כניסה ← ביקורי סבתא" opens the Grandma Visits identification screen.

**Pass criteria:** Both module options visible; each routes correctly.

---

### TEST 3 — Unknown descendant shows styled Hebrew error

**URL:** `http://localhost:8501/?mode=grandma`

**Steps:**
1. Open the direct Grandma link.
2. Enter a name that does **not** exist in the `descendants` table, e.g., `שם לא קיים`.
3. Click "המשך ←".

**Expected:**
- A styled error card appears (warm red gradient background, RTL, rounded corners).
- Card title: **"השם לא נמצא במערכת"**
- Card body: "אנא פני למנהל/ת התוכנית לקבלת גישה."
- The user remains on the identification screen.
- The name input is still visible and editable.

**Pass criteria:**
- Error card is visually distinct (not a plain red `st.error` box).
- User cannot proceed to dashboard.
- Error persists after the screen re-renders (not lost on rerun).

---

### TEST 4 — Known descendant opens dashboard

**URL:** `http://localhost:8501/?mode=grandma`

**Steps:**
1. Open the direct Grandma link.
2. Enter the exact name from the `descendants` table (e.g., `רחל כהן`).
3. Click "המשך ←".

**Expected:**
- Dashboard opens immediately.
- Hero banner: "🌸 שלום רחל כהן!"
- Section: "📅 הביקורים הקרובים שלך" (empty or with scheduled visits).
- Button: "🌸 קביעת ביקור חדש" is visible.

**Pass criteria:** Dashboard visible with correct name greeting.

---

### TEST 5 — Only future slots are shown for booking

**Steps:**
1. From the dashboard, click "🌸 קביעת ביקור חדש".

**Expected:**
- Only slots with `slot_start > now()` are shown.
- No past slots appear.
- If no future slots exist → message: "אין מועדים פנויים כרגע. אנא בדקי שוב מאוחר יותר."

**Verify in Supabase:**
```sql
-- Confirm only future, available slots exist:
SELECT id, slot_start, is_available FROM visit_slots
WHERE slot_start > NOW() AND is_available = true
ORDER BY slot_start;
```

**Pass criteria:** Count of displayed slots matches the query result.

---

### TEST 6 — Booking a slot saves it and prevents double-booking

**Steps:**
1. From the schedule screen, click any available slot button.
2. Review the confirmation card (name, date, time in Israeli format + Hebrew date).
3. Click "✅ אישור".

**Expected after first booking:**
- Success banner: "🌸 הביקור נקבע בהצלחה! סבתא מחכה לך."
- Balloons animation plays.
- Dashboard shows the booked visit under "הביקורים הקרובים שלך".

**Verify in Supabase:**
```sql
SELECT * FROM grandma_visits ORDER BY created_at DESC LIMIT 5;
SELECT id, is_available FROM visit_slots WHERE is_available = false;
```

**Double-booking test:**
1. Open a second browser tab at `http://localhost:8501/?mode=grandma`.
2. Log in as the same or a different descendant.
3. Go to schedule → try to select the same slot.

**Expected:** Slot no longer appears (is_available=false). If you somehow click it simultaneously, the system shows: "⚠️ מצטערים, המועד הזה כבר נתפס."

**Pass criteria:** `grandma_visits` has one row; `visit_slots.is_available` = false for that slot.

---

### TEST 7 — Manager receives email notification on booking

**Steps:**
1. Complete a booking (Test 6 above).

**Expected:**
- An email arrives at the address in `visit_managers` with:
  - Subject: `נקבע ביקור חדש אצל סבתא`
  - Body includes visitor name, date (dd/MM/yyyy), time (HH:mm), Hebrew date.

**If SMTP is not configured locally:**
The booking still succeeds. Check the app log for this line:
```
WARNING email_service: [MAIL] SMTP secrets incomplete — skipping visit notification
```

To test email locally, add SMTP credentials to `.streamlit/secrets.toml`:
```toml
SMTP_SERVER   = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = "your@gmail.com"
SMTP_PASSWORD = "your-app-password"
```

**Pass criteria:** Email received OR log confirms it was attempted (SMTP configured) / skipped (no config).

---

### TEST 8 — Post-visit notes and photo upload

**Steps:**
1. In Supabase, manually update a visit's `slot_end` to a past time:
```sql
UPDATE grandma_visits
SET slot_end = NOW() - INTERVAL '1 hour'
WHERE id = '<your-visit-id>';
```
2. Return to the dashboard (re-login if needed).
3. Under "📝 ביקורים שעברו — הוסיפי סיכום", click "📝 הוסיפי סיכום".
4. Enter notes in the text area.
5. (Optional) Upload an image file ≤10MB.
6. Click "💾 שמירה".

**Expected:**
- Success message: "💛 תודה! פרטי הביקור נשמרו."
- Redirects back to dashboard.

**Verify in Supabase:**
```sql
SELECT id, status, notes, photo_url FROM grandma_visits
WHERE id = '<your-visit-id>';
```
Expected: `status = 'completed'`, `notes` populated, `photo_url` populated (if uploaded).

**Photo upload note:** Requires the `grandma-visit-photos` Supabase Storage bucket to be created and set to public. If the bucket is missing, the booking still saves without a photo, and a warning is shown.

---

### TEST 9 — Admin mode still works

**URL:** `http://localhost:8501/?mode=admin`

**Steps:**
1. Open the URL.
2. Enter `ADMIN_PASSWORD` from `secrets.toml`.
3. Verify four tabs: Dry Run (×3) + Grandma Visits.
4. In the Grandma tab → "📅 מועדים" → add a new future slot.
5. In the Grandma tab → "👥 נכדים/ות" → add a new descendant.
6. In the Grandma tab → "📧 מנהלים" → verify the manager appears.

**Pass criteria:** All admin operations work; Dry Run tabs (slots, bookings, users) are unaffected.

---

### TEST 10 — Dry Run still works end-to-end

**URL:** `http://localhost:8501/?mode=user`

**Steps:**
1. Open the URL.
2. Enter an email from the `users` table.
3. Select an available slot.
4. Confirm the booking.

**Expected:** Booking succeeds exactly as before my changes.

**Pass criteria:** Dry Run flow completely unaffected.

---

## Running Automated Tests

No extra packages needed — uses Python's built-in `unittest`:

```bash
cd scheduling_app
python -m unittest discover tests/ -v
```

Expected output: `Ran 32 tests in ~3s OK`

### What the automated tests cover

| # | Test class | What is verified |
|---|---|---|
| 4 | `TestDescendantsRepository` | Name lookup, trimming, is_active filter |
| 4 | `TestVisitSlotsRepository` | Atomic booking, race condition, release |
| 6 | `TestGrandmaVisitsRepository` | Future/past queries, notes update, cancel |
| 7 | `TestGrandmaVisitService` | Full booking flow, email to all managers, cancel |
| 3 | `TestEmailService` | No-SMTP skip, SMTP sendmail called |
| 5 | `TestDateFormatting` | Z-suffix fix, Israeli format, Israel timezone |
| 3 | `TestSlotFiltering` | is_available filter, future-only filter, slot_end lte |

### What requires manual testing (UI / network)
- Module selection → Dry Run / Grandma routing
- Styled error card rendering
- Supabase live queries
- Email delivery
- Photo upload to Supabase Storage
- Double-booking race in two concurrent browser tabs
