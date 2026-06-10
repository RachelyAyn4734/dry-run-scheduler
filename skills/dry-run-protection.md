# Dry Run Protection — Project Guideline

The Dry Run module (`?mode=user`, `?mode=admin`) is the original, stable part of this app.
**Never refactor, reformat, or restructure Dry Run code when working on Grandma Visits.**

---

## Rule: Scope Changes to the Right Module

When a task says "fix Grandma Visits", touch only:
- Functions prefixed with `grandma_` in `app.py`
- `services/grandma_visit_service.py`
- `repositories/descendants_repository.py`, `visit_slots_repository.py`, `grandma_visits_repository.py`, `grandmas_repository.py`
- Grandma-specific blocks in `services/email_service.py`

Do **not** touch:
- `user_view()`, `admin_view()`, `booking_service.py`, `calendar_service.py`
- `repositories/slots_repository.py`, `repositories/users_repository.py`
- Dry Run session state keys: `pending_slot`, `confirm_cancel`, `show_booking_success`, `gcal_booked`, `mail_sent`

---

## Shared Code: Change with Caution

`email_service.py` and `utils/` are shared. When modifying them:
1. Make the minimum change needed for the Grandma Visits fix.
2. Verify the Dry Run email function (`send_confirmation`) is unchanged and still works.
3. Do not rename or remove existing function signatures.

---

## After Every Change to `app.py` or Shared Services

Manually verify:
- `?mode=user` — Dry Run booking flow still works end-to-end
- `?mode=admin` — admin dashboard loads, slots/users display correctly
- No import errors or Python syntax errors (`python -c "import app"` or check Streamlit startup)

---

## Do Not "Clean Up" Dry Run While in the Area

Even if you notice style inconsistencies or date formatting issues in Dry Run code:
- **Do not fix them unless explicitly asked.**
- File a note in the review report instead.
- Mixing Dry Run and Grandma Visits changes in one PR makes it harder to isolate regressions.
