"""
Unit tests for the Grandma Visits module.

Run:
    python -m unittest discover tests/ -v
    # or if pytest is installed:
    python -m pytest tests/ -v

All tests use mocks — no live Supabase or SMTP connection required.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Mock helpers ─────────────────────────────────────────────────────────────

def _sb_returning(data):
    """
    Return a MagicMock Supabase client whose full query chain yields `data`.
    Covers the most common filter chains used in the grandma repositories.
    """
    sb = MagicMock()
    mr = MagicMock()
    mr.data = data if data is not None else []

    # Chains used across the repositories:
    chains = [
        # get_descendant_by_name: .table.select.eq.eq.limit.execute
        lambda m: m.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute,
        # get_all_descendants / get_all_visits: .table.select.order.execute
        lambda m: m.table.return_value.select.return_value.order.return_value.execute,
        # get_future_visits: .table.select.eq.eq.gt.order.execute
        lambda m: m.table.return_value.select.return_value.eq.return_value.eq.return_value.gt.return_value.order.return_value.execute,
        # get_past_visits: .table.select.eq.lte.neq.order.execute
        lambda m: m.table.return_value.select.return_value.eq.return_value.lte.return_value.neq.return_value.order.return_value.execute,
        # fetch_available_visit_slots: .table.select.eq.gt.order.execute
        lambda m: m.table.return_value.select.return_value.eq.return_value.gt.return_value.order.return_value.execute,
        # fetch_all_visit_slots: .table.select.order.execute (same as above)
        # atomic_book / clear: .table.update.eq.eq.execute
        lambda m: m.table.return_value.update.return_value.eq.return_value.eq.return_value.execute,
        # get_active_managers: .table.select.eq.execute
        lambda m: m.table.return_value.select.return_value.eq.return_value.execute,
    ]
    for chain_fn in chains:
        chain_fn(sb).return_value = mr
    return sb


# ═══════════════════════════════════════════════════════════════
# 1. Descendants Repository
# ═══════════════════════════════════════════════════════════════

class TestDescendantsRepository(unittest.TestCase):

    def test_not_found_returns_none(self):
        from repositories.descendants_repository import get_descendant_by_name
        sb = _sb_returning([])
        self.assertIsNone(get_descendant_by_name(sb, "שם לא קיים"))

    def test_found_returns_row_dict(self):
        from repositories.descendants_repository import get_descendant_by_name
        row = {"id": "uuid-1", "name": "רחל כהן", "is_active": True}
        sb = _sb_returning([row])
        result = get_descendant_by_name(sb, "רחל כהן")
        self.assertEqual(result, row)

    def test_whitespace_name_is_trimmed(self):
        """Surrounding whitespace must be stripped before the DB eq() call."""
        from repositories.descendants_repository import get_descendant_by_name
        sb = _sb_returning([])
        get_descendant_by_name(sb, "  רחל כהן  ")
        # The second .eq() call should receive the trimmed value "רחל כהן"
        eq_chain = sb.table.return_value.select.return_value.eq.return_value.eq
        actual_name_arg = eq_chain.call_args[0][1]  # second positional arg
        self.assertEqual(actual_name_arg, "רחל כהן")

    def test_inactive_descendants_excluded(self):
        """is_active filter must be applied (first eq call uses 'is_active')."""
        from repositories.descendants_repository import get_descendant_by_name
        sb = _sb_returning([])
        get_descendant_by_name(sb, "רחל")
        first_eq_call = sb.table.return_value.select.return_value.eq.call_args
        self.assertEqual(first_eq_call[0][0], "is_active")
        self.assertTrue(first_eq_call[0][1])


# ═══════════════════════════════════════════════════════════════
# 2. Visit Slots Repository — atomic booking
# ═══════════════════════════════════════════════════════════════

class TestVisitSlotsRepository(unittest.TestCase):

    def _make_update_sb(self, returned_rows):
        sb = MagicMock()
        sb.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = returned_rows
        return sb

    def test_atomic_book_returns_false_when_slot_already_taken(self):
        """Empty update result means another request won the race."""
        from repositories.visit_slots_repository import atomic_book_visit_slot
        sb = self._make_update_sb([])
        self.assertFalse(atomic_book_visit_slot(sb, "slot-uuid"))

    def test_atomic_book_returns_true_when_slot_is_available(self):
        """Non-empty update result means this request won."""
        from repositories.visit_slots_repository import atomic_book_visit_slot
        sb = self._make_update_sb([{"id": "slot-uuid", "is_available": False}])
        self.assertTrue(atomic_book_visit_slot(sb, "slot-uuid"))

    def test_atomic_book_updates_is_available_to_false(self):
        """The update payload must set is_available=False."""
        from repositories.visit_slots_repository import atomic_book_visit_slot
        sb = self._make_update_sb([{"id": "slot-uuid"}])
        atomic_book_visit_slot(sb, "slot-uuid")
        update_payload = sb.table.return_value.update.call_args[0][0]
        self.assertFalse(update_payload["is_available"])

    def test_release_slot_sets_is_available_true(self):
        """Releasing a slot must set is_available=True."""
        from repositories.visit_slots_repository import release_visit_slot
        sb = MagicMock()
        release_visit_slot(sb, "slot-uuid")
        update_payload = sb.table.return_value.update.call_args[0][0]
        self.assertTrue(update_payload["is_available"])


# ═══════════════════════════════════════════════════════════════
# 3. Grandma Visits Repository
# ═══════════════════════════════════════════════════════════════

class TestGrandmaVisitsRepository(unittest.TestCase):

    def test_get_future_visits_empty_when_no_data(self):
        from repositories.grandma_visits_repository import get_future_visits
        sb = _sb_returning([])
        self.assertEqual(get_future_visits(sb, "desc-uuid"), [])

    def test_get_future_visits_returns_rows(self):
        from repositories.grandma_visits_repository import get_future_visits
        row = {"id": "v1", "descendant_id": "d1", "status": "scheduled"}
        sb = _sb_returning([row])
        result = get_future_visits(sb, "d1")
        self.assertEqual(result, [row])

    def test_update_visit_sets_status_completed(self):
        from repositories.grandma_visits_repository import update_visit_notes_photo
        sb = MagicMock()
        update_visit_notes_photo(sb, "visit-uuid", notes="ביקור נהדר", photo_url=None)
        payload = sb.table.return_value.update.call_args[0][0]
        self.assertEqual(payload["status"], "completed")

    def test_update_visit_includes_notes(self):
        from repositories.grandma_visits_repository import update_visit_notes_photo
        sb = MagicMock()
        update_visit_notes_photo(sb, "v1", notes="כיף גדול!", photo_url=None)
        payload = sb.table.return_value.update.call_args[0][0]
        self.assertEqual(payload["notes"], "כיף גדול!")

    def test_update_visit_includes_photo_url_when_provided(self):
        from repositories.grandma_visits_repository import update_visit_notes_photo
        sb = MagicMock()
        update_visit_notes_photo(sb, "v1", notes=None, photo_url="https://example.com/photo.jpg")
        payload = sb.table.return_value.update.call_args[0][0]
        self.assertEqual(payload["photo_url"], "https://example.com/photo.jpg")

    def test_cancel_visit_sets_status_cancelled(self):
        from repositories.grandma_visits_repository import cancel_visit
        sb = MagicMock()
        cancel_visit(sb, "visit-uuid")
        payload = sb.table.return_value.update.call_args[0][0]
        self.assertEqual(payload["status"], "cancelled")


# ═══════════════════════════════════════════════════════════════
# 4. Grandma Visit Service — booking orchestration
# ═══════════════════════════════════════════════════════════════

class TestGrandmaVisitService(unittest.TestCase):

    _SLOT_START = "2026-06-10T10:00:00+00:00"
    _SLOT_END   = "2026-06-10T11:00:00+00:00"

    def _book(self, **patch_overrides):
        """Call book_visit with sensible defaults and return the result."""
        defaults = {
            "atomic":   True,
            "create":   {"id": "visit-uuid"},
            "managers": [],
            "mail":     True,
        }
        defaults.update(patch_overrides)
        sb = MagicMock()
        with patch("services.grandma_visit_service.atomic_book_visit_slot",
                   return_value=defaults["atomic"]), \
             patch("services.grandma_visit_service.create_visit",
                   return_value=defaults["create"]), \
             patch("services.grandma_visit_service.get_active_managers",
                   return_value=defaults["managers"]), \
             patch("services.grandma_visit_service.email_service.send_visit_notification",
                   return_value=defaults["mail"]) as mock_mail:
            from services.grandma_visit_service import book_visit
            result = book_visit(sb, {}, "slot-id",
                                self._SLOT_START, self._SLOT_END,
                                "desc-id", "רחל")
        return result, mock_mail

    def test_fails_immediately_when_slot_already_taken(self):
        result, _ = self._book(atomic=False)
        self.assertFalse(result["success"])
        self.assertIsNone(result["visit_id"])

    def test_succeeds_and_returns_visit_id(self):
        result, _ = self._book()
        self.assertTrue(result["success"])
        self.assertEqual(result["visit_id"], "visit-uuid")

    def test_no_managers_means_mail_ok_is_true(self):
        """Zero managers → no emails needed → mail_ok=True."""
        result, mock_mail = self._book(managers=[])
        self.assertTrue(result["mail_ok"])
        mock_mail.assert_not_called()

    def test_sends_email_to_every_active_manager(self):
        managers = [
            {"name": "מנהלת א", "email": "mgr1@test.com"},
            {"name": "מנהל ב",  "email": "mgr2@test.com"},
        ]
        result, mock_mail = self._book(managers=managers)
        self.assertTrue(result["success"])
        self.assertEqual(mock_mail.call_count, 2)

    def test_mail_ok_false_when_at_least_one_send_fails(self):
        managers = [{"name": "מנהלת", "email": "mgr@test.com"}]
        result, _ = self._book(managers=managers, mail=False)
        self.assertFalse(result["mail_ok"])

    def test_email_contains_visitor_name(self):
        managers = [{"name": "מנהלת", "email": "mgr@test.com"}]
        _, mock_mail = self._book(managers=managers)
        kwargs = mock_mail.call_args[1]
        self.assertEqual(kwargs["visitor_name"], "רחל")

    def test_cancel_releases_slot_and_cancels_visit(self):
        sb = MagicMock()
        with patch("services.grandma_visit_service.release_visit_slot") as mock_release, \
             patch("services.grandma_visit_service.cancel_visit") as mock_cancel:
            from services.grandma_visit_service import cancel_booked_visit
            cancel_booked_visit(sb, "v-uuid", "s-uuid")
        mock_release.assert_called_once_with(sb, "s-uuid")
        mock_cancel.assert_called_once_with(sb, "v-uuid")


# ═══════════════════════════════════════════════════════════════
# 5. Email Service
# ═══════════════════════════════════════════════════════════════

class TestEmailService(unittest.TestCase):

    def test_visit_notification_returns_false_without_smtp(self):
        from services.email_service import send_visit_notification
        result = send_visit_notification(
            secrets={},
            manager_email="mgr@example.com",
            manager_name="מנהלת",
            visitor_name="רחל",
            date_str="10/06/2026",
            time_str="10:00",
        )
        self.assertFalse(result)

    def test_confirmation_returns_false_without_smtp(self):
        from services.email_service import send_confirmation
        result = send_confirmation(
            secrets={},
            user_email="user@example.com",
            user_name="רחל",
            date_str="2026-06-10",
            time_str="10:00",
        )
        self.assertFalse(result)

    def test_visit_notification_calls_smtp_when_configured(self):
        """With valid SMTP secrets, SMTP.sendmail must be called."""
        from services.email_service import send_visit_notification
        secrets = {
            "SMTP_SERVER": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "sender@example.com",
            "SMTP_PASSWORD": "secret",
        }
        with patch("smtplib.SMTP") as MockSMTP:
            instance = MockSMTP.return_value.__enter__.return_value
            instance.sendmail.return_value = {}
            result = send_visit_notification(
                secrets=secrets,
                manager_email="mgr@example.com",
                manager_name="מנהלת",
                visitor_name="רחל",
                date_str="10/06/2026",
                time_str="10:00",
                heb_date_str="י׳ בסיוון תשפ״ו",
            )
        self.assertTrue(result)
        instance.sendmail.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# 6. Date / Timestamp Utilities
# ═══════════════════════════════════════════════════════════════

class TestDateFormatting(unittest.TestCase):

    def test_z_suffix_timestamp_parseable(self):
        """Python 3.10 cannot parse Z suffix — our workaround must fix it."""
        from datetime import datetime
        raw = "2026-06-10T10:00:00Z"
        fixed = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(fixed)
        self.assertEqual(dt.hour, 10)

    def test_plus_offset_timestamp_parseable(self):
        from datetime import datetime
        dt = datetime.fromisoformat("2026-06-10T10:00:00+00:00")
        self.assertEqual(dt.hour, 10)

    def test_format_slot_for_email_israeli_date(self):
        from services.grandma_visit_service import _format_slot_for_email
        date_str, time_str, heb = _format_slot_for_email("2026-06-10T07:00:00+00:00")
        # Israeli format dd/MM/yyyy
        self.assertRegex(date_str, r"^\d{2}/\d{2}/\d{4}$")
        # HH:MM
        self.assertRegex(time_str, r"^\d{2}:\d{2}$")
        # Hebrew calendar string must be non-empty
        self.assertTrue(len(heb.strip()) > 0)

    def test_format_slot_for_email_applies_israel_timezone(self):
        """UTC 07:00 = Israel 10:00 in summer (UTC+3)."""
        from services.grandma_visit_service import _format_slot_for_email
        _, time_str, _ = _format_slot_for_email("2026-06-10T07:00:00+00:00")
        self.assertEqual(time_str, "10:00")

    def test_slot_range_label_adds_one_hour(self):
        from utils.dates import slot_range_label
        self.assertEqual(slot_range_label("10:00"), "10:00 - 11:00")
        self.assertEqual(slot_range_label("23:00"), "23:00 - 00:00")


# ═══════════════════════════════════════════════════════════════
# 7. Past-slot filtering (repository-level query logic)
# ═══════════════════════════════════════════════════════════════

class TestSlotFiltering(unittest.TestCase):

    def test_fetch_available_slots_filters_by_is_available(self):
        """The is_available=True filter must be applied."""
        from repositories.visit_slots_repository import fetch_available_visit_slots
        sb = _sb_returning([])
        fetch_available_visit_slots(sb)
        eq_call = sb.table.return_value.select.return_value.eq.call_args
        self.assertEqual(eq_call[0][0], "is_available")
        self.assertTrue(eq_call[0][1])

    def test_fetch_available_slots_filters_future_only(self):
        """A .gt('slot_start', ...) filter must be applied for future-only query."""
        from repositories.visit_slots_repository import fetch_available_visit_slots
        sb = _sb_returning([])
        fetch_available_visit_slots(sb)
        gt_call = sb.table.return_value.select.return_value.eq.return_value.gt.call_args
        self.assertEqual(gt_call[0][0], "slot_start")

    def test_get_past_visits_uses_lte_on_slot_end(self):
        """Past-visit query must use .lte('slot_end', now) not slot_start."""
        from repositories.grandma_visits_repository import get_past_visits
        sb = _sb_returning([])
        get_past_visits(sb, "desc-uuid")
        lte_call = sb.table.return_value.select.return_value.eq.return_value.lte.call_args
        self.assertEqual(lte_call[0][0], "slot_end")


if __name__ == "__main__":
    unittest.main(verbosity=2)
